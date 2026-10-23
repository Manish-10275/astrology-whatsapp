"""Tests for WhatsApp Cloud API Webhook, Meta challenge verification, HMAC signatures, and multi-turn conversation flow."""

import json
import hmac
import hashlib
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.config import get_settings
from api.db.models.user import User, UserPreferences, UserStatus, AstrologySystemEnum
from api.db.models.consent import ConsentRecord
from api.db.models.birth_profile import BirthProfile, TimeUncertaintyEnum
from api.db.models.conversation import (
    Conversation,
    ConversationMessage,
    ConversationStatus,
    ConversationState,
    MessageDirection,
    MessageSender,
)
from api.security.encryption import compute_phone_hash, decrypt_field
from api.services.whatsapp import _PROCESSED_MESSAGE_IDS


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
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }


def sign_payload(payload: dict, secret) -> tuple[bytes, str]:
    """Serializes payload and calculates X-Hub-Signature-256 header."""
    secret_val = secret.get_secret_value() if hasattr(secret, "get_secret_value") else str(secret)
    raw_bytes = json.dumps(payload).encode("utf-8")
    sig = hmac.new(secret_val.encode("utf-8"), raw_bytes, hashlib.sha256).hexdigest()
    return raw_bytes, f"sha256={sig}"


@pytest.fixture(autouse=True)
def reset_message_dedup_cache():
    """Clears the in-memory message ID deduplication set between test cases."""
    _PROCESSED_MESSAGE_IDS.clear()
    yield
    _PROCESSED_MESSAGE_IDS.clear()


# ── 1. Webhook Challenge Verification (GET) ───────────────────────────────────

@pytest.mark.asyncio
async def test_meta_challenge_verification_success(client: AsyncClient):
    """Verify GET challenge returns 200 with raw challenge text when verify_token matches."""
    settings = get_settings()
    token = settings.WHATSAPP_VERIFY_TOKEN.get_secret_value()
    challenge = "9876543210"

    response = await client.get(
        "/api/v1/webhook/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": token,
            "hub.challenge": challenge,
        },
    )

    assert response.status_code == 200
    assert response.text == challenge


@pytest.mark.asyncio
async def test_meta_challenge_verification_invalid_token(client: AsyncClient):
    """Verify GET challenge fails with 403 Forbidden when verify_token is invalid."""
    response = await client.get(
        "/api/v1/webhook/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong_invalid_token",
            "hub.challenge": "12345",
        },
    )

    assert response.status_code == 403
    assert "Verification token mismatch" in response.json()["detail"]


@pytest.mark.asyncio
async def test_meta_challenge_verification_missing_mode(client: AsyncClient):
    """Verify GET challenge fails with 403 when hub.mode is not subscribe."""
    settings = get_settings()
    token = settings.WHATSAPP_VERIFY_TOKEN.get_secret_value()
    response = await client.get(
        "/api/v1/webhook/whatsapp",
        params={
            "hub.mode": "other",
            "hub.verify_token": token,
            "hub.challenge": "12345",
        },
    )

    assert response.status_code == 403


# ── 2. Webhook Signature Verification (POST) ─────────────────────────────────

@pytest.mark.asyncio
async def test_post_webhook_missing_signature_rejected(client: AsyncClient):
    """Verify POST webhook without X-Hub-Signature-256 is rejected with 403."""
    payload = make_whatsapp_payload("wamid.test_01")
    raw_body = json.dumps(payload).encode("utf-8")

    response = await client.post(
        "/api/v1/webhook/whatsapp",
        content=raw_body,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 403
    assert "Invalid request signature" in response.json()["detail"]


@pytest.mark.asyncio
async def test_post_webhook_tampered_signature_rejected(client: AsyncClient):
    """Verify POST webhook with tampered body or forged signature is rejected with 403."""
    settings = get_settings()
    payload = make_whatsapp_payload("wamid.test_02")
    raw_body, _ = sign_payload(payload, settings.WHATSAPP_APP_SECRET)

    # Supply an invalid signature
    bad_signature = "sha256=0000000000000000000000000000000000000000000000000000000000000000"

    response = await client.post(
        "/api/v1/webhook/whatsapp",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": bad_signature,
        },
    )

    assert response.status_code == 403
    assert "Invalid request signature" in response.json()["detail"]


# ── 3. Webhook Deduplication / Idempotency ────────────────────────────────────

