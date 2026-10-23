"""GDPR and DPDP Right-to-Erasure deletion tracking models."""

import uuid
from datetime import datetime, timezone
from typing import Optional
from enum import Enum
from sqlalchemy import String, Integer, Text, DateTime, Enum as SQLEnum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from api.db.base import Base


class DeletionStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class DeletionRequest(Base):
    """Tracks asynchronous and idempotent privacy erasure requests.
    
    Retained independently with pseudonymized phone_hash to audit compliance fulfillment.
    """
    __tablename__ = "deletion_requests"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    phone_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    status: Mapped[DeletionStatus] = mapped_column(
        SQLEnum(DeletionStatus, name="deletion_status_enum", native_enum=False),
        default=DeletionStatus.PENDING,
        nullable=False
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    records_deleted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
