"""Tests for extended astrological capabilities, system switching, dasha, panchang, compatibility, and multilingual flows."""

import json
import hmac
import hashlib
import pytest
from datetime import date, time
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.config import get_settings
from api.db.models.user import User, UserPreferences, UserStatus, AstrologySystemEnum
from api.db.models.consent import ConsentRecord
from api.db.models.birth_profile import BirthProfile, TimeUncertaintyEnum
from api.db.models.conversation import Conversation, ConversationMessage, ConversationState, ConversationStatus
from api.security.encryption import compute_phone_hash, encrypt_field
from api.services.whatsapp import _PROCESSED_MESSAGE_IDS
from api.services.astrology_service import detect_language, generate_astrology_reading, compute_astrology_chart


def make_payload(msg_id: str, text: str, phone: str = "919876543210") -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "123",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"display_phone_number": "15551234567", "phone_number_id": "1000"},
                            "contacts": [{"profile": {"name": "Test User"}, "wa_id": phone}],
                            "messages": [{"from": phone, "id": msg_id, "timestamp": "1710000000", "type": "text", "text": {"body": text}}],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }


def sign(payload: dict, secret) -> tuple[bytes, str]:
    secret_val = secret.get_secret_value() if hasattr(secret, "get_secret_value") else str(secret)
    raw = json.dumps(payload).encode("utf-8")
    sig = hmac.new(secret_val.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    return raw, f"sha256={sig}"


async def setup_consented_user_with_profile(db_session: AsyncSession, phone: str = "919876543210") -> User:
    """Helper to seed an active consented user with a primary birth profile."""
    _PROCESSED_MESSAGE_IDS.clear()
    phone_e164 = f"+{phone}"
    user = User(
        phone_hash=compute_phone_hash(phone_e164),
        encrypted_phone=encrypt_field(phone_e164),
        whatsapp_name="Arjun Sharma",
        status=UserStatus.ACTIVE
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    pref = UserPreferences(
        user_id=user.id,
        astrology_system=AstrologySystemEnum.VEDIC,
        preferred_language="en",
        auto_detect_language=True
    )
    db_session.add(pref)

    consent = ConsentRecord(
        user_id=user.id,
        purpose="birth_data_processing",
        policy_version="v1.0",
        channel="whatsapp",
        granted=True
    )
    db_session.add(consent)

    profile = BirthProfile(
        user_id=user.id,
        profile_label="Primary",
        is_primary=True,
        timezone_name="Asia/Kolkata",
        time_uncertainty=TimeUncertaintyEnum.EXACT
    )
    profile.set_birth_details(
        birth_date=date(1995, 10, 24),
        birth_time=time(14, 30),
        latitude=28.6139,
        longitude=77.2090,
        location_name="New Delhi, India"
    )
    db_session.add(profile)

    conv = Conversation(
        user_id=user.id,
        channel="whatsapp",
        status=ConversationStatus.ACTIVE,
        current_state=ConversationState.READING_READY,
        state_metadata={}
    )
    db_session.add(conv)
    await db_session.commit()
    return user


@pytest.mark.asyncio
async def test_system_selection_and_switching(client: AsyncClient, db_session: AsyncSession):
    """Tests switching between Vedic and Western astrology and verifying preferences update."""
    user = await setup_consented_user_with_profile(db_session, "919811111111")
    settings = get_settings()

    # Switch to Western
    p1 = make_payload("msg_switch_1", "Please switch to western astrology", "919811111111")
    raw1, sig1 = sign(p1, settings.WHATSAPP_APP_SECRET)
    resp1 = await client.post("/api/v1/webhook/whatsapp", content=raw1, headers={"X-Hub-Signature-256": sig1, "Content-Type": "application/json"})
    assert resp1.status_code == 200

    # Verify user preference is now WESTERN
    await db_session.refresh(user)
    pref_stmt = select(UserPreferences).where(UserPreferences.user_id == user.id)
    pref = (await db_session.execute(pref_stmt)).scalar_one()
    assert pref.astrology_system == AstrologySystemEnum.WESTERN

    # Switch back to Vedic
    p2 = make_payload("msg_switch_2", "switch to vedic", "919811111111")
    raw2, sig2 = sign(p2, settings.WHATSAPP_APP_SECRET)
    resp2 = await client.post("/api/v1/webhook/whatsapp", content=raw2, headers={"X-Hub-Signature-256": sig2, "Content-Type": "application/json"})
    assert resp2.status_code == 200

    await db_session.refresh(user)
    pref = (await db_session.execute(pref_stmt)).scalar_one()
    assert pref.astrology_system == AstrologySystemEnum.VEDIC


@pytest.mark.asyncio
async def test_on_demand_daily_horoscope(client: AsyncClient, db_session: AsyncSession):
    """Tests requesting daily horoscope on demand."""
    user = await setup_consented_user_with_profile(db_session, "919822222222")
    settings = get_settings()

    p = make_payload("msg_horo_1", "What is my daily horoscope today?", "919822222222")
    raw, sig = sign(p, settings.WHATSAPP_APP_SECRET)
    resp = await client.post("/api/v1/webhook/whatsapp", content=raw, headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"})
    assert resp.status_code == 200

    # Check the outbound message recorded
    msg_stmt = (
        select(ConversationMessage)
        .where(ConversationMessage.user_id == user.id, ConversationMessage.direction == "outbound")
        .order_by(ConversationMessage.created_at.desc())
    )
    last_msg = (await db_session.execute(msg_stmt)).scalars().first()
    assert last_msg is not None
    content = last_msg.get_decrypted_content()
    assert "Daily Horoscope" in content
    assert "Moon Sign" in content


@pytest.mark.asyncio
async def test_dasha_inquiry(client: AsyncClient, db_session: AsyncSession):
    """Tests querying current Vimshottari Dasha."""
    user = await setup_consented_user_with_profile(db_session, "919833333333")
    settings = get_settings()

    p = make_payload("msg_dasha_1", "Tell me my current mahadasha and antardasha", "919833333333")
    raw, sig = sign(p, settings.WHATSAPP_APP_SECRET)
    resp = await client.post("/api/v1/webhook/whatsapp", content=raw, headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"})
    assert resp.status_code == 200

    msg_stmt = (
        select(ConversationMessage)
        .where(ConversationMessage.user_id == user.id, ConversationMessage.direction == "outbound")
        .order_by(ConversationMessage.created_at.desc())
    )
    last_msg = (await db_session.execute(msg_stmt)).scalars().first()
    assert last_msg is not None
    content = last_msg.get_decrypted_content()
    assert "Vimshottari Dasha" in content or "विंशोत्तरी दशा" in content
    assert "Mahadasha" in content or "महादशा" in content
    assert "Antardasha" in content or "अंतर्दशा" in content


@pytest.mark.asyncio
async def test_transits_and_sade_sati_inquiry(client: AsyncClient, db_session: AsyncSession):
    """Tests querying planetary transits and Shani Sade Sati status."""
    user = await setup_consented_user_with_profile(db_session, "919844444444")
    settings = get_settings()

    p = make_payload("msg_transits_1", "Am I in Shani Sade Sati right now? What are my transits?", "919844444444")
    raw, sig = sign(p, settings.WHATSAPP_APP_SECRET)
    resp = await client.post("/api/v1/webhook/whatsapp", content=raw, headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"})
    assert resp.status_code == 200

    msg_stmt = (
        select(ConversationMessage)
        .where(ConversationMessage.user_id == user.id, ConversationMessage.direction == "outbound")
        .order_by(ConversationMessage.created_at.desc())
    )
    last_msg = (await db_session.execute(msg_stmt)).scalars().first()
    assert last_msg is not None
    content = last_msg.get_decrypted_content()
    assert "Sade Sati Status" in content
    assert "Transits" in content or "Gochara" in content


@pytest.mark.asyncio
async def test_panchang_inquiry(client: AsyncClient, db_session: AsyncSession):
    """Tests querying Vedic Panchang."""
    user = await setup_consented_user_with_profile(db_session, "919855555555")
    settings = get_settings()

    p = make_payload("msg_panchang_1", "Can you show today's panchang?", "919855555555")
    raw, sig = sign(p, settings.WHATSAPP_APP_SECRET)
    resp = await client.post("/api/v1/webhook/whatsapp", content=raw, headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"})
    assert resp.status_code == 200

    msg_stmt = (
        select(ConversationMessage)
        .where(ConversationMessage.user_id == user.id, ConversationMessage.direction == "outbound")
        .order_by(ConversationMessage.created_at.desc())
    )
    last_msg = (await db_session.execute(msg_stmt)).scalars().first()
    assert last_msg is not None
    content = last_msg.get_decrypted_content()
    assert "Tithi" in content or "तिथि" in content
    assert "Nakshatra" in content or "नक्षत्र" in content
    assert "Yoga" in content or "योग" in content


@pytest.mark.asyncio
async def test_multi_turn_compatibility_matching_flow(client: AsyncClient, db_session: AsyncSession):
    """Tests interactive 3-step partner birth data collection and Ashtakoota compatibility calculation."""
    user = await setup_consented_user_with_profile(db_session, "919866666666")
    settings = get_settings()

    # Step 1: Initiate compatibility
    p1 = make_payload("msg_compat_1", "I want to check compatibility with my partner", "919866666666")
    raw1, sig1 = sign(p1, settings.WHATSAPP_APP_SECRET)
    resp1 = await client.post("/api/v1/webhook/whatsapp", content=raw1, headers={"X-Hub-Signature-256": sig1, "Content-Type": "application/json"})
    assert resp1.status_code == 200

    # Step 2: Provide partner date
    p2 = make_payload("msg_compat_2", "1996-05-15", "919866666666")
    raw2, sig2 = sign(p2, settings.WHATSAPP_APP_SECRET)
    resp2 = await client.post("/api/v1/webhook/whatsapp", content=raw2, headers={"X-Hub-Signature-256": sig2, "Content-Type": "application/json"})
    assert resp2.status_code == 200

    # Step 3: Provide partner time
    p3 = make_payload("msg_compat_3", "14:30", "919866666666")
    raw3, sig3 = sign(p3, settings.WHATSAPP_APP_SECRET)
    resp3 = await client.post("/api/v1/webhook/whatsapp", content=raw3, headers={"X-Hub-Signature-256": sig3, "Content-Type": "application/json"})
    assert resp3.status_code == 200

    # Step 4: Provide partner place -> Triggers calculation
    p4 = make_payload("msg_compat_4", "Mumbai, India", "919866666666")
    raw4, sig4 = sign(p4, settings.WHATSAPP_APP_SECRET)
    resp4 = await client.post("/api/v1/webhook/whatsapp", content=raw4, headers={"X-Hub-Signature-256": sig4, "Content-Type": "application/json"})
    assert resp4.status_code == 200

    # Verify compatibility reading
    msg_stmt = (
        select(ConversationMessage)
        .where(ConversationMessage.user_id == user.id, ConversationMessage.direction == "outbound")
        .order_by(ConversationMessage.created_at.desc())
    )
    last_msg = (await db_session.execute(msg_stmt)).scalars().first()
    assert last_msg is not None
    content = last_msg.get_decrypted_content()
    assert "Kundli Milan & Compatibility" in content
    assert "Total Guna Score" in content
    assert "Verdict" in content
    assert "Nadi Dosha" in content


@pytest.mark.asyncio
async def test_daily_horoscope_subscription_chat_commands(client: AsyncClient, db_session: AsyncSession):
    """Tests subscribing and unsubscribing to daily horoscopes via conversational WhatsApp commands."""
    user = await setup_consented_user_with_profile(db_session, "919877777777")
    settings = get_settings()

    # Subscribe
    p1 = make_payload("msg_sub_1", "Please subscribe me to daily horoscope", "919877777777")
    raw1, sig1 = sign(p1, settings.WHATSAPP_APP_SECRET)
    resp1 = await client.post("/api/v1/webhook/whatsapp", content=raw1, headers={"X-Hub-Signature-256": sig1, "Content-Type": "application/json"})
    assert resp1.status_code == 200

    pref_stmt = select(UserPreferences).where(UserPreferences.user_id == user.id)
    pref = (await db_session.execute(pref_stmt)).scalar_one()
    assert pref.daily_horoscope_opt_in is True

    # Unsubscribe
    p2 = make_payload("msg_unsub_1", "unsubscribe daily horoscope", "919877777777")
    raw2, sig2 = sign(p2, settings.WHATSAPP_APP_SECRET)
    resp2 = await client.post("/api/v1/webhook/whatsapp", content=raw2, headers={"X-Hub-Signature-256": sig2, "Content-Type": "application/json"})
    assert resp2.status_code == 200

    await db_session.refresh(pref)
    assert pref.daily_horoscope_opt_in is False


def test_detect_language_multilingual_inputs():
    """Verify accurate language detection across Hindi (Devanagari), Hinglish, and English."""
    assert detect_language("Hello, what is my birth chart?") == "en"
    assert detect_language("What are my planetary transits today?") == "en"
    assert detect_language("नमस्ते, मुझे अपनी कुंडली देखनी है") == "hi"
    assert detect_language("आज का राशिफल क्या है?") == "hi"
    assert detect_language("mera dasha aur kundli batao") == "hinglish"
    assert detect_language("kya shani sade sati chal rahi hai?") == "hinglish"


@pytest.mark.asyncio
async def test_generate_astrology_reading_multilingual_fallback():
    """Verify deterministic fallback produces accurate Hindi, Hinglish, and English readings grounded in calculation facts."""
    chart = compute_astrology_chart(
        birth_date=date(1995, 10, 24),
        birth_time=time(14, 30),
        latitude=28.6139,
        longitude=77.2090,
        timezone_name="Asia/Kolkata",
        time_uncertainty=TimeUncertaintyEnum.EXACT,
    )

    # 1. Hindi reading
    hi_reading = await generate_astrology_reading(
        chart=chart,
        time_uncertainty=TimeUncertaintyEnum.EXACT,
        user_name="राहुल",
        lang="hi"
    )
    assert "नमस्ते राहुल!" in hi_reading
    assert "वैदिक जन्म कुंडली" in hi_reading
    assert "चंद्र राशि:" in hi_reading
    assert "सूर्य राशि:" in hi_reading
    assert chart.ascendant.sign_sanskrit in hi_reading

    # 2. Hinglish reading
    hinglish_reading = await generate_astrology_reading(
        chart=chart,
        time_uncertainty=TimeUncertaintyEnum.EXACT,
        user_name="Rahul",
        lang="hinglish"
    )
    assert "Namaste Rahul!" in hinglish_reading
    assert "Yeh rahi aapki authentic Vedic Birth Chart" in hinglish_reading
    assert "Moon Sign" in hinglish_reading
    assert "Sun Sign" in hinglish_reading
    assert chart.ascendant.sign_sanskrit in hinglish_reading

    # 3. Unknown birth time in Hindi reading withholds lagna
    hi_unknown = await generate_astrology_reading(
        chart=chart,
        time_uncertainty=TimeUncertaintyEnum.UNKNOWN,
        user_name="राहुल",
        lang="hi"
    )
    assert "लग्न (Ascendant): अज्ञात" in hi_unknown
    assert "सटीक जन्म समय उपलब्ध न होने के कारण भाव और लग्न रोके गए हैं" in hi_unknown


@pytest.mark.asyncio
async def test_inbound_hinglish_auto_language_switch(client: AsyncClient, db_session: AsyncSession):
    """Verify that an inbound message in Hinglish auto-detects language and returns a localized response."""
    user = await setup_consented_user_with_profile(db_session, "919888899999")
    settings = get_settings()

    # User sends Hinglish dasha query
    p = make_payload("msg_hinglish_1", "mera mahadasha aur dasha batao please", "919888899999")
    raw, sig = sign(p, settings.WHATSAPP_APP_SECRET)
    resp = await client.post(
        "/api/v1/webhook/whatsapp",
        content=raw,
        headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"}
    )
    assert resp.status_code == 200

    # Verify user preference auto-updated to Hinglish
    await db_session.refresh(user)
    pref_stmt = select(UserPreferences).where(UserPreferences.user_id == user.id)
    pref = (await db_session.execute(pref_stmt)).scalar_one()
    assert pref.preferred_language == "hinglish"

    # Verify reply was delivered in Hinglish/Hindi format
    msg_stmt = (
        select(ConversationMessage)
        .where(ConversationMessage.user_id == user.id, ConversationMessage.direction == "outbound")
        .order_by(ConversationMessage.created_at.desc())
    )
    last_msg = (await db_session.execute(msg_stmt)).scalars().first()
    assert last_msg is not None
    content = last_msg.get_decrypted_content()
    assert "Vimshottari Dasha" in content or "विंशोत्तरी दशा" in content

