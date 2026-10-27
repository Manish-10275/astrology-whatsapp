"""Admin router for Message Center: direct outbound messaging, recipient eligibility, and delivery status."""

import uuid
import logging
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import get_db_session
from api.db.models.admin import AdminUser
from api.security.rbac import require_permission
from api.services.message_center import (
    list_eligible_recipients,
    get_recipient_window_status,
    send_direct_user_message,
    send_direct_template_message,
    get_recent_outbound_messages,
)
from api.services.whatsapp_templates import WhatsAppTemplateError

logger = logging.getLogger("api.routers.admin_messages")

router = APIRouter(prefix="/api/v1/admin/messages", tags=["Admin Message Center"])


class DirectMessageSendRequest(BaseModel):
    user_id: uuid.UUID
    message_text: str = Field(..., min_length=1, max_length=2000)
    confirmed: bool = Field(False, description="Explicit confirmation required to prevent accidental sends")


class DirectTemplateSendRequest(BaseModel):
    user_id: uuid.UUID
    template_name: str = Field(..., min_length=1, max_length=512)
    language_code: str = Field("en", min_length=2, max_length=10)
    body_parameters: List[str] = Field(default_factory=list)
    header_parameters: Optional[List[str]] = None
    confirmed: bool = Field(False, description="Explicit confirmation required to prevent accidental sends")


@router.get("/recipients")
async def get_recipients_endpoint(
    limit: int = 50,
    session: AsyncSession = Depends(get_db_session),
    current_admin: AdminUser = Depends(require_permission("messages:send")),
):
    """Lists active, opted-in WhatsApp recipients with their current 24-hour service window status."""
    recipients = await list_eligible_recipients(session=session, limit=limit)
    return {"recipients": recipients, "total": len(recipients)}


@router.get("/recipients/{user_id}/status")
async def get_recipient_status_endpoint(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    current_admin: AdminUser = Depends(require_permission("messages:send")),
):
    """Returns the 24-hour customer service window status for a specific recipient."""
    window_status = await get_recipient_window_status(session=session, user_id=user_id)
    return window_status


@router.post("/send")
async def send_direct_message_endpoint(
    body: DirectMessageSendRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    current_admin: AdminUser = Depends(require_permission("messages:send")),
):
    """Sends a single direct WhatsApp message to an eligible recipient with confirmation."""
    if not body.confirmed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmation required. Please explicitly confirm recipient and message before sending.",
        )

    client_ip = request.client.host if request.client else None
    try:
        result = await send_direct_user_message(
            session=session,
            admin=current_admin,
            user_id=body.user_id,
            message_text=body.message_text,
            ip_address=client_ip,
        )
        return result
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_err),
        )
    except Exception as exc:
        logger.error("Failed to deliver direct message to user %s: %s", body.user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Message delivery failed: {str(exc)}",
        )


@router.post("/send-template")
async def send_direct_template_endpoint(
    body: DirectTemplateSendRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    current_admin: AdminUser = Depends(require_permission("messages:send")),
):
    """Sends an approved Meta WhatsApp template to an eligible recipient (allowed outside 24h window)."""
    if not body.confirmed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmation required. Please explicitly confirm recipient and template before sending.",
        )

    client_ip = request.client.host if request.client else None
    try:
        result = await send_direct_template_message(
            session=session,
            admin=current_admin,
            user_id=body.user_id,
            template_name=body.template_name,
            language_code=body.language_code,
            body_parameters=body.body_parameters,
            header_parameters=body.header_parameters,
            ip_address=client_ip,
        )
        return result
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_err),
        )
    except WhatsAppTemplateError as templ_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Template delivery failed: {str(templ_err)}",
        )
    except Exception as exc:
        logger.error("Failed to deliver template '%s' to user %s: %s", body.template_name, body.user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Message delivery failed: {str(exc)}",
        )


@router.get("/recent")
async def get_recent_messages_endpoint(
    limit: int = 30,
    session: AsyncSession = Depends(get_db_session),
    current_admin: AdminUser = Depends(require_permission("messages:send")),
):
    """Returns recent outbound messages with their real-time delivery status tracking."""
    recent_messages = await get_recent_outbound_messages(session=session, limit=limit)
    return {"messages": recent_messages, "total": len(recent_messages)}
