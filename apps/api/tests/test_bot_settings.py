"""Tests for Bot Settings, Bot Controls (Pause & Maintenance Mode), and Custom Message Manager."""

import json
import hmac
import hashlib
import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.config import get_settings
from api.db.models.admin import AdminUser, AdminRole
from api.db.models.bot_settings import BotSettings, DEFAULT_WELCOME_MESSAGE
from api.db.models.audit import AuditEvent
from api.db.models.conversation import ConversationMessage, MessageDirection
from api.security.hashing import hash_password
from api.security.token import create_access_token
from api.services.bot_settings_service import (
    get_or_create_bot_settings,
    update_bot_settings,
    set_bot_pause_state,
)
from api.services.whatsapp import _PROCESSED_MESSAGE_IDS


def sign_payload(payload: dict, secret) -> tuple[bytes, str]:
    """Serializes payload and calculates X-Hub-Signature-256 header."""
    secret_val = secret.get_secret_value() if hasattr(secret, "get_secret_value") else str(secret)
    raw_bytes = json.dumps(payload).encode("utf-8")
    sig = hmac.new(secret_val.encode("utf-8"), raw_bytes, hashlib.sha256).hexdigest()
    return raw_bytes, f"sha256={sig}"


def make_whatsapp_payload(
    message_id: str,
    from_phone: str = "919876543210",
    text_body: str = "Namaste",
    contact_name: str = "Aarav Sharma",
    msg_type: str = "text",
) -> dict:
    """Constructs a standard Meta WhatsApp Cloud API webhook message payload."""
    msg_obj = {
        "from": from_phone,
        "id": message_id,
        "timestamp": "1710000000",
        "type": msg_type,
    }
    if msg_type == "text":
        msg_obj["text"] = {"body": text_body}

    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "123456789",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15551234567",
                                "phone_number_id": "100000000000000",
                            },
                            "contacts": [
                                {
                                    "profile": {"name": contact_name},
                                    "wa_id": from_phone,
                                }
                            ],
                            "messages": [msg_obj],
                        }
                    }
                ],
            }
        ],
    }


