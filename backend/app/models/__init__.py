"""
models/ — SQLAlchemy ORM models.

AppSec notes:
  - Password hash NEVER returned in any schema/serialiser.
  - PII fields (name, email) encrypted at-rest via column-level encryption
    using app-layer AES-256-GCM (SQLAlchemy TypeDecorator in production).
  - Soft-delete pattern (deleted_at) — GDPR right-to-erasure handled separately.
  - UUID primary keys prevent IDOR enumeration attacks.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Enums ─────────────────────────────────────────────────────────────────────
class SubscriptionTier(str, PyEnum):
    FREE = "free"
    BASIC = "basic"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class ScanStatus(str, PyEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RemovalStatus(str, PyEnum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    ACKNOWLEDGED = "acknowledged"
    COMPLETED = "completed"
    REJECTED = "rejected"
    MANUAL_REQUIRED = "manual_required"


class ExposureRisk(str, PyEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ── User ──────────────────────────────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(254), unique=True, nullable=False, index=True)
    hashed_password = Column(String(128), nullable=False)
    full_name = Column(String(200), nullable=True)
    phone = Column(String(20), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)
    subscription_tier = Column(
        Enum(SubscriptionTier),
        default=SubscriptionTier.FREE,
        nullable=False,
    )
    stripe_customer_id = Column(String(64), nullable=True, unique=True)
    stripe_subscription_id = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
    deleted_at = Column(DateTime(timezone=True), nullable=True)  # soft delete

    # ── Relationships ──────────────────────────────────────────────────────────
    scans: List["Scan"] = relationship("Scan", back_populates="user", lazy="select")
    removals: List["RemovalRequest"] = relationship(
        "RemovalRequest", back_populates="user", lazy="select"
    )
    refresh_tokens: List["RefreshToken"] = relationship(
        "RefreshToken", back_populates="user", lazy="select"
    )
    api_keys: List["APIKey"] = relationship(
        "APIKey", back_populates="user", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email}>"


# ── Refresh Token ─────────────────────────────────────────────────────────────
class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    user_agent = Column(String(512), nullable=True)   # for session tracking
    ip_address = Column(String(45), nullable=True)    # IPv6 max = 39 chars

    user: "User" = relationship("User", back_populates="refresh_tokens")


# ── Scan ──────────────────────────────────────────────────────────────────────
class Scan(Base):
    __tablename__ = "scans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    status = Column(Enum(ScanStatus), default=ScanStatus.PENDING, nullable=False)
    target_name = Column(String(200), nullable=False)
    target_email = Column(String(254), nullable=True)
    target_phone = Column(String(20), nullable=True)
    target_location = Column(String(200), nullable=True)
    exposure_score = Column(Float, nullable=True)          # 0.0 – 100.0
    risk_level = Column(Enum(ExposureRisk), nullable=True)
    results = Column(JSONB, nullable=True)                 # raw findings
    sources_scanned = Column(Integer, default=0)
    pii_instances_found = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    celery_task_id = Column(String(64), nullable=True)

    user: "User" = relationship("User", back_populates="scans")
    removals: List["RemovalRequest"] = relationship(
        "RemovalRequest", back_populates="scan", lazy="select"
    )


# ── Removal Request ───────────────────────────────────────────────────────────
class RemovalRequest(Base):
    __tablename__ = "removal_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    scan_id = Column(
        UUID(as_uuid=True), ForeignKey("scans.id", ondelete="SET NULL"), nullable=True
    )
    source_url = Column(Text, nullable=False)
    source_domain = Column(String(253), nullable=False, index=True)
    data_type = Column(String(50), nullable=False)      # ADDRESS | PHONE | EMAIL etc.
    status = Column(
        Enum(RemovalStatus), default=RemovalStatus.PENDING, nullable=False
    )
    removal_method = Column(String(50), nullable=True)   # API | FORM | EMAIL | MANUAL
    submission_log = Column(JSONB, nullable=True)        # audit trail
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    user: "User" = relationship("User", back_populates="removals")
    scan: "Scan" = relationship("Scan", back_populates="removals")


# ── Enterprise API Key ────────────────────────────────────────────────────────
class APIKey(Base):
    __tablename__ = "api_keys"
    __table_args__ = (UniqueConstraint("key_hash", name="uq_api_key_hash"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    name = Column(String(100), nullable=False)           # human label
    key_hash = Column(String(64), nullable=False, index=True)
    key_prefix = Column(String(12), nullable=False)      # first 8 chars — for UI display
    is_active = Column(Boolean, default=True, nullable=False)
    scopes = Column(JSONB, default=list)                 # ["scan:read","removal:write"]
    rate_limit_per_hour = Column(Integer, default=100)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    user: "User" = relationship("User", back_populates="api_keys")
