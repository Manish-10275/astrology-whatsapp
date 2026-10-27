"""Persistent bot controls, custom messages, and platform operational settings."""

import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy import String, Boolean, Text, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column

from api.db.base import Base

DEFAULT_WELCOME_MESSAGE = (
    "Welcome to the Astrology Assistant! 🌟 I provide personalized astrological readings "
    "grounded in high-precision astronomical calculations (Vedic and Western).\n\n"
    "Before we begin, do you consent to the secure storage and processing of your birth details "
    "(date, time, place) to calculate your astrological chart?\n\n"
    "Please reply *YES* to agree and begin, or *NO* to decline."
)

DEFAULT_FALLBACK_MESSAGE = (
    "Welcome! How can I assist you with your astrological reading today? "
    "You can ask for your daily horoscope, kundli, dasha, transits, or compatibility matching!"
)

DEFAULT_GENERAL_INSTRUCTIONS = (
    "You are an authentic, deeply insightful, and empathetic Vedic Astrologer on WhatsApp. "
    "Strictly base your analysis on the verified calculation facts provided. "
    "Never invent, hallucinate, or alter any planetary sign, degree, house, or placement."
)

DEFAULT_HOROSCOPE_INTRO = (
    "Here is your personalized daily horoscope forecast based on your planetary transits and natal chart:"
)

DEFAULT_MAINTENANCE_MESSAGE = (
    "Our astrology assistant is currently undergoing brief scheduled maintenance to improve our "
    "astronomical calculations. We will be back shortly! 🕉️"
)


class BotSettings(Base):
    """Singleton configuration table for WhatsApp Assistant behavior and custom messages."""
    __tablename__ = "bot_settings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(32), unique=True, index=True, default="default", nullable=False)

    # Bot Controls (distinct operational states)
    is_paused: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    maintenance_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Custom Message Manager
    welcome_message: Mapped[str] = mapped_column(Text, default=DEFAULT_WELCOME_MESSAGE, nullable=False)
    fallback_message: Mapped[str] = mapped_column(Text, default=DEFAULT_FALLBACK_MESSAGE, nullable=False)
    general_instructions: Mapped[str] = mapped_column(Text, default=DEFAULT_GENERAL_INSTRUCTIONS, nullable=False)
    horoscope_intro: Mapped[str] = mapped_column(Text, default=DEFAULT_HOROSCOPE_INTRO, nullable=False)
    maintenance_message: Mapped[str] = mapped_column(Text, default=DEFAULT_MAINTENANCE_MESSAGE, nullable=False)

    # Extensible parameters (rate limits, auto-reply delays, etc.)
    extra_config: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    updated_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
