"""Service for fetching and updating WhatsApp Business Profile via Meta Graph API."""

import io
import logging
from typing import Dict, Any, Optional, List
import httpx

from api.config import get_settings

logger = logging.getLogger("api.services.whatsapp_profile")

MAX_PROFILE_PHOTO_SIZE = 5 * 1024 * 1024  # 5 MB
VALID_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/jpg"}
JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class WhatsAppProfileError(Exception):
    """Base exception for profile management failures."""
    pass


def parse_meta_graph_error(resp: httpx.Response) -> str:
    """Extracts structured error details from Meta Graph API error response."""
    try:
        err_json = resp.json()
        if "error" in err_json:
            err = err_json["error"]
            code = err.get("code")
            subcode = err.get("error_subcode")
            msg = err.get("message") or resp.text
            return f"Meta Graph API error (code {code}, subcode {subcode}): {msg}"
    except Exception:
        pass
    return f"Meta Graph API HTTP error ({resp.status_code}): {resp.text}"


def validate_profile_image(file_bytes: bytes, content_type: Optional[str] = None) -> str:
    """Validates image file size, content-type, and magic bytes. Returns detected MIME type."""
    if not file_bytes:
        raise WhatsAppProfileError("Uploaded file is empty.")

    if len(file_bytes) > MAX_PROFILE_PHOTO_SIZE:
        raise WhatsAppProfileError(
            f"Image exceeds maximum allowed size of 5 MB ({len(file_bytes)} bytes provided)."
        )

    if file_bytes.startswith(JPEG_MAGIC):
        return "image/jpeg"
    elif file_bytes.startswith(PNG_MAGIC):
        return "image/png"
    else:
        raise WhatsAppProfileError("Invalid image format. Only JPEG and PNG images are supported.")


async def get_whatsapp_business_profile(
    client: Optional[httpx.AsyncClient] = None,
) -> Dict[str, Any]:
    """Fetches the WhatsApp Business Profile fields from Meta Graph API.

    Clearly distinguishes mock/diagnostic fallback from live Meta responses.
    """
    settings = get_settings()
    phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
    access_token = (
        settings.WHATSAPP_ACCESS_TOKEN.get_secret_value()
        if settings.WHATSAPP_ACCESS_TOKEN
        else None
    )

    if not phone_number_id or not access_token:
        logger.warning("WhatsApp credentials not configured; returning mock profile.")
        return {
            "configured": False,
            "live_meta": False,
            "mocked": True,
            "messaging_product": "whatsapp",
            "about": "Astrology Assistant Grounded in Precision Calculations",
            "address": "Digital Astro Platform",
            "description": "Authentic Vedic and Western astrology assistant powered by high-precision Swiss Ephemeris calculations.",
            "email": "contact@pixellab.media",
            "profile_picture_url": None,
            "websites": ["https://astro.apps.pixellab.media"],
            "vertical": "ENTERTAINMENT",
        }

    url = (
        f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}/{phone_number_id}/whatsapp_business_profile"
        "?fields=about,address,description,email,profile_picture_url,websites,vertical"
    )
    headers = {
        "Authorization": f"Bearer {access_token}",
    }

    try:
        if client:
            resp = await client.get(url, headers=headers, timeout=15.0)
        else:
            async with httpx.AsyncClient() as default_client:
                resp = await default_client.get(url, headers=headers, timeout=15.0)

        resp.raise_for_status()
        data = resp.json().get("data", [])
        profile_data = data[0] if data else {}
        profile_data["configured"] = True
        profile_data["live_meta"] = True
        profile_data["mocked"] = False
        return profile_data
    except httpx.HTTPStatusError as exc:
        err_msg = parse_meta_graph_error(exc.response)
        logger.error("Meta Graph API error fetching business profile: %s", err_msg)
        raise WhatsAppProfileError(err_msg)
    except Exception as exc:
        logger.error("Failed to connect to Meta Graph API: %s", exc)
        raise WhatsAppProfileError(f"Failed to connect to Meta Graph API: {str(exc)}")


async def update_whatsapp_business_profile(
    about: Optional[str] = None,
    address: Optional[str] = None,
    description: Optional[str] = None,
    email: Optional[str] = None,
    websites: Optional[List[str]] = None,
    vertical: Optional[str] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> Dict[str, Any]:
    """Updates WhatsApp Business Profile fields via Meta Graph API."""
    settings = get_settings()
    phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
    access_token = (
        settings.WHATSAPP_ACCESS_TOKEN.get_secret_value()
        if settings.WHATSAPP_ACCESS_TOKEN
        else None
    )

    payload: Dict[str, Any] = {"messaging_product": "whatsapp"}
    if about is not None:
        payload["about"] = about.strip()
    if address is not None:
        payload["address"] = address.strip()
    if description is not None:
        payload["description"] = description.strip()
    if email is not None:
        payload["email"] = email.strip()
    if websites is not None:
        payload["websites"] = [w.strip() for w in websites if w.strip()]
    if vertical is not None:
        payload["vertical"] = vertical.strip()

    if not phone_number_id or not access_token:
        logger.warning("WhatsApp credentials not configured; returning mock profile update.")
        return {"success": True, "live_meta": False, "mocked": True, "updated": payload}

    url = f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}/{phone_number_id}/whatsapp_business_profile"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    try:
        if client:
            resp = await client.post(url, headers=headers, json=payload, timeout=15.0)
        else:
            async with httpx.AsyncClient() as default_client:
                resp = await default_client.post(url, headers=headers, json=payload, timeout=15.0)

        resp.raise_for_status()
        return {"success": True, "live_meta": True, "mocked": False, "result": resp.json()}
    except httpx.HTTPStatusError as exc:
        err_msg = parse_meta_graph_error(exc.response)
        logger.error("Meta Graph API error updating business profile: %s", err_msg)
        raise WhatsAppProfileError(err_msg)
    except Exception as exc:
        logger.error("Failed to connect to Meta Graph API: %s", exc)
        raise WhatsAppProfileError(f"Failed to connect to Meta Graph API: {str(exc)}")


