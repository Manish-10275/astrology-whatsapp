"""Tests for daily horoscope batch dispatch, idempotency, and scheduler endpoints."""

import pytest
from datetime import date, time, datetime, timezone
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.db.models.user import User, UserPreferences, UserStatus, AstrologySystemEnum
from api.db.models.birth_profile import BirthProfile, TimeUncertaintyEnum
from api.db.models.conversation import Conversation, ConversationMessage, ConversationStatus
from api.db.models.admin import AdminUser, AdminRole
from api.security.encryption import compute_phone_hash, encrypt_field
from api.security.hashing import hash_password
from api.security.token import create_access_token
from api.services.scheduler import dispatch_daily_horoscopes


@pytest.mark.asyncio
async def test_scheduler_opt_in_dispatch_and_idempotency(db_session: AsyncSession):
    """Verifies that opted-in users receive daily horoscopes and repeat calls on the same day are idempotent."""
    # 1. Create a user opted-in to daily horoscopes
    phone = "+919876543210"
    user = User(
        phone_hash=compute_phone_hash(phone),
        encrypted_phone=encrypt_field(phone),
        whatsapp_name="Aarav Test",
        status=UserStatus.ACTIVE
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    pref = UserPreferences(
        user_id=user.id,
        astrology_system=AstrologySystemEnum.VEDIC,
        daily_horoscope_opt_in=True,
        last_horoscope_sent_date=None
    )
    db_session.add(pref)

    # Add primary birth profile
    profile = BirthProfile(
        user_id=user.id,
        profile_label="Primary",
        is_primary=True,
        timezone_name="Asia/Kolkata",
        time_uncertainty=TimeUncertaintyEnum.EXACT
    )
    profile.set_birth_details(
        birth_date=date(1995, 10, 24),
        birth_time=time(14, 30),
        latitude=28.6139,
        longitude=77.2090,
        location_name="New Delhi, India"
    )
    db_session.add(profile)
    await db_session.commit()

    test_date = date(2026, 10, 24)

    # 2. First Dispatch Run: Should successfully deliver
    stats = await dispatch_daily_horoscopes(session=db_session, target_date=test_date)
    assert stats["total_eligible"] == 1
    assert stats["sent"] == 1
    assert stats["skipped_already_sent"] == 0
    assert stats["errors"] == 0

    # Verify user preferences updated with sent date
    await db_session.refresh(pref)
    assert pref.last_horoscope_sent_date == test_date

    # Verify message was logged to conversation
    msg_stmt = select(ConversationMessage).where(ConversationMessage.user_id == user.id)
    msgs = (await db_session.execute(msg_stmt)).scalars().all()
    assert len(msgs) >= 1
    content = msgs[0].get_decrypted_content()
    assert "Daily Horoscope" in content or "दैनिक राशिफल" in content

    # 3. Second Dispatch Run on SAME Date: Must be skipped idempotently
    second_stats = await dispatch_daily_horoscopes(session=db_session, target_date=test_date)
    assert second_stats["total_eligible"] == 1
    assert second_stats["sent"] == 0
    assert second_stats["skipped_already_sent"] == 1


@pytest.mark.asyncio
async def test_scheduler_skips_users_without_opt_in_or_profile(db_session: AsyncSession):
    """Verifies that users who have not opted in or have no primary profile are properly handled."""
    # User 1: Opted out
    u1 = User(
        phone_hash=compute_phone_hash("+919111111111"),
        encrypted_phone=encrypt_field("+919111111111"),
        status=UserStatus.ACTIVE
    )
    db_session.add(u1)
    await db_session.commit()
    await db_session.refresh(u1)
    pref1 = UserPreferences(user_id=u1.id, daily_horoscope_opt_in=False)
    db_session.add(pref1)

    # User 2: Opted in, but has NO birth profile
    u2 = User(
        phone_hash=compute_phone_hash("+919222222222"),
        encrypted_phone=encrypt_field("+919222222222"),
        status=UserStatus.ACTIVE
    )
    db_session.add(u2)
    await db_session.commit()
    await db_session.refresh(u2)
    pref2 = UserPreferences(user_id=u2.id, daily_horoscope_opt_in=True)
    db_session.add(pref2)
    await db_session.commit()

    stats = await dispatch_daily_horoscopes(session=db_session, target_date=date(2026, 10, 24))
    # Only u2 is eligible by query (opt_in == True)
    assert stats["total_eligible"] == 1
    assert stats["sent"] == 0
    assert stats["skipped_no_profile"] == 1


@pytest.mark.asyncio
async def test_scheduler_api_endpoint(client: AsyncClient, db_session: AsyncSession):
    """Tests POST /api/v1/schedules/daily-horoscopes/dispatch endpoint authentication and execution."""
    # 1. Without auth -> 401
    resp_unauth = await client.post("/api/v1/schedules/daily-horoscopes/dispatch")
    assert resp_unauth.status_code == 401

    # 2. With Super Admin auth -> 200
    admin = AdminUser(
        username="superadmin_scheduler",
        email="superadmin_scheduler@astrology.internal",
        password_hash=hash_password("SuperSecretP@ss123"),
        role=AdminRole.SUPER_ADMIN,
        is_active=True
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)

    token = create_access_token(
        admin_id=str(admin.id),
        username=admin.username,
        role=admin.role.value,
        permissions=admin.get_permissions()
    )
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post("/api/v1/schedules/daily-horoscopes/dispatch?target_date=2026-10-24", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["dispatch_date"] == "2026-10-24"
    assert "sent" in data
    assert "skipped_already_sent" in data
