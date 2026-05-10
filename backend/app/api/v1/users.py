"""api/v1/users.py — User profile endpoints."""
from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.v1.deps import get_current_user
from app.database import get_db
from app.models import User

router = APIRouter(prefix="/users", tags=["Users"])

class UserResponse(BaseModel):
    id: str
    email: str
    full_name: Optional[str]
    subscription_tier: str
    is_verified: bool
    class Config:
        from_attributes = True

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return {"id": str(current_user.id), "email": current_user.email,
            "full_name": current_user.full_name,
            "subscription_tier": current_user.subscription_tier.value,
            "is_verified": current_user.is_verified}

@router.patch("/me", response_model=UserResponse)
async def update_me(
    payload: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if payload.full_name is not None:
        current_user.full_name = payload.full_name
    if payload.phone is not None:
        current_user.phone = payload.phone
    await db.commit()
    await db.refresh(current_user)
    return {"id": str(current_user.id), "email": current_user.email,
            "full_name": current_user.full_name,
            "subscription_tier": current_user.subscription_tier.value,
            "is_verified": current_user.is_verified}

from datetime import datetime, timezone
from fastapi import status

@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    GDPR Art.17 / DPDP Act 2023 S.12 — right to erasure.
    Hard-deletes user + all associated data via CASCADE foreign keys.
    MinIO user files purged separately via background task.
    """
    import structlog
    logger = structlog.get_logger(__name__)

    # Soft-delete first (audit trail for 30 days)
    current_user.deleted_at = datetime.now(timezone.utc)
    current_user.is_active = False
    current_user.email = f"deleted_{current_user.id}@erased.local"  # anonymise
    await db.commit()

    # Enqueue hard-delete after 30-day retention window
    from app.workers.tasks import hard_delete_user_task
    hard_delete_user_task.apply_async(
        args=[str(current_user.id)],
        countdown=30 * 24 * 3600,   # 30 days
    )
    logger.info("User erasure requested", user_id=str(current_user.id))
