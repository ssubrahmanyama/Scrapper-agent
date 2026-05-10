"""tests/conftest.py — Pytest configuration and shared fixtures."""
from __future__ import annotations

import asyncio
import os
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# ── Override settings for tests BEFORE any app imports ───────────────────────
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://privacyshield:devpassword@localhost:5432/privacyshield_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/15")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/15")
os.environ.setdefault("SECRET_KEY", "test-secret-key-do-not-use-in-production-ever-ok")
os.environ.setdefault("GOOGLE_CUSTOM_SEARCH_API_KEY", "fake-key")
os.environ.setdefault("GOOGLE_SEARCH_ENGINE_ID", "fake-id")
os.environ.setdefault("SENDGRID_API_KEY", "fake-key")
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_fake")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_fake")
os.environ.setdefault("STRIPE_PRICE_BASIC", "price_fake_basic")
os.environ.setdefault("STRIPE_PRICE_PRO", "price_fake_pro")
os.environ.setdefault("STRIPE_PRICE_ENTERPRISE", "price_fake_ent")
os.environ.setdefault("BACKEND_CORS_ORIGINS", "http://localhost:3000")


# ── Async event loop ──────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def event_loop():
    """Single event loop for entire test session."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


# ── pytest-asyncio mode ────────────────────────────────────────────────────────
def pytest_configure(config):
    config.addinivalue_line(
        "markers", "asyncio: mark test as async"
    )


# ── pytest.ini equivalent config ─────────────────────────────────────────────
pytest_plugins = ["pytest_asyncio"]