@pytest.mark.asyncio
async def test_post_webhook_message_deduplication(client: AsyncClient, db_session: AsyncSession):
    """Verify duplicate message deliveries from Meta retries are ignored idempotently."""
    settings = get_settings()
    msg_id = "wamid.dedup_test_999"
    payload = make_whatsapp_payload(message_id=msg_id, text_body="Hello")
    raw_body, signature = sign_payload(payload, settings.WHATSAPP_APP_SECRET)
    headers = {
        "Content-Type": "application/json",
        "X-Hub-Signature-256": signature,
    }

    # First delivery: processed successfully
    res1 = await client.post("/api/v1/webhook/whatsapp", content=raw_body, headers=headers)
    assert res1.status_code == 200
    assert res1.json()["status"] == "success"

    # Second delivery with identical message ID: ignored via deduplication
    res2 = await client.post("/api/v1/webhook/whatsapp", content=raw_body, headers=headers)
    assert res2.status_code == 200
    assert res2.json()["status"] == "duplicate_ignored"

    # Verify in DB that only one inbound message with this message ID was stored
    stmt = select(ConversationMessage).where(ConversationMessage.whatsapp_message_id == msg_id)
    records = (await db_session.execute(stmt)).scalars().all()
    assert len(records) == 1


# ── 4. Complete Multi-Turn Conversation Flow ──────────────────────────────────

