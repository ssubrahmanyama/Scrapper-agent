"""
api/v1/scans.py — Scan management endpoints.

Endpoints:
  POST   /scans          — Initiate a new scan
  GET    /scans          — List user's scans
  GET    /scans/{id}     — Get scan details + results
  DELETE /scans/{id}     — Delete scan record
  POST   /scans/{id}/rescan — Force rescan
"""
from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, require_subscription
from app.core.exceptions import NotFoundError, ScanLimitExceededError
from app.database import get_db
from app.models import Scan, ScanStatus, SubscriptionTier, User

router = APIRouter(prefix="/scans", tags=["Scans"])


# ── Schemas ───────────────────────────────────────────────────────────────────
class ScanCreateRequest(BaseModel):
    target_name: str = Field(min_length=2, max_length=200)
    target_email: Optional[str] = Field(default=None, max_length=254)
    target_phone: Optional[str] = Field(default=None, max_length=20)
    target_location: Optional[str] = Field(default=None, max_length=200)


class ScanResponse(BaseModel):
    id: UUID
    status: ScanStatus
    target_name: str
    exposure_score: Optional[float]
    risk_level: Optional[str]
    pii_instances_found: int
    sources_scanned: int
    created_at: str
    completed_at: Optional[str]

    class Config:
        from_attributes = True


class ScanDetailResponse(ScanResponse):
    results: Optional[dict]
    error_message: Optional[str]


# ── Scan limits per tier ──────────────────────────────────────────────────────
DAILY_SCAN_LIMITS = {
    SubscriptionTier.FREE: 1,
    SubscriptionTier.BASIC: 5,
    SubscriptionTier.PRO: 50,
    SubscriptionTier.ENTERPRISE: 1000,
}


async def _check_scan_limit(user: User, db: AsyncSession) -> None:
    """Raise ScanLimitExceededError if user exceeded daily scan limit."""
    from datetime import datetime, timezone, timedelta

    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    result = await db.execute(
        select(Scan).where(
            Scan.user_id == user.id,
            Scan.created_at >= today_start,
        )
    )
    count = len(result.scalars().all())
    limit = DAILY_SCAN_LIMITS.get(user.subscription_tier, 1)
    if count >= limit:
        raise ScanLimitExceededError(
            f"Daily scan limit ({limit}) reached for {user.subscription_tier.value} plan."
        )


# ── Routes ────────────────────────────────────────────────────────────────────
@router.post(
    "",
    response_model=ScanDetailResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_scan(
    payload: ScanCreateRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Initiate an async privacy scan.
    Returns immediately with scan_id; results available via GET /scans/{id}.
    """
    await _check_scan_limit(current_user, db)

    scan = Scan(
        user_id=current_user.id,
        target_name=payload.target_name,
        target_email=payload.target_email,
        target_phone=payload.target_phone,
        target_location=payload.target_location,
        status=ScanStatus.PENDING,
    )
    db.add(scan)
    await db.commit()
    await db.refresh(scan)

    # Enqueue Celery task
    from app.workers.tasks import run_scan_task
    task = run_scan_task.delay(str(scan.id), str(current_user.id))
    scan.celery_task_id = task.id
    await db.commit()

    return _format_scan(scan)


@router.get("", response_model=List[ScanResponse])
async def list_scans(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, le=100),
    status_filter: Optional[ScanStatus] = Query(default=None, alias="status"),
):
    """List all scans for the current user, newest first."""
    query = select(Scan).where(Scan.user_id == current_user.id)
    if status_filter:
        query = query.where(Scan.status == status_filter)
    query = query.order_by(desc(Scan.created_at)).offset(skip).limit(limit)

    result = await db.execute(query)
    scans = result.scalars().all()
    return [_format_scan(s) for s in scans]


@router.get("/{scan_id}", response_model=ScanDetailResponse)
async def get_scan(
    scan_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get scan details and PII findings."""
    result = await db.execute(
        select(Scan).where(
            Scan.id == scan_id,
            Scan.user_id == current_user.id,  # Enforce ownership
        )
    )
    scan = result.scalar_one_or_none()
    if not scan:
        raise NotFoundError("Scan not found.")
    return _format_scan(scan, include_results=True)


@router.delete("/{scan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scan(
    scan_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a scan record (GDPR right to erasure)."""
    result = await db.execute(
        select(Scan).where(
            Scan.id == scan_id,
            Scan.user_id == current_user.id,
        )
    )
    scan = result.scalar_one_or_none()
    if not scan:
        raise NotFoundError("Scan not found.")
    await db.delete(scan)
    await db.commit()


@router.post("/{scan_id}/rescan", response_model=ScanDetailResponse)
async def rescan(
    scan_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Force a re-scan of an existing scan target."""
    await _check_scan_limit(current_user, db)

    result = await db.execute(
        select(Scan).where(
            Scan.id == scan_id,
            Scan.user_id == current_user.id,
        )
    )
    original = result.scalar_one_or_none()
    if not original:
        raise NotFoundError("Scan not found.")

    # Create new scan based on original
    new_scan = Scan(
        user_id=current_user.id,
        target_name=original.target_name,
        target_email=original.target_email,
        target_phone=original.target_phone,
        target_location=original.target_location,
        status=ScanStatus.PENDING,
    )
    db.add(new_scan)
    await db.commit()
    await db.refresh(new_scan)

    from app.workers.tasks import run_scan_task
    task = run_scan_task.delay(str(new_scan.id), str(current_user.id))
    new_scan.celery_task_id = task.id
    await db.commit()

    return _format_scan(new_scan)


# ── Helpers ───────────────────────────────────────────────────────────────────
def _format_scan(scan: Scan, include_results: bool = False) -> dict:
    data = {
        "id": scan.id,
        "status": scan.status,
        "target_name": scan.target_name,
        "exposure_score": scan.exposure_score,
        "risk_level": scan.risk_level.value if scan.risk_level else None,
        "pii_instances_found": scan.pii_instances_found or 0,
        "sources_scanned": scan.sources_scanned or 0,
        "created_at": scan.created_at.isoformat() if scan.created_at else None,
        "completed_at": scan.completed_at.isoformat() if scan.completed_at else None,
    }
    if include_results:
        data["results"] = scan.results
        data["error_message"] = scan.error_message
    return data
