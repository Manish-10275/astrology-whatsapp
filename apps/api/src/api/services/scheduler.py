"""Automated, idempotent daily horoscope scheduler and batch dispatch runner.

Supports timezone-aware delivery hour matching, concurrency protection,
audit logging without PII, proactive WhatsApp template delivery, and an
in-process background runner daemon for automated execution.
"""

import zoneinfo
import asyncio
import logging
from datetime import date, datetime, timezone
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.config import get_settings
from api.db.models.user import User, UserPreferences, UserStatus, AstrologySystemEnum
from api.db.models.birth_profile import BirthProfile
from api.db.models.audit import AuditEvent
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
from api.services.whatsapp_templates import send_whatsapp_template, DailyHoroscopeTemplatePayload
from api.services.astrology_service import generate_daily_horoscope_for_profile

logger = logging.getLogger("api.services.scheduler")

# Concurrency lock to prevent concurrent dispatch executions from overlapping
_DISPATCH_LOCK = asyncio.Lock()


async def dispatch_daily_horoscopes(
    session: AsyncSession,
    target_date: Optional[date] = None,
    target_hour: Optional[int] = None,
    batch_size: int = 500
) -> Dict[str, Any]:
    """Scans all users opted in to daily horoscopes and dispatches personalized readings idempotently.
    
    Guarantees:
    - Concurrency safety: Returns immediately if a batch dispatch is already running.
    - Idempotency: Never delivers twice to the same user on the same calendar date.
    - Timezone awareness: Evaluates user local date and optional local target hour.
    - Proactive template delivery: Uses pre-approved Meta WhatsApp templates when configured.
    - Audit logging: Logs aggregate execution metrics without storing PII.
    """
    if _DISPATCH_LOCK.locked():
        logger.warning("Daily horoscope dispatch is already running; skipping concurrent trigger.")
        return {
            "status": "concurrency_skip",
            "message": "A daily horoscope dispatch is currently in progress.",
            "dispatch_date": (target_date or datetime.now(timezone.utc).date()).isoformat(),
            "total_eligible": 0,
            "sent": 0,
            "skipped_already_sent": 0,
            "skipped_no_profile": 0,
            "skipped_wrong_time": 0,
            "errors": 0,
        }

    async with _DISPATCH_LOCK:
        settings = get_settings()
        now_utc = datetime.now(timezone.utc)
        dispatch_utc_date = target_date or now_utc.date()
        logger.info("Starting daily horoscope batch dispatch (UTC date: %s, target_hour: %s)", dispatch_utc_date, target_hour)

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
            "status": "completed",
            "dispatch_date": dispatch_utc_date.isoformat(),
            "total_eligible": len(user_pairs),
            "sent": 0,
            "skipped_already_sent": 0,
            "skipped_no_profile": 0,
            "skipped_wrong_time": 0,
            "errors": 0
        }

        for user, pref in user_pairs:
            # 1. Check Primary Birth Profile & Timezone
            prof_stmt = select(BirthProfile).where(
                BirthProfile.user_id == user.id,
                BirthProfile.is_primary == True
            )
            profile = (await session.execute(prof_stmt)).scalars().first()
            if not profile:
                stats["skipped_no_profile"] += 1
                logger.warning("User %s opted in to horoscopes but has no primary birth profile; skipping.", user.id)
                continue

            # Determine user's local date and time using their configured timezone
            user_tz_str = profile.timezone_name or "UTC"
            try:
                user_tz = zoneinfo.ZoneInfo(user_tz_str)
            except Exception:
                user_tz = timezone.utc

            user_now = datetime.now(user_tz)
            user_local_date = target_date or user_now.date()

            # 2. Check Delivery Time Hour (if target_hour is specified)
            if target_hour is not None:
                pref_hour = 7  # Default 07:00
                if pref.horoscope_delivery_time:
                    try:
                        pref_hour = int(pref.horoscope_delivery_time.split(":")[0])
                    except (ValueError, IndexError):
                        pref_hour = 7

                if user_now.hour != target_hour or pref_hour != target_hour:
                    stats["skipped_wrong_time"] += 1
                    continue

            # 3. Idempotency Check: Skip if already delivered on this user's local calendar date
            if pref.last_horoscope_sent_date == user_local_date:
                stats["skipped_already_sent"] += 1
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

                # 4. Generate Personalized Daily Horoscope
                horoscope_msg = generate_daily_horoscope_for_profile(
                    birth_date=details["birth_date"],
                    birth_time=details["birth_time"],
                    latitude=details["latitude"],
                    longitude=details["longitude"],
                    timezone_name=details["timezone_name"],
                    target_date=user_local_date,
                    user_name=user.whatsapp_name,
                    system=astrology_sys,
                    lang=lang
                )

                # 5. Delivery: Meta WhatsApp Template (proactive) vs Freeform Text
                if settings.WHATSAPP_USE_TEMPLATES_FOR_PROACTIVE:
                    template_name = settings.WHATSAPP_TEMPLATE_DAILY_HOROSCOPE
                    sign_summary = f"{astrology_sys.value.title()} Horoscope"
                    payload = DailyHoroscopeTemplatePayload(
                        user_name=user.whatsapp_name or "Seeker",
                        date_str=user_local_date.strftime("%d %B %Y"),
                        sign_summary=sign_summary,
                        horoscope_text=horoscope_msg[:1000]
                    )
                    await send_whatsapp_template(
                        to_phone=user_phone,
                        template_name=template_name,
                        language_code=lang,
                        body_parameters=payload.to_body_parameters(),
                    )
                else:
                    await send_whatsapp_text(to_phone=user_phone, text_body=horoscope_msg)

                # 6. Record Outbound Message in Active Conversation
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

                # 7. Mark Date as Sent (Idempotency stamp)
                pref.last_horoscope_sent_date = user_local_date
                conv.last_activity_at = datetime.now(timezone.utc)
                await session.commit()

                stats["sent"] += 1
            except Exception as exc:
                logger.error("Failed to generate/deliver daily horoscope for user %s: %s", user.id, exc)
                stats["errors"] += 1
                await session.rollback()

        # 8. Record Non-PII Audit Event
        try:
            audit = AuditEvent(
                action="HOROSCOPE_BATCH_DISPATCH",
                user_id=None,
                actor="scheduler",
                ip_address=None,
                details=stats
            )
            session.add(audit)
            await session.commit()
        except Exception as audit_exc:
            logger.warning("Failed to record scheduler audit event: %s", audit_exc)

        logger.info("Daily horoscope batch dispatch completed: %s", stats)
        return stats


