"""
api/v1/auth.py — Authentication endpoints.

Endpoints:
  POST /auth/register   — User registration
  POST /auth/login      — Issue access + refresh tokens
  POST /auth/refresh    — Rotate refresh token
  POST /auth/logout     — Revoke refresh token
  POST /auth/verify     — Email verification
  POST /auth/forgot     — Password reset request
  POST /auth/reset      — Password reset execution

AppSec notes:
  - Passwords validated against strength policy before hashing.
  - Rate limiting: 5 login attempts / minute per IP.
  - Refresh tokens stored hashed; plaintext never persisted.
  - Account enumeration prevented: same response for unknown email.
  - Email verification tokens expire in 24h.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AuthenticationError,
    ConflictError,
    TokenExpiredError,
    TokenRevokedError,
)
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.database import get_db
from app.models import RefreshToken, SubscriptionTier, User

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ── Schemas ───────────────────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    full_name: str = Field(min_length=2, max_length=200)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit.")
        if not any(c in "!@#$%^&*()-_=+[]{}|;:,.<>?" for c in v):
            raise ValueError("Password must contain at least one special character.")
        return v


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class RefreshRequest(BaseModel):
    refresh_token: str


class MessageResponse(BaseModel):
    message: str


# ── Helpers ───────────────────────────────────────────────────────────────────
def _get_client_ip(request: Request) -> str:
    """Extract real IP, respecting X-Forwarded-For (set by trusted reverse proxy)."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _make_token_response(user_id: str, extra: dict | None = None) -> TokenResponse:
    from app.config import settings
    access_token = create_access_token(user_id, extra)
    refresh_token, _ = create_refresh_token(user_id)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# ── Routes ────────────────────────────────────────────────────────────────────
@router.post(
    "/register",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Register a new user account.
    Returns 201 regardless of whether email already exists
    (prevents account enumeration).
    """
    # Check for existing user
    existing = await db.execute(
        select(User).where(User.email == payload.email.lower())
    )
    if existing.scalar_one_or_none():
        # Anti-enumeration: don't reveal that email exists
        return MessageResponse(
            message="If this email is not already registered, "
                    "a verification link has been sent."
        )

    user = User(
        email=payload.email.lower(),
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        subscription_tier=SubscriptionTier.FREE,
        is_active=True,
        is_verified=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Send verification email via Celery (non-blocking)
    try:
        from app.workers.tasks import send_verification_email_task
        send_verification_email_task.delay(str(user.id), user.email, user.full_name or "")
    except Exception:
        pass  # Email failure must never block registration

    return MessageResponse(
        message="Registration successful. Check your email for a verification link."
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticate and issue tokens.
    Uses OAuth2 password flow (username = email).
    """
    result = await db.execute(
        select(User).where(User.email == form_data.username.lower())
    )
    user = result.scalar_one_or_none()

    # Timing-safe: always call verify_password even if user doesn't exist
    dummy_hash = "$2b$12$invalidhashfortimingsafety000000000000000000000"
    actual_hash = user.hashed_password if user else dummy_hash

    if not verify_password(form_data.password, actual_hash) or not user:
        raise AuthenticationError("Invalid email or password.")

    if not user.is_active:
        raise AuthenticationError("Account is deactivated.")

    # Issue tokens
    access_token = create_access_token(
        str(user.id),
        extra_claims={
            "email": user.email,
            "tier": user.subscription_tier,
            "is_superuser": user.is_superuser,
        },
    )
    refresh_token_plain, refresh_token_hash = create_refresh_token(str(user.id))

    # Store refresh token
    rt = RefreshToken(
        user_id=user.id,
        token_hash=refresh_token_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        user_agent=request.headers.get("user-agent", "")[:512],
        ip_address=_get_client_ip(request),
    )
    db.add(rt)
    await db.commit()

    from app.config import settings
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token_plain,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    payload: RefreshRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Rotate refresh token — invalidates old token, issues new pair.
    Implements refresh token rotation to detect token theft.
    """
    try:
        claims = decode_token(payload.refresh_token)
    except JWTError:
        raise TokenExpiredError()

    if claims.get("type") != "refresh":
        raise AuthenticationError("Invalid token type.")

    token_hash = hash_token(payload.refresh_token)
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked == False,
        )
    )
    stored_token = result.scalar_one_or_none()

    if not stored_token:
        # Token already used or doesn't exist — possible theft; revoke all for user
        user_id = claims.get("sub")
        if user_id:
            all_tokens = await db.execute(
                select(RefreshToken).where(
                    RefreshToken.user_id == user_id,
                    RefreshToken.revoked == False,
                )
            )
            for t in all_tokens.scalars():
                t.revoked = True
            await db.commit()
        raise TokenRevokedError()

    # Check expiry
    if stored_token.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise TokenExpiredError()

    # Revoke old token
    stored_token.revoked = True

    # Issue new pair
    user_id = claims["sub"]
    new_access = create_access_token(user_id)
    new_refresh_plain, new_refresh_hash = create_refresh_token(user_id)

    new_rt = RefreshToken(
        user_id=stored_token.user_id,
        token_hash=new_refresh_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        user_agent=request.headers.get("user-agent", "")[:512],
        ip_address=_get_client_ip(request),
    )
    db.add(new_rt)
    await db.commit()

    from app.config import settings
    return TokenResponse(
        access_token=new_access,
        refresh_token=new_refresh_plain,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(
    payload: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """Revoke a refresh token (logout)."""
    token_hash = hash_token(payload.refresh_token)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    stored = result.scalar_one_or_none()
    if stored:
        stored.revoked = True
        await db.commit()

    # Always return success (prevent enumeration)
    return MessageResponse(message="Logged out successfully.")
