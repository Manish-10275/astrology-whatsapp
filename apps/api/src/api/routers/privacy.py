"""Privacy, consent lifecycle, and Right-to-Erasure endpoints."""

import uuid
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete

from api.db.session import get_db_session
from api.db.models.user import User, UserStatus, UserPreferences
from api.db.models.consent import ConsentRecord
from api.db.models.deletion import DeletionRequest, DeletionStatus
from api.db.models.audit import AuditEvent
from api.security.encryption import compute_phone_hash, encrypt_field

router = APIRouter(prefix="/api/v1/privacy", tags=["Privacy & Consent"])


class ConsentRequest(BaseModel):
    phone_e164: str = Field(..., description="E.164 phone number, e.g. '+919876543210'")
    purpose: str = Field(default="birth_data_processing")
    policy_version: str = Field(default="v1.0")
    channel: str = Field(default="whatsapp")


class RevokeConsentRequest(BaseModel):
    phone_e164: str
    purpose: str = Field(default="birth_data_processing")


class DeletionApiRequest(BaseModel):
    phone_e164: str = Field(..., description="E.164 phone number requesting erasure")


class DeletionResponse(BaseModel):
    deletion_id: str
    status: str
    phone_hash_prefix: str
    records_deleted: int
    requested_at: datetime
    processed_at: Optional[datetime]


@router.post("/consent", status_code=status.HTTP_201_CREATED)
async def grant_consent(
    payload: ConsentRequest,
    session: AsyncSession = Depends(get_db_session)
):
    """Records explicit affirmative consent linked to the user's pseudonymized identity."""
    phone_hash = compute_phone_hash(payload.phone_e164)

    # Check if user exists, or create new user
    result = await session.execute(select(User).where(User.phone_hash == phone_hash))
    user = result.scalar_one_or_none()

    if not user:
        encrypted_phone = encrypt_field(payload.phone_e164)
        user = User(
            phone_hash=phone_hash,
            encrypted_phone=encrypted_phone,
            status=UserStatus.ACTIVE
        )
        session.add(user)
        await session.flush()

        # Create default preferences
        pref = UserPreferences(user_id=user.id)
        session.add(pref)

    consent = ConsentRecord(
        user_id=user.id,
        purpose=payload.purpose,
        policy_version=payload.policy_version,
        granted=True,
        channel=payload.channel
    )
    session.add(consent)
    await session.commit()

    return {
        "status": "granted",
        "user_id": str(user.id),
        "consent_id": str(consent.id),
        "policy_version": consent.policy_version
    }


@router.post("/consent/revoke")
async def revoke_consent(
    payload: RevokeConsentRequest,
    session: AsyncSession = Depends(get_db_session)
):
    """Revokes active user consent for a specific processing purpose."""
    phone_hash = compute_phone_hash(payload.phone_e164)

    result = await session.execute(select(User).where(User.phone_hash == phone_hash))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found."
        )

    now_utc = datetime.now(timezone.utc)
    # Update active consent records
    stmt = (
        update(ConsentRecord)
        .where(
            ConsentRecord.user_id == user.id,
            ConsentRecord.purpose == payload.purpose,
            ConsentRecord.revoked_at.is_(None)
        )
        .values(revoked_at=now_utc, granted=False)
    )
    await session.execute(stmt)
    await session.commit()

    return {
        "status": "revoked",
        "user_id": str(user.id),
        "purpose": payload.purpose,
        "revoked_at": now_utc.isoformat()
    }


@router.post("/deletion-request", response_model=DeletionResponse)
async def request_data_deletion(
    payload: DeletionApiRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session)
):
    """Executes atomic, idempotent Right-to-Erasure (GDPR Art. 17 / DPDP Sec. 12).
    
    Cascading wipe permanently purges:
    - User account row
    - Birth profiles & encrypted coordinates
    - User preferences
    - Active consent history
    
    Retains an immutable DeletionRequest and an anonymized AuditEvent without PII.
    """
    phone_hash = compute_phone_hash(payload.phone_e164)
    now_utc = datetime.now(timezone.utc)

    # Find target user
    result = await session.execute(select(User).where(User.phone_hash == phone_hash))
    user = result.scalar_one_or_none()

    if not user:
        # Idempotent: Record request even if user was already purged
        existing_del = await session.execute(
            select(DeletionRequest)
            .where(DeletionRequest.phone_hash == phone_hash)
            .order_by(DeletionRequest.requested_at.desc())
        )
        prior = existing_del.scalars().first()
        if prior:
            return DeletionResponse(
                deletion_id=str(prior.id),
                status=prior.status.value,
                phone_hash_prefix=prior.phone_hash[:8] + "...",
                records_deleted=prior.records_deleted,
                requested_at=prior.requested_at,
                processed_at=prior.processed_at
            )

        # First request for non-existent user
        del_req = DeletionRequest(
            phone_hash=phone_hash,
            status=DeletionStatus.COMPLETED,
            requested_at=now_utc,
            processed_at=now_utc,
            records_deleted=0
        )
        session.add(del_req)
        await session.commit()
        return DeletionResponse(
            deletion_id=str(del_req.id),
            status=del_req.status.value,
            phone_hash_prefix=phone_hash[:8] + "...",
            records_deleted=0,
            requested_at=del_req.requested_at,
            processed_at=del_req.processed_at
        )

    # Count records that will be purged
    profile_count = len(user.birth_profiles)
    consent_count = len(user.consent_records)
    total_purged = 1 + profile_count + consent_count + (1 if user.preferences else 0)

    # 1. Log immutable audit event BEFORE delete
    audit_event = AuditEvent(
        actor_id="USER_SELF",
        actor_role="user",
        action="USER_DATA_ERASURE",
        target_entity="user",
        target_id=str(user.id),
        details={"records_purged": total_purged},
        ip_address=request.client.host if request.client else None
    )
    session.add(audit_event)

    # 2. Record deletion fulfillment
    del_record = DeletionRequest(
        user_id=None,  # Set NULL to allow user row deletion
        phone_hash=phone_hash,
        status=DeletionStatus.COMPLETED,
        requested_at=now_utc,
        processed_at=now_utc,
        records_deleted=total_purged
    )
    session.add(del_record)

    # 3. Purge user (Cascades to child tables via ON DELETE CASCADE)
    await session.delete(user)
    await session.commit()

    return DeletionResponse(
        deletion_id=str(del_record.id),
        status=del_record.status.value,
        phone_hash_prefix=phone_hash[:8] + "...",
        records_deleted=total_purged,
        requested_at=del_record.requested_at,
        processed_at=del_record.processed_at
    )
