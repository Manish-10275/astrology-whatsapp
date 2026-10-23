"""User identity and preference models."""

import uuid
from datetime import datetime, timezone
from typing import Optional, List
from enum import Enum
from sqlalchemy import String, Text, DateTime, Enum as SQLEnum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.db.base import Base


class UserStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELETED = "deleted"
    ANONYMIZED = "anonymized"


class AstrologySystemEnum(str, Enum):
    VEDIC = "vedic"
    WESTERN = "western"


class User(Base):
    """Core user record linked to WhatsApp identity.
    
    Privacy standard:
    - phone_hash: HMAC-SHA256(phone, salt) for deterministic, indexable lookups.
    - encrypted_phone: AES-256-GCM encrypted E.164 phone number.
    - No plain text PII is ever stored in queryable columns.
    """
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    phone_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    encrypted_phone: Mapped[str] = mapped_column(Text, nullable=False)
    whatsapp_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[UserStatus] = mapped_column(
        SQLEnum(UserStatus, name="user_status_enum", native_enum=False),
        default=UserStatus.ACTIVE,
        nullable=False
    )
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
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    preferences: Mapped[Optional["UserPreferences"]] = relationship(
        "UserPreferences",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    consent_records: Mapped[List["ConsentRecord"]] = relationship(
        "ConsentRecord",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    birth_profiles: Mapped[List["BirthProfile"]] = relationship(
        "BirthProfile",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin"
    )


class UserPreferences(Base):
    """User astrological and language settings."""
    __tablename__ = "user_preferences"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False
    )
    astrology_system: Mapped[AstrologySystemEnum] = mapped_column(
        SQLEnum(AstrologySystemEnum, name="astrology_system_enum", native_enum=False),
        default=AstrologySystemEnum.VEDIC,
        nullable=False
    )
    preferred_language: Mapped[str] = mapped_column(String(10), default="en", nullable=False)
    auto_detect_language: Mapped[bool] = mapped_column(default=True, nullable=False)
    ayanamsa: Mapped[str] = mapped_column(String(32), default="lahiri", nullable=False)
    house_system: Mapped[str] = mapped_column(String(32), default="placidus", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="preferences")
