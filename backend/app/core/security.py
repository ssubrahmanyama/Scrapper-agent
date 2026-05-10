"""
core/security.py — Password hashing, JWT creation/validation, token rotation.

AppSec notes:
  - bcrypt with work factor 12 (adjustable via BCRYPT_ROUNDS env).
  - Short-lived access tokens (30 min) + long-lived refresh tokens (7 days).
  - Refresh tokens stored hashed in DB — plaintext never persisted.
  - JTI (JWT ID) enables server-side token revocation via Redis blocklist.
  - Timing-safe comparison used for all secret comparisons.
"""
from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

# ── Password hashing ──────────────────────────────────────────────────────────
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,
)


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Timing-safe password verification."""
    return pwd_context.verify(plain_password, hashed_password)


# ── Token creation ────────────────────────────────────────────────────────────
def create_access_token(
    subject: str,
    extra_claims: Optional[dict] = None,
) -> str:
    """
    Create a signed JWT access token.
    - exp: 30 minutes
    - jti: unique per-token ID (enables revocation)
    - sub: user UUID string
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": subject,
        "iat": now,
        "exp": expire,
        "jti": str(uuid.uuid4()),
        "type": "access",
        **(extra_claims or {}),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(subject: str) -> tuple[str, str]:
    """
    Create a refresh token.
    Returns (plaintext_token, hashed_token).
    Only the hash is persisted in the database.
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    payload = {
        "sub": subject,
        "iat": now,
        "exp": expire,
        "jti": str(uuid.uuid4()),
        "type": "refresh",
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    return token, token_hash


def decode_token(token: str) -> dict:
    """
    Decode and validate a JWT.
    Raises JWTError on invalid/expired tokens.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"verify_exp": True},
        )
        return payload
    except JWTError:
        raise


def hash_token(token: str) -> str:
    """SHA-256 hash of a token string for DB storage."""
    return hashlib.sha256(token.encode()).hexdigest()


def constant_time_compare(a: str, b: str) -> bool:
    """Timing-safe string comparison."""
    return hmac.compare_digest(a.encode(), b.encode())


# ── API Key generation ────────────────────────────────────────────────────────
def generate_api_key() -> tuple[str, str]:
    """
    Generate an Enterprise API key.
    Returns (plaintext, hash). Only hash stored in DB.
    Format: ps_live_<random_40_chars>
    """
    raw = f"ps_live_{uuid.uuid4().hex}{uuid.uuid4().hex}"[:48]
    return raw, hashlib.sha256(raw.encode()).hexdigest()
