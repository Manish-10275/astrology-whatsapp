"""Persistent, encrypted conversation history and message models with idempotency."""

import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from enum import Enum
from sqlalchemy import String, Text, DateTime, JSON, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.db.base import Base
from api.security.encryption import encrypt_field, decrypt_field


class ConversationStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    CLOSED = "closed"


class ConversationState(str, Enum):
    ONBOARDING_CONSENT = "onboarding_consent"
    AWAITING_BIRTH_DATE = "awaiting_birth_date"
    AWAITING_BIRTH_TIME = "awaiting_birth_time"
    AWAITING_BIRTH_PLACE = "awaiting_birth_place"
    READING_READY = "reading_ready"
    ACTIVE = "active"


class MessageDirection(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class MessageSender(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class Conversation(Base):
    """WhatsApp conversation session and astrological state tracker."""
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )
    channel: Mapped[str] = mapped_column(String(32), default="whatsapp", nullable=False)
    status: Mapped[ConversationStatus] = mapped_column(
        SQLEnum(ConversationStatus, name="conversation_status_enum", native_enum=False),
        default=ConversationStatus.ACTIVE,
        nullable=False
    )
    current_state: Mapped[ConversationState] = mapped_column(
        SQLEnum(ConversationState, name="conversation_state_enum", native_enum=False),
        default=ConversationState.ONBOARDING_CONSENT,
        nullable=False
    )
    # Transient state metadata for multi-step onboarding (e.g. pending birth date, time)
    state_metadata: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

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
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    # Relationships
    messages: Mapped[List["ConversationMessage"]] = relationship(
        "ConversationMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ConversationMessage.created_at"
    )


class ConversationMessage(Base):
    """Encrypted message record stored at rest with AES-256-GCM.
    
    Privacy standard:
    - encrypted_content stores the ciphertext; plaintext messages are never stored in the database.
    - whatsapp_message_id is uniquely indexed for idempotent deduplication.
    """
    __tablename__ = "conversation_messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )
    # Meta WhatsApp Message ID (e.g. 'wamid.HBgL...') for deduplication
    whatsapp_message_id: Mapped[Optional[str]] = mapped_column(
        String(128),
        unique=True,
        index=True,
        nullable=True
    )
    direction: Mapped[MessageDirection] = mapped_column(
        SQLEnum(MessageDirection, name="message_direction_enum", native_enum=False),
        nullable=False
    )
    sender: Mapped[MessageSender] = mapped_column(
        SQLEnum(MessageSender, name="message_sender_enum", native_enum=False),
        nullable=False
    )
    encrypted_content: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(String(32), default="text", nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    # Relationships
    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages")

    def set_content(self, raw_text: str, key_version: Optional[str] = None) -> None:
        """Encrypts plaintext message before storing."""
        self.encrypted_content = encrypt_field(raw_text, key_version)

    def get_content(self) -> str:
        """Decrypts and authenticates message content fail-closed."""
        return decrypt_field(self.encrypted_content)
