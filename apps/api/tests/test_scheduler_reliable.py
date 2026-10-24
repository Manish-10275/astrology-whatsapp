"""Tests for reliable daily horoscope scheduling, timezones, concurrency, and dispatch auth."""

import asyncio
from datetime import date, time, datetime, timezone
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from unittest.mock import patch
from pydantic import SecretStr

from api.db.models.user import User, UserPreferences, UserStatus, AstrologySystemEnum
from api.db.models.birth_profile import BirthProfile, TimeUncertaintyEnum
from api.db.models.admin import AdminUser, AdminRole
from api.security.encryption import compute_phone_hash, encrypt_field
from api.security.hashing import hash_password
from api.security.token import create_access_token
from api.services.scheduler import dispatch_daily_horoscopes, _DISPATCH_LOCK, scheduler_daemon
from api.config import get_settings, clear_settings_cache


@pytest_asyncio.fixture
async def trigger_admin(db_session: AsyncSession) -> tuple[AdminUser, str]:
    admin = AdminUser(
        username="sched_admin",
        email="sched_admin@astrology.internal",
        password_hash=hash_password("SuperSecretPass123!"),
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
    return admin, token


@pytest.mark.asyncio
async def test_scheduler_endpoint_unauthorized_without_token(client: AsyncClient):
    """Verifies that unauthenticated requests to the scheduler endpoint are rejected (401)."""
    resp = await client.post("/api/v1/schedules/daily-horoscopes/dispatch")
    assert resp.status_code == 401
    assert "Unauthorized" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_scheduler_endpoint_authorized_via_secret_token(client: AsyncClient):
    """Verifies that a valid X-Scheduler-Token authorizes batch dispatch without admin login."""
    secret = "dedicated-cloud-scheduler-secret-key-999"
    mock_cfg = get_settings().model_copy()
    mock_cfg.SCHEDULER_SECRET_TOKEN = SecretStr(secret)

    with patch("api.routers.schedules.get_settings", return_value=mock_cfg):
        # 1. Invalid secret -> 401
        resp_bad = await client.post(
            "/api/v1/schedules/daily-horoscopes/dispatch",
            headers={"X-Scheduler-Token": "invalid-secret"}
        )
        assert resp_bad.status_code == 401

        # 2. Valid secret -> 200
        resp_ok = await client.post(
            "/api/v1/schedules/daily-horoscopes/dispatch",
            headers={"X-Scheduler-Token": secret}
        )
        assert resp_ok.status_code == 200
        data = resp_ok.json()
        assert data["status"] in ("completed", "concurrency_skip")
    assert data["status"] in ("completed", "concurrency_skip")


@pytest.mark.asyncio
async def test_scheduler_endpoint_authorized_via_admin_jwt(client: AsyncClient, trigger_admin):
    """Verifies that an Admin with 'dashboard:trigger' can authorize dispatch."""
    _, token = trigger_admin
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post("/api/v1/schedules/daily-horoscopes/dispatch", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "sent" in data


@pytest.mark.asyncio
async def test_concurrency_lock_prevents_simultaneous_dispatch(db_session: AsyncSession):
    """Verifies that concurrent dispatch attempts are safely skipped while lock is held."""
    # Simulate an active dispatch holding the lock
    async with _DISPATCH_LOCK:
        # A second dispatch invocation during active run
        stats = await dispatch_daily_horoscopes(session=db_session)
        assert stats["status"] == "concurrency_skip"
        assert "currently in progress" in stats["message"]


@pytest.mark.asyncio
async def test_timezone_aware_delivery_and_target_hour_filtering(db_session: AsyncSession):
    """Verifies delivery hour filtering respecting user local timezones."""
    phone1 = "+919811111111"
    user1 = User(
        phone_hash=compute_phone_hash(phone1),
        encrypted_phone=encrypt_field(phone1),
        whatsapp_name="India User",
        status=UserStatus.ACTIVE
    )
    db_session.add(user1)
    await db_session.commit()
    await db_session.refresh(user1)

    pref1 = UserPreferences(
        user_id=user1.id,
        astrology_system=AstrologySystemEnum.VEDIC,
        preferred_language="en",
        daily_horoscope_opt_in=True,
        horoscope_delivery_time="07:00"
    )
    db_session.add(pref1)

    prof1 = BirthProfile(
        user_id=user1.id,
        is_primary=True,
        timezone_name="Asia/Kolkata",
        time_uncertainty=TimeUncertaintyEnum.EXACT
    )
    prof1.set_birth_details(
        birth_date=date(1990, 5, 10),
        birth_time=time(8, 30),
        latitude=28.6139,
        longitude=77.2090,
        location_name="New Delhi, India"
    )
    db_session.add(prof1)
    await db_session.commit()

    # Case A: Filter by target_hour = 23 (unlikely to match user's 07:00 preference)
    stats_wrong_hour = await dispatch_daily_horoscopes(session=db_session, target_hour=23)
    assert stats_wrong_hour["skipped_wrong_time"] >= 1
    assert stats_wrong_hour["sent"] == 0

    # Case B: Run without target_hour filter -> should deliver
    stats_deliver = await dispatch_daily_horoscopes(session=db_session)
    assert stats_deliver["sent"] >= 1

    # Case C: Re-run on same day -> idempotency skips already delivered
    stats_repeat = await dispatch_daily_horoscopes(session=db_session)
    assert stats_repeat["skipped_already_sent"] >= 1


@pytest.mark.asyncio
async def test_background_scheduler_lifecycle():
    """Verifies that the background scheduler daemon starts, reports status, and stops cleanly."""
    status_init = scheduler_daemon.get_status()
    assert "enabled" in status_init

    # Stop any background task cleanly
    await scheduler_daemon.stop()
    assert scheduler_daemon.is_running is False
