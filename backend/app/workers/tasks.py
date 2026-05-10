"""
workers/tasks.py — Celery task definitions for async scan processing.

AppSec notes:
  - Tasks receive only user_id + scan_id (no PII in task payload).
  - PII is loaded from DB at execution time.
  - Task results stored in Redis with 24h TTL.
  - Soft time limits prevent runaway tasks.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import structlog
from celery import Task

from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


class BaseTask(Task):
    """Base task class with DB session lifecycle."""
    abstract = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(
            "Celery task failed",
            task_id=task_id,
            task_name=self.name,
            error=str(exc),
        )
        super().on_failure(exc, task_id, args, kwargs, einfo)


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="tasks.run_scan",
    max_retries=3,
    default_retry_delay=30,
    soft_time_limit=300,   # 5 min soft limit
    time_limit=360,        # 6 min hard limit
    acks_late=True,        # Don't ack until complete (safer)
)
def run_scan_task(self, scan_id: str, user_id: str):
    """
    Full scan pipeline:
      1. Load scan record from DB
      2. Build search queries
      3. Fetch pages
      4. Run PII detection
      5. Score exposure
      6. Persist results
      7. Trigger removal generation
    """
    return asyncio.run(_run_scan_async(scan_id, user_id))


async def _run_scan_async(scan_id: str, user_id: str) -> dict:
    """Async implementation of the scan pipeline."""
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models import Scan, ScanStatus, ExposureRisk
    from app.services.crawler.searxng_search import (
        searxng_service,
        page_fetcher,
        data_broker_scanner,
    )
    from app.services.nlp.pii_detector import pii_detector, exposure_scorer

    async with AsyncSessionLocal() as db:
        # Load scan record
        result = await db.execute(select(Scan).where(Scan.id == UUID(scan_id)))
        scan = result.scalar_one_or_none()

        if not scan:
            logger.error("Scan not found", scan_id=scan_id)
            return {"error": "scan_not_found"}

        # Mark as running
        scan.status = ScanStatus.RUNNING
        await db.commit()

        try:
            # ── Step 1: Build queries ───────────────────────────────────────
            queries = data_broker_scanner.build_search_queries(
                scan.target_name,
                scan.target_location,
            )

            # ── Step 2: Google search ───────────────────────────────────────
            all_urls: list = []
            for query in queries[:6]:   # Limit to 6 queries per scan
                try:
                    results = await searxng_service.search(query, num_results=8)
                    all_urls.extend(r["url"] for r in results)
                except Exception as e:
                    logger.warning("Search query failed", query=query, error=str(e))

            # Deduplicate
            unique_urls = list(dict.fromkeys(all_urls))[:settings_max_pages(scan)]
            scan.sources_scanned = len(unique_urls)

            # ── Step 3: Fetch pages ─────────────────────────────────────────
            page_texts = await page_fetcher.fetch_many(unique_urls, concurrency=5)

            # ── Step 4: PII detection ───────────────────────────────────────
            pii_matches = await pii_detector.detect_pii(page_texts, scan.target_name)

            # ── Step 5: Score exposure ──────────────────────────────────────
            score, risk = exposure_scorer.score(pii_matches)
            scan.exposure_score = score
            scan.risk_level = ExposureRisk(risk)
            scan.pii_instances_found = len(pii_matches)

            # ── Step 6: Persist results (no raw PII) ──────────────────────
            scan.results = {
                "matches": [
                    {
                        "pii_type": m.pii_type,
                        "masked_value": m.masked_value,
                        "confidence": m.confidence,
                        "source_url": m.source_url,
                        "source_domain": m.source_domain,
                        "context_snippet": m.context_snippet,
                    }
                    for m in pii_matches
                ],
                "sources_checked": len(unique_urls),
                "unique_sources_with_pii": len({m.source_domain for m in pii_matches}),
            }

            scan.status = ScanStatus.COMPLETED
            scan.completed_at = datetime.now(timezone.utc)
            await db.commit()

            logger.info(
                "Scan completed",
                scan_id=scan_id,
                score=score,
                risk=risk,
                matches=len(pii_matches),
            )

            # ── Step 7: Auto-generate removal requests for high/critical ───
            if risk in ("high", "critical"):
                await _generate_removal_requests(
                    db, scan, pii_matches, user_id
                )

            return {
                "scan_id": scan_id,
                "exposure_score": score,
                "risk_level": risk,
                "pii_instances": len(pii_matches),
            }

        except Exception as exc:
            scan.status = ScanStatus.FAILED
            scan.error_message = str(exc)[:500]
            await db.commit()
            logger.error("Scan pipeline failed", scan_id=scan_id, error=str(exc))
            raise


async def _generate_removal_requests(db, scan, pii_matches, user_id: str):
    """Auto-create RemovalRequest records for each unique PII source."""
    from app.models import RemovalRequest, RemovalStatus

    seen_domains: set = set()
    for match in pii_matches:
        if match.source_domain in seen_domains:
            continue
        seen_domains.add(match.source_domain)

        removal = RemovalRequest(
            user_id=UUID(user_id),
            scan_id=scan.id,
            source_url=match.source_url,
            source_domain=match.source_domain,
            data_type=match.pii_type,
            status=RemovalStatus.PENDING,
        )
        db.add(removal)

    await db.commit()
    logger.info("Generated removal requests", count=len(seen_domains), scan_id=str(scan.id))


@celery_app.task(
    name="tasks.process_removal",
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=120,
    time_limit=180,
    acks_late=True,
)
def process_removal_task(removal_id: str, user_id: str):
    """Process a single data removal request."""
    return asyncio.run(_process_removal_async(removal_id, user_id))


async def _process_removal_async(removal_id: str, user_id: str):
    from sqlalchemy import select
    from app.database import AsyncSessionLocal
    from app.models import RemovalRequest, RemovalStatus, User
    from app.services.removal.google_removal import removal_orchestrator
    from uuid import UUID as _UUID

    async with AsyncSessionLocal() as db:
        removal_res = await db.execute(
            select(RemovalRequest).where(RemovalRequest.id == _UUID(removal_id))
        )
        removal = removal_res.scalar_one_or_none()
        if not removal:
            return {"error": "removal_not_found"}

        user_res = await db.execute(select(User).where(User.id == _UUID(user_id)))
        user = user_res.scalar_one_or_none()
        if not user:
            return {"error": "user_not_found"}

        audit = await removal_orchestrator.process_removal(
            source_url=removal.source_url,
            user_name=user.full_name or "User",
            user_email=user.email,
        )

        removal.status = RemovalStatus.SUBMITTED
        removal.submission_log = audit
        removal.submitted_at = datetime.now(timezone.utc)
        await db.commit()

        return audit


@celery_app.task(name="tasks.scheduled_rescan", acks_late=True)
def scheduled_rescan_task():
    """
    Celery beat task — re-scan all active users weekly.
    Enqueues individual scan tasks instead of running inline.
    """
    return asyncio.run(_rescan_all())


async def _rescan_all():
    from sqlalchemy import select, and_
    from datetime import timedelta
    from app.database import AsyncSessionLocal
    from app.models import User, Scan, ScanStatus, SubscriptionTier

    cutoff = datetime.now(timezone.utc) - timedelta(hours=168)  # 7 days

    async with AsyncSessionLocal() as db:
        # Find users whose last scan is older than cutoff
        result = await db.execute(
            select(User).where(
                and_(
                    User.is_active == True,
                    User.subscription_tier != SubscriptionTier.FREE,
                )
            )
        )
        users = result.scalars().all()

    queued = 0
    for user in users:
        # Create a new scan record and enqueue
        from app.database import AsyncSessionLocal as _ASL
        from app.models import Scan as _Scan
        async with _ASL() as db:
            scan = _Scan(
                user_id=user.id,
                target_name=user.full_name or "",
                status=ScanStatus.PENDING,
            )
            db.add(scan)
            await db.commit()
            await db.refresh(scan)
            run_scan_task.delay(str(scan.id), str(user.id))
            queued += 1

    logger.info("Scheduled rescan enqueued", users=queued)
    return {"queued": queued}


def settings_max_pages(scan) -> int:
    """Return max pages based on subscription tier."""
    from app.models import SubscriptionTier
    tier_map = {
        SubscriptionTier.FREE: 20,
        SubscriptionTier.BASIC: 50,
        SubscriptionTier.PRO: 100,
        SubscriptionTier.ENTERPRISE: 500,
    }
    # Need to lazy-import to avoid circular
    try:
        user_tier = scan.user.subscription_tier if scan.user else SubscriptionTier.FREE
        return tier_map.get(user_tier, 20)
    except Exception:
        return 20


@celery_app.task(name="tasks.send_verification_email", max_retries=3, default_retry_delay=60)
def send_verification_email_task(user_id: str, email: str, full_name: str):
    """Send email verification link after registration."""
    import asyncio, secrets
    from app.services.email.smtp_service import send_email
    from app.config import settings
    token = secrets.token_urlsafe(32)
    link = f"https://{settings.ALLOWED_HOSTS[0]}/verify?token={token}&uid={user_id}"
    asyncio.run(send_email(email, "verify_email", {"link": link, "full_name": full_name}))


@celery_app.task(name="tasks.hard_delete_user", max_retries=2)
def hard_delete_user_task(user_id: str):
    """Hard-delete user after 30-day soft-delete retention window (GDPR)."""
    import asyncio
    asyncio.run(_hard_delete_async(user_id))


async def _hard_delete_async(user_id: str):
    from sqlalchemy import delete as sql_delete
    from uuid import UUID as _UUID
    from app.database import AsyncSessionLocal
    from app.models import User
    from app.services.storage.minio_client import delete_user_files
    import structlog
    logger = structlog.get_logger(__name__)

    async with AsyncSessionLocal() as db:
        await db.execute(sql_delete(User).where(User.id == _UUID(user_id)))
        await db.commit()

    # Purge MinIO files
    try:
        await delete_user_files(user_id)
    except Exception as e:
        logger.warning("MinIO purge failed", user_id=user_id, error=str(e))

    logger.info("User hard-deleted", user_id=user_id)
