"""Tests for database models, constraints, cascades, and enum integrity."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select

from api.db.models.user import User, UserPreferences, UserStatus, AstrologySystemEnum
from api.db.models.birth_profile import BirthProfile, TimeUncertaintyEnum
from api.db.models.admin import AdminUser, AdminRole
from api.security.encryption import compute_phone_hash, encrypt_field
from api.security.hashing import hash_password


@pytest.mark.asyncio
async def test_duplicate_phone_hash_rejected(db_session: AsyncSession):
    """Verify unique constraint on User.phone_hash rejects duplicates."""
    phone_hash = compute_phone_hash("+919876543210")
    u1 = User(phone_hash=phone_hash, encrypted_phone=encrypt_field("+919876543210"))
    db_session.add(u1)
    await db_session.commit()

    u2 = User(phone_hash=phone_hash, encrypted_phone=encrypt_field("+919876543210"))
    db_session.add(u2)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_duplicate_admin_username_rejected(db_session: AsyncSession):
    """Verify unique constraint on AdminUser.username rejects duplicates."""
    a1 = AdminUser(
        username="admin1",
        email="admin1@example.com",
        password_hash=hash_password("Pass123!"),
        role=AdminRole.SUPER_ADMIN,
    )
    db_session.add(a1)
    await db_session.commit()

    a2 = AdminUser(
        username="admin1",
        email="other@example.com",
        password_hash=hash_password("Pass123!"),
        role=AdminRole.SUPPORT,
    )
    db_session.add(a2)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_cascade_deletion_on_user(db_session: AsyncSession):
    """Verify that deleting a User cascades to their preferences and birth profiles."""
    user = User(
        phone_hash=compute_phone_hash("+911122334455"),
        encrypted_phone=encrypt_field("+911122334455"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    pref = UserPreferences(user_id=user.id, astrology_system=AstrologySystemEnum.VEDIC)
    prof = BirthProfile(
        user_id=user.id,
        profile_label="Primary",
        time_uncertainty=TimeUncertaintyEnum.EXACT,
        timezone_name="UTC",
    )
    prof.set_birth_details(
        birth_date="1985-06-20",
        birth_time="10:00:00",
        latitude=12.9716,
        longitude=77.5946,
        location_name="Bangalore, India",
    )
    db_session.add_all([pref, prof])
    await db_session.commit()

    # Now delete user directly
    await db_session.delete(user)
    await db_session.commit()

    # Check child records are automatically removed by CASCADE
    p_check = (
        await db_session.execute(select(UserPreferences).where(UserPreferences.user_id == user.id))
    ).scalars().first()
    assert p_check is None

    b_check = (
        await db_session.execute(select(BirthProfile).where(BirthProfile.user_id == user.id))
    ).scalars().first()
    assert b_check is None


@pytest.mark.asyncio
async def test_bot_settings_singleton_and_defaults(db_session: AsyncSession):
    """Verify BotSettings model creates singleton with valid defaults and unique key constraint."""
    from api.db.models.bot_settings import BotSettings, DEFAULT_WELCOME_MESSAGE

    # Clean existing default row if left from prior test runs
    existing = (await db_session.execute(select(BotSettings).where(BotSettings.key == "default"))).scalars().first()
    if existing:
        await db_session.delete(existing)
        await db_session.commit()

    settings1 = BotSettings(key="default")
    db_session.add(settings1)
    await db_session.commit()
    await db_session.refresh(settings1)

    assert settings1.is_paused is False
    assert settings1.maintenance_mode is False
    assert settings1.welcome_message == DEFAULT_WELCOME_MESSAGE
    assert "Astrology Assistant" in settings1.welcome_message

    # Duplicate key must be rejected
    settings2 = BotSettings(key="default")
    db_session.add(settings2)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_conversation_message_delivery_status_tracking(db_session: AsyncSession):
    """Verify ConversationMessage stores and updates delivery status fields."""
    from api.db.models.conversation import Conversation, ConversationMessage, MessageDirection, MessageSender

    user = User(
        phone_hash=compute_phone_hash("+918888777766"),
        encrypted_phone=encrypt_field("+918888777766"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    conv = Conversation(user_id=user.id)
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)

    msg = ConversationMessage(
        conversation_id=conv.id,
        user_id=user.id,
        direction=MessageDirection.OUTBOUND,
        sender=MessageSender.ASSISTANT,
        whatsapp_message_id="wamid.test_delivery_123",
        delivery_status="sent",
    )
    msg.set_content("Hello seeker, your chart is ready.")
    db_session.add(msg)
    await db_session.commit()
    await db_session.refresh(msg)

    assert msg.delivery_status == "sent"
    assert msg.status_timestamp is None

    # Simulate Meta webhook delivery update
    from datetime import datetime, timezone
    msg.delivery_status = "delivered"
    msg.status_timestamp = datetime.now(timezone.utc)
    await db_session.commit()
    await db_session.refresh(msg)

    assert msg.delivery_status == "delivered"
    assert msg.status_timestamp is not None
