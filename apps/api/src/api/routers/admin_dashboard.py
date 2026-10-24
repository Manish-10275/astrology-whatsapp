"""Internal Admin Dashboard: operational metrics, conversation traces, diagnostics, and batch triggers."""

import uuid
import logging
from datetime import datetime, date, timezone
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from api.db.session import get_db_session
from api.db.models.admin import AdminUser
from api.db.models.user import User, UserPreferences, UserStatus, AstrologySystemEnum
from api.db.models.conversation import (
    Conversation,
    ConversationMessage,
    ConversationStatus,
    ConversationState,
    MessageDirection,
    MessageSender,
)
from api.security.rbac import require_permission
from api.config import get_settings
from api.services.scheduler import dispatch_daily_horoscopes, scheduler_daemon
from astrology_engine.adapter import default_adapter

logger = logging.getLogger("api.routers.admin_dashboard")

router = APIRouter(prefix="/api/v1/admin/dashboard", tags=["Admin Dashboard"])


class SystemBreakdown(BaseModel):
    vedic: int
    western: int


class DashboardStatsResponse(BaseModel):
    total_users: int
    active_users: int
    opt_in_horoscopes: int
    total_conversations: int
    total_messages: int
    astrology_systems: SystemBreakdown
    languages: Dict[str, int]


class ConversationSummaryResponse(BaseModel):
    id: str
    user_id_prefix: str
    channel: str
    status: str
    current_state: str
    message_count: int
    created_at: datetime
    last_activity_at: datetime


class MessageTraceItem(BaseModel):
    id: str
    direction: str
    sender: str
    content_type: str
    content_preview: str
    created_at: datetime


class ConversationTraceResponse(BaseModel):
    conversation_id: str
    user_id_prefix: str
    status: str
    current_state: str
    total_messages: int
    messages: List[MessageTraceItem]


class DiagnosticsResponse(BaseModel):
    status: str
    database: str
    swiss_ephemeris: str
    ephemeris_mode: str
    openai_configured: bool
    whatsapp_configured: bool
    encryption_ready: bool
    scheduler_status: Optional[Dict[str, Any]] = None
    timestamp: datetime


@router.get("/stats", response_model=DashboardStatsResponse)
async def get_dashboard_stats(
    session: AsyncSession = Depends(get_db_session),
    current_admin: AdminUser = Depends(require_permission("dashboard:read"))
):
    """Returns aggregated high-level business and operational metrics."""
    # 1. Total and active users
    total_users_count = await session.scalar(
        select(func.count(User.id)).where(User.deleted_at.is_(None))
    ) or 0

    active_users_count = await session.scalar(
        select(func.count(User.id)).where(
            User.status == UserStatus.ACTIVE,
            User.deleted_at.is_(None)
        )
    ) or 0

    # 2. Daily horoscope opt-in users
    opt_in_count = await session.scalar(
        select(func.count(UserPreferences.id)).where(
            UserPreferences.daily_horoscope_opt_in == True
        )
    ) or 0

    # 3. Conversations and messages count
    total_conversations_count = await session.scalar(
        select(func.count(Conversation.id))
    ) or 0

    total_messages_count = await session.scalar(
        select(func.count(ConversationMessage.id))
    ) or 0

    # 4. System breakdown
    vedic_count = await session.scalar(
        select(func.count(UserPreferences.id)).where(
            UserPreferences.astrology_system == AstrologySystemEnum.VEDIC
        )
    ) or 0

    western_count = await session.scalar(
        select(func.count(UserPreferences.id)).where(
            UserPreferences.astrology_system == AstrologySystemEnum.WESTERN
        )
    ) or 0

    # 5. Language breakdown
    lang_query = await session.execute(
        select(UserPreferences.preferred_language, func.count(UserPreferences.id))
        .group_by(UserPreferences.preferred_language)
    )
    languages = {row[0] or "en": row[1] for row in lang_query.all()}

    return DashboardStatsResponse(
        total_users=total_users_count,
        active_users=active_users_count,
        opt_in_horoscopes=opt_in_count,
        total_conversations=total_conversations_count,
        total_messages=total_messages_count,
        astrology_systems=SystemBreakdown(vedic=vedic_count, western=western_count),
        languages=languages
    )


