"""Tests for Meta WhatsApp Message Templates service, parameter contracts, and delivery."""

import pytest
import pytest_asyncio
import httpx
from pydantic import SecretStr
from unittest.mock import patch, AsyncMock

from api.services.whatsapp_templates import (
    validate_template_name,
    normalize_language_code,
    build_template_components,
    send_whatsapp_template,
    DailyHoroscopeTemplatePayload,
    WhatsAppTemplateValidationError,
    WhatsAppTemplateDeliveryError,
)
from api.config import get_settings, clear_settings_cache


def test_template_name_validation():
    """Verifies that template names strictly adhere to Meta naming specifications."""
    # Valid names
    validate_template_name("daily_horoscope_update")
    validate_template_name("horoscope_v1")
    validate_template_name("alert_123")

    # Invalid names
    with pytest.raises(WhatsAppTemplateValidationError):
        validate_template_name("")

    with pytest.raises(WhatsAppTemplateValidationError):
        validate_template_name("Daily_Horoscope")  # Uppercase not allowed

    with pytest.raises(WhatsAppTemplateValidationError):
        validate_template_name("daily-horoscope")  # Hyphen not allowed

    with pytest.raises(WhatsAppTemplateValidationError):
        validate_template_name("daily horoscope!")  # Spaces and symbols not allowed


def test_language_code_normalization():
    """Verifies that internal language strings normalize to Meta ISO codes."""
    assert normalize_language_code("hi") == "hi"
    assert normalize_language_code("hindi") == "hi"
    assert normalize_language_code("en") == "en"
    assert normalize_language_code("english") == "en"
    assert normalize_language_code("hinglish") == "en"
    assert normalize_language_code("en_US") == "en_US"
    assert normalize_language_code(None) == "en"
    assert normalize_language_code("unknown_xyz") == "en"


def test_template_components_builder_and_validation():
    """Verifies component payload construction and parameter validation."""
    components = build_template_components(
        body_parameters=["Manish", "24 Oct 2026", "Aries", "Great day ahead!"],
        header_parameters=["Welcome"]
    )
    assert len(components) == 2
    assert components[0]["type"] == "header"
    assert components[0]["parameters"][0]["text"] == "Welcome"
    assert components[1]["type"] == "body"
    assert len(components[1]["parameters"]) == 4

    # Empty body parameters should raise validation error
    with pytest.raises(WhatsAppTemplateValidationError):
        build_template_components([])

    # Empty string inside parameter should raise validation error
    with pytest.raises(WhatsAppTemplateValidationError):
        build_template_components(["Valid", ""])


def test_daily_horoscope_template_contract():
    """Verifies the DailyHoroscopeTemplatePayload contract."""
    payload = DailyHoroscopeTemplatePayload(
        user_name="Seeker",
        date_str="24 October 2026",
        sign_summary="Vedic Moon in Mesha (Aries) - Ashwini",
        horoscope_text="Today brings clear intuition and creative breakthroughs."
    )
    params = payload.to_body_parameters()
    assert len(params) == 4
    assert params[0] == "Seeker"
    assert "24 October 2026" in params[1]
    assert "Mesha" in params[2]


@pytest.mark.asyncio
async def test_send_whatsapp_template_mocked_mode_without_credentials():
    """Verifies that template delivery safely returns mocked status when credentials are not configured."""
    with patch("api.services.whatsapp_templates.get_settings") as mock_settings:
        mock_cfg = get_settings().model_copy()
        mock_cfg.WHATSAPP_PHONE_NUMBER_ID = None
        mock_cfg.WHATSAPP_ACCESS_TOKEN = None
        mock_settings.return_value = mock_cfg

        result = await send_whatsapp_template(
            to_phone="+919876543210",
            template_name="daily_horoscope_update",
            language_code="hi",
            body_parameters=["User", "24 Oct 2026", "Sign", "Reading"]
        )

        assert result["status"] == "mocked"
        assert result["template"] == "daily_horoscope_update"
        assert result["language"] == "hi"
        assert result["recipient"] == "919876543210"
        assert result["parameters_count"] == 4


@pytest.mark.asyncio
async def test_send_whatsapp_template_successful_delivery():
    """Verifies successful template dispatch over Meta Graph API."""
    mock_cfg = get_settings().model_copy()
    mock_cfg.WHATSAPP_PHONE_NUMBER_ID = "1000123456789"
    mock_cfg.WHATSAPP_ACCESS_TOKEN = SecretStr("valid_access_token_secret_123")

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert "1000123456789" in str(request.url)
        assert request.headers["authorization"] == "Bearer valid_access_token_secret_123"
        return httpx.Response(
            200,
            json={
                "messaging_product": "whatsapp",
                "contacts": [{"input": "919876543210", "wa_id": "919876543210"}],
                "messages": [{"id": "wamid.HBgL..."}]
            }
        )

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as mock_client:
        with patch("api.services.whatsapp_templates.get_settings", return_value=mock_cfg):
            result = await send_whatsapp_template(
                to_phone="+919876543210",
                template_name="daily_horoscope_update",
                language_code="en",
                body_parameters=["Manish", "24 Oct", "Aries", "Great energy today"],
                client=mock_client
            )

    assert "messages" in result
    assert result["messages"][0]["id"] == "wamid.HBgL..."


@pytest.mark.asyncio
async def test_send_whatsapp_template_rejection_error_handling():
    """Verifies that Meta 400 template rejection raises WhatsAppTemplateDeliveryError without retrying."""
    mock_cfg = get_settings().model_copy()
    mock_cfg.WHATSAPP_PHONE_NUMBER_ID = "1000123456789"
    mock_cfg.WHATSAPP_ACCESS_TOKEN = SecretStr("valid_access_token_secret_123")

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            headers={"content-type": "application/json"},
            json={
                "error": {
                    "message": "(#132000) Template name does not exist in the translation",
                    "type": "OAuthException",
                    "code": 132000,
                    "error_subcode": 2494011,
                    "fbtrace_id": "A1B2C3D4"
                }
            }
        )

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as mock_client:
        with patch("api.services.whatsapp_templates.get_settings", return_value=mock_cfg):
            with pytest.raises(WhatsAppTemplateDeliveryError) as exc_info:
                await send_whatsapp_template(
                    to_phone="+919876543210",
                    template_name="unapproved_template_xyz",
                    language_code="en",
                    body_parameters=["Param1", "Param2", "Param3", "Param4"],
                    client=mock_client
                )

    assert exc_info.value.status_code == 400
    assert exc_info.value.error_code == 132000


@pytest.mark.asyncio
async def test_send_whatsapp_template_transient_retry():
    """Verifies that transient 500 errors are retried and succeed on second attempt."""
    mock_cfg = get_settings().model_copy()
    mock_cfg.WHATSAPP_PHONE_NUMBER_ID = "1000123456789"
    mock_cfg.WHATSAPP_ACCESS_TOKEN = SecretStr("valid_access_token_secret_123")

    calls = 0

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(500, text="Internal Server Error")
        return httpx.Response(200, json={"messages": [{"id": "wamid.success_on_retry"}]})

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as mock_client:
        with patch("api.services.whatsapp_templates.get_settings", return_value=mock_cfg):
            result = await send_whatsapp_template(
                to_phone="+919876543210",
                template_name="daily_horoscope_update",
                language_code="en",
                body_parameters=["User", "24 Oct", "Taurus", "Steady progress"],
                client=mock_client,
                max_retries=1
            )

    assert calls == 2
    assert result["messages"][0]["id"] == "wamid.success_on_retry"
