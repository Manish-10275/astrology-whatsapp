"""Role-Based Access Control (RBAC) dependencies and authorization guards."""

import uuid
from typing import Callable, List
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.db.session import get_db_session
from api.db.models.admin import AdminUser, AdminRole
from api.security.token import decode_access_token, TokenExpiredError, TokenError

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_db_session)
) -> AdminUser:
    """FastAPI dependency to extract and authenticate the current administrative user."""
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed authorization token.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token = credentials.credentials
    try:
        payload = decode_access_token(token)
    except TokenExpiredError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token has expired.",
            headers={"WWW-Authenticate": "Bearer"}
        )
    except TokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    admin_id_str = payload.get("sub")
    if not admin_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload: missing subject.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    try:
        admin_uuid = uuid.UUID(admin_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin ID format in token.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    result = await session.execute(select(AdminUser).where(AdminUser.id == admin_uuid))
    admin = result.scalar_one_or_none()

    if not admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin user not found.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    if not admin.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin account is deactivated."
        )

    if admin.is_locked():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin account is temporarily locked due to failed login attempts."
        )

    return admin


def require_permission(required_permission: str) -> Callable:
    """Dependency factory checking whether the authenticated admin holds a specific permission."""
    async def permission_checker(
        current_admin: AdminUser = Depends(get_current_admin)
    ) -> AdminUser:
        granted_permissions = current_admin.get_permissions()
        if required_permission not in granted_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access forbidden: requires permission '{required_permission}'."
            )
        return current_admin
    return permission_checker


def require_role(required_role: AdminRole) -> Callable:
    """Dependency factory checking whether the authenticated admin holds a specific role."""
    async def role_checker(
        current_admin: AdminUser = Depends(get_current_admin)
    ) -> AdminUser:
        if current_admin.role != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access forbidden: requires role '{required_role.value}'."
            )
        return current_admin
    return role_checker
