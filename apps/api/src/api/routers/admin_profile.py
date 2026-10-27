"""Admin router for Meta WhatsApp Business Profile management and profile photo upload."""

import logging
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field, EmailStr
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import get_db_session
from api.db.models.admin import AdminUser
from api.db.models.audit import AuditEvent
from api.security.rbac import require_permission
from api.services.whatsapp_profile import (
    get_whatsapp_business_profile,
    update_whatsapp_business_profile,
    upload_whatsapp_profile_photo,
    WhatsAppProfileError,
)

logger = logging.getLogger("api.routers.admin_profile")

router = APIRouter(prefix="/api/v1/admin/whatsapp/profile", tags=["Admin WhatsApp Profile"])


class WhatsAppProfileUpdateRequest(BaseModel):
    about: Optional[str] = Field(None, max_length=139)
    address: Optional[str] = Field(None, max_length=256)
    description: Optional[str] = Field(None, max_length=512)
    email: Optional[str] = Field(None, max_length=128)
    websites: Optional[List[str]] = Field(None, max_length=2)
    vertical: Optional[str] = Field(None, max_length=64)


@router.get("")
async def get_profile_endpoint(
    current_admin: AdminUser = Depends(require_permission("settings:read")),
):
    """Fetches the live WhatsApp Business Profile from Meta Cloud API."""
    try:
        profile = await get_whatsapp_business_profile()
        return profile
    except WhatsAppProfileError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )


@router.post("")
async def update_profile_endpoint(
    body: WhatsAppProfileUpdateRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    current_admin: AdminUser = Depends(require_permission("profile:manage")),
):
    """Updates WhatsApp Business Profile fields via Meta Cloud API."""
    try:
        res = await update_whatsapp_business_profile(
            about=body.about,
            address=body.address,
            description=body.description,
            email=body.email,
            websites=body.websites,
            vertical=body.vertical,
        )

        client_ip = request.client.host if request.client else None
        audit = AuditEvent(
            actor_id=str(current_admin.id),
            actor_role=current_admin.role.value if hasattr(current_admin.role, "value") else str(current_admin.role),
            action="WHATSAPP_PROFILE_UPDATE",
            target_entity="whatsapp_business_profile",
            target_id="meta_business_profile",
            details={
                "updated_keys": [k for k, v in body.model_dump(exclude_unset=True).items() if v is not None]
            },
            ip_address=client_ip,
        )
        session.add(audit)
        await session.commit()

        return {"status": "success", "result": res}
    except WhatsAppProfileError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )


@router.post("/photo")
async def upload_profile_photo_endpoint(
    file: UploadFile = File(...),
    request: Request = None,
    session: AsyncSession = Depends(get_db_session),
    current_admin: AdminUser = Depends(require_permission("profile:manage")),
):
    """Uploads a new profile picture to Meta and updates the profile picture handle."""
    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    try:
        res = await upload_whatsapp_profile_photo(
            file_bytes=content,
            filename=file.filename or "profile.jpg",
        )

        client_ip = request.client.host if request and request.client else None
        audit = AuditEvent(
            actor_id=str(current_admin.id),
            actor_role=current_admin.role.value if hasattr(current_admin.role, "value") else str(current_admin.role),
            action="WHATSAPP_PROFILE_PHOTO_UPLOAD",
            target_entity="whatsapp_business_profile",
            target_id="profile_photo",
            details={"filename": file.filename, "size_bytes": len(content)},
            ip_address=client_ip,
        )
        session.add(audit)
        await session.commit()

        return {"status": "success", "result": res}
    except WhatsAppProfileError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
