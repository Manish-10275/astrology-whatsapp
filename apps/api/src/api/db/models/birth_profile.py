"""Birth profile model with field-level encryption for sensitive astrological coordinates."""

import uuid
from datetime import datetime, date, time, timezone
from typing import Optional, Dict, Any
from enum import Enum
from sqlalchemy import String, Boolean, Text, DateTime, Enum as SQLEnum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.db.base import Base
from api.security.encryption import encrypt_field, decrypt_field


class TimeUncertaintyEnum(str, Enum):
    EXACT = "exact"
    APPROXIMATE_WINDOW = "approximate_window"
    UNKNOWN = "unknown"


class BirthProfile(Base):
    """Birth profile record storing sensitive birth details encrypted with AES-256-GCM.
    
    Fields encrypted at rest:
    - encrypted_birth_date (YYYY-MM-DD)
    - encrypted_birth_time (HH:MM:SS)
    - encrypted_latitude (decimal float string)
    - encrypted_longitude (decimal float string)
    - encrypted_location_name (e.g., 'Mumbai, India')
    """
    __tablename__ = "birth_profiles"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )
    profile_label: Mapped[str] = mapped_column(String(64), default="Self", nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    time_uncertainty: Mapped[TimeUncertaintyEnum] = mapped_column(
        SQLEnum(TimeUncertaintyEnum, name="time_uncertainty_enum", native_enum=False),
        default=TimeUncertaintyEnum.EXACT,
        nullable=False
    )

    # Sensitive encrypted attributes (AES-256-GCM authenticated ciphertexts)
    encrypted_birth_date: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_birth_time: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    encrypted_latitude: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_longitude: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_location_name: Mapped[str] = mapped_column(Text, nullable=False)

    # Operational non-sensitive routing attribute
    timezone_name: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g., 'Asia/Kolkata'

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

    user: Mapped["User"] = relationship("User", back_populates="birth_profiles")

    def set_birth_details(
        self,
        birth_date: date | str,
        birth_time: Optional[time | str],
        latitude: float,
        longitude: float,
        location_name: str,
        key_version: Optional[str] = None
    ) -> None:
        """Encrypts and stores sensitive birth parameters."""
        b_date_str = birth_date.isoformat() if hasattr(birth_date, "isoformat") else str(birth_date)
        b_time_str = (
            birth_time.isoformat() if hasattr(birth_time, "isoformat") else str(birth_time)
        ) if birth_time is not None else None

        self.encrypted_birth_date = encrypt_field(b_date_str, key_version)
        self.encrypted_birth_time = (
            encrypt_field(b_time_str, key_version) if b_time_str else None
        )
        self.encrypted_latitude = encrypt_field(str(latitude), key_version)
        self.encrypted_longitude = encrypt_field(str(longitude), key_version)
        self.encrypted_location_name = encrypt_field(location_name, key_version)

    def get_decrypted_details(self) -> Dict[str, Any]:
        """Decrypts and verifies authentication of sensitive birth fields.
        
        Fail-closed: Raises DecryptionError if tampered with or unauthenticated.
        """
        b_date_str = decrypt_field(self.encrypted_birth_date)
        b_time_str = (
            decrypt_field(self.encrypted_birth_time) if self.encrypted_birth_time else None
        )
        lat_str = decrypt_field(self.encrypted_latitude)
        lon_str = decrypt_field(self.encrypted_longitude)
        loc_str = decrypt_field(self.encrypted_location_name)

        return {
            "birth_date": date.fromisoformat(b_date_str),
            "birth_time": time.fromisoformat(b_time_str) if b_time_str else None,
            "latitude": float(lat_str),
            "longitude": float(lon_str),
            "location_name": loc_str,
            "timezone_name": self.timezone_name,
            "time_uncertainty": self.time_uncertainty
        }