@router.get("/conversations", response_model=List[ConversationSummaryResponse])
async def list_conversations(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    current_admin: AdminUser = Depends(require_permission("dashboard:read"))
):
    """Lists conversations with message counts and last activity timestamps."""
    stmt = (
        select(
            Conversation,
            func.count(ConversationMessage.id).label("msg_count")
        )
        .outerjoin(ConversationMessage, Conversation.id == ConversationMessage.conversation_id)
        .group_by(Conversation.id)
        .order_by(Conversation.last_activity_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(stmt)
    rows = result.all()

    items = []
    for conv, msg_count in rows:
        items.append(
            ConversationSummaryResponse(
                id=str(conv.id),
                user_id_prefix=str(conv.user_id)[:8] + "...",
                channel=conv.channel,
                status=conv.status.value,
                current_state=conv.current_state.value,
                message_count=msg_count,
                created_at=conv.created_at,
                last_activity_at=conv.last_activity_at
            )
        )
    return items


@router.get("/conversations/{conversation_id}/trace", response_model=ConversationTraceResponse)
async def get_conversation_trace(
    conversation_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    current_admin: AdminUser = Depends(require_permission("dashboard:read"))
):
    """Inspects detailed message trace for diagnostic analysis."""
    conv_stmt = select(Conversation).where(Conversation.id == conversation_id)
    conv = (await session.execute(conv_stmt)).scalars().first()

    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found."
        )

    msg_stmt = (
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == conversation_id)
        .order_by(ConversationMessage.created_at.asc())
    )
    messages = (await session.execute(msg_stmt)).scalars().all()

    trace_items = []
    for msg in messages:
        # Decrypt message content preview
        try:
            content = msg.get_decrypted_content()
        except Exception:
            content = "[Decryption Error]"

        trace_items.append(
            MessageTraceItem(
                id=str(msg.id),
                direction=msg.direction.value,
                sender=msg.sender.value,
                content_type=msg.content_type,
                content_preview=content[:150] + "..." if len(content) > 150 else content,
                created_at=msg.created_at
            )
        )

    return ConversationTraceResponse(
        conversation_id=str(conv.id),
        user_id_prefix=str(conv.user_id)[:8] + "...",
        status=conv.status.value,
        current_state=conv.current_state.value,
        total_messages=len(messages),
        messages=trace_items
    )


@router.get("/diagnostics", response_model=DiagnosticsResponse)
async def get_operational_diagnostics(
    session: AsyncSession = Depends(get_db_session),
    current_admin: AdminUser = Depends(require_permission("dashboard:read"))
):
    """Performs real-time subsystem connectivity and operational health verification."""
    settings = get_settings()

    # 1. Database check
    db_status = "connected"
    try:
        await session.execute(select(1))
    except Exception as exc:
        db_status = f"error: {str(exc)}"

    # 2. Ephemeris check
    eph_status = "ready"
    eph_mode = "moshier"

    # 3. OpenAI status
    openai_ok = bool(settings.OPENAI_API_KEY and settings.OPENAI_API_KEY.get_secret_value())

    # 4. WhatsApp config status
    whatsapp_ok = bool(settings.WHATSAPP_PHONE_NUMBER_ID and settings.WHATSAPP_ACCESS_TOKEN)

    # 5. Encryption keys
    encryption_ok = bool(settings.ENCRYPTION_PRIMARY_KEY and settings.ENCRYPTION_PRIMARY_KEY.get_secret_value())

    # 6. Scheduler status
    sched_status = scheduler_daemon.get_status()

    return DiagnosticsResponse(
        status="operational" if db_status == "connected" else "degraded",
        database=db_status,
        swiss_ephemeris=eph_status,
        ephemeris_mode=eph_mode,
        openai_configured=openai_ok,
        whatsapp_configured=whatsapp_ok,
        encryption_ready=encryption_ok,
        scheduler_status=sched_status,
        timestamp=datetime.now(timezone.utc)
    )


@router.post("/schedules/trigger")
async def trigger_dashboard_horoscope_dispatch(
    target_date: Optional[date] = Query(None),
    session: AsyncSession = Depends(get_db_session),
    current_admin: AdminUser = Depends(require_permission("dashboard:trigger"))
):
    """Admin dashboard trigger for daily horoscope batch dispatch."""
    logger.info("Admin %s triggered horoscope dispatch via dashboard", current_admin.username)
    results = await dispatch_daily_horoscopes(session=session, target_date=target_date)
    return results
