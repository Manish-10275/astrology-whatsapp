"""Admin authentication, login rate-limiting, and session validation endpoints."""

from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.config import get_settings
from api.db.session import get_db_session
from api.db.models.admin import AdminUser
from api.db.models.audit import AuditEvent
from api.security.hashing import verify_password
from api.security.token import create_access_token
from api.security.rbac import get_current_admin

router = APIRouter(prefix="/api/v1/admin/auth", tags=["Admin Authentication"])


class LoginRequest(BaseModel):
    username: str = Field(..., description="Administrator username")
    password: str = Field(..., description="Administrator password")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int
    role: str
    username: str


class AdminMeResponse(BaseModel):
    id: str
    username: str
    email: str
    role: str
    permissions: list[str]
    last_login_at: datetime | None


@router.post("/login", response_model=TokenResponse)
async def admin_login(
    payload: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session)
):
    """Authenticates administrator credentials with Argon2id and brute-force lockout."""
    settings = get_settings()
    ip_addr = request.client.host if request.client else None

    # Fetch admin user
    result = await session.execute(
        select(AdminUser).where(AdminUser.username == payload.username)
    )
    admin = result.scalar_one_or_none()

    now_utc = datetime.now(timezone.utc)

    if not admin:
        # Prevent username enumeration with constant-time response behavior
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    if not admin.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Contact a system administrator."
        )

    # Check brute-force lockout
    if admin.is_locked():
        lockout_remaining_secs = int((admin.locked_until - now_utc).total_seconds())
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account is temporarily locked. Try again in {lockout_remaining_secs} seconds."
        )

    # Verify password
    is_valid = verify_password(payload.password, admin.password_hash)

    if not is_valid:
        admin.failed_login_attempts += 1
        audit_event = AuditEvent(
            actor_id=payload.username,
            actor_role="unknown",
            action="LOGIN_FAILED",
            target_entity="admin_user",
            target_id=str(admin.id),
            details={"attempt": admin.failed_login_attempts},
            ip_address=ip_addr
        )
        session.add(audit_event)

        # Trigger lockout if threshold reached
        if admin.failed_login_attempts >= settings.AUTH_MAX_FAILED_ATTEMPTS:
            admin.locked_until = now_utc + timedelta(minutes=settings.AUTH_LOCKOUT_MINUTES)

        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # Password verified: reset failure counter and record success
    admin.failed_login_attempts = 0
    admin.locked_until = None
    admin.last_login_at = now_utc

    audit_success = AuditEvent(
        actor_id=str(admin.id),
        actor_role=admin.role.value,
        action="LOGIN_SUCCESS",
        target_entity="admin_user",
        target_id=str(admin.id),
        ip_address=ip_addr
    )
    session.add(audit_success)
    await session.commit()

    token = create_access_token(
        admin_id=str(admin.id),
        username=admin.username,
        role=admin.role.value,
        permissions=admin.get_permissions()
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in_seconds=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        role=admin.role.value,
        username=admin.username
    )


@router.get("/me", response_model=AdminMeResponse)
async def get_current_admin_profile(
    current_admin: AdminUser = Depends(get_current_admin)
):
    """Returns the authenticated administrator's profile and assigned permissions."""
    return AdminMeResponse(
        id=str(current_admin.id),
        username=current_admin.username,
        email=current_admin.email,
        role=current_admin.role.value,
        permissions=current_admin.get_permissions(),
        last_login_at=current_admin.last_login_at
    )
