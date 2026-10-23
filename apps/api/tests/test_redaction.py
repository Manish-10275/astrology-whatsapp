"""Tests for PII redaction, field encryption verification, access auditing, and health probes."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.db.models.user import User, UserPreferences
from api.db.models.birth_profile import BirthProfile
from api.db.models.admin import AdminRole
from api.db.models.audit import AuditEvent
from api.security.encryption import compute_phone_hash, encrypt_field


@pytest.mark.asyncio
async def test_admin_user_list_phone_redaction(
    client: AsyncClient, db_session: AsyncSession, create_test_admin
):
    """Verify that admin user listing returns pseudonymized hash prefixes and never raw phone numbers."""
    # Setup test admin and user
    _, admin_token = await create_test_admin(username="auditor", role=AdminRole.SUPER_ADMIN)

    phone = "+919876543210"
    user = User(
        phone_hash=compute_phone_hash(phone),
        encrypted_phone=encrypt_field(phone),
        whatsapp_name="Astro User",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    pref = UserPreferences(user_id=user.id)
    db_session.add(pref)
    await db_session.commit()

    headers = {"Authorization": f"Bearer {admin_token}"}
    response = await client.get("/api/v1/admin/users", headers=headers)
    assert response.status_code == 200
    items = response.json()
    assert len(items) >= 1

    user_meta = items[0]
    # Phone number must NOT appear in response payload
    assert phone not in str(response.json())
    assert "phone_hash_prefix" in user_meta
    assert user_meta["phone_hash_prefix"].endswith("...")
    assert len(user_meta["phone_hash_prefix"]) == 11


@pytest.mark.asyncio
async def test_raw_db_row_contains_encrypted_birth_details(db_session: AsyncSession):
    """Verify that sensitive birth attributes in the database table are strictly encrypted at rest."""
    user = User(
        phone_hash=compute_phone_hash("+919123456789"),
        encrypted_phone=encrypt_field("+919123456789"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    profile = BirthProfile(
        user_id=user.id,
        profile_label="Test Native",
        is_primary=True,
        timezone_name="Asia/Kolkata",
    )
    raw_date = "1995-10-24"
    raw_time = "08:15:00"
    raw_lat = 19.0760
    raw_lon = 72.8777
    raw_loc = "Mumbai, India"

    profile.set_birth_details(
        birth_date=raw_date,
        birth_time=raw_time,
        latitude=raw_lat,
        longitude=raw_lon,
        location_name=raw_loc,
    )
    db_session.add(profile)
    await db_session.commit()
    await db_session.refresh(profile)

    # Inspect the raw column values directly
    assert profile.encrypted_birth_date.startswith("v1:")
    assert profile.encrypted_birth_date != raw_date
    assert profile.encrypted_birth_time.startswith("v1:")
    assert profile.encrypted_birth_time != raw_time
    assert profile.encrypted_latitude.startswith("v1:")
    assert profile.encrypted_longitude.startswith("v1:")
    assert profile.encrypted_location_name.startswith("v1:")
    assert profile.encrypted_location_name != raw_loc

    # Decrypted helper returns original data
    details = profile.get_decrypted_details()
    assert details["birth_date"].isoformat() == raw_date
    assert (details["birth_time"].isoformat() if details["birth_time"] else None) == raw_time
    assert details["latitude"] == raw_lat
    assert details["longitude"] == raw_lon
    assert details["location_name"] == raw_loc


@pytest.mark.asyncio
async def test_authorized_sensitive_access_leaves_audit_trail_without_pii(
    client: AsyncClient, db_session: AsyncSession, create_test_admin
):
    """Verify that accessing sensitive profile data requires authorization, logs audit event, and redacts PII from logs."""
    admin, admin_token = await create_test_admin(
        username="secops", role=AdminRole.SUPER_ADMIN
    )

    user = User(
        phone_hash=compute_phone_hash("+919999888877"),
        encrypted_phone=encrypt_field("+919999888877"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    profile = BirthProfile(
        user_id=user.id,
        profile_label="Client Chart",
        timezone_name="UTC",
    )
    profile.set_birth_details(
        birth_date="2000-01-01",
        birth_time="12:00:00",
        latitude=51.5074,
        longitude=-0.1278,
        location_name="London, UK",
    )
    db_session.add(profile)
    await db_session.commit()
    await db_session.refresh(profile)

    headers = {"Authorization": f"Bearer {admin_token}"}
    url = f"/api/v1/admin/users/{user.id}/profiles/{profile.id}/sensitive"
    response = await client.get(url, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["birth_date"] == "2000-01-01"
    assert data["location_name"] == "London, UK"

    # Verify audit event logged
    stmt = select(AuditEvent).where(
        AuditEvent.action == "PROFILE_SENSITIVE_READ",
        AuditEvent.target_id == str(profile.id),
    )
    audit = (await db_session.execute(stmt)).scalars().first()
    assert audit is not None
    assert audit.actor_id == str(admin.id)
    # Ensure audit log details does NOT contain decrypted PII
    assert "2000-01-01" not in str(audit.details)
    assert "London" not in str(audit.details)


@pytest.mark.asyncio
async def test_health_endpoints(client: AsyncClient):
    """Verify liveness and readiness probes respond accurately without credential exposure."""
    live_resp = await client.get("/health/live")
    assert live_resp.status_code == 200
    assert live_resp.json() == {"status": "live"}

    ready_resp = await client.get("/health/ready")
    assert ready_resp.status_code == 200
    data = ready_resp.json()
    assert data["status"] == "ready"
    assert data["database"] == "connected"
    # Ensure connection string, host, port, username are not exposed
    assert "localhost" not in str(data)
    assert "postgres" not in str(data)