async def upload_whatsapp_profile_photo(
    file_bytes: bytes,
    filename: str = "profile.jpg",
    client: Optional[httpx.AsyncClient] = None,
) -> Dict[str, Any]:
    """Uploads a profile picture to Meta using the Graph API Resumable Upload session.

    Flow:
    1. POST /app/uploads?file_length=...&file_type=... -> returns session ID
    2. POST /{upload_session_id} with raw bytes and file_offset: 0 -> returns handle 'h'
    3. POST /{phone_number_id}/whatsapp_business_profile with profile_picture_handle: 'h'
    """
    mime_type = validate_profile_image(file_bytes)

    settings = get_settings()
    phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
    access_token = (
        settings.WHATSAPP_ACCESS_TOKEN.get_secret_value()
        if settings.WHATSAPP_ACCESS_TOKEN
        else None
    )

    if not phone_number_id or not access_token:
        logger.warning("WhatsApp credentials not configured; returning mock photo upload.")
        return {
            "success": True,
            "live_meta": False,
            "mocked": True,
            "profile_picture_url": None,
            "note": "WhatsApp credentials not configured; simulated mock photo upload acknowledged.",
        }

    # Step 1: Create Resumable Upload Session
    upload_init_url = (
        f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}/app/uploads"
        f"?file_length={len(file_bytes)}&file_type={mime_type}"
    )
    init_headers = {
        "Authorization": f"Bearer {access_token}",
    }

    try:
        if client:
            init_resp = await client.post(upload_init_url, headers=init_headers, timeout=15.0)
        else:
            async with httpx.AsyncClient() as default_client:
                init_resp = await default_client.post(upload_init_url, headers=init_headers, timeout=15.0)

        init_resp.raise_for_status()
        upload_data = init_resp.json()
        raw_session_id = upload_data.get("id", "")
        # Remove prefix if present: "upload:12345" -> "12345" or retain full id
        upload_session_id = raw_session_id.split("upload:")[-1] if "upload:" in raw_session_id else raw_session_id

        if not upload_session_id:
            raise WhatsAppProfileError("Meta Upload API did not return a valid upload session ID.")

        # Step 2: Upload file bytes to the upload session
        session_upload_url = f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}/{upload_session_id}"
        upload_headers = {
            "Authorization": f"OAuth {access_token}",
            "file_offset": "0",
            "Content-Type": "application/octet-stream",
        }

        if client:
            upload_resp = await client.post(session_upload_url, headers=upload_headers, content=file_bytes, timeout=30.0)
        else:
            async with httpx.AsyncClient() as default_client:
                upload_resp = await default_client.post(session_upload_url, headers=upload_headers, content=file_bytes, timeout=30.0)

        upload_resp.raise_for_status()
        session_result = upload_resp.json()
        photo_handle = session_result.get("h")

        if not photo_handle:
            raise WhatsAppProfileError("Meta API did not return a valid profile photo handle (field 'h').")

        # Step 3: Update WhatsApp Business Profile with profile_picture_handle
        profile_url = f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}/{phone_number_id}/whatsapp_business_profile"
        prof_headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        prof_payload = {
            "messaging_product": "whatsapp",
            "profile_picture_handle": photo_handle,
        }

        if client:
            prof_resp = await client.post(profile_url, headers=prof_headers, json=prof_payload, timeout=15.0)
        else:
            async with httpx.AsyncClient() as default_client:
                prof_resp = await default_client.post(profile_url, headers=prof_headers, json=prof_payload, timeout=15.0)

        prof_resp.raise_for_status()
        return {
            "success": True,
            "live_meta": True,
            "mocked": False,
            "profile_picture_handle": photo_handle,
            "result": prof_resp.json(),
        }
    except httpx.HTTPStatusError as exc:
        err_msg = parse_meta_graph_error(exc.response)
        logger.error("Meta Graph API error during photo upload: %s", err_msg)
        raise WhatsAppProfileError(err_msg)
    except Exception as exc:
        logger.error("Failed to upload profile photo to Meta: %s", exc)
        raise WhatsAppProfileError(f"Failed to upload profile photo: {str(exc)}")
