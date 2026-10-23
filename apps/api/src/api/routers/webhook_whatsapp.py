"""WhatsApp Cloud API Webhook: Meta verification, signature validation, and conversational state machine."""

import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone, date, time
from fastapi import APIRouter, Request, Response, HTTPException, status, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.config import get_settings
from api.db.session import get_db_session
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
from api.security.encryption import compute_phone_hash, encrypt_field
from astrology_engine.models import AstrologySystem
from api.services.whatsapp import (
    verify_meta_signature,
    is_message_duplicate,
    send_whatsapp_text,
)
from api.services.astrology_service import (
    parse_birth_date,
    parse_birth_time,
    resolve_birthplace,
    compute_astrology_chart,
    generate_astrology_reading,
)

logger = logging.getLogger("api.routers.webhook_whatsapp")

router = APIRouter(prefix="/api/v1/webhook/whatsapp", tags=["WhatsApp Webhook"])


@router.get("", response_class=PlainTextResponse)
async def verify_webhook_challenge(request: Request):
    """Handles Meta's initial Webhook Verification Challenge (GET).
    
    Meta sends:
    - hub.mode: 'subscribe'
    - hub.verify_token: token configured in Meta App Dashboard
    - hub.challenge: random integer/string to echo back
    """
    settings = get_settings()
    params = request.query_params

    mode = params.get("hub.mode")
    verify_token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    expected_token = settings.WHATSAPP_VERIFY_TOKEN.get_secret_value()

    if mode == "subscribe" and verify_token == expected_token:
        logger.info("WhatsApp webhook challenge verification succeeded.")
        return challenge or ""

    logger.warning("WhatsApp webhook challenge verification failed (token mismatch or invalid mode).")
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Verification token mismatch"
    )


