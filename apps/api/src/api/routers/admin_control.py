"""Admin router for bot operational controls, pause/resume, and custom message configuration."""

import logging
from datetime import datetime
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import get_db_session
from api.db.models.admin import AdminUser
from api.security.rbac import require_permission
from api.services.bot_settings_service import (
    get_or_create_bot_settings,
    update_bot_settings,
    set_bot_pause_state,
)

logger = logging.getLogger("api.routers.admin_control")

router = APIRouter(prefix="/api/v1/admin/control", tags=["Admin Bot Control & Settings"])


class BotSettingsResponse(BaseModel):
    key: str
    is_paused: bool
    maintenance_mode: bool
    welcome_message: str
    fallback_message: str
    general_instructions: str
    horoscope_intro: str
    maintenance_message: str
    extra_config: Dict[str, Any]
    updated_at: datetime
    updated_by: Optional[str]


class BotSettingsUpdateRequest(BaseModel):
    welcome_message: Optional[str] = Field(None, max_length=2000)
    fallback_message: Optional[str] = Field(None, max_length=2000)
    general_instructions: Optional[str] = Field(None, max_length=4000)
    horoscope_intro: Optional[str] = Field(None, max_length=1000)
    maintenance_message: Optional[str] = Field(None, max_length=2000)
    extra_config: Optional[Dict[str, Any]] = None


class BotPauseRequest(BaseModel):
    maintenance_mode: bool = False


@router.get("/settings", response_model=BotSettingsResponse)
async def get_bot_settings_endpoint(
    session: AsyncSession = Depends(get_db_session),
    current_admin: AdminUser = Depends(require_permission("settings:read")),
):
    """Retrieves current bot configuration, operational controls, and custom messages."""
    settings = await get_or_create_bot_settings(session)
    return BotSettingsResponse(
        key=settings.key,
        is_paused=settings.is_paused,
        maintenance_mode=settings.maintenance_mode,
        welcome_message=settings.welcome_message,
        fallback_message=settings.fallback_message,
        general_instructions=settings.general_instructions,
        horoscope_intro=settings.horoscope_intro,
        maintenance_message=settings.maintenance_message,
        extra_config=settings.extra_config or {},
        updated_at=settings.updated_at,
        updated_by=settings.updated_by,
    )


@router.put("/settings", response_model=BotSettingsResponse)
async def update_bot_settings_endpoint(
    body: BotSettingsUpdateRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    current_admin: AdminUser = Depends(require_permission("settings:write")),
):
    """Updates bot configuration and custom messages with validation and audit logging."""
    update_data = body.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No update fields provided.",
        )

    client_ip = request.client.host if request.client else None
    try:
        updated = await update_bot_settings(
            session=session,
            admin=current_admin,
            update_data=update_data,
            ip_address=client_ip,
        )
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(val_err),
        )

    return BotSettingsResponse(
        key=updated.key,
        is_paused=updated.is_paused,
        maintenance_mode=updated.maintenance_mode,
        welcome_message=updated.welcome_message,
        fallback_message=updated.fallback_message,
        general_instructions=updated.general_instructions,
        horoscope_intro=updated.horoscope_intro,
        maintenance_message=updated.maintenance_message,
        extra_config=updated.extra_config or {},
        updated_at=updated.updated_at,
        updated_by=updated.updated_by,
    )


@router.post("/bot/pause")
async def pause_bot_endpoint(
    body: BotPauseRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    current_admin: AdminUser = Depends(require_permission("bot:control")),
):
    """Pauses bot automatic replies with optional maintenance mode."""
    client_ip = request.client.host if request.client else None
    settings = await set_bot_pause_state(
        session=session,
        admin=current_admin,
        is_paused=True,
        maintenance_mode=body.maintenance_mode,
        ip_address=client_ip,
    )
    return {
        "status": "success",
        "action": "paused",
        "is_paused": settings.is_paused,
        "maintenance_mode": settings.maintenance_mode,
        "updated_at": settings.updated_at.isoformat(),
        "updated_by": settings.updated_by,
    }


@router.post("/bot/resume")
async def resume_bot_endpoint(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    current_admin: AdminUser = Depends(require_permission("bot:control")),
):
    """Resumes normal bot operations."""
    client_ip = request.client.host if request.client else None
    settings = await set_bot_pause_state(
        session=session,
        admin=current_admin,
        is_paused=False,
        maintenance_mode=False,
        ip_address=client_ip,
    )
    return {
        "status": "success",
        "action": "resumed",
        "is_paused": settings.is_paused,
        "maintenance_mode": settings.maintenance_mode,
        "updated_at": settings.updated_at.isoformat(),
        "updated_by": settings.updated_by,
    }
