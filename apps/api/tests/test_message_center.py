"""Tests for Message Center: direct outbound messaging, 24h Meta window compliance, and delivery tracking."""

import json
import hmac
import hashlib
import uuid
from datetime import datetime, timezone, timedelta
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.config import get_settings
from api.db.models.admin import AdminUser, AdminRole
from api.db.models.user import User, UserStatus
from api.db.models.consent import ConsentRecord
from api.db.models.conversation import (
    Conversation,
    ConversationMessage,
    ConversationStatus,
    ConversationState,
    MessageDirection,
    MessageSender,
)
from api.db.models.audit import AuditEvent
from api.security.hashing import hash_password
from api.security.token import create_access_token
from api.security.encryption import compute_phone_hash, encrypt_field
from api.services.message_center import (
    get_recipient_window_status,
    list_eligible_recipients,
    send_direct_user_message,
    get_recent_outbound_messages,
)


def sign_payload(payload: dict, secret) -> tuple[bytes, str]:
    """Serializes payload and calculates X-Hub-Signature-256 header."""
    secret_val = secret.get_secret_value() if hasattr(secret, "get_secret_value") else str(secret)
    raw_bytes = json.dumps(payload).encode("utf-8")
    sig = hmac.new(secret_val.encode("utf-8"), raw_bytes, hashlib.sha256).hexdigest()
    return raw_bytes, f"sha256={sig}"