@pytest_asyncio.fixture
async def super_admin(db_session: AsyncSession) -> AdminUser:
    admin = AdminUser(
        username="super_ctrl",
        email="super_ctrl@astrology.internal",
        password_hash=hash_password("SuperSecretP@ss123"),
        role=AdminRole.SUPER_ADMIN,
        is_active=True,
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin


@pytest_asyncio.fixture
async def support_admin(db_session: AsyncSession) -> AdminUser:
    admin = AdminUser(
        username="support_ctrl",
        email="support_ctrl@astrology.internal",
        password_hash=hash_password("SupportSecretP@ss123"),
        role=AdminRole.SUPPORT,
        is_active=True,
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin


@pytest.mark.asyncio
async def test_bot_settings_service_crud_and_validation(db_session: AsyncSession, super_admin: AdminUser):
    """Tests bot settings initialization, updates, validation, and audit logging."""
    # 1. Initialization
    settings = await get_or_create_bot_settings(db_session)
    assert settings.key == "default"
    assert settings.is_paused is False
    assert settings.maintenance_mode is False
    assert settings.welcome_message == DEFAULT_WELCOME_MESSAGE

    # 2. Update with valid custom text
    updated = await update_bot_settings(
        session=db_session,
        admin=super_admin,
        update_data={
            "welcome_message": "Hello and welcome to custom astrology!",
            "horoscope_intro": "Today's cosmic forecast:",
        },
        ip_address="127.0.0.1",
    )
    assert updated.welcome_message == "Hello and welcome to custom astrology!"
    assert updated.horoscope_intro == "Today's cosmic forecast:"
    assert updated.updated_by == super_admin.username

    # Verify audit event
    audit_stmt = select(AuditEvent).where(
        AuditEvent.action == "BOT_SETTINGS_UPDATE",
        AuditEvent.target_id == "default",
    )
    audit = (await db_session.execute(audit_stmt)).scalars().first()
    assert audit is not None
    assert "welcome_message" in audit.details["updated_fields"]

    # 3. Reject empty welcome message
    with pytest.raises(ValueError, match="cannot be empty"):
        await update_bot_settings(
            session=db_session,
            admin=super_admin,
            update_data={"welcome_message": "   "},
        )

    # 4. Toggle pause and maintenance state
    paused = await set_bot_pause_state(
        session=db_session,
        admin=super_admin,
        is_paused=True,
        maintenance_mode=True,
        ip_address="127.0.0.1",
    )
    assert paused.is_paused is True
    assert paused.maintenance_mode is True

    # Verify pause audit
    pause_audit = (
        await db_session.execute(
            select(AuditEvent).where(AuditEvent.action == "BOT_PAUSE")
        )
    ).scalars().first()
    assert pause_audit is not None
    assert pause_audit.details["is_paused"] is True


@pytest.mark.asyncio
async def test_bot_control_endpoints_and_rbac(
    client: AsyncClient,
    db_session: AsyncSession,
    super_admin: AdminUser,
    support_admin: AdminUser,
):
    """Tests REST endpoints for bot settings and controls with RBAC enforcement."""
    super_token = create_access_token(
        admin_id=str(super_admin.id),
        username=super_admin.username,
        role=super_admin.role.value,
        permissions=super_admin.get_permissions(),
    )
    support_token = create_access_token(
        admin_id=str(support_admin.id),
        username=support_admin.username,
        role=support_admin.role.value,
        permissions=support_admin.get_permissions(),
    )

    super_headers = {"Authorization": f"Bearer {super_token}"}
    support_headers = {"Authorization": f"Bearer {support_token}"}

    # 1. GET /settings - Allowed for both super_admin and support
    resp_super = await client.get("/api/v1/admin/control/settings", headers=super_headers)
    assert resp_super.status_code == 200
    assert resp_super.json()["key"] == "default"

    resp_support = await client.get("/api/v1/admin/control/settings", headers=support_headers)
    assert resp_support.status_code == 200

    # 2. PUT /settings - Allowed for super_admin ('settings:write'), Forbidden for support
    put_payload = {"welcome_message": "Super Admin customized welcome message."}
    resp_put_forbidden = await client.put(
        "/api/v1/admin/control/settings",
        json=put_payload,
        headers=support_headers,
    )
    assert resp_put_forbidden.status_code == 403

    resp_put_ok = await client.put(
        "/api/v1/admin/control/settings",
        json=put_payload,
        headers=super_headers,
    )
    assert resp_put_ok.status_code == 200
    assert resp_put_ok.json()["welcome_message"] == "Super Admin customized welcome message."

    # 3. POST /bot/pause - Allowed for super_admin ('bot:control'), Forbidden for support
    resp_pause_forbidden = await client.post(
        "/api/v1/admin/control/bot/pause",
        json={"maintenance_mode": False},
        headers=support_headers,
    )
    assert resp_pause_forbidden.status_code == 403

    resp_pause_ok = await client.post(
        "/api/v1/admin/control/bot/pause",
        json={"maintenance_mode": False},
        headers=super_headers,
    )
    assert resp_pause_ok.status_code == 200
    assert resp_pause_ok.json()["is_paused"] is True
    assert resp_pause_ok.json()["maintenance_mode"] is False

    # 4. POST /bot/resume
    resp_resume_ok = await client.post(
        "/api/v1/admin/control/bot/resume",
        headers=super_headers,
    )
    assert resp_resume_ok.status_code == 200
    assert resp_resume_ok.json()["is_paused"] is False


@pytest.mark.asyncio
async def test_webhook_bot_paused_behavior(
    client: AsyncClient,
    db_session: AsyncSession,
    super_admin: AdminUser,
):
    """Tests that a paused bot acknowledges webhooks, records messages, suppresses replies, and deduplicates."""
    _PROCESSED_MESSAGE_IDS.clear()

    # Pause bot (without maintenance mode)
    await set_bot_pause_state(
        session=db_session,
        admin=super_admin,
        is_paused=True,
        maintenance_mode=False,
    )

    msg_id = f"wamid_paused_{uuid.uuid4().hex[:8]}"
    payload = make_whatsapp_payload(message_id=msg_id, from_phone="919999900001", text_body="Hello paused bot")

    # Send inbound webhook
    settings = get_settings()
    raw_b, sig = sign_payload(payload, settings.WHATSAPP_APP_SECRET)
    resp = await client.post(
        "/api/v1/webhook/whatsapp",
        content=raw_b,
        headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "bot_paused"

    # Inbound message must be securely recorded
    inbound_stmt = select(ConversationMessage).where(
        ConversationMessage.whatsapp_message_id == msg_id,
        ConversationMessage.direction == MessageDirection.INBOUND,
    )
    inbound_record = (await db_session.execute(inbound_stmt)).scalars().first()
    assert inbound_record is not None
    assert inbound_record.get_content() == "Hello paused bot"

    # No outbound message should be generated
    outbound_stmt = select(ConversationMessage).where(
        ConversationMessage.conversation_id == inbound_record.conversation_id,
        ConversationMessage.direction == MessageDirection.OUTBOUND,
    )
    outbound_count = len((await db_session.execute(outbound_stmt)).scalars().all())
    assert outbound_count == 0

    # Retrying the same webhook message must be deduplicated
    retry_resp = await client.post(
        "/api/v1/webhook/whatsapp",
        content=raw_b,
        headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"},
    )
    assert retry_resp.status_code == 200
    assert retry_resp.json()["status"] == "duplicate_ignored"


@pytest.mark.asyncio
async def test_webhook_maintenance_mode_behavior(
    client: AsyncClient,
    db_session: AsyncSession,
    super_admin: AdminUser,
):
    """Tests that maintenance mode sends the configured maintenance reply and prevents duplicate replies."""
    _PROCESSED_MESSAGE_IDS.clear()

    custom_maint_text = "Scheduled calculation upgrade in progress. Back shortly! 🕉️"
    await update_bot_settings(
        session=db_session,
        admin=super_admin,
        update_data={"maintenance_message": custom_maint_text},
    )
    await set_bot_pause_state(
        session=db_session,
        admin=super_admin,
        is_paused=True,
        maintenance_mode=True,
    )

    msg_id = f"wamid_maint_{uuid.uuid4().hex[:8]}"
    payload = make_whatsapp_payload(message_id=msg_id, from_phone="919999900002", text_body="Is the bot working?")

    settings = get_settings()
    raw_b, sig = sign_payload(payload, settings.WHATSAPP_APP_SECRET)
    resp = await client.post(
        "/api/v1/webhook/whatsapp",
        content=raw_b,
        headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "maintenance_mode_replied"

    # Outbound maintenance message must be recorded
    out_stmt = select(ConversationMessage).where(
        ConversationMessage.direction == MessageDirection.OUTBOUND,
    )
    out_msgs = (await db_session.execute(out_stmt)).scalars().all()
    assert any(custom_maint_text in m.get_content() for m in out_msgs)

    # Retry must be deduplicated and not send another maintenance reply
    retry_resp = await client.post(
        "/api/v1/webhook/whatsapp",
        content=raw_b,
        headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"},
    )
    assert retry_resp.status_code == 200
    assert retry_resp.json()["status"] == "duplicate_ignored"


@pytest.mark.asyncio
async def test_webhook_custom_messages_delivered(
    client: AsyncClient,
    db_session: AsyncSession,
    super_admin: AdminUser,
):
    """Tests that configured custom welcome and fallback messages are delivered by the active bot."""
    _PROCESSED_MESSAGE_IDS.clear()

    # Ensure bot is unpaused
    await set_bot_pause_state(
        session=db_session,
        admin=super_admin,
        is_paused=False,
        maintenance_mode=False,
    )

    custom_welcome = "🌟 Welcome to Jyotish Divine! Reply YES to begin your sacred reading."
    custom_fallback = "🌟 Need help? You can ask for kundli, daily horoscope, or dasha."

    await update_bot_settings(
        session=db_session,
        admin=super_admin,
        update_data={
            "welcome_message": custom_welcome,
            "fallback_message": custom_fallback,
        },
    )

    # 1. New user arrives -> gets custom welcome message
    msg_id_1 = f"wamid_custom_{uuid.uuid4().hex[:8]}"
    payload1 = make_whatsapp_payload(message_id=msg_id_1, from_phone="919999900003", text_body="Hi")

    settings = get_settings()
    raw_b1, sig1 = sign_payload(payload1, settings.WHATSAPP_APP_SECRET)
    resp1 = await client.post(
        "/api/v1/webhook/whatsapp",
        content=raw_b1,
        headers={"X-Hub-Signature-256": sig1, "Content-Type": "application/json"},
    )
    assert resp1.status_code == 200
    assert resp1.json()["status"] == "success"

    out_stmt = select(ConversationMessage).where(
        ConversationMessage.direction == MessageDirection.OUTBOUND,
    )
    out_msgs = (await db_session.execute(out_stmt)).scalars().all()
    assert any(custom_welcome == m.get_content() for m in out_msgs)
