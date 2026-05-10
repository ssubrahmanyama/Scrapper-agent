"""api/v1/removals.py — Removal request endpoints."""
from __future__ import annotations
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.v1.deps import get_current_user
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models import RemovalRequest, RemovalStatus, User

router = APIRouter(prefix="/removals", tags=["Removals"])

class RemovalResponse(BaseModel):
    id: UUID
    source_domain: str
    source_url: str
    data_type: str
    status: RemovalStatus
    removal_method: Optional[str]
    submitted_at: Optional[str]
    created_at: str
    class Config:
        from_attributes = True

@router.get("", response_model=List[RemovalResponse])
async def list_removals(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, le=100),
    status: Optional[RemovalStatus] = None,
):
    q = select(RemovalRequest).where(RemovalRequest.user_id == current_user.id)
    if status:
        q = q.where(RemovalRequest.status == status)
    q = q.order_by(desc(RemovalRequest.created_at)).offset(skip).limit(limit)
    result = await db.execute(q)
    items = result.scalars().all()
    return [
        {"id": r.id, "source_domain": r.source_domain, "source_url": r.source_url,
         "data_type": r.data_type, "status": r.status, "removal_method": r.removal_method,
         "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
         "created_at": r.created_at.isoformat()}
        for r in items
    ]

@router.post("/{removal_id}/process")
async def process_removal(
    removal_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(RemovalRequest).where(RemovalRequest.id == removal_id, RemovalRequest.user_id == current_user.id)
    )
    removal = result.scalar_one_or_none()
    if not removal:
        raise NotFoundError("Removal request not found.")
    from app.workers.tasks import process_removal_task
    process_removal_task.delay(str(removal_id), str(current_user.id))
    return {"message": "Removal queued", "removal_id": str(removal_id)}
