"""Admin user and role-based access control (RBAC) persistence models."""

import uuid
from datetime import datetime, timezone
from typing import Optional, List
from enum import Enum
from sqlalchemy import String, Boolean, Integer, DateTime, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column

from api.db.base import Base


class AdminRole(str, Enum):
    SUPER_ADMIN = "super_admin"
    SUPPORT = "support"
    ASTROLOGY_QA = "astrology_qa"
    COMPLIANCE = "compliance"


# Mapping of roles to granted granular permissions
ROLE_PERMISSIONS = {
    AdminRole.SUPER_ADMIN: [
        "admin:manage",
        "user:read",
        "user:write",
        "profile:read_sensitive",
        "consent:read",
        "consent:revoke",
        "deletion:execute",
        "audit:read",
    ],
    AdminRole.SUPPORT: [
        "user:read",
        "consent:read",
        "audit:read",
    ],
    AdminRole.ASTROLOGY_QA: [
        "user:read",
        "profile:read_sensitive",
        "audit:read",
    ],
    AdminRole.COMPLIANCE: [
        "user:read",
        "consent:read",
        "consent:revoke",
        "deletion:execute",
        "audit:read",
    ],
}


class AdminUser(Base):
    """Internal administrator user record."""
    __tablename__ = "admin_users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[AdminRole] = mapped_column(
        SQLEnum(AdminRole, name="admin_role_enum", native_enum=False),
        default=AdminRole.SUPPORT,
        nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    def is_locked(self) -> bool:
        """Returns True if the account is temporarily locked due to failed login attempts."""
        if self.locked_until is None:
            return False
        return datetime.now(timezone.utc) < self.locked_until

    def get_permissions(self) -> List[str]:
        """Returns the list of permissions associated with the user's role."""
        return ROLE_PERMISSIONS.get(self.role, [])
