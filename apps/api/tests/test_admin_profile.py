"""Tests for WhatsApp Business Profile management, photo upload validation, and RBAC."""

import io
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.db.models.admin import AdminUser, AdminRole
from api.db.models.audit import AuditEvent
from api.security.hashing import hash_password
from api.security.token import create_access_token
from api.services.whatsapp_profile import (
    validate_profile_image,
    WhatsAppProfileError,
    JPEG_MAGIC,
    PNG_MAGIC,
)


@pytest_asyncio.fixture
async def super_admin(db_session: AsyncSession) -> AdminUser:
    admin = AdminUser(
        username="super_prof",
        email="super_prof@astrology.internal",
        password_hash=hash_password("SuperSecretP@ss123"),
        role=AdminRole.SUPER_ADMIN,
        is_active=True,
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin


@pytest_asyncio.fixture
async def support_admin(db_session: AsyncSession) -> AdminUser:
    admin = AdminUser(
        username="support_prof",
        email="support_prof@astrology.internal",
        password_hash=hash_password("SupportSecretP@ss123"),
        role=AdminRole.SUPPORT,
        is_active=True,
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin


def test_validate_profile_image():
    """Tests file size, format magic bytes, and error handling for profile images."""
    # 1. Valid JPEG
    jpeg_bytes = JPEG_MAGIC + b"\x00" * 100
    assert validate_profile_image(jpeg_bytes) == "image/jpeg"

    # 2. Valid PNG
    png_bytes = PNG_MAGIC + b"\x00" * 100
    assert validate_profile_image(png_bytes) == "image/png"

    # 3. Empty file
    with pytest.raises(WhatsAppProfileError, match="empty"):
        validate_profile_image(b"")

    # 4. Invalid format
    with pytest.raises(WhatsAppProfileError, match="Invalid image format"):
        validate_profile_image(b"GIF89a...")

    # 5. File exceeding 5 MB
    too_large = JPEG_MAGIC + b"\x00" * (5 * 1024 * 1024 + 10)
    with pytest.raises(WhatsAppProfileError, match="exceeds maximum allowed size"):
        validate_profile_image(too_large)


@pytest.mark.asyncio
async def test_get_and_update_profile_endpoints(
    client: AsyncClient,
    db_session: AsyncSession,
    super_admin: AdminUser,
    support_admin: AdminUser,
):
    """Tests GET/POST profile endpoints with RBAC enforcement and AuditEvent logging."""
    super_token = create_access_token(
        admin_id=str(super_admin.id),
        username=super_admin.username,
        role=super_admin.role.value,
        permissions=super_admin.get_permissions(),
    )
    support_token = create_access_token(
        admin_id=str(support_admin.id),
        username=support_admin.username,
        role=support_admin.role.value,
        permissions=support_admin.get_permissions(),
    )

    super_headers = {"Authorization": f"Bearer {super_token}"}
    support_headers = {"Authorization": f"Bearer {support_token}"}

    # 1. GET /api/v1/admin/whatsapp/profile - Allowed for both (read)
    resp_get = await client.get("/api/v1/admin/whatsapp/profile", headers=super_headers)
    assert resp_get.status_code == 200
    profile_data = resp_get.json()
    assert "about" in profile_data
    assert profile_data["mocked"] is True
    assert profile_data["live_meta"] is False

    # 2. POST /api/v1/admin/whatsapp/profile - Forbidden for support ('profile:manage' required)
    payload = {
        "about": "Precision Sidereal Astrology on WhatsApp",
        "vertical": "ENTERTAINMENT",
        "description": "Authentic Jyotish calculation engine.",
        "email": "contact@pixellab.media",
        "websites": ["https://astro.apps.pixellab.media"],
    }
    resp_post_forbidden = await client.post(
        "/api/v1/admin/whatsapp/profile",
        json=payload,
        headers=support_headers,
    )
    assert resp_post_forbidden.status_code == 403

    # Allowed for super_admin
    resp_post_ok = await client.post(
        "/api/v1/admin/whatsapp/profile",
        json=payload,
        headers=super_headers,
    )
    assert resp_post_ok.status_code == 200
    assert resp_post_ok.json()["status"] == "success"
    assert resp_post_ok.json()["result"]["mocked"] is True
    assert resp_post_ok.json()["result"]["live_meta"] is False

    # Verify AuditEvent
    audit = (
        await db_session.execute(
            select(AuditEvent).where(AuditEvent.action == "WHATSAPP_PROFILE_UPDATE")
        )
    ).scalars().first()
    assert audit is not None
    assert audit.target_entity == "whatsapp_business_profile"


@pytest.mark.asyncio
async def test_upload_profile_photo_endpoint(
    client: AsyncClient,
    db_session: AsyncSession,
    super_admin: AdminUser,
):
    """Tests multipart profile photo upload endpoint, validation, and audit recording."""
    token = create_access_token(
        admin_id=str(super_admin.id),
        username=super_admin.username,
        role=super_admin.role.value,
        permissions=super_admin.get_permissions(),
    )
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Reject invalid image format
    invalid_files = {"file": ("avatar.txt", io.BytesIO(b"Hello world text file"), "text/plain")}
    resp_invalid = await client.post(
        "/api/v1/admin/whatsapp/profile/photo",
        files=invalid_files,
        headers=headers,
    )
    assert resp_invalid.status_code == 400
    assert "Invalid image format" in resp_invalid.json()["detail"]

    # 2. Accept valid JPEG image
    valid_jpeg = JPEG_MAGIC + b"\x00" * 500
    valid_files = {"file": ("avatar.jpg", io.BytesIO(valid_jpeg), "image/jpeg")}
    resp_valid = await client.post(
        "/api/v1/admin/whatsapp/profile/photo",
        files=valid_files,
        headers=headers,
    )
    assert resp_valid.status_code == 200
    assert resp_valid.json()["status"] == "success"
    assert resp_valid.json()["result"]["mocked"] is True
    assert resp_valid.json()["result"]["live_meta"] is False

    # Verify AuditEvent
    audit = (
        await db_session.execute(
            select(AuditEvent).where(AuditEvent.action == "WHATSAPP_PROFILE_PHOTO_UPLOAD")
        )
    ).scalars().first()
    assert audit is not None
    assert audit.details["filename"] == "avatar.jpg"
