"""Meta WhatsApp Cloud API pre-approved message templates service.

Handles template contracts, parameter validation, language negotiation,
error handling, and separate proactive delivery paths.
"""

import re
import asyncio
import logging
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
import httpx

from api.config import get_settings

logger = logging.getLogger("api.services.whatsapp_templates")

# Meta template naming rules: lowercase alphanumeric + underscore, max 512 chars
TEMPLATE_NAME_PATTERN = re.compile(r"^[a-z0-9_]{1,512}$")

# Common supported language codes for WhatsApp templates
SUPPORTED_LANGUAGE_CODES = {
    "en", "en_US", "en_GB", "hi", "hi_IN"
}

# Max parameter text length allowed by Meta
MAX_PARAM_LENGTH = 1024


class WhatsAppTemplateError(Exception):
    """Base exception for WhatsApp template operations."""
    pass


class WhatsAppTemplateValidationError(WhatsAppTemplateError):
    """Raised when template name, language, or parameters fail validation."""
    pass


class WhatsAppTemplateDeliveryError(WhatsAppTemplateError):
    """Raised when Meta Graph API rejects or fails to deliver a template."""
    def __init__(self, message: str, status_code: int, error_code: Optional[int] = None, error_subcode: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.error_subcode = error_subcode


class DailyHoroscopeTemplatePayload(BaseModel):
    """Validated parameter payload for the daily horoscope message template."""
    user_name: str = Field(..., max_length=100, description="Recipient's name or friendly greeting")
    date_str: str = Field(..., max_length=50, description="Date of the horoscope (e.g., '24 Oct 2026')")
    sign_summary: str = Field(..., max_length=150, description="Sign and Nakshatra summary")
    horoscope_text: str = Field(..., max_length=MAX_PARAM_LENGTH, description="Personalized forecast content")

    def to_body_parameters(self) -> List[str]:
        return [
            self.user_name.strip(),
            self.date_str.strip(),
            self.sign_summary.strip(),
            self.horoscope_text.strip(),
        ]


def validate_template_name(template_name: str) -> None:
    """Validates that a template name complies with Meta specifications."""
    if not template_name or not TEMPLATE_NAME_PATTERN.match(template_name):
        raise WhatsAppTemplateValidationError(
            f"Invalid template name '{template_name}'. Must be 1-512 characters, lowercase alphanumeric and underscore only."
        )


def normalize_language_code(lang: str) -> str:
    """Maps internal language identifiers to Meta-compliant language codes."""
    cleaned = (lang or "en").strip()
    if cleaned in ("hi", "hindi"):
        return "hi"
    elif cleaned in ("en", "english", "hinglish"):
        return "en"
    elif cleaned in SUPPORTED_LANGUAGE_CODES:
        return cleaned
    # Fallback to English if unrecognized
    return "en"


def build_template_components(
    body_parameters: List[str],
    header_parameters: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """Builds and validates Meta template components payload."""
    components: List[Dict[str, Any]] = []

    if header_parameters:
        header_params = []
        for p in header_parameters:
            if not isinstance(p, str) or not p.strip():
                raise WhatsAppTemplateValidationError("Header parameter cannot be empty.")
            header_params.append({"type": "text", "text": p.strip()[:MAX_PARAM_LENGTH]})
        components.append({"type": "header", "parameters": header_params})

    if not body_parameters:
        raise WhatsAppTemplateValidationError("Body parameters list cannot be empty for template delivery.")

    body_params = []
    for idx, p in enumerate(body_parameters):
        if not isinstance(p, str) or not p.strip():
            raise WhatsAppTemplateValidationError(f"Body parameter at index {idx} cannot be empty.")
        body_params.append({"type": "text", "text": p.strip()[:MAX_PARAM_LENGTH]})

    components.append({"type": "body", "parameters": body_params})
    return components


async def send_whatsapp_template(
    to_phone: str,
    template_name: str,
    language_code: str,
    body_parameters: List[str],
    header_parameters: Optional[List[str]] = None,
    client: Optional[httpx.AsyncClient] = None,
    max_retries: int = 2
) -> Dict[str, Any]:
    """Sends an approved Meta WhatsApp Message Template.

    This function provides a dedicated, separate sending path for proactive,
    out-of-window messages, preventing mixing with free-form conversational replies.

    - Fail-closed parameter validation.
    - Safe logging with masked recipient phone.
    - Automatic exponential backoff retries for transient HTTP errors.
    """
    validate_template_name(template_name)
    lang_code = normalize_language_code(language_code)
    components = build_template_components(body_parameters, header_parameters)

    settings = get_settings()
    phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
    access_token = settings.WHATSAPP_ACCESS_TOKEN.get_secret_value() if settings.WHATSAPP_ACCESS_TOKEN else None

    # Sanitize phone to digits only (e.g. '+919876543210' -> '919876543210')
    recipient_clean = to_phone.lstrip("+").strip()
    masked_phone = f"...{recipient_clean[-4:]}" if len(recipient_clean) >= 4 else "XXXX"

    if not phone_number_id or not access_token:
        logger.warning(
            "WhatsApp credentials not configured; skipping live Meta Graph API template call '%s' for recipient ending in %s",
            template_name,
            masked_phone
        )
        return {
            "status": "mocked",
            "template": template_name,
            "language": lang_code,
            "recipient": recipient_clean,
            "parameters_count": len(body_parameters)
        }

    url = f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient_clean,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {
                "code": lang_code
            },
            "components": components
        }
    }

    last_exc: Optional[Exception] = None

    for attempt in range(max_retries + 1):
        try:
            if client is not None:
                resp = await client.post(url, headers=headers, json=payload, timeout=15.0)
            else:
                async with httpx.AsyncClient() as default_client:
                    resp = await default_client.post(url, headers=headers, json=payload, timeout=15.0)

            if resp.status_code == 200:
                logger.info(
                    "WhatsApp template '%s' delivered successfully to %s (attempt %d)",
                    template_name, masked_phone, attempt + 1
                )
                return resp.json()

            # Handle Meta Graph API error payload
            err_data = resp.json().get("error", {}) if resp.headers.get("content-type", "").startswith("application/json") else {}
            err_code = err_data.get("code")
            err_subcode = err_data.get("error_subcode")
            err_msg = err_data.get("message", resp.text)

            logger.error(
                "WhatsApp template delivery failed: status=%s code=%s subcode=%s msg=%s for recipient %s",
                resp.status_code, err_code, err_subcode, err_msg, masked_phone
            )

            # Client errors (400, 401, 403, 404) are deterministic; do not retry
            if 400 <= resp.status_code < 500:
                raise WhatsAppTemplateDeliveryError(
                    message=f"Meta API template rejected: {err_msg}",
                    status_code=resp.status_code,
                    error_code=err_code,
                    error_subcode=err_subcode
                )

            # 5xx server error: retryable
            resp.raise_for_status()

        except WhatsAppTemplateDeliveryError:
            raise
        except (httpx.RequestError, httpx.HTTPStatusError) as exc:
            last_exc = exc
            if attempt < max_retries:
                backoff = 0.5 * (2 ** attempt)
                logger.warning(
                    "Transient error sending template to %s (attempt %d/%d). Retrying in %.1fs: %s",
                    masked_phone, attempt + 1, max_retries + 1, backoff, exc
                )
                await asyncio.sleep(backoff)
            else:
                break

    raise WhatsAppTemplateDeliveryError(
        message=f"Failed to deliver WhatsApp template after {max_retries + 1} attempts: {last_exc}",
        status_code=500
    )
