"""Security and administrative audit event models."""

import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy import String, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column

from api.db.base import Base


class AuditEvent(Base):
    """Immutable audit log for security, administrative, and compliance actions."""
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False)  # Admin user ID, 'USER_SELF', or 'SYSTEM'
    actor_role: Mapped[str] = mapped_column(String(32), nullable=False)  # 'super_admin', 'user', 'system'
    action: Mapped[str] = mapped_column(String(64), index=True, nullable=False)  # 'LOGIN_SUCCESS', 'USER_DATA_ERASURE', etc.
    target_entity: Mapped[str] = mapped_column(String(64), nullable=False)  # 'user', 'birth_profile', etc.
    target_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
        nullable=False
    )
