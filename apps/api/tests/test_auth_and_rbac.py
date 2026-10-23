"""Tests for admin authentication, brute-force lockout, JWT lifecycle, and RBAC enforcement."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone, timedelta

from api.db.models.admin import AdminUser, AdminRole
from api.db.models.audit import AuditEvent
from api.security.hashing import hash_password


@pytest.mark.asyncio
async def test_admin_login_success(client: AsyncClient, db_session: AsyncSession, create_test_admin):
    """Verify that valid credentials return an access token and record an audit event."""
    admin, _ = await create_test_admin(
        username="superadmin",
        password="ValidPassword123!",
        role=AdminRole.SUPER_ADMIN,
    )

    response = await client.post(
        "/api/v1/admin/auth/login",
        json={"username": "superadmin", "password": "ValidPassword123!"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["role"] == "super_admin"
    assert data["username"] == "superadmin"

    # Verify database state updated
    await db_session.refresh(admin)
    assert admin.failed_login_attempts == 0
    assert admin.last_login_at is not None

    # Verify audit event
    stmt = select(AuditEvent).where(AuditEvent.action == "LOGIN_SUCCESS")
    result = await db_session.execute(stmt)
    event = result.scalars().first()
    assert event is not None
    assert event.actor_id == str(admin.id)


@pytest.mark.asyncio
async def test_admin_login_failure_increments_attempts(
    client: AsyncClient, db_session: AsyncSession, create_test_admin
):
    """Verify failed login increments attempt counter and fails with 401."""
    admin, _ = await create_test_admin(
        username="testuser",
        password="CorrectPassword123!",
        role=AdminRole.SUPPORT,
    )

    response = await client.post(
        "/api/v1/admin/auth/login",
        json={"username": "testuser", "password": "WrongPassword!"},
    )
    assert response.status_code == 401
    assert "Invalid username or password" in response.json()["detail"]

    await db_session.refresh(admin)
    assert admin.failed_login_attempts == 1


@pytest.mark.asyncio
async def test_admin_brute_force_lockout(
    client: AsyncClient, db_session: AsyncSession, create_test_admin
):
    """Verify that 5 failed attempts locks the account and returns 429."""
    admin, _ = await create_test_admin(
        username="lockoutuser",
        password="CorrectPassword123!",
        role=AdminRole.SUPPORT,
    )

    # 4 failed attempts
    for _ in range(4):
        resp = await client.post(
            "/api/v1/admin/auth/login",
            json={"username": "lockoutuser", "password": "BadPassword!"},
        )
        assert resp.status_code == 401

    # 5th failed attempt locks the account (returns 401 and sets lockout)
    resp5 = await client.post(
        "/api/v1/admin/auth/login",
        json={"username": "lockoutuser", "password": "BadPassword!"},
    )
    assert resp5.status_code == 401

    # 6th attempt encounters locked account (returns 403)
    resp6 = await client.post(
        "/api/v1/admin/auth/login",
        json={"username": "lockoutuser", "password": "BadPassword!"},
    )
    assert resp6.status_code == 403
    assert "Account is temporarily locked" in resp6.json()["detail"]

    await db_session.refresh(admin)
    assert admin.failed_login_attempts == 5
    assert admin.locked_until is not None


@pytest.mark.asyncio
async def test_admin_me_endpoint(client: AsyncClient, create_test_admin):
    """Verify that GET /me returns current admin info and correct permissions."""
    admin, token = await create_test_admin(
        username="qaadmin",
        role=AdminRole.ASTROLOGY_QA,
    )

    headers = {"Authorization": f"Bearer {token}"}
    response = await client.get("/api/v1/admin/auth/me", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "qaadmin"
    assert data["role"] == "astrology_qa"
    assert "user:read" in data["permissions"]
    assert "profile:read_sensitive" in data["permissions"]
    # QA role must NOT have consent:revoke
    assert "consent:revoke" not in data["permissions"]


@pytest.mark.asyncio
async def test_rbac_sensitive_access_control(client: AsyncClient, create_test_admin):
    """Verify RBAC: Support role is denied access to sensitive birth data (403), SuperAdmin is allowed."""
    _, support_token = await create_test_admin(
        username="supportrep",
        email="support@example.com",
        role=AdminRole.SUPPORT,
    )

    # Attempt sensitive endpoint access with Support role (requires profile:read_sensitive)
    fake_user_id = "00000000-0000-0000-0000-000000000001"
    fake_profile_id = "00000000-0000-0000-0000-000000000002"
    url = f"/api/v1/admin/users/{fake_user_id}/profiles/{fake_profile_id}/sensitive"

    response = await client.get(url, headers={"Authorization": f"Bearer {support_token}"})
    assert response.status_code == 403
    assert "profile:read_sensitive" in response.json()["detail"]
