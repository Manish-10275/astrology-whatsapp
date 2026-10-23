"""Administrative endpoints for user and profile metadata inspection."""

import uuid
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime

from api.db.session import get_db_session
from api.db.models.user import User, UserStatus
from api.db.models.birth_profile import BirthProfile
from api.db.models.admin import AdminUser
from api.db.models.audit import AuditEvent
from api.security.rbac import require_permission

router = APIRouter(prefix="/api/v1/admin/users", tags=["Admin User Management"])


class UserMetadataResponse(BaseModel):
    id: str
    phone_hash_prefix: str
    status: str
    preferred_language: str
    astrology_system: str
    profile_count: int
    created_at: datetime


class ProfileMetadataResponse(BaseModel):
    id: str
    profile_label: str
    is_primary: bool
    time_uncertainty: str
    timezone_name: str
    created_at: datetime


class UserDetailResponse(BaseModel):
    id: str
    phone_hash: str
    status: str
    preferred_language: str
    astrology_system: str
    created_at: datetime
    profiles: List[ProfileMetadataResponse]


@router.get("", response_model=List[UserMetadataResponse])
async def list_users(
    session: AsyncSession = Depends(get_db_session),
    current_admin: AdminUser = Depends(require_permission("user:read"))
):
    """Lists registered customer accounts with phone numbers masked to prevent PII leakage."""
    result = await session.execute(
        select(User).order_by(User.created_at.desc()).limit(100)
    )
    users = result.scalars().all()

    items = []
    for u in users:
        lang = u.preferences.preferred_language if u.preferences else "en"
        sys_type = u.preferences.astrology_system.value if u.preferences else "vedic"
        items.append(
            UserMetadataResponse(
                id=str(u.id),
                phone_hash_prefix=u.phone_hash[:8] + "...",
                status=u.status.value,
                preferred_language=lang,
                astrology_system=sys_type,
                profile_count=len(u.birth_profiles),
                created_at=u.created_at
            )
        )
    return items


@router.get("/{user_id}", response_model=UserDetailResponse)
async def get_user_detail(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    current_admin: AdminUser = Depends(require_permission("user:read"))
):
    """Retrieves user metadata and non-sensitive birth profile labels."""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID '{user_id}' not found."
        )

    lang = user.preferences.preferred_language if user.preferences else "en"
    sys_type = user.preferences.astrology_system.value if user.preferences else "vedic"

    profiles = [
        ProfileMetadataResponse(
            id=str(p.id),
            profile_label=p.profile_label,
            is_primary=p.is_primary,
            time_uncertainty=p.time_uncertainty.value,
            timezone_name=p.timezone_name,
            created_at=p.created_at
        )
        for p in user.birth_profiles
    ]

    return UserDetailResponse(
        id=str(user.id),
        phone_hash=user.phone_hash,
        status=user.status.value,
        preferred_language=lang,
        astrology_system=sys_type,
        created_at=user.created_at,
        profiles=profiles
    )


@router.get("/{user_id}/profiles/{profile_id}/sensitive")
async def get_sensitive_birth_details(
    user_id: uuid.UUID,
    profile_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    current_admin: AdminUser = Depends(require_permission("profile:read_sensitive"))
):
    """Secure, audited endpoint allowing authorized roles to inspect decrypted birth details."""
    result = await session.execute(
        select(BirthProfile).where(
            BirthProfile.id == profile_id,
            BirthProfile.user_id == user_id
        )
    )
    profile = result.scalar_one_or_none()

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Birth profile not found."
        )

    # Mandatory security audit log for sensitive data access
    audit_event = AuditEvent(
        actor_id=str(current_admin.id),
        actor_role=current_admin.role.value,
        action="PROFILE_SENSITIVE_READ",
        target_entity="birth_profile",
        target_id=str(profile.id),
        details={"user_id": str(user_id)},
        ip_address=request.client.host if request.client else None
    )
    session.add(audit_event)
    await session.commit()

    decrypted = profile.get_decrypted_details()
    return {
        "profile_id": str(profile.id),
        "user_id": str(user_id),
        "profile_label": profile.profile_label,
        "birth_date": decrypted["birth_date"].isoformat(),
        "birth_time": decrypted["birth_time"].isoformat() if decrypted["birth_time"] else None,
        "latitude": decrypted["latitude"],
        "longitude": decrypted["longitude"],
        "location_name": decrypted["location_name"],
        "timezone_name": decrypted["timezone_name"],
        "time_uncertainty": decrypted["time_uncertainty"].value
    }
