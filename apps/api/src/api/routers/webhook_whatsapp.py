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
from api.db.models.bot_settings import BotSettings
from api.services.bot_settings_service import get_or_create_bot_settings
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
    format_dasha_reading,
    format_transits_reading,
    format_panchang_reading,
    format_compatibility_reading,
    generate_daily_horoscope_for_profile,
    detect_language,
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

    # Process delivery and read status updates
    entry_list = payload.get("entry", [])
    if not entry_list:
        return {"status": "no_entries"}

    changes = entry_list[0].get("changes", [])
    if not changes:
        return {"status": "no_changes"}

    value = changes[0].get("value", {})

    # 2a. Track message delivery statuses (sent, delivered, read, failed)
    statuses = value.get("statuses", [])
    if statuses:
        for status_item in statuses:
            wamid = status_item.get("id")
            s_val = status_item.get("status")
            s_ts = status_item.get("timestamp")
            s_errors = status_item.get("errors", [])
            if wamid and s_val:
                msg_stmt = select(ConversationMessage).where(
                    ConversationMessage.whatsapp_message_id == wamid
                )
                msg_record = (await session.execute(msg_stmt)).scalars().first()
                if msg_record:
                    # Enforce status progression: pending < sent < delivered < read (never downgrade)
                    status_rank = {"pending": 0, "sent": 1, "delivered": 2, "read": 3, "failed": 4}
                    curr_rank = status_rank.get(msg_record.delivery_status or "pending", 0)
                    new_rank = status_rank.get(s_val, 0)

                    if s_val == "failed" or new_rank >= curr_rank:
                        msg_record.delivery_status = s_val

                    if s_ts:
                        try:
                            parsed_ts = datetime.fromtimestamp(int(s_ts), tz=timezone.utc)
                            if not msg_record.status_timestamp or parsed_ts >= msg_record.status_timestamp:
                                msg_record.status_timestamp = parsed_ts
                        except Exception:
                            if not msg_record.status_timestamp:
                                msg_record.status_timestamp = datetime.now(timezone.utc)
                    else:
                        if not msg_record.status_timestamp:
                            msg_record.status_timestamp = datetime.now(timezone.utc)

                    if s_errors and isinstance(s_errors, list):
                        msg_record.error_code = str(s_errors[0].get("code", ""))
                        msg_record.error_message = str(s_errors[0].get("message") or s_errors[0].get("title", ""))
                    await session.commit()
                    logger.info("Updated delivery status for message %s: %s", wamid, msg_record.delivery_status)
        return {"status": "statuses_processed"}

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
            preferred_language="en",
            daily_horoscope_opt_in=False
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

    # 8. Check Bot Controls (Pause & Maintenance Mode)
    bot_settings = await get_or_create_bot_settings(session)
    if bot_settings.is_paused:
        logger.info(
            "Bot is currently paused. Inbound message %s from %s safely recorded.",
            msg_id,
            user.id
        )
        if bot_settings.maintenance_mode:
            maint_reply = bot_settings.maintenance_message
            out_msg_record = ConversationMessage(
                conversation_id=conversation.id,
                user_id=user.id,
                direction=MessageDirection.OUTBOUND,
                sender=MessageSender.ASSISTANT,
                content_type="text",
                delivery_status="pending",
                status_timestamp=datetime.now(timezone.utc)
            )
            out_msg_record.set_content(maint_reply)
            session.add(out_msg_record)
            await session.commit()

            try:
                send_res = await send_whatsapp_text(to_phone=sender_e164, text_body=maint_reply)
                out_msg_record.delivery_status = "sent"
                out_msg_record.status_timestamp = datetime.now(timezone.utc)
                if isinstance(send_res, dict) and send_res.get("messages"):
                    out_msg_record.whatsapp_message_id = send_res["messages"][0].get("id")
                await session.commit()
            except Exception as exc:
                out_msg_record.delivery_status = "failed"
                out_msg_record.status_timestamp = datetime.now(timezone.utc)
                out_msg_record.error_message = str(exc)
                await session.commit()
                logger.error("Failed to send maintenance reply to %s: %s", user.id, exc)

            return {"status": "maintenance_mode_replied", "processed_message_id": msg_id}

        return {"status": "bot_paused", "processed_message_id": msg_id}

    # 9. State Machine Processing
    reply_text = await process_conversational_state(
        conversation=conversation,
        user=user,
        user_input=text_body,
        session=session,
        bot_settings=bot_settings
    )

    # 10. Record Outbound Reply (Encrypted at rest)
    out_msg_record = ConversationMessage(
        conversation_id=conversation.id,
        user_id=user.id,
        direction=MessageDirection.OUTBOUND,
        sender=MessageSender.ASSISTANT,
        content_type="text",
        delivery_status="pending",
        status_timestamp=datetime.now(timezone.utc)
    )
    out_msg_record.set_content(reply_text)
    session.add(out_msg_record)
    await session.commit()

    # 11. Deliver Reply over WhatsApp Graph API
    try:
        send_res = await send_whatsapp_text(to_phone=sender_e164, text_body=reply_text)
        out_msg_record.delivery_status = "sent"
        out_msg_record.status_timestamp = datetime.now(timezone.utc)
        if isinstance(send_res, dict) and send_res.get("messages"):
            out_msg_record.whatsapp_message_id = send_res["messages"][0].get("id")
        await session.commit()
    except Exception as exc:
        out_msg_record.delivery_status = "failed"
        out_msg_record.status_timestamp = datetime.now(timezone.utc)
        out_msg_record.error_message = str(exc)
        await session.commit()
        logger.error("Failed to deliver reply to %s: %s", user.id, exc)

    return {"status": "success", "processed_message_id": msg_id}


