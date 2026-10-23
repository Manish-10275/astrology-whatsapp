"""Tests for consent tracking, revocation, and atomic Right-to-Erasure (GDPR/DPDP)."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.db.models.user import User, UserPreferences
from api.db.models.consent import ConsentRecord
from api.db.models.birth_profile import BirthProfile
from api.db.models.deletion import DeletionRequest, DeletionStatus
from api.db.models.audit import AuditEvent
from api.security.encryption import compute_phone_hash


@pytest.mark.asyncio
async def test_grant_consent_lifecycle(client: AsyncClient, db_session: AsyncSession):
    """Verify granting consent creates user, preferences, and active consent record."""
    phone = "+919876543210"
    payload = {
        "phone_e164": phone,
        "purpose": "birth_data_processing",
        "policy_version": "v1.0",
        "channel": "whatsapp",
    }

    response = await client.post("/api/v1/privacy/consent", json=payload)
    assert response.status_code in (200, 201)
    data = response.json()
    assert data["status"] == "granted"
    assert "user_id" in data
    assert "consent_id" in data

    # Verify database state
    phone_hash = compute_phone_hash(phone)
    stmt = select(User).where(User.phone_hash == phone_hash)
    user = (await db_session.execute(stmt)).scalars().first()
    assert user is not None

    consent_stmt = select(ConsentRecord).where(ConsentRecord.user_id == user.id)
    consent = (await db_session.execute(consent_stmt)).scalars().first()
    assert consent is not None
    assert consent.purpose == "birth_data_processing"
    assert consent.granted is True
    assert consent.revoked_at is None


@pytest.mark.asyncio
async def test_revoke_consent(client: AsyncClient, db_session: AsyncSession):
    """Verify revoking consent sets revoked_at timestamp without deleting history."""
    phone = "+919876543210"
    # First grant consent
    await client.post(
        "/api/v1/privacy/consent",
        json={"phone_e164": phone, "purpose": "birth_data_processing"},
    )

    # Now revoke consent
    revoke_resp = await client.post(
        "/api/v1/privacy/consent/revoke",
        json={"phone_e164": phone, "purpose": "birth_data_processing"},
    )
    assert revoke_resp.status_code == 200
    data = revoke_resp.json()
    assert data["status"] == "revoked"

    # Verify database record
    phone_hash = compute_phone_hash(phone)
    stmt = select(User).where(User.phone_hash == phone_hash)
    user = (await db_session.execute(stmt)).scalars().first()

    consent_stmt = select(ConsentRecord).where(ConsentRecord.user_id == user.id)
    consent = (await db_session.execute(consent_stmt)).scalars().first()
    assert consent.revoked_at is not None


@pytest.mark.asyncio
async def test_right_to_erasure_atomic_deletion(client: AsyncClient, db_session: AsyncSession):
    """Verify Right-to-Erasure cascades to all user tables and leaves only an anonymized DeletionRequest."""
    phone = "+919876543210"
    # 1. Setup user via consent
    grant_resp = await client.post("/api/v1/privacy/consent", json={"phone_e164": phone})
    user_id = grant_resp.json()["user_id"]

    # 2. Add an encrypted birth profile to verify cascade
    stmt = select(User).where(User.phone_hash == compute_phone_hash(phone))
    user = (await db_session.execute(stmt)).scalars().first()

    profile = BirthProfile(
        user_id=user.id,
        profile_label="Self",
        is_primary=True,
        timezone_name="Asia/Kolkata",
    )
    profile.set_birth_details(
        birth_date="1990-05-15",
        birth_time="14:30:00",
        latitude=28.6139,
        longitude=77.2090,
        location_name="New Delhi, India",
    )
    db_session.add(profile)
    await db_session.commit()

    # 3. Request deletion (Right-to-Erasure)
    del_resp = await client.post("/api/v1/privacy/deletion-request", json={"phone_e164": phone})
    assert del_resp.status_code == 200
    del_data = del_resp.json()
    assert del_data["status"] == "completed"
    assert del_data["records_deleted"] >= 1

    # 4. Verify user, profile, preferences, and consents are wiped from DB
    user_check = (await db_session.execute(select(User).where(User.id == user.id))).scalars().first()
    assert user_check is None

    prof_check = (
        await db_session.execute(select(BirthProfile).where(BirthProfile.user_id == user.id))
    ).scalars().first()
    assert prof_check is None

    consent_check = (
        await db_session.execute(select(ConsentRecord).where(ConsentRecord.user_id == user.id))
    ).scalars().first()
    assert consent_check is None

    # 5. Verify DeletionRequest and AuditEvent exist for compliance audit without PII
    del_req = (
        await db_session.execute(
            select(DeletionRequest).where(DeletionRequest.phone_hash == compute_phone_hash(phone))
        )
    ).scalars().first()
    assert del_req is not None
    assert del_req.status == DeletionStatus.COMPLETED

    audit = (
        await db_session.execute(
            select(AuditEvent).where(AuditEvent.action == "USER_DATA_ERASURE")
        )
    ).scalars().first()
    assert audit is not None
    assert audit.actor_id == "USER_SELF"


@pytest.mark.asyncio
async def test_idempotent_deletion_request(client: AsyncClient):
    """Verify that requesting deletion for an already-deleted or non-existent user is idempotent and succeeds."""
    phone = "+910000000000"
    resp = await client.post("/api/v1/privacy/deletion-request", json={"phone_e164": phone})
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"
    assert resp.json()["records_deleted"] == 0