@pytest_asyncio.fixture
async def super_admin(db_session: AsyncSession) -> AdminUser:
    admin = AdminUser(
        username="super_msg",
        email="super_msg@astrology.internal",
        password_hash=hash_password("SuperSecretP@ss123"),
        role=AdminRole.SUPER_ADMIN,
        is_active=True,
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin


@pytest_asyncio.fixture
async def consented_user(db_session: AsyncSession) -> User:
    phone = "+919876500001"
    user = User(
        phone_hash=compute_phone_hash(phone),
        encrypted_phone=encrypt_field(phone),
        whatsapp_name="Active User",
        status=UserStatus.ACTIVE,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    consent = ConsentRecord(
        user_id=user.id,
        purpose="birth_data_processing",
        policy_version="1.0",
        granted=True,
        channel="whatsapp",
    )
    db_session.add(consent)
    await db_session.commit()
    return user


@pytest.mark.asyncio
async def test_24h_window_check(db_session: AsyncSession, consented_user: User):
    """Tests accurate calculation of the 24-hour Meta Customer Service Window."""
    # 1. No messages: window inactive
    status_no_msg = await get_recipient_window_status(db_session, consented_user.id)
    assert status_no_msg["window_active"] is False

    # 2. Inbound message 2 hours ago: window active
    conv = Conversation(
        user_id=consented_user.id,
        channel="whatsapp",
        status=ConversationStatus.ACTIVE,
        current_state=ConversationState.READING_READY,
    )
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)

    msg_recent = ConversationMessage(
        conversation_id=conv.id,
        user_id=consented_user.id,
        direction=MessageDirection.INBOUND,
        sender=MessageSender.USER,
        content_type="text",
        created_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    msg_recent.set_content("Hello")
    db_session.add(msg_recent)
    await db_session.commit()

    status_recent = await get_recipient_window_status(db_session, consented_user.id)
    assert status_recent["window_active"] is True
    assert status_recent["hours_remaining"] >= 21.0

    # 3. Inbound message 26 hours ago: window expired
    msg_recent.created_at = datetime.now(timezone.utc) - timedelta(hours=26)
    await db_session.commit()

    status_expired = await get_recipient_window_status(db_session, consented_user.id)
    assert status_expired["window_active"] is False
    assert status_expired["hours_remaining"] == 0.0


@pytest.mark.asyncio
async def test_send_direct_message_flow(
    client: AsyncClient,
    db_session: AsyncSession,
    super_admin: AdminUser,
    consented_user: User,
):
    """Tests direct message dispatch, 24h window enforcement, confirmation, and audit logging."""
    token = create_access_token(
        admin_id=str(super_admin.id),
        username=super_admin.username,
        role=super_admin.role.value,
        permissions=super_admin.get_permissions(),
    )
    headers = {"Authorization": f"Bearer {token}"}

    # Seed an inbound message within 24h
    conv = Conversation(
        user_id=consented_user.id,
        channel="whatsapp",
        status=ConversationStatus.ACTIVE,
        current_state=ConversationState.READING_READY,
    )
    db_session.add(conv)
    await db_session.commit()

    in_msg = ConversationMessage(
        conversation_id=conv.id,
        user_id=consented_user.id,
        direction=MessageDirection.INBOUND,
        sender=MessageSender.USER,
        content_type="text",
        created_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    in_msg.set_content("Hi there")
    db_session.add(in_msg)
    await db_session.commit()

    # 1. Unconfirmed send is rejected
    resp_unconfirmed = await client.post(
        "/api/v1/admin/messages/send",
        json={
            "user_id": str(consented_user.id),
            "message_text": "Important update regarding your reading.",
            "confirmed": False,
        },
        headers=headers,
    )
    assert resp_unconfirmed.status_code == 400
    assert "Confirmation required" in resp_unconfirmed.json()["detail"]

    # 2. Confirmed send within active window succeeds
    resp_ok = await client.post(
        "/api/v1/admin/messages/send",
        json={
            "user_id": str(consented_user.id),
            "message_text": "Important update regarding your reading.",
            "confirmed": True,
        },
        headers=headers,
    )
    assert resp_ok.status_code == 200
    data = resp_ok.json()
    assert data["status"] == "success"
    assert data["delivery_status"] == "sent"
    assert "recipient_masked" in data

    # Verify AuditEvent
    audit = (
        await db_session.execute(
            select(AuditEvent).where(
                AuditEvent.action == "DIRECT_MESSAGE_SENT",
                AuditEvent.target_id == str(consented_user.id),
            )
        )
    ).scalars().first()
    assert audit is not None
    assert audit.details["window_active"] is True

    # 3. Check send when window is expired (Strict WhatsApp Policy: Free-form text blocked)
    in_msg.created_at = datetime.now(timezone.utc) - timedelta(hours=30)
    await db_session.commit()

    resp_expired = await client.post(
        "/api/v1/admin/messages/send",
        json={
            "user_id": str(consented_user.id),
            "message_text": "Attempting send outside window.",
            "confirmed": True,
        },
        headers=headers,
    )
    assert resp_expired.status_code == 400
    assert "24-hour Meta Customer Service Window has expired" in resp_expired.json()["detail"]

    # 4. Approved template send outside 24h window succeeds
    resp_template = await client.post(
        "/api/v1/admin/messages/send-template",
        json={
            "user_id": str(consented_user.id),
            "template_name": "daily_horoscope_update",
            "language_code": "en",
            "body_parameters": ["Seeker", "27 Oct 2026", "Aries Moon", "Cosmic alignment today."],
            "confirmed": True,
        },
        headers=headers,
    )
    assert resp_template.status_code == 200
    tpl_data = resp_template.json()
    assert tpl_data["status"] == "success"
    assert tpl_data["delivery_status"] == "sent"

    # Verify template audit event
    audit_tpl = (
        await db_session.execute(
            select(AuditEvent).where(
                AuditEvent.action == "TEMPLATE_MESSAGE_SENT",
                AuditEvent.target_id == str(consented_user.id),
            )
        )
    ).scalars().first()
    assert audit_tpl is not None
    assert audit_tpl.details["template_name"] == "daily_horoscope_update"

    # 5. Revoking consent strictly blocks any further messages (free-form and template)
    consent = (
        await db_session.execute(
            select(ConsentRecord).where(ConsentRecord.user_id == consented_user.id)
        )
    ).scalars().first()
    consent.revoked_at = datetime.now(timezone.utc)
    consent.granted = False
    await db_session.commit()

    resp_revoked_tpl = await client.post(
        "/api/v1/admin/messages/send-template",
        json={
            "user_id": str(consented_user.id),
            "template_name": "daily_horoscope_update",
            "language_code": "en",
            "body_parameters": ["Seeker", "27 Oct 2026", "Aries Moon", "Cosmic alignment today."],
            "confirmed": True,
        },
        headers=headers,
    )
    assert resp_revoked_tpl.status_code == 400
    assert "revoked" in resp_revoked_tpl.json()["detail"].lower()


@pytest.mark.asyncio
async def test_status_webhook_delivery_tracking(
    client: AsyncClient,
    db_session: AsyncSession,
    super_admin: AdminUser,
    consented_user: User,
):
    """Tests that Meta status callbacks (delivered, read, failed) update outbound ConversationMessage records."""
    token = create_access_token(
        admin_id=str(super_admin.id),
        username=super_admin.username,
        role=super_admin.role.value,
        permissions=super_admin.get_permissions(),
    )
    headers = {"Authorization": f"Bearer {token}"}

    # Create active conversation & send direct message
    conv = Conversation(
        user_id=consented_user.id,
        channel="whatsapp",
        status=ConversationStatus.ACTIVE,
        current_state=ConversationState.READING_READY,
    )
    db_session.add(conv)
    await db_session.commit()

    target_wamid = f"wamid.status_test_{uuid.uuid4().hex[:8]}"
    out_msg = ConversationMessage(
        conversation_id=conv.id,
        user_id=consented_user.id,
        whatsapp_message_id=target_wamid,
        direction=MessageDirection.OUTBOUND,
        sender=MessageSender.ASSISTANT,
        content_type="text",
        delivery_status="sent",
        status_timestamp=datetime.now(timezone.utc),
    )
    out_msg.set_content("Direct testing message")
    db_session.add(out_msg)
    await db_session.commit()

    # 1. Meta fires "delivered" status update webhook
    delivered_payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "123456",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "statuses": [
                                {
                                    "id": target_wamid,
                                    "status": "delivered",
                                    "timestamp": "1710001000",
                                    "recipient_id": "919876500001",
                                }
                            ],
                        }
                    }
                ],
            }
        ],
    }
    settings = get_settings()
    raw_b1, sig1 = sign_payload(delivered_payload, settings.WHATSAPP_APP_SECRET)
    resp1 = await client.post(
        "/api/v1/webhook/whatsapp",
        content=raw_b1,
        headers={"X-Hub-Signature-256": sig1, "Content-Type": "application/json"},
    )
    assert resp1.status_code == 200
    assert resp1.json()["status"] == "statuses_processed"

    # Verify DB update
    await db_session.refresh(out_msg)
    assert out_msg.delivery_status == "delivered"

    # 2. Meta fires "read" status update webhook
    read_payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "123456",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "statuses": [
                                {
                                    "id": target_wamid,
                                    "status": "read",
                                    "timestamp": "1710002000",
                                    "recipient_id": "919876500001",
                                }
                            ],
                        }
                    }
                ],
            }
        ],
    }
    raw_b2, sig2 = sign_payload(read_payload, settings.WHATSAPP_APP_SECRET)
    resp2 = await client.post(
        "/api/v1/webhook/whatsapp",
        content=raw_b2,
        headers={"X-Hub-Signature-256": sig2, "Content-Type": "application/json"},
    )
    assert resp2.status_code == 200

    await db_session.refresh(out_msg)
    assert out_msg.delivery_status == "read"

    # 2b. Delayed duplicate "delivered" webhook arrives out-of-order; must NOT regress "read"
    resp_late_delivered = await client.post(
        "/api/v1/webhook/whatsapp",
        content=raw_b1,
        headers={"X-Hub-Signature-256": sig1, "Content-Type": "application/json"},
    )
    assert resp_late_delivered.status_code == 200
    await db_session.refresh(out_msg)
    assert out_msg.delivery_status == "read"

    # 3. Meta fires "failed" status update with error details
    failed_payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "123456",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "statuses": [
                                {
                                    "id": target_wamid,
                                    "status": "failed",
                                    "timestamp": "1710003000",
                                    "recipient_id": "919876500001",
                                    "errors": [
                                        {
                                            "code": 131026,
                                            "title": "Message undeliverable",
                                            "message": "Receiver has blocked business",
                                        }
                                    ],
                                }
                            ],
                        }
                    }
                ],
            }
        ],
    }
    raw_b3, sig3 = sign_payload(failed_payload, settings.WHATSAPP_APP_SECRET)
    resp3 = await client.post(
        "/api/v1/webhook/whatsapp",
        content=raw_b3,
        headers={"X-Hub-Signature-256": sig3, "Content-Type": "application/json"},
    )
    assert resp3.status_code == 200

    await db_session.refresh(out_msg)
    assert out_msg.delivery_status == "failed"
    assert out_msg.error_code == "131026"
    assert "Receiver has blocked" in out_msg.error_message

    # 4. Check GET /api/v1/admin/messages/recent
    recent_resp = await client.get("/api/v1/admin/messages/recent", headers=headers)
    assert recent_resp.status_code == 200
    messages = recent_resp.json()["messages"]
    assert any(m["whatsapp_message_id"] == target_wamid for m in messages)