@pytest.mark.asyncio
async def test_complete_multi_turn_onboarding_and_reading_flow(
    client: AsyncClient, db_session: AsyncSession
):
    """Verify end-to-end multi-turn conversation flow:
    Turn 1: Greeting -> Consent request
    Turn 2: Consent granted ('YES') -> Prompt for Birth Date
    Turn 3: Date provided ('1995-10-24') -> Prompt for Birth Time
    Turn 4: Time provided ('14:30') -> Prompt for Birth Place
    Turn 5: Place provided ('New Delhi, India') -> Deterministic Chart & Vedic Reading generated!
    """
    settings = get_settings()
    phone = "919876543210"
    user_name = "Vikram Aditya"

    async def send_turn(msg_id: str, text: str) -> dict:
        payload = make_whatsapp_payload(
            message_id=msg_id,
            from_phone=phone,
            text_body=text,
            contact_name=user_name,
        )
        raw_body, signature = sign_payload(payload, settings.WHATSAPP_APP_SECRET)
        resp = await client.post(
            "/api/v1/webhook/whatsapp",
            content=raw_body,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature},
        )
        assert resp.status_code == 200
        return resp.json()

    # ── Turn 1: Greeting ──
    turn1 = await send_turn("wamid.flow_01", "Hello, I want my astrology reading")
    assert turn1["status"] == "success"

    # Verify user created in DB
    phone_hash = compute_phone_hash(f"+{phone}")
    user = (await db_session.execute(select(User).where(User.phone_hash == phone_hash))).scalars().first()
    assert user is not None
    assert user.whatsapp_name == user_name

    # Verify conversation state is ONBOARDING_CONSENT
    conv = (await db_session.execute(select(Conversation).where(Conversation.user_id == user.id))).scalars().first()
    assert conv is not None
    assert conv.current_state == ConversationState.ONBOARDING_CONSENT

    # Verify outbound reply asks for consent
    outbound_1 = (
        await db_session.execute(
            select(ConversationMessage).where(
                ConversationMessage.conversation_id == conv.id,
                ConversationMessage.direction == MessageDirection.OUTBOUND,
            )
        )
    ).scalars().first()
    assert outbound_1 is not None
    assert "consent" in outbound_1.get_content().lower()

    # ── Turn 2: Affirmative Consent ('YES') ──
    turn2 = await send_turn("wamid.flow_02", "YES")
    assert turn2["status"] == "success"

    # Verify ConsentRecord created
    consent = (
        await db_session.execute(
            select(ConsentRecord).where(ConsentRecord.user_id == user.id, ConsentRecord.granted == True)
        )
    ).scalars().first()
    assert consent is not None
    assert consent.revoked_at is None

    # Verify conversation advanced to AWAITING_BIRTH_DATE
    await db_session.refresh(conv)
    assert conv.current_state == ConversationState.AWAITING_BIRTH_DATE

    # ── Turn 3: Birth Date Provided ──
    turn3 = await send_turn("wamid.flow_03", "1995-10-24")
    assert turn3["status"] == "success"

    await db_session.refresh(conv)
    assert conv.current_state == ConversationState.AWAITING_BIRTH_TIME
    assert conv.state_metadata.get("birth_date") == "1995-10-24"

    # ── Turn 4: Birth Time Provided ──
    turn4 = await send_turn("wamid.flow_04", "14:30")
    assert turn4["status"] == "success"

    await db_session.refresh(conv)
    assert conv.current_state == ConversationState.AWAITING_BIRTH_PLACE
    assert conv.state_metadata.get("birth_time") == "14:30:00"

    # ── Turn 5: Birth Place Provided (New Delhi, India) ──
    turn5 = await send_turn("wamid.flow_05", "New Delhi, India")
    assert turn5["status"] == "success"

    await db_session.refresh(conv)
    assert conv.current_state == ConversationState.READING_READY

    # Verify BirthProfile persisted with encrypted birth details
    profile = (
        await db_session.execute(
            select(BirthProfile).where(BirthProfile.user_id == user.id, BirthProfile.is_primary == True)
        )
    ).scalars().first()
    assert profile is not None
    details = profile.get_decrypted_details()
    assert details["birth_date"].isoformat() == "1995-10-24"
    assert details["birth_time"].strftime("%H:%M") == "14:30"
    assert "New Delhi" in details["location_name"]
    assert profile.time_uncertainty == TimeUncertaintyEnum.EXACT

    # Verify latest outbound message is the complete Kundli reading
    outbound_messages = (
        (
            await db_session.execute(
                select(ConversationMessage)
                .where(
                    ConversationMessage.conversation_id == conv.id,
                    ConversationMessage.direction == MessageDirection.OUTBOUND,
                )
                .order_by(ConversationMessage.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    latest_reading = outbound_messages[0].get_content()

    # Verify reading contains authentic astrological signatures grounded in deterministic calculation
    assert "Kundli" in latest_reading or "Vedic" in latest_reading or "Ascendant" in latest_reading
    assert "Ascendant" in latest_reading or "Lagna" in latest_reading
    assert "Moon" in latest_reading or "Chandra" in latest_reading


# ── 5. Unknown Birth Time Flow ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unknown_birth_time_flow(client: AsyncClient, db_session: AsyncSession):
    """Verify that when user specifies UNKNOWN birth time:
    - TimeUncertainty is preserved as UNKNOWN
    - Lagna and house placements are appropriately withheld
    - Moon and planetary sign placements remain accurate and grounded
    """
    settings = get_settings()
    phone = "919999888877"

    async def send_turn(msg_id: str, text: str):
        payload = make_whatsapp_payload(
            message_id=msg_id,
            from_phone=phone,
            text_body=text,
            contact_name="Pooja Sharma",
        )
        raw_body, signature = sign_payload(payload, settings.WHATSAPP_APP_SECRET)
        await client.post(
            "/api/v1/webhook/whatsapp",
            content=raw_body,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature},
        )

    await send_turn("wamid.unk_01", "Hi")
    await send_turn("wamid.unk_02", "YES")
    await send_turn("wamid.unk_03", "1992-08-18")
    await send_turn("wamid.unk_04", "UNKNOWN")
    await send_turn("wamid.unk_05", "Mumbai, India")

    phone_hash = compute_phone_hash(f"+{phone}")
    user = (await db_session.execute(select(User).where(User.phone_hash == phone_hash))).scalars().first()
    assert user is not None

    profile = (
        await db_session.execute(
            select(BirthProfile).where(BirthProfile.user_id == user.id, BirthProfile.is_primary == True)
        )
    ).scalars().first()
    assert profile is not None
    assert profile.time_uncertainty == TimeUncertaintyEnum.UNKNOWN

    # Check reading message contents
    conv = (await db_session.execute(select(Conversation).where(Conversation.user_id == user.id))).scalars().first()
    outbounds = (
        (
            await db_session.execute(
                select(ConversationMessage)
                .where(
                    ConversationMessage.conversation_id == conv.id,
                    ConversationMessage.direction == MessageDirection.OUTBOUND,
                )
                .order_by(ConversationMessage.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    latest_reading = outbounds[0].get_content()

    # Verify Lagna/houses withheld explanation is present
    assert "Withheld" in latest_reading or "UNKNOWN" in latest_reading or "withheld" in latest_reading.lower()
    assert "Moon" in latest_reading or "Chandra" in latest_reading


# ── 6. Consent Rejection & Revocation ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_consent_rejection(client: AsyncClient, db_session: AsyncSession):
    """Verify that declining consent does not store birth profiles and returns respectful guidance."""
    settings = get_settings()
    phone = "919111222333"

    async def send_msg(msg_id: str, text: str):
        payload = make_whatsapp_payload(message_id=msg_id, from_phone=phone, text_body=text)
        raw_body, signature = sign_payload(payload, settings.WHATSAPP_APP_SECRET)
        return await client.post(
            "/api/v1/webhook/whatsapp",
            content=raw_body,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature},
        )

    await send_msg("wamid.rej_01", "Hello")
    res = await send_msg("wamid.rej_02", "NO")
    assert res.status_code == 200

    phone_hash = compute_phone_hash(f"+{phone}")
    user = (await db_session.execute(select(User).where(User.phone_hash == phone_hash))).scalars().first()
    assert user is not None

    # No consent records granted
    consents = (
        (await db_session.execute(select(ConsentRecord).where(ConsentRecord.user_id == user.id)))
        .scalars()
        .all()
    )
    assert len(consents) == 0

    # No birth profiles created
    profiles = (
        (await db_session.execute(select(BirthProfile).where(BirthProfile.user_id == user.id)))
        .scalars()
        .all()
    )
    assert len(profiles) == 0


@pytest.mark.asyncio
async def test_consent_revocation_at_any_time(client: AsyncClient, db_session: AsyncSession):
    """Verify user can revoke consent at any time, marking consent record revoked and resetting state."""
    settings = get_settings()
    phone = "919555666777"

    async def send_msg(msg_id: str, text: str):
        payload = make_whatsapp_payload(message_id=msg_id, from_phone=phone, text_body=text)
        raw_body, signature = sign_payload(payload, settings.WHATSAPP_APP_SECRET)
        return await client.post(
            "/api/v1/webhook/whatsapp",
            content=raw_body,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature},
        )

    await send_msg("wamid.rev_01", "Hi")
    await send_msg("wamid.rev_02", "YES")
    # User revokes consent
    await send_msg("wamid.rev_03", "revoke consent")

    phone_hash = compute_phone_hash(f"+{phone}")
    user = (await db_session.execute(select(User).where(User.phone_hash == phone_hash))).scalars().first()
    assert user is not None

    # Consent marked revoked
    consent = (
        (await db_session.execute(select(ConsentRecord).where(ConsentRecord.user_id == user.id)))
        .scalars()
        .first()
    )
    assert consent is not None
    assert consent.revoked_at is not None

    # State reset to ONBOARDING_CONSENT
    conv = (await db_session.execute(select(Conversation).where(Conversation.user_id == user.id))).scalars().first()
    assert conv is not None
    assert conv.current_state == ConversationState.ONBOARDING_CONSENT


# ── 7. Encrypted Conversation Persistence at Rest ────────────────────────────

@pytest.mark.asyncio
async def test_encrypted_conversation_persistence_at_rest(
    client: AsyncClient, db_session: AsyncSession
):
    """Verify all conversation messages are stored encrypted in DB and cannot be read without decryption."""
    settings = get_settings()
    phone = "919444333222"
    secret_message = "Sensitive astrological query for testing encryption"

    payload = make_whatsapp_payload(
        message_id="wamid.sec_enc_01",
        from_phone=phone,
        text_body=secret_message,
    )
    raw_body, signature = sign_payload(payload, settings.WHATSAPP_APP_SECRET)
    await client.post(
        "/api/v1/webhook/whatsapp",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature},
    )

    phone_hash = compute_phone_hash(f"+{phone}")
    user = (await db_session.execute(select(User).where(User.phone_hash == phone_hash))).scalars().first()
    conv = (await db_session.execute(select(Conversation).where(Conversation.user_id == user.id))).scalars().first()

    # Query raw database record
    msg = (
        await db_session.execute(
            select(ConversationMessage).where(
                ConversationMessage.conversation_id == conv.id,
                ConversationMessage.direction == MessageDirection.INBOUND,
            )
        )
    ).scalars().first()

    assert msg is not None
    # 1. Plaintext must NOT appear in raw encrypted_content column
    assert secret_message not in msg.encrypted_content
    # 2. Must be prefixed with version tag (e.g., 'v1:')
    assert msg.encrypted_content.startswith("v1:")
    # 3. Decrypts cleanly with key
    assert msg.get_content() == secret_message


# ── 8. Unsupported Payload Handling ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_unsupported_media_message_handling(client: AsyncClient, db_session: AsyncSession):
    """Verify non-text media messages (image/audio) receive polite guidance without crashing."""
    settings = get_settings()
    payload = make_whatsapp_payload(
        message_id="wamid.media_01",
        from_phone="919777888999",
        msg_type="image",
    )
    raw_body, signature = sign_payload(payload, settings.WHATSAPP_APP_SECRET)

    res = await client.post(
        "/api/v1/webhook/whatsapp",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature},
    )

    assert res.status_code == 200
    assert res.json()["status"] == "unsupported_type_handled"
