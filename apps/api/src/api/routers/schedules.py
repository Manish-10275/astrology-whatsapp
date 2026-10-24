"""Horoscope dispatch and scheduled job trigger endpoints."""

import hmac
import logging
from datetime import date
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, status, Query, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import get_settings
from api.db.session import get_db_session
from api.db.models.admin import AdminUser
from api.security.rbac import get_current_admin, require_permission
from api.security.token import decode_access_token
from api.services.scheduler import dispatch_daily_horoscopes, scheduler_daemon

logger = logging.getLogger("api.routers.schedules")

router = APIRouter(prefix="/api/v1/schedules", tags=["Scheduled Tasks"])


class DispatchResponse(BaseModel):
    status: str = Field(default="completed")
    dispatch_date: str
    total_eligible: int
    sent: int
    skipped_already_sent: int
    skipped_no_profile: int
    skipped_wrong_time: int = 0
    errors: int
    message: Optional[str] = None


class SchedulerStatusResponse(BaseModel):
    enabled: bool
    running: bool
    last_run_time: Optional[str] = None
    last_run_stats: Optional[Dict[str, Any]] = None


async def verify_scheduler_caller(
    request: Request,
    x_scheduler_token: Optional[str] = Header(None, alias="X-Scheduler-Token"),
    session: AsyncSession = Depends(get_db_session)
) -> str:
    """Verifies that caller is either authorized via dedicated secret token or Admin JWT.
    
    Fail-closed: Rejects all requests that lack both credentials.
    """
    settings = get_settings()

    # 1. Check dedicated scheduler secret token if configured
    if x_scheduler_token and settings.SCHEDULER_SECRET_TOKEN and settings.SCHEDULER_SECRET_TOKEN.get_secret_value():
        expected_secret = settings.SCHEDULER_SECRET_TOKEN.get_secret_value()
        if hmac.compare_digest(x_scheduler_token.strip(), expected_secret):
            return "service:scheduler_token"

    # 2. Check Authorization Header (Bearer token could be admin JWT or secret token)
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()

        # Check if Bearer token matches dedicated scheduler secret
        if settings.SCHEDULER_SECRET_TOKEN and settings.SCHEDULER_SECRET_TOKEN.get_secret_value():
            if hmac.compare_digest(token, settings.SCHEDULER_SECRET_TOKEN.get_secret_value()):
                return "service:bearer_secret"

        # Check if Bearer token is an admin JWT with 'dashboard:trigger'
        try:
            payload = decode_access_token(token)
            permissions = payload.get("permissions", [])
            if "dashboard:trigger" in permissions:
                return f"admin:{payload.get('sub', 'unknown')}"
        except Exception:
            pass

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized: requires valid X-Scheduler-Token or Admin bearer token with 'dashboard:trigger' permission."
    )


@router.post("/daily-horoscopes/dispatch", response_model=DispatchResponse, status_code=status.HTTP_200_OK)
async def trigger_daily_horoscope_dispatch(
    target_date: Optional[date] = Query(None, description="Optional target date to dispatch (default: today)"),
    target_hour: Optional[int] = Query(None, ge=0, le=23, description="Optional local hour window (0-23) to filter users"),
    caller: str = Depends(verify_scheduler_caller),
    session: AsyncSession = Depends(get_db_session),
):
    """Triggers the automated daily horoscope batch runner idempotently.
    
    Requires administrative authentication with 'dashboard:trigger' OR pre-shared 'X-Scheduler-Token'.
    """
    logger.info("Caller '%s' triggered daily horoscope dispatch (date=%s, hour=%s)", caller, target_date, target_hour)
    results = await dispatch_daily_horoscopes(session=session, target_date=target_date, target_hour=target_hour)
    return results


@router.get("/daily-horoscopes/status", response_model=SchedulerStatusResponse)
async def get_scheduler_status(
    caller: str = Depends(verify_scheduler_caller)
):
    """Reports status of the in-process background scheduler worker."""
    return scheduler_daemon.get_status()