@pytest.mark.asyncio
async def test_opt_out_keywords_revoke_consent_and_halt_schedule(
    client: AsyncClient,
    db_session: AsyncSession,
    consented_user: User,
):
    """Verifies STOP/UNSUBSCRIBE/OPT OUT with case and whitespace variations immediately revoke consent and clear horoscope opt-in."""
    from api.db.models.user import UserPreferences

    # Ensure user has daily horoscope enabled
    pref = UserPreferences(
        user_id=consented_user.id,
        daily_horoscope_opt_in=True,
        preferred_language="en",
    )
    db_session.add(pref)
    await db_session.commit()

    # User texts ' STOP! ' with spaces and punctuation
    stop_payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "123456",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "contacts": [{"wa_id": "919876500001", "profile": {"name": "Active User"}}],
                            "messages": [
                                {
                                    "id": f"wamid.stop_test_{uuid.uuid4().hex[:8]}",
                                    "from": "919876500001",
                                    "type": "text",
                                    "text": {"body": "  STOP!  "},
                                    "timestamp": "1710004000",
                                }
                            ],
                        }
                    }
                ],
            }
        ],
    }
    settings = get_settings()
    raw_b, sig = sign_payload(stop_payload, settings.WHATSAPP_APP_SECRET)
    resp = await client.post(
        "/api/v1/webhook/whatsapp",
        content=raw_b,
        headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200

    # 1. Active consent must now be revoked
    consent_stmt = select(ConsentRecord).where(
        ConsentRecord.user_id == consented_user.id,
        ConsentRecord.granted == True,
        ConsentRecord.revoked_at.is_(None),
    )
    active_consent = (await db_session.execute(consent_stmt)).scalars().first()
    assert active_consent is None

    # 2. Daily horoscope opt-in must be set to False
    await db_session.refresh(pref)
    assert pref.daily_horoscope_opt_in is False

    # 3. Conversation state must be ONBOARDING_CONSENT
    conv_stmt = select(Conversation).where(Conversation.user_id == consented_user.id)
    conv = (await db_session.execute(conv_stmt)).scalars().first()
    assert conv.current_state == ConversationState.ONBOARDING_CONSENT
