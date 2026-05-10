"""
database.py — Async SQLAlchemy engine + session factory.

Security notes:
  - Connection string never logged (structlog redacts DSN).
  - Pool recycled every 30 min to avoid stale connections.
  - SSL enforced in production via ?sslmode=require in DATABASE_URL.
"""
from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import settings


def _build_engine():
    """Build async engine; use NullPool for test environments."""
    kwargs: dict = {
        "echo": settings.DATABASE_ECHO,
        "pool_pre_ping": True,
        "pool_recycle": 1800,  # 30 min
    }
    if settings.ENVIRONMENT == "test":
        kwargs["poolclass"] = NullPool
    else:
        kwargs["pool_size"] = settings.DATABASE_POOL_SIZE
        kwargs["max_overflow"] = settings.DATABASE_MAX_OVERFLOW

    return create_async_engine(str(settings.DATABASE_URL), **kwargs)


engine = _build_engine()

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a database session per request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def create_tables() -> None:
    """Create all tables (used in dev/test; Alembic handles production)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
