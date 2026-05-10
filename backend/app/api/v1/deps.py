"""api/v1/deps.py — FastAPI dependency injection helpers."""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AuthenticationError,
    InsufficientPermissionsError,
    SubscriptionRequiredError,
    TokenExpiredError,
)
from app.core.security import decode_token
from app.database import get_db
from app.models import APIKey, SubscriptionTier, User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Extract and validate the JWT bearer token.
    Returns the authenticated User object.
    """
    if not token:
        raise AuthenticationError("Authentication required.")

    try:
        payload = decode_token(token)
    except JWTError:
        raise TokenExpiredError()

    if payload.get("type") != "access":
        raise AuthenticationError("Invalid token type.")

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise AuthenticationError("Invalid token payload.")

    try:
        user_id = UUID(user_id_str)
    except ValueError:
        raise AuthenticationError("Invalid token payload.")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise AuthenticationError("User not found.")
    if not user.is_active:
        raise AuthenticationError("Account deactivated.")

    return user


async def get_current_active_superuser(
    current_user: User = Depends(get_current_user),
) -> User:
    """Require superuser role."""
    if not current_user.is_superuser:
        raise InsufficientPermissionsError()
    return current_user


def require_subscription(*tiers: SubscriptionTier):
    """
    Dependency factory — require specific subscription tier(s).
    Usage: Depends(require_subscription(SubscriptionTier.PRO, SubscriptionTier.ENTERPRISE))
    """
    async def _check(current_user: User = Depends(get_current_user)) -> User:
        if current_user.subscription_tier not in tiers:
            tier_names = ", ".join(t.value for t in tiers)
            raise SubscriptionRequiredError(
                f"This feature requires: {tier_names} plan."
            )
        return current_user
    return _check


# ── Enterprise API Key auth ───────────────────────────────────────────────────
import hashlib

async def get_api_key_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Authenticate via Enterprise API key.
    Supports both Bearer <token> and ps_live_<key> format.
    """
    if not credentials:
        raise AuthenticationError("API key required.")

    raw_key = credentials.credentials
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    from datetime import datetime, timezone
    result = await db.execute(
        select(APIKey).where(
            APIKey.key_hash == key_hash,
            APIKey.is_active == True,
        )
    )
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise AuthenticationError("Invalid API key.")

    if api_key.expires_at and api_key.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise AuthenticationError("API key expired.")

    # Update last used
    api_key.last_used_at = datetime.now(timezone.utc)
    await db.commit()

    # Load user
    user_result = await db.execute(select(User).where(User.id == api_key.user_id))
    user = user_result.scalar_one_or_none()
    if not user or not user.is_active:
        raise AuthenticationError("Associated user account is inactive.")

    return user
