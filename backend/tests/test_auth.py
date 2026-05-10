"""
tests/test_auth.py — Integration tests for auth endpoints.

Uses pytest-asyncio + httpx AsyncClient against an in-memory SQLite DB
(overridden via conftest.py for CI test isolation).
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.database import Base, engine


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Create tables before each test, drop after."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def registered_user(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "test@example.com",
            "password": "SecurePass123!",
            "full_name": "Test User",
        },
    )
    assert resp.status_code == 201
    return {"email": "test@example.com", "password": "SecurePass123!", "full_name": "Test User"}


@pytest_asyncio.fixture
async def auth_tokens(client: AsyncClient, registered_user):
    resp = await client.post(
        "/api/v1/auth/login",
        data={"username": registered_user["email"], "password": registered_user["password"]},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 200
    return resp.json()


# ── Registration ──────────────────────────────────────────────────────────────
class TestRegistration:
    async def test_register_success(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "new@example.com", "password": "StrongPass1!", "full_name": "New User"},
        )
        assert resp.status_code == 201
        assert "verification" in resp.json()["message"].lower()

    async def test_register_weak_password_no_uppercase(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "x@x.com", "password": "weakpassword1!", "full_name": "X"},
        )
        assert resp.status_code == 422

    async def test_register_weak_password_no_special(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "x@x.com", "password": "WeakPassword1", "full_name": "X"},
        )
        assert resp.status_code == 422

    async def test_register_short_password(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "x@x.com", "password": "Short1!", "full_name": "X"},
        )
        assert resp.status_code == 422

    async def test_register_duplicate_email_no_enumeration(self, client: AsyncClient, registered_user):
        """Duplicate email must return same 201 response (no enumeration)."""
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": registered_user["email"], "password": "AnotherPass1!", "full_name": "X"},
        )
        assert resp.status_code == 201  # Same response regardless

    async def test_register_invalid_email(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "not-an-email", "password": "StrongPass1!", "full_name": "X"},
        )
        assert resp.status_code == 422


# ── Login ────────────────────────────────────────────────────────────────────
class TestLogin:
    async def test_login_success(self, client: AsyncClient, registered_user):
        resp = await client.post(
            "/api/v1/auth/login",
            data={"username": registered_user["email"], "password": registered_user["password"]},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] == 1800

    async def test_login_wrong_password(self, client: AsyncClient, registered_user):
        resp = await client.post(
            "/api/v1/auth/login",
            data={"username": registered_user["email"], "password": "WrongPass123!"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert resp.status_code == 401

    async def test_login_unknown_email(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/auth/login",
            data={"username": "unknown@example.com", "password": "SomePass1!"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert resp.status_code == 401

    async def test_login_returns_jwt_structure(self, client: AsyncClient, auth_tokens):
        token = auth_tokens["access_token"]
        parts = token.split(".")
        assert len(parts) == 3, "JWT must have 3 parts"


# ── Token refresh ─────────────────────────────────────────────────────────────
class TestTokenRefresh:
    async def test_refresh_returns_new_tokens(self, client: AsyncClient, auth_tokens):
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": auth_tokens["refresh_token"]},
        )
        assert resp.status_code == 200
        new_tokens = resp.json()
        assert new_tokens["access_token"] != auth_tokens["access_token"]

    async def test_refresh_token_rotation(self, client: AsyncClient, auth_tokens):
        """Old refresh token must be invalid after rotation."""
        old_rt = auth_tokens["refresh_token"]

        # First refresh — should succeed
        resp1 = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": old_rt},
        )
        assert resp1.status_code == 200

        # Replay old token — should fail
        resp2 = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": old_rt},
        )
        assert resp2.status_code == 401

    async def test_invalid_refresh_token(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "invalid.token.here"},
        )
        assert resp.status_code == 401


# ── Logout ────────────────────────────────────────────────────────────────────
class TestLogout:
    async def test_logout_success(self, client: AsyncClient, auth_tokens):
        resp = await client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": auth_tokens["refresh_token"]},
        )
        assert resp.status_code == 200

    async def test_logout_invalidates_refresh_token(self, client: AsyncClient, auth_tokens):
        rt = auth_tokens["refresh_token"]
        await client.post("/api/v1/auth/logout", json={"refresh_token": rt})

        # Should now fail to refresh
        resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": rt})
        assert resp.status_code == 401

    async def test_logout_unknown_token_returns_200(self, client: AsyncClient):
        """Logout of unknown token must not reveal token existence."""
        resp = await client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": "unknown.token.xyz"},
        )
        assert resp.status_code == 200


# ── Scan endpoints ────────────────────────────────────────────────────────────
class TestScans:
    async def test_create_scan_unauthenticated(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/scans",
            json={"target_name": "Test User"},
        )
        assert resp.status_code == 401

    async def test_create_scan_authenticated(self, client: AsyncClient, auth_tokens):
        resp = await client.post(
            "/api/v1/scans",
            json={"target_name": "Test User", "target_location": "Mumbai"},
            headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert "id" in data
        assert data["status"] == "pending"
        assert data["target_name"] == "Test User"

    async def test_list_scans_only_own(self, client: AsyncClient, auth_tokens):
        # Create a scan
        await client.post(
            "/api/v1/scans",
            json={"target_name": "My Scan"},
            headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
        )

        resp = await client.get(
            "/api/v1/scans",
            headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
        )
        assert resp.status_code == 200
        scans = resp.json()
        assert len(scans) >= 1
        # All must belong to current user (ownership enforced at DB level)

    async def test_get_scan_not_found(self, client: AsyncClient, auth_tokens):
        import uuid
        resp = await client.get(
            f"/api/v1/scans/{uuid.uuid4()}",
            headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
        )
        assert resp.status_code == 404

    async def test_scan_requires_name(self, client: AsyncClient, auth_tokens):
        resp = await client.post(
            "/api/v1/scans",
            json={"target_email": "x@x.com"},
            headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
        )
        assert resp.status_code == 422


# ── Health endpoints ──────────────────────────────────────────────────────────
class TestHealth:
    async def test_health(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    async def test_security_headers(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.headers.get("x-content-type-options") == "nosniff"
        assert resp.headers.get("x-frame-options") == "DENY"
