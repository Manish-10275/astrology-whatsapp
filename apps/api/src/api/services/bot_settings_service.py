"""Service for managing persistent bot operational controls and custom messages."""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.bot_settings import BotSettings
from api.db.models.admin import AdminUser
from api.db.models.audit import AuditEvent

logger = logging.getLogger("api.services.bot_settings_service")

SETTINGS_SINGLETON_KEY = "default"


async def get_or_create_bot_settings(session: AsyncSession) -> BotSettings:
    """Retrieves the singleton bot settings, initializing with defaults if missing."""
    stmt = select(BotSettings).where(BotSettings.key == SETTINGS_SINGLETON_KEY)
    result = await session.execute(stmt)
    settings = result.scalar_one_or_none()

    if settings is None:
        logger.info("Initializing singleton BotSettings row with defaults.")
        try:
            settings = BotSettings(key=SETTINGS_SINGLETON_KEY)
            session.add(settings)
            await session.commit()
            await session.refresh(settings)
        except Exception:
            await session.rollback()
            result = await session.execute(stmt)
            settings = result.scalar_one_or_none()

    return settings


async def update_bot_settings(
    session: AsyncSession,
    admin: AdminUser,
    update_data: Dict[str, Any],
    ip_address: Optional[str] = None,
) -> BotSettings:
    """Updates bot settings with validation and creates an immutable audit event."""
    settings = await get_or_create_bot_settings(session)

    allowed_fields = {
        "is_paused",
        "maintenance_mode",
        "welcome_message",
        "fallback_message",
        "general_instructions",
        "horoscope_intro",
        "maintenance_message",
        "extra_config",
    }

    updated_fields = []
    for field, value in update_data.items():
        if field in allowed_fields and value is not None:
            if isinstance(value, str):
                val_stripped = value.strip()
                if not val_stripped and field in {
                    "welcome_message",
                    "fallback_message",
                    "maintenance_message",
                }:
                    raise ValueError(f"{field} cannot be empty.")
                setattr(settings, field, val_stripped)
            else:
                setattr(settings, field, value)
            updated_fields.append(field)

    if updated_fields:
        settings.updated_at = datetime.now(timezone.utc)
        settings.updated_by = admin.username

        audit = AuditEvent(
            actor_id=str(admin.id),
            actor_role=admin.role.value if hasattr(admin.role, "value") else str(admin.role),
            action="BOT_SETTINGS_UPDATE",
            target_entity="bot_settings",
            target_id=SETTINGS_SINGLETON_KEY,
            details={"updated_fields": updated_fields},
            ip_address=ip_address,
        )
        session.add(audit)
        await session.commit()
        await session.refresh(settings)
        logger.info("Admin %s updated bot settings: %s", admin.username, updated_fields)

    return settings


async def set_bot_pause_state(
    session: AsyncSession,
    admin: AdminUser,
    is_paused: bool,
    maintenance_mode: Optional[bool] = None,
    ip_address: Optional[str] = None,
) -> BotSettings:
    """Toggles bot pause and optional maintenance mode with an audit log."""
    settings = await get_or_create_bot_settings(session)
    settings.is_paused = is_paused
    if maintenance_mode is not None:
        settings.maintenance_mode = maintenance_mode

    settings.updated_at = datetime.now(timezone.utc)
    settings.updated_by = admin.username

    action = "BOT_PAUSE" if is_paused else "BOT_RESUME"
    audit = AuditEvent(
        actor_id=str(admin.id),
        actor_role=admin.role.value if hasattr(admin.role, "value") else str(admin.role),
        action=action,
        target_entity="bot_settings",
        target_id=SETTINGS_SINGLETON_KEY,
        details={
            "is_paused": is_paused,
            "maintenance_mode": settings.maintenance_mode,
        },
        ip_address=ip_address,
    )
    session.add(audit)
    await session.commit()
    await session.refresh(settings)
    logger.info("Admin %s performed %s (maintenance=%s)", admin.username, action, settings.maintenance_mode)
    return settings
