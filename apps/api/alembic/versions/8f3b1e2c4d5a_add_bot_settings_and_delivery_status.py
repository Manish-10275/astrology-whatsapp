"""Add bot settings singleton and message delivery status tracking.

Revision ID: 8f3b1e2c4d5a
Revises: 7e2c9a4b6d10
Create Date: 2026-10-27
"""
import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "8f3b1e2c4d5a"
down_revision: Union[str, None] = "7e2c9a4b6d10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

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


def upgrade() -> None:
    # 1. Create bot_settings table
    op.create_table(
        "bot_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=32), nullable=False),
        sa.Column("is_paused", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("maintenance_mode", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("welcome_message", sa.Text(), nullable=False),
        sa.Column("fallback_message", sa.Text(), nullable=False),
        sa.Column("general_instructions", sa.Text(), nullable=False),
        sa.Column("horoscope_intro", sa.Text(), nullable=False),
        sa.Column("maintenance_message", sa.Text(), nullable=False),
        sa.Column("extra_config", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", name="uq_bot_settings_key")
    )
    op.create_index("ix_bot_settings_key", "bot_settings", ["key"])

    # 2. Insert initial singleton default settings row
    bot_settings_table = sa.table(
        "bot_settings",
        sa.column("id", sa.Uuid),
        sa.column("key", sa.String),
        sa.column("is_paused", sa.Boolean),
        sa.column("maintenance_mode", sa.Boolean),
        sa.column("welcome_message", sa.Text),
        sa.column("fallback_message", sa.Text),
        sa.column("general_instructions", sa.Text),
        sa.column("horoscope_intro", sa.Text),
        sa.column("maintenance_message", sa.Text),
        sa.column("extra_config", sa.JSON),
        sa.column("updated_at", sa.DateTime(timezone=True)),
        sa.column("updated_by", sa.String),
    )
    op.bulk_insert(
        bot_settings_table,
        [
            {
                "id": uuid.uuid4(),
                "key": "default",
                "is_paused": False,
                "maintenance_mode": False,
                "welcome_message": DEFAULT_WELCOME_MESSAGE,
                "fallback_message": DEFAULT_FALLBACK_MESSAGE,
                "general_instructions": DEFAULT_GENERAL_INSTRUCTIONS,
                "horoscope_intro": DEFAULT_HOROSCOPE_INTRO,
                "maintenance_message": DEFAULT_MAINTENANCE_MESSAGE,
                "extra_config": {},
                "updated_at": datetime.now(timezone.utc),
                "updated_by": "system_init",
            }
        ]
    )

    # 3. Add delivery tracking fields to conversation_messages
    op.add_column("conversation_messages", sa.Column("delivery_status", sa.String(length=32), nullable=True, server_default="sent"))
    op.add_column("conversation_messages", sa.Column("status_timestamp", sa.DateTime(timezone=True), nullable=True))
    op.add_column("conversation_messages", sa.Column("error_code", sa.String(length=64), nullable=True))
    op.add_column("conversation_messages", sa.Column("error_message", sa.Text(), nullable=True))
    op.create_index("ix_conversation_messages_delivery_status", "conversation_messages", ["delivery_status"])


def downgrade() -> None:
    op.drop_index("ix_conversation_messages_delivery_status", table_name="conversation_messages")
    op.drop_column("conversation_messages", "error_message")
    op.drop_column("conversation_messages", "error_code")
    op.drop_column("conversation_messages", "status_timestamp")
    op.drop_column("conversation_messages", "delivery_status")
    op.drop_index("ix_bot_settings_key", table_name="bot_settings")
    op.drop_table("bot_settings")