class BackgroundScheduler:
    """In-process background daemon for scheduled horoscope dispatch."""

    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._is_running = False
        self.last_run_stats: Optional[Dict[str, Any]] = None
        self.last_run_time: Optional[datetime] = None

    @property
    def is_running(self) -> bool:
        return self._is_running and self._task is not None and not self._task.done()

    def get_status(self) -> Dict[str, Any]:
        return {
            "enabled": self._is_running,
            "running": self.is_running,
            "last_run_time": self.last_run_time.isoformat() if self.last_run_time else None,
            "last_run_stats": self.last_run_stats,
        }

    def start(self, session_maker):
        """Starts the background worker task."""
        if self._is_running:
            return
        self._is_running = True
        self._task = asyncio.create_task(self._run_loop(session_maker))
        logger.info("Background horoscope scheduler started.")

    async def stop(self):
        """Stops the background worker task cleanly."""
        self._is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Background horoscope scheduler stopped.")

    async def _run_loop(self, session_maker):
        """Periodic loop executing hourly checks."""
        settings = get_settings()
        interval = settings.SCHEDULER_CHECK_INTERVAL_SECONDS

        while self._is_running:
            try:
                logger.debug("Background scheduler waking up for check cycle...")
                async with session_maker() as session:
                    stats = await dispatch_daily_horoscopes(session=session)
                    self.last_run_stats = stats
                    self.last_run_time = datetime.now(timezone.utc)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Background scheduler error during check cycle: %s", exc)

            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break


# Global singleton instance for app lifespan attachment
scheduler_daemon = BackgroundScheduler()
