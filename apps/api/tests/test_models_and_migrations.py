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