async def process_conversational_state(
    conversation: Conversation,
    user: User,
    user_input: str,
    session: AsyncSession,
    bot_settings: Optional[BotSettings] = None
) -> str:
    """Core state machine transitioning through consent, profile collection, system switching, and reading generation."""
    clean_text = user_input.strip()
    lowered = clean_text.lower()
    meta = dict(conversation.state_metadata or {})

    # Detect user language
    detected_lang = detect_language(clean_text)
    pref: Optional[UserPreferences] = user.preferences
    if pref and pref.auto_detect_language and detected_lang in ("hi", "hinglish"):
        pref.preferred_language = detected_lang
        await session.commit()

    lang = pref.preferred_language if pref else detected_lang
    user_system = pref.astrology_system if pref else AstrologySystemEnum.VEDIC
    astrology_sys = (
        AstrologySystem.WESTERN
        if user_system == AstrologySystemEnum.WESTERN
        else AstrologySystem.VEDIC
    )

    # Check active consent record
    consent_stmt = select(ConsentRecord).where(
        ConsentRecord.user_id == user.id,
        ConsentRecord.purpose == "birth_data_processing",
        ConsentRecord.granted == True,
        ConsentRecord.revoked_at.is_(None)
    )
    active_consent = (await session.execute(consent_stmt)).scalars().first()

    # ── Global Intent 1: Revoke Consent / Delete Data (Honors WhatsApp STOP/UNSUBSCRIBE) ───
    normalized_kw = lowered.strip(" .!?,;:")
    if normalized_kw in (
        "stop",
        "unsubscribe",
        "opt out",
        "opt-out",
        "halt",
        "revoke consent",
        "stop consent",
        "delete my data",
        "delete data",
        "erase my data",
    ):
        if active_consent:
            active_consent.revoked_at = datetime.now(timezone.utc)
            active_consent.granted = False
            await session.commit()
        if pref:
            pref.daily_horoscope_opt_in = False
            await session.commit()
        conversation.current_state = ConversationState.ONBOARDING_CONSENT
        conversation.state_metadata = {}
        await session.commit()
        return (
            "Your consent has been revoked. We have stopped processing your birth data. "
            "To permanently erase all your records, you may also request Right-to-Erasure anytime. "
            "Reply 'YES' if you wish to start fresh."
        )

    # ── Global Intent 2: System Selection & Switching ────────────────────────
    if any(k in lowered for k in ("switch to western", "use western", "change to western", "/system western")):
        if pref:
            pref.astrology_system = AstrologySystemEnum.WESTERN
            await session.commit()
        return (
            "✨ Astrological system switched to **Western Astrology** (Tropical Zodiac & Placidus houses). "
            "Your upcoming readings and daily horoscopes will now be presented using Western astrological methods."
        )

    if any(k in lowered for k in ("switch to vedic", "use vedic", "change to vedic", "/system vedic")):
        if pref:
            pref.astrology_system = AstrologySystemEnum.VEDIC
            await session.commit()
        return (
            "🕉️ Astrological system switched to **Vedic Astrology (Jyotish)** (Sidereal Zodiac, Lahiri Ayanamsa & Nakshatras). "
            "Your upcoming readings and daily horoscopes will now be presented using Vedic traditions."
        )

    # ── Global Intent 3: Daily Horoscope Subscription / Opt-in Management ────
    if ("horoscope" in lowered or "rashifal" in lowered) and any(k in lowered for k in ("unsubscribe", "pause", "stop", "cancel", "turn off", "opt out", "opt-out")):
        if pref:
            pref.daily_horoscope_opt_in = False
            await session.commit()
        return (
            "🔕 **Daily Horoscope Paused.**\n\n"
            "You will no longer receive scheduled morning horoscopes. "
            "You can still request an on-demand horoscope anytime by replying 'daily horoscope'!"
        )

    if ("horoscope" in lowered or "rashifal" in lowered) and any(k in lowered for k in ("subscribe", "opt in", "opt-in", "start daily", "send daily")):
        if pref:
            pref.daily_horoscope_opt_in = True
            await session.commit()
        delivery_time = pref.horoscope_delivery_time if pref else "07:00"
        return (
            f"🔔 **Daily Horoscope Subscribed!**\n\n"
            f"You will now automatically receive your personalized horoscope every morning at {delivery_time} UTC. "
            "To pause or unsubscribe at any time, just reply 'unsubscribe horoscope'."
        )

    # ── Global Intent 4: Recalculate / Update Birth Details ───────────────────
    if any(k in lowered for k in ("new chart", "update birth", "recalculate chart", "nayi kundli", "change birth details")):
        conversation.current_state = ConversationState.AWAITING_BIRTH_DATE
        conversation.state_metadata = {}
        await session.commit()
        return "Let's update your birth details.\n\n1️⃣ What is your date of birth? (YYYY-MM-DD, e.g. 1995-10-24)"

    # ── Compatibility Multi-Turn Flow Handling ─────────────────────────────────
    if meta.get("action") == "compatibility":
        if lowered in ("cancel", "stop", "abort", "exit"):
            meta.pop("action", None)
            meta.pop("step", None)
            conversation.state_metadata = meta
            await session.commit()
            return "Compatibility matching flow cancelled. How else can I assist you?"

        step = meta.get("step")
        if step == "awaiting_partner_date":
            p_date = parse_birth_date(clean_text)
            if not p_date:
                return "I couldn't understand that date. Please provide your partner's birth date in YYYY-MM-DD format (e.g. 1996-05-15):"
            meta["partner_date"] = p_date.isoformat()
            meta["step"] = "awaiting_partner_time"
            conversation.state_metadata = meta
            await session.commit()
            return f"Got it ({p_date.strftime('%d %B %Y')})!\n\n2️⃣ What time was your partner born? (HH:MM or reply *UNKNOWN*):"

        elif step == "awaiting_partner_time":
            p_time, p_unc = parse_birth_time(clean_text)
            meta["partner_time"] = p_time.isoformat() if p_time else None
            meta["partner_time_uncertainty"] = p_unc.value
            meta["step"] = "awaiting_partner_place"
            conversation.state_metadata = meta
            await session.commit()
            return "3️⃣ Where was your partner born? (City and Country, e.g. Mumbai, India or London, UK):"

        elif step == "awaiting_partner_place":
            lat, lon, loc_name, tz_name = resolve_birthplace(clean_text)
            p_date = date.fromisoformat(meta["partner_date"])
            p_time_str = meta.get("partner_time")
            p_time = time.fromisoformat(p_time_str) if p_time_str else None
            p_unc = TimeUncertaintyEnum(meta.get("partner_time_uncertainty", TimeUncertaintyEnum.EXACT.value))

            # Retrieve user's primary birth profile
            prof_stmt = select(BirthProfile).where(
                BirthProfile.user_id == user.id,
                BirthProfile.is_primary == True
            )
            profile = (await session.execute(prof_stmt)).scalars().first()

            if not profile:
                meta.pop("action", None)
                conversation.state_metadata = meta
                await session.commit()
                return "Your primary birth profile was not found. Please complete your own birth profile first."

            user_details = profile.get_decrypted_details()

            # Compute primary chart and partner chart
            chart1 = compute_astrology_chart(
                birth_date=user_details["birth_date"],
                birth_time=user_details["birth_time"],
                latitude=user_details["latitude"],
                longitude=user_details["longitude"],
                timezone_name=user_details["timezone_name"],
                time_uncertainty=user_details["time_uncertainty"],
                system=AstrologySystem.VEDIC
            )

            chart2 = compute_astrology_chart(
                birth_date=p_date,
                birth_time=p_time,
                latitude=lat,
                longitude=lon,
                timezone_name=tz_name,
                time_uncertainty=p_unc,
                system=AstrologySystem.VEDIC
            )

            # Clear compatibility flow
            meta.pop("action", None)
            meta.pop("step", None)
            meta.pop("partner_date", None)
            meta.pop("partner_time", None)
            meta.pop("partner_time_uncertainty", None)
            conversation.state_metadata = meta
            await session.commit()

            return format_compatibility_reading(
                person1_chart=chart1,
                person2_chart=chart2,
                name1=user.whatsapp_name or "You",
                name2="Partner",
                lang=lang
            )

    # ── State: ONBOARDING_CONSENT ──────────────────────────────────────────────
    if conversation.current_state == ConversationState.ONBOARDING_CONSENT:
        if active_consent:
            prof_stmt = select(BirthProfile).where(BirthProfile.user_id == user.id)
            existing_profile = (await session.execute(prof_stmt)).scalars().first()
            if existing_profile:
                conversation.current_state = ConversationState.READING_READY
                await session.commit()
                return (
                    f"Welcome back{', ' + user.whatsapp_name if user.whatsapp_name else ''}! 🌟 "
                    "Your birth profile is active. You can ask for your daily horoscope, transits, dasha, or check compatibility!"
                )
            else:
                conversation.current_state = ConversationState.AWAITING_BIRTH_DATE
                await session.commit()
                return (
                    "Welcome! Let's generate your authentic astrological birth chart.\n\n"
                    "1️⃣ What is your date of birth? (Please reply in YYYY-MM-DD format, e.g., 1995-10-24)"
                )

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
            if bot_settings and bot_settings.welcome_message:
                return bot_settings.welcome_message
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

        # 2. Compute Deterministic Chart
        chart = compute_astrology_chart(
            birth_date=b_date,
            birth_time=b_time,
            latitude=lat,
            longitude=lon,
            timezone_name=tz_name,
            time_uncertainty=uncertainty,
            system=astrology_sys
        )

        # 3. Generate Grounded Astrological Reading
        reading_text = await generate_astrology_reading(
            chart=chart,
            time_uncertainty=uncertainty,
            user_name=user.whatsapp_name,
            lang=lang
        )

        conversation.current_state = ConversationState.READING_READY
        conversation.state_metadata = {"last_chart_calculated_at": datetime.now(timezone.utc).isoformat()}
        await session.commit()

        return reading_text

    # ── State: READING_READY / ACTIVE ──────────────────────────────────────────
    prof_stmt = select(BirthProfile).where(
        BirthProfile.user_id == user.id,
        BirthProfile.is_primary == True
    )
    profile = (await session.execute(prof_stmt)).scalars().first()

    if profile:
        details = profile.get_decrypted_details()

        # Check for Compatibility Trigger
        if any(k in lowered for k in ("compatibility", "kundli milan", "milan", "match kundli", "matchmaking", "gun milan")):
            meta["action"] = "compatibility"
            meta["step"] = "awaiting_partner_date"
            conversation.state_metadata = meta
            await session.commit()
            return (
                "💑 **Kundli Milan & Compatibility (Ashtakoota 36 Gunas)**\n\n"
                "Let's compare charts to assess emotional, physiological, and spiritual harmony.\n\n"
                "1️⃣ What is your partner's date of birth? (Please reply in YYYY-MM-DD format, e.g. 1996-05-15)"
            )

        # Check for Daily Horoscope Trigger
        if any(k in lowered for k in ("daily horoscope", "today's horoscope", "today horoscope", "rashifal", "aaj ka rashifal", "horoscope")):
            return generate_daily_horoscope_for_profile(
                birth_date=details["birth_date"],
                birth_time=details["birth_time"],
                latitude=details["latitude"],
                longitude=details["longitude"],
                timezone_name=details["timezone_name"],
                user_name=user.whatsapp_name,
                system=astrology_sys,
                lang=lang,
                horoscope_intro=bot_settings.horoscope_intro if bot_settings else None
            )

        # Check for Dasha Trigger
        if any(k in lowered for k in ("dasha", "mahadasha", "antardasha", "vimshottari")):
            return format_dasha_reading(
                birth_date=details["birth_date"],
                birth_time=details["birth_time"],
                latitude=details["latitude"],
                longitude=details["longitude"],
                timezone_name=details["timezone_name"],
                lang=lang
            )

        # Check for Transits / Sade Sati Trigger
        if any(k in lowered for k in ("transit", "transits", "sade sati", "gochara", "shani")):
            return format_transits_reading(
                birth_date=details["birth_date"],
                birth_time=details["birth_time"],
                latitude=details["latitude"],
                longitude=details["longitude"],
                timezone_name=details["timezone_name"],
                time_uncertainty=details["time_uncertainty"],
                lang=lang
            )

        # Check for Panchang Trigger
        if any(k in lowered for k in ("panchang", "tithi", "aaj ka panchang", "muhurta")):
            return format_panchang_reading(
                latitude=details["latitude"],
                longitude=details["longitude"],
                timezone_name=details["timezone_name"],
                lang=lang
            )

        # Default reading / follow-up reading
        chart = compute_astrology_chart(
            birth_date=details["birth_date"],
            birth_time=details["birth_time"],
            latitude=details["latitude"],
            longitude=details["longitude"],
            timezone_name=details["timezone_name"],
            time_uncertainty=details["time_uncertainty"],
            system=astrology_sys
        )
        return await generate_astrology_reading(
            chart=chart,
            time_uncertainty=details["time_uncertainty"],
            user_name=user.whatsapp_name,
            lang=lang,
            general_instructions=bot_settings.general_instructions if bot_settings else None
        )

    # Fallback to onboarding
    conversation.current_state = ConversationState.ONBOARDING_CONSENT
    await session.commit()
    if bot_settings and bot_settings.fallback_message:
        return bot_settings.fallback_message
    return "Welcome! How can I assist you with your astrological reading today?"
