"""
services/monitoring/scheduler.py
Manages re-scan scheduling logic outside Celery beat.
Used to check whether a user is due for a weekly re-scan before enqueuing.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Scan, ScanStatus, User, SubscriptionTier
import structlog

logger = structlog.get_logger(__name__)

RESCAN_INTERVALS = {
    SubscriptionTier.FREE:       None,         # No auto-rescan
    SubscriptionTier.BASIC:      timedelta(days=14),
    SubscriptionTier.PRO:        timedelta(days=7),
    SubscriptionTier.ENTERPRISE: timedelta(days=1),
}


async def is_rescan_due(user: User, db: AsyncSession) -> bool:
    """Returns True if user's last completed scan is older than their tier's interval."""
    interval = RESCAN_INTERVALS.get(user.subscription_tier)
    if interval is None:
        return False

    result = await db.execute(
        select(Scan)
        .where(and_(Scan.user_id == user.id, Scan.status == ScanStatus.COMPLETED))
        .order_by(Scan.completed_at.desc())
        .limit(1)
    )
    last_scan = result.scalar_one_or_none()
    if not last_scan or not last_scan.completed_at:
        return True

    cutoff = datetime.now(timezone.utc) - interval
    return last_scan.completed_at.replace(tzinfo=timezone.utc) < cutoff


async def get_users_due_for_rescan(db: AsyncSession) -> list[User]:
    """Fetch all active paid users who are due for a re-scan."""
    result = await db.execute(
        select(User).where(
            and_(
                User.is_active == True,
                User.deleted_at == None,
                User.subscription_tier.in_([
                    SubscriptionTier.BASIC,
                    SubscriptionTier.PRO,
                    SubscriptionTier.ENTERPRISE,
                ]),
            )
        )
    )
    users = result.scalars().all()
    due = [u for u in users if await is_rescan_due(u, db)]
    logger.info("Users due for rescan", count=len(due))
    return due
