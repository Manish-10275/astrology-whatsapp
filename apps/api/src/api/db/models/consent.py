"""Consent tracking and revocation models complying with GDPR and India DPDP 2023."""

import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.db.base import Base


class ConsentRecord(Base):
    """Immutable record of affirmative user consent or revocation."""
    __tablename__ = "consent_records"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )
    purpose: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g., 'privacy_policy', 'birth_data_processing'
    policy_version: Mapped[str] = mapped_column(String(32), nullable=False)  # e.g., 'v1.0'
    granted: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    channel: Mapped[str] = mapped_column(String(32), default="whatsapp", nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="consent_records")
