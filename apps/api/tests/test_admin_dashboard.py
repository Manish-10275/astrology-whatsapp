"""Tests for internal admin dashboard endpoints, diagnostics, conversation traces, and RBAC."""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date, time, datetime, timezone

from api.db.models.admin import AdminUser, AdminRole
from api.db.models.user import User, UserPreferences, UserStatus, AstrologySystemEnum
from api.db.models.conversation import Conversation, ConversationMessage, ConversationStatus, ConversationState, MessageDirection, MessageSender
from api.security.hashing import hash_password
from api.security.token import create_access_token
from api.security.encryption import compute_phone_hash, encrypt_field


@pytest_asyncio.fixture
async def super_admin(db_session: AsyncSession) -> AdminUser:
    admin = AdminUser(
        username="super_dash",
        email="super_dash@astrology.internal",
        password_hash=hash_password("SuperSecretP@ss123"),
        role=AdminRole.SUPER_ADMIN,
        is_active=True
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin


@pytest_asyncio.fixture
async def support_admin(db_session: AsyncSession) -> AdminUser:
    admin = AdminUser(
        username="support_dash",
        email="support_dash@astrology.internal",
        password_hash=hash_password("SupportSecretP@ss123"),
        role=AdminRole.SUPPORT,
        is_active=True
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin


@pytest.mark.asyncio
async def test_dashboard_stats_endpoint(client: AsyncClient, db_session: AsyncSession, super_admin: AdminUser):
    """Tests GET /api/v1/admin/dashboard/stats endpoint."""
    # Seed a user and preferences
    phone = "+919800000001"
    user = User(
        phone_hash=compute_phone_hash(phone),
        encrypted_phone=encrypt_field(phone),
        whatsapp_name="Stats User",
        status=UserStatus.ACTIVE
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    pref = UserPreferences(
        user_id=user.id,
        astrology_system=AstrologySystemEnum.VEDIC,
        preferred_language="en",
        daily_horoscope_opt_in=True
    )
    db_session.add(pref)
    await db_session.commit()

    token = create_access_token(
        admin_id=str(super_admin.id),
        username=super_admin.username,
        role=super_admin.role.value,
        permissions=super_admin.get_permissions()
    )
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get("/api/v1/admin/dashboard/stats", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_users"] >= 1
    assert data["active_users"] >= 1
    assert data["opt_in_horoscopes"] >= 1
    assert data["astrology_systems"]["vedic"] >= 1


@pytest.mark.asyncio
async def test_dashboard_conversations_and_trace(client: AsyncClient, db_session: AsyncSession, super_admin: AdminUser):
    """Tests GET /api/v1/admin/dashboard/conversations and trace inspection."""
    phone = "+919800000002"
    user = User(
        phone_hash=compute_phone_hash(phone),
        encrypted_phone=encrypt_field(phone),
        whatsapp_name="Trace User",
        status=UserStatus.ACTIVE
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    conv = Conversation(
        user_id=user.id,
        channel="whatsapp",
        status=ConversationStatus.ACTIVE,
        current_state=ConversationState.READING_READY,
        state_metadata={}
    )
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)

    msg = ConversationMessage(
        conversation_id=conv.id,
        user_id=user.id,
        direction=MessageDirection.INBOUND,
        sender=MessageSender.USER,
        content_type="text"
    )
    msg.set_content("Tell me my daily horoscope")
    db_session.add(msg)
    await db_session.commit()

    token = create_access_token(
        admin_id=str(super_admin.id),
        username=super_admin.username,
        role=super_admin.role.value,
        permissions=super_admin.get_permissions()
    )
    headers = {"Authorization": f"Bearer {token}"}

    # 1. List conversations
    resp_list = await client.get("/api/v1/admin/dashboard/conversations", headers=headers)
    assert resp_list.status_code == 200
    items = resp_list.json()
    assert len(items) >= 1
    assert any(c["id"] == str(conv.id) for c in items)

    # 2. Inspect trace
    resp_trace = await client.get(f"/api/v1/admin/dashboard/conversations/{conv.id}/trace", headers=headers)
    assert resp_trace.status_code == 200
    trace_data = resp_trace.json()
    assert trace_data["conversation_id"] == str(conv.id)
    assert trace_data["total_messages"] >= 1
    assert "daily horoscope" in trace_data["messages"][0]["content_preview"].lower()


@pytest.mark.asyncio
async def test_dashboard_diagnostics(client: AsyncClient, super_admin: AdminUser):
    """Tests GET /api/v1/admin/dashboard/diagnostics."""
    token = create_access_token(
        admin_id=str(super_admin.id),
        username=super_admin.username,
        role=super_admin.role.value,
        permissions=super_admin.get_permissions()
    )
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get("/api/v1/admin/dashboard/diagnostics", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("operational", "degraded")
    assert data["database"] == "connected"
    assert data["swiss_ephemeris"] == "ready"
    assert "ephemeris_mode" in data


@pytest.mark.asyncio
async def test_dashboard_rbac_guards(client: AsyncClient, support_admin: AdminUser):
    """Verifies that unauthorized or insufficiently permitted users are blocked."""
    # 1. No token -> 401
    resp_no_auth = await client.get("/api/v1/admin/dashboard/stats")
    assert resp_no_auth.status_code == 401

    # 2. Support admin has 'dashboard:read' -> 200 on stats
    support_token = create_access_token(
        admin_id=str(support_admin.id),
        username=support_admin.username,
        role=support_admin.role.value,
        permissions=support_admin.get_permissions()
    )
    headers = {"Authorization": f"Bearer {support_token}"}
    resp_support = await client.get("/api/v1/admin/dashboard/stats", headers=headers)
    assert resp_support.status_code == 200

    # 3. Support admin does NOT have 'dashboard:trigger' -> 403 on trigger
    resp_trigger_forbidden = await client.post("/api/v1/admin/dashboard/schedules/trigger", headers=headers)
    assert resp_trigger_forbidden.status_code == 403