@router.post("", status_code=status.HTTP_200_OK)
async def receive_whatsapp_webhook(
    request: Request,
    session: AsyncSession = Depends(get_db_session)
):
    """Handles inbound WhatsApp messages with X-Hub-Signature-256 authentication and state machine dispatch."""
    settings = get_settings()
    raw_body = await request.body()

    # 1. Signature Verification (Fail-closed if app secret is configured)
    if settings.WHATSAPP_APP_SECRET and settings.WHATSAPP_APP_SECRET.get_secret_value():
        sig_header = request.headers.get("X-Hub-Signature-256")
        app_secret = settings.WHATSAPP_APP_SECRET.get_secret_value()
        if not verify_meta_signature(raw_body, sig_header, app_secret):
            logger.error("WhatsApp webhook rejected: invalid X-Hub-Signature-256.")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid request signature."
            )

    # 2. Parse JSON Payload
    try:
        payload = await request.json()
    except Exception as exc:
        logger.error("Failed to decode JSON from WhatsApp webhook: %s", exc)
        return {"status": "invalid_json"}

    # Ignore status updates (sent, delivered, read)
    entry_list = payload.get("entry", [])
    if not entry_list:
        return {"status": "no_entries"}

    changes = entry_list[0].get("changes", [])
    if not changes:
        return {"status": "no_changes"}

    value = changes[0].get("value", {})
    messages = value.get("messages", [])

    if not messages:
        # Acknowledge delivery / read receipts safely
        return {"status": "acknowledged"}

    inbound_msg = messages[0]
    msg_id = inbound_msg.get("id")
    msg_type = inbound_msg.get("type")
    sender_raw = inbound_msg.get("from")

    if not msg_id or not sender_raw:
        return {"status": "missing_identifiers"}

    sender_e164 = f"+{sender_raw.lstrip('+')}"

    # 3. Idempotency Check (In-memory + Database duplicate check)
    if is_message_duplicate(msg_id):
        logger.info("Ignoring duplicate message (in-memory): %s", msg_id)
        return {"status": "duplicate_ignored"}

    existing_msg_stmt = select(ConversationMessage).where(
        ConversationMessage.whatsapp_message_id == msg_id
    )
    existing_msg = (await session.execute(existing_msg_stmt)).scalars().first()
    if existing_msg:
        logger.info("Ignoring duplicate message (database): %s", msg_id)
        return {"status": "duplicate_ignored"}

    # Extract user contact profile name if available
    contact_name = None
    contacts = value.get("contacts", [])
    if contacts and "profile" in contacts[0]:
        contact_name = contacts[0]["profile"].get("name")

    # 4. Handle Unsupported Types (images, voice, stickers)
    if msg_type != "text":
        reply_unsupported = (
            "Thank you for reaching out! Currently, I can only understand text messages. "
            "Please send your message as text to continue."
        )
        await send_whatsapp_text(sender_e164, reply_unsupported)
        return {"status": "unsupported_type_handled"}

    text_body = inbound_msg.get("text", {}).get("body", "").strip()

    # 5. User Identification and Session Retrieval
    phone_hash = compute_phone_hash(sender_e164)
    user_stmt = select(User).where(User.phone_hash == phone_hash)
    user = (await session.execute(user_stmt)).scalars().first()

    if not user:
        user = User(
            phone_hash=phone_hash,
            encrypted_phone=encrypt_field(sender_e164),
            whatsapp_name=contact_name,
            status=UserStatus.ACTIVE
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        user_pref = UserPreferences(
            user_id=user.id,
            astrology_system=AstrologySystemEnum.VEDIC,
            preferred_language="en"
        )
        session.add(user_pref)
        await session.commit()
    elif contact_name and user.whatsapp_name != contact_name:
        user.whatsapp_name = contact_name
        await session.commit()

    # 6. Retrieve or Create Active Conversation
    conv_stmt = select(Conversation).where(
        Conversation.user_id == user.id,
        Conversation.status == ConversationStatus.ACTIVE
    )
    conversation = (await session.execute(conv_stmt)).scalars().first()

    if not conversation:
        conversation = Conversation(
            user_id=user.id,
            channel="whatsapp",
            status=ConversationStatus.ACTIVE,
            current_state=ConversationState.ONBOARDING_CONSENT,
            state_metadata={}
        )
        session.add(conversation)
        await session.commit()
        await session.refresh(conversation)

    # 7. Record Inbound Message (Encrypted at rest)
    in_msg_record = ConversationMessage(
        conversation_id=conversation.id,
        user_id=user.id,
        whatsapp_message_id=msg_id,
        direction=MessageDirection.INBOUND,
        sender=MessageSender.USER,
        content_type="text"
    )
    in_msg_record.set_content(text_body)
    session.add(in_msg_record)

    # Update conversation last activity
    conversation.last_activity_at = datetime.now(timezone.utc)
    await session.commit()

    # 8. State Machine Processing
    reply_text = await process_conversational_state(
        conversation=conversation,
        user=user,
        user_input=text_body,
        session=session
    )

    # 9. Record Outbound Reply (Encrypted at rest)
    out_msg_record = ConversationMessage(
        conversation_id=conversation.id,
        user_id=user.id,
        direction=MessageDirection.OUTBOUND,
        sender=MessageSender.ASSISTANT,
        content_type="text"
    )
    out_msg_record.set_content(reply_text)
    session.add(out_msg_record)
    await session.commit()

    # 10. Deliver Reply over WhatsApp Graph API
    await send_whatsapp_text(to_phone=sender_e164, text_body=reply_text)

    return {"status": "success", "processed_message_id": msg_id}


async def process_conversational_state(
    conversation: Conversation,
    user: User,
    user_input: str,
    session: AsyncSession
) -> str:
    """Core state machine transitioning through consent, profile collection, and reading generation."""
    clean_text = user_input.strip()
    lowered = clean_text.lower()
    meta = dict(conversation.state_metadata or {})

    # Check active consent record
    consent_stmt = select(ConsentRecord).where(
        ConsentRecord.user_id == user.id,
        ConsentRecord.purpose == "birth_data_processing",
        ConsentRecord.granted == True,
        ConsentRecord.revoked_at.is_(None)
    )
    active_consent = (await session.execute(consent_stmt)).scalars().first()

    # If user revokes consent at any time:
    if lowered in ("revoke consent", "stop consent", "delete my data", "delete data"):
        if active_consent:
            active_consent.revoked_at = datetime.now(timezone.utc)
            await session.commit()
        conversation.current_state = ConversationState.ONBOARDING_CONSENT
        conversation.state_metadata = {}
        await session.commit()
        return (
            "Your consent has been revoked. We have stopped processing your birth data. "
            "To permanently erase all your records, you may also request Right-to-Erasure anytime. "
            "Reply 'YES' if you wish to start fresh."
        )

    # ── State: ONBOARDING_CONSENT ──────────────────────────────────────────────
    if conversation.current_state == ConversationState.ONBOARDING_CONSENT:
        if active_consent:
            # Consent already exists; check if profile already exists
            prof_stmt = select(BirthProfile).where(BirthProfile.user_id == user.id)
            existing_profile = (await session.execute(prof_stmt)).scalars().first()
            if existing_profile:
                conversation.current_state = ConversationState.READING_READY
                await session.commit()
                return (
                    f"Welcome back{', ' + user.whatsapp_name if user.whatsapp_name else ''}! 🌟 "
                    "Your birth profile is active. Ask any question about your planetary placements, "
                    "or send a new date to recalculate your chart!"
                )
            else:
                conversation.current_state = ConversationState.AWAITING_BIRTH_DATE
                await session.commit()
                return (
                    "Welcome! Let's generate your authentic Vedic birth chart.\n\n"
                    "1️⃣ What is your date of birth? (Please reply in YYYY-MM-DD format, e.g., 1995-10-24)"
                )

        # Check for user response to consent request
        if lowered in ("yes", "i agree", "agree", "consent", "yup", "sure", "ok", "haan"):
            consent_record = ConsentRecord(
                user_id=user.id,
                purpose="birth_data_processing",
                policy_version="v1.0",
                channel="whatsapp",
                granted=True
            )
            session.add(consent_record)
            conversation.current_state = ConversationState.AWAITING_BIRTH_DATE
            conversation.state_metadata = {}
            await session.commit()

            return (
                "Thank you! Your consent has been recorded securely under GDPR/DPDP guidelines. 🔒\n\n"
                "Let's create your authentic birth chart:\n\n"
                "1️⃣ What is your date of birth? (Please reply in YYYY-MM-DD format, e.g., 1995-10-24)"
            )
        elif lowered in ("no", "disagree", "decline", "nahi"):
            return (
                "We completely respect your privacy. Under our Privacy-by-Design standard, "
                "no birth details or personal history will be stored without your affirmative consent.\n\n"
                "If you wish to explore your chart in the future, just reply *YES* anytime to get started."
            )
        else:
            return (
                "Welcome to the Astrology Assistant! 🌟 I provide personalized astrological readings "
                "grounded in high-precision astronomical calculations (Vedic and Western).\n\n"
                "Before we begin, do you consent to the secure storage and processing of your birth details "
                "(date, time, place) to calculate your astrological chart?\n\n"
                "Please reply *YES* to agree and begin, or *NO* to decline."
            )

    # ── State: AWAITING_BIRTH_DATE ─────────────────────────────────────────────
    if conversation.current_state == ConversationState.AWAITING_BIRTH_DATE:
        parsed_d = parse_birth_date(clean_text)
        if not parsed_d:
            return (
                "I couldn't quite understand that date format. "
                "Please provide your birth date in YYYY-MM-DD format (for example: 1995-10-24)."
            )

        meta["birth_date"] = parsed_d.isoformat()
        conversation.state_metadata = meta
        conversation.current_state = ConversationState.AWAITING_BIRTH_TIME
        await session.commit()

        formatted_date = parsed_d.strftime("%d %B %Y")
        return (
            f"Got it! Date of birth: {formatted_date}.\n\n"
            "2️⃣ What time were you born? "
            "(Please reply in 24-hour HH:MM format like 14:30 or 08:15 AM. "
            "If you do not know your exact birth time, simply reply *UNKNOWN*)."
        )

    # ── State: AWAITING_BIRTH_TIME ─────────────────────────────────────────────
    if conversation.current_state == ConversationState.AWAITING_BIRTH_TIME:
        time_obj, uncertainty = parse_birth_time(clean_text)

        meta["birth_time"] = time_obj.isoformat() if time_obj else None
        meta["time_uncertainty"] = uncertainty.value
        conversation.state_metadata = meta
        conversation.current_state = ConversationState.AWAITING_BIRTH_PLACE
        await session.commit()

        time_feedback = time_obj.strftime("%I:%M %p") if time_obj else "Unknown"
        return (
            f"Noted! Birth time: {time_feedback}.\n\n"
            "3️⃣ Where were you born? "
            "(Please reply with the city and country, for example: Mumbai, India or London, UK)"
        )

    # ── State: AWAITING_BIRTH_PLACE ────────────────────────────────────────────
    if conversation.current_state == ConversationState.AWAITING_BIRTH_PLACE:
        lat, lon, loc_name, tz_name = resolve_birthplace(clean_text)

        b_date_str = meta.get("birth_date")
        b_time_str = meta.get("birth_time")
        uncertainty_val = meta.get("time_uncertainty", TimeUncertaintyEnum.EXACT.value)

        if not b_date_str:
            conversation.current_state = ConversationState.AWAITING_BIRTH_DATE
            await session.commit()
            return "Let's restart from your birth date. What is your date of birth (YYYY-MM-DD)?"

        b_date = date.fromisoformat(b_date_str)
        b_time = time.fromisoformat(b_time_str) if b_time_str else None
        uncertainty = TimeUncertaintyEnum(uncertainty_val)

        # 1. Persist or Update Primary BirthProfile (Encrypted at rest)
        prof_stmt = select(BirthProfile).where(
            BirthProfile.user_id == user.id,
            BirthProfile.is_primary == True
        )
        profile = (await session.execute(prof_stmt)).scalars().first()

        if not profile:
            profile = BirthProfile(
                user_id=user.id,
                profile_label="Primary",
                is_primary=True,
                timezone_name=tz_name,
                time_uncertainty=uncertainty
            )
            session.add(profile)

        profile.timezone_name = tz_name
        profile.time_uncertainty = uncertainty
        profile.set_birth_details(
            birth_date=b_date,
            birth_time=b_time,
            latitude=lat,
            longitude=lon,
            location_name=loc_name
        )
        await session.commit()

        # 2. Compute Deterministic D1 Chart using existing calculation engine
        chart = compute_astrology_chart(
            birth_date=b_date,
            birth_time=b_time,
            latitude=lat,
            longitude=lon,
            timezone_name=tz_name,
            time_uncertainty=uncertainty,
            system=AstrologySystem.VEDIC
        )

        # 3. Generate Grounded Astrological Reading
        reading_text = await generate_astrology_reading(
            chart=chart,
            time_uncertainty=uncertainty,
            user_name=user.whatsapp_name
        )

        conversation.current_state = ConversationState.READING_READY
        conversation.state_metadata = {"last_chart_calculated_at": datetime.now(timezone.utc).isoformat()}
        await session.commit()

        return reading_text

    # ── State: READING_READY / ACTIVE ──────────────────────────────────────────
    # User has an active chart and is asking a follow-up question
    prof_stmt = select(BirthProfile).where(
        BirthProfile.user_id == user.id,
        BirthProfile.is_primary == True
    )
    profile = (await session.execute(prof_stmt)).scalars().first()

    if profile:
        details = profile.get_decrypted_details()
        chart = compute_astrology_chart(
            birth_date=details["birth_date"],
            birth_time=details["birth_time"],
            latitude=details["latitude"],
            longitude=details["longitude"],
            timezone_name=details["timezone_name"],
            time_uncertainty=details["time_uncertainty"],
            system=AstrologySystem.VEDIC
        )
        return await generate_astrology_reading(
            chart=chart,
            time_uncertainty=details["time_uncertainty"],
            user_name=user.whatsapp_name
        )

    # Fallback to greeting
    conversation.current_state = ConversationState.ONBOARDING_CONSENT
    await session.commit()
    return "Welcome! How can I assist you with your astrological reading today?"
