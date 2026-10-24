"""WhatsApp Cloud API client, signature verification, and deduplication utilities."""

import os
import hmac
import hashlib
import logging
from typing import Optional, Dict, Any, Set
import httpx

from api.config import get_settings
from api.services.whatsapp_templates import (
    send_whatsapp_template,
    WhatsAppTemplateError,
    WhatsAppTemplateValidationError,
    WhatsAppTemplateDeliveryError,
    DailyHoroscopeTemplatePayload,
)

logger = logging.getLogger("api.services.whatsapp")

# In-memory deduplication cache fallback (message_id -> timestamp)
_PROCESSED_MESSAGE_IDS: Set[str] = set()
_MAX_CACHE_SIZE = 10000


def verify_meta_signature(raw_body: bytes, signature_header: Optional[str], app_secret: str) -> bool:
    """Verifies X-Hub-Signature-256 header from Meta against the raw request body.
    
    Fail-closed: Returns False if header is missing, malformed, or signature mismatch.
    """
    if not signature_header:
        logger.warning("WhatsApp webhook rejected: missing X-Hub-Signature-256 header.")
        return False

    if not signature_header.startswith("sha256="):
        logger.warning("WhatsApp webhook rejected: malformed signature format.")
        return False

    expected_sig = signature_header[7:].strip()
    computed_sig = hmac.new(
        key=app_secret.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected_sig, computed_sig)


def is_message_duplicate(whatsapp_message_id: str) -> bool:
    """Checks if a message ID has already been seen to ensure idempotency."""
    global _PROCESSED_MESSAGE_IDS
    if not whatsapp_message_id:
        return False

    if whatsapp_message_id in _PROCESSED_MESSAGE_IDS:
        return True

    if len(_PROCESSED_MESSAGE_IDS) > _MAX_CACHE_SIZE:
        _PROCESSED_MESSAGE_IDS.clear()

    _PROCESSED_MESSAGE_IDS.add(whatsapp_message_id)
    return False


async def send_whatsapp_text(
    to_phone: str,
    text_body: str,
    client: Optional[httpx.AsyncClient] = None
) -> Dict[str, Any]:
    """Sends a text message reply through Meta's WhatsApp Cloud API.
    
    Never logs secret access tokens or full message contents.
    """
    settings = get_settings()

    phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
    access_token = settings.WHATSAPP_ACCESS_TOKEN.get_secret_value() if settings.WHATSAPP_ACCESS_TOKEN else None

    # Sanitize phone number to digits only for Graph API (e.g., '+919876543210' -> '919876543210')
    recipient_clean = to_phone.lstrip("+").strip()

    if not phone_number_id or not access_token:
        logger.warning(
            "WhatsApp credentials not configured; skipping live Meta Graph API call for recipient ending in ...%s",
            recipient_clean[-4:] if len(recipient_clean) >= 4 else "XXXX"
        )
        return {"status": "mocked", "recipient": recipient_clean}

    url = f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient_clean,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": text_body
        }
    }

    try:
        if client is not None:
            response = await client.post(url, headers=headers, json=payload, timeout=15.0)
        else:
            async with httpx.AsyncClient() as default_client:
                response = await default_client.post(url, headers=headers, json=payload, timeout=15.0)

        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        logger.error(
            "WhatsApp Graph API HTTP error: status=%s response=%s",
            exc.response.status_code,
            exc.response.text
        )
        raise
    except Exception as exc:
        logger.error("Failed to deliver WhatsApp message via Graph API: %s", exc)
        raise
