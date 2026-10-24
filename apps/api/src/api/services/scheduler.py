"""Automated, idempotent daily horoscope scheduler and batch dispatch runner."""

import logging
from datetime import date, datetime, timezone
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.db.models.user import User, UserPreferences, UserStatus, AstrologySystemEnum
from api.db.models.birth_profile import BirthProfile
from api.db.models.conversation import (
    Conversation,
    ConversationMessage,
    ConversationStatus,
    ConversationState,
    MessageDirection,
    MessageSender,
)
from astrology_engine.models import AstrologySystem
from api.services.whatsapp import send_whatsapp_text
from api.services.astrology_service import generate_daily_horoscope_for_profile

logger = logging.getLogger("api.services.scheduler")


async def dispatch_daily_horoscopes(
    session: AsyncSession,
    target_date: Optional[date] = None,
    batch_size: int = 500
) -> Dict[str, Any]:
    """Scans all users opted in to daily horoscopes and dispatches personalized readings idempotently.
    
    Guarantees:
    - Never delivers twice to the same user on the same calendar date (idempotency check via last_horoscope_sent_date).
    - Respects user consent and account status (only active users).
    - Logs delivery metrics and isolates per-user failures without aborting the batch.
    """
    dispatch_date = target_date or datetime.now(timezone.utc).date()
    logger.info("Starting daily horoscope batch dispatch for date: %s", dispatch_date)

    # Query eligible active users together with their preferences
    stmt = (
        select(User, UserPreferences)
        .join(UserPreferences, User.id == UserPreferences.user_id)
        .where(
            User.status == UserStatus.ACTIVE,
            UserPreferences.daily_horoscope_opt_in == True,
            User.deleted_at.is_(None)
        )
        .limit(batch_size)
    )
    result = await session.execute(stmt)
    user_pairs = list(result.all())

    stats = {
        "dispatch_date": dispatch_date.isoformat(),
        "total_eligible": len(user_pairs),
        "sent": 0,
        "skipped_already_sent": 0,
        "skipped_no_profile": 0,
        "errors": 0
    }

    for user, pref in user_pairs:
        # 1. Idempotency Check: Skip if already delivered on this date
        if pref.last_horoscope_sent_date == dispatch_date:
            stats["skipped_already_sent"] += 1
            continue

        # 2. Check Primary Birth Profile
        prof_stmt = select(BirthProfile).where(
            BirthProfile.user_id == user.id,
            BirthProfile.is_primary == True
        )
        profile = (await session.execute(prof_stmt)).scalars().first()
        if not profile:
            stats["skipped_no_profile"] += 1
            logger.warning("User %s opted in to horoscopes but has no primary birth profile; skipping.", user.id)
            continue

        try:
            details = profile.get_decrypted_details()
            user_phone = user.get_decrypted_phone()

            astrology_sys = (
                AstrologySystem.WESTERN
                if pref.astrology_system == AstrologySystemEnum.WESTERN
                else AstrologySystem.VEDIC
            )
            lang = pref.preferred_language or "en"

            # 3. Generate Personalized Daily Horoscope
            horoscope_msg = generate_daily_horoscope_for_profile(
                birth_date=details["birth_date"],
                birth_time=details["birth_time"],
                latitude=details["latitude"],
                longitude=details["longitude"],
                timezone_name=details["timezone_name"],
                target_date=dispatch_date,
                user_name=user.whatsapp_name,
                system=astrology_sys,
                lang=lang
            )

            # 4. Deliver via WhatsApp Graph API (or mock transport)
            await send_whatsapp_text(to_phone=user_phone, text_body=horoscope_msg)

            # 5. Record Outbound Message in Active Conversation
            conv_stmt = select(Conversation).where(
                Conversation.user_id == user.id,
                Conversation.status == ConversationStatus.ACTIVE
            )
            conv = (await session.execute(conv_stmt)).scalars().first()
            if not conv:
                conv = Conversation(
                    user_id=user.id,
                    channel="whatsapp",
                    status=ConversationStatus.ACTIVE,
                    current_state=ConversationState.READING_READY,
                    state_metadata={}
                )
                session.add(conv)
                await session.flush()

            out_msg = ConversationMessage(
                conversation_id=conv.id,
                user_id=user.id,
                direction=MessageDirection.OUTBOUND,
                sender=MessageSender.ASSISTANT,
                content_type="text"
            )
            out_msg.set_content(horoscope_msg)
            session.add(out_msg)

            # 6. Mark Date as Sent (Idempotency stamp)
            pref.last_horoscope_sent_date = dispatch_date
            conv.last_activity_at = datetime.now(timezone.utc)
            await session.commit()

            stats["sent"] += 1
        except Exception as exc:
            logger.error("Failed to generate/deliver daily horoscope for user %s: %s", user.id, exc)
            stats["errors"] += 1
            await session.rollback()

    logger.info("Daily horoscope batch dispatch completed: %s", stats)
    return stats
