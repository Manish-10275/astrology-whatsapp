"""Horoscope dispatch and scheduled job trigger endpoints."""

import logging
from datetime import date
from typing import Optional, Dict, Any
from pydantic import BaseModel
from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import get_db_session
from api.db.models.admin import AdminUser
from api.security.rbac import require_permission
from api.services.scheduler import dispatch_daily_horoscopes

logger = logging.getLogger("api.routers.schedules")

router = APIRouter(prefix="/api/v1/schedules", tags=["Scheduled Tasks"])


class DispatchResponse(BaseModel):
    dispatch_date: str
    total_eligible: int
    sent: int
    skipped_already_sent: int
    skipped_no_profile: int
    errors: int


@router.post("/daily-horoscopes/dispatch", response_model=DispatchResponse, status_code=status.HTTP_200_OK)
async def trigger_daily_horoscope_dispatch(
    target_date: Optional[date] = Query(None, description="Optional target date to dispatch (default: today)"),
    session: AsyncSession = Depends(get_db_session),
    current_admin: AdminUser = Depends(require_permission("dashboard:trigger"))
):
    """Triggers the automated daily horoscope batch runner idempotently.
    
    Requires administrative permission 'dashboard:trigger' (Super Admin).
    """
    logger.info("Admin %s triggered manual daily horoscope dispatch", current_admin.username)
    results = await dispatch_daily_horoscopes(session=session, target_date=target_date)
    return results
