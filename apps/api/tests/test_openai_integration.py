"""Tests for OpenAI client initialization, prompt grounding, language preservation, and error fallback."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date, time
from pydantic import SecretStr

from api.config import get_settings
from api.db.models.birth_profile import TimeUncertaintyEnum
from api.services.astrology_service import (
    compute_astrology_chart,
    format_chart_facts_for_llm,
    generate_astrology_reading,
)


@pytest.fixture
def sample_exact_chart():
    return compute_astrology_chart(
        birth_date=date(1995, 10, 24),
        birth_time=time(14, 30),
        latitude=28.6139,
        longitude=77.2090,
        timezone_name="Asia/Kolkata",
        time_uncertainty=TimeUncertaintyEnum.EXACT,
    )


@pytest.fixture
def sample_unknown_time_chart():
    return compute_astrology_chart(
        birth_date=date(1992, 8, 18),
        birth_time=None,
        latitude=19.0760,
        longitude=72.8777,
        timezone_name="Asia/Kolkata",
        time_uncertainty=TimeUncertaintyEnum.UNKNOWN,
    )


# ── 1. Prompt Construction and Factual Grounding ──────────────────────────────

def test_chart_facts_formatting_with_exact_birth_time(sample_exact_chart):
    """Verify factual grounding prompt block includes exact Lagna, Nakshatra, and all planetary positions."""
    facts = format_chart_facts_for_llm(sample_exact_chart, TimeUncertaintyEnum.EXACT)

    assert "Astrological System: VEDIC" in facts
    assert "Ayanamsa: LAHIRI" in facts
    assert "Ascendant (Lagna): Aquarius (Kumbha)" in facts
    assert "Ascendant Nakshatra:" in facts
    assert "Planetary Placements:" in facts
    assert "- Sun: Libra (Tula)" in facts
    assert "- Moon: Libra (Tula)" in facts
    assert "- Jupiter: Scorpio (Vrischika)" in facts
    assert "House" in facts  # Houses are included when birth time is exact


def test_chart_facts_formatting_with_unknown_birth_time(sample_unknown_time_chart):
    """Verify factual grounding prompt block withholds Lagna and houses when birth time is unknown."""
    facts = format_chart_facts_for_llm(sample_unknown_time_chart, TimeUncertaintyEnum.UNKNOWN)

    assert "Ascendant (Lagna): UNKNOWN (Exact birth time was not provided; houses not calculated)" in facts
    # Planetary signs and Nakshatras remain grounded
    assert "- Moon: Pisces (Meena)" in facts
    assert "- Sun: Leo (Simha)" in facts
    # Houses must NOT be attributed to planets
    assert "House" not in facts


# ── 2. OpenAI Client Invocation & Language Selection ──────────────────────────

@pytest.mark.asyncio
async def test_openai_call_constructs_grounded_prompts_and_uses_configured_model(sample_exact_chart, monkeypatch):
    """Verify OpenAI client receives factual prompt, configured model, and strict grounding instructions."""
    settings = get_settings()
    monkeypatch.setattr(settings, "OPENAI_API_KEY", SecretStr("sk-dummy-mock-api-key-for-test"))

    mock_chat_completion = MagicMock()
    mock_chat_completion.choices = [
        MagicMock(message=MagicMock(content="✨ Personalized AI interpretation based strictly on your chart."))
    ]

    mock_client = AsyncMock()
    mock_client.chat.completions.create.return_value = mock_chat_completion

    with patch("api.services.astrology_service.get_settings", return_value=settings), \
         patch("openai.AsyncOpenAI", return_value=mock_client):

        result = await generate_astrology_reading(
            chart=sample_exact_chart,
            time_uncertainty=TimeUncertaintyEnum.EXACT,
            user_name="Aarav",
            lang="en"
        )

    assert result == "✨ Personalized AI interpretation based strictly on your chart."
    mock_client.chat.completions.create.assert_called_once()
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs

    # Model configuration check
    assert call_kwargs["model"] == settings.OPENAI_MODEL
    assert call_kwargs["temperature"] == 0.7
    assert call_kwargs["max_tokens"] == 600

    messages = call_kwargs["messages"]
    system_msg = messages[0]["content"]
    user_msg = messages[1]["content"]

    # Invariants in system prompt
    assert "Respond in English." in system_msg
    assert "CRITICAL RULES:" in system_msg
    assert "NEVER invent, hallucinate, or alter any planetary sign" in system_msg

    # Invariants in user prompt
    assert "Client Name: Aarav" in user_msg
    assert "Verified Chart Calculations:" in user_msg
    assert "Ascendant (Lagna): Aquarius (Kumbha)" in user_msg
    assert "Moon: Libra (Tula)" in user_msg


@pytest.mark.asyncio
async def test_openai_prompt_preserves_hindi_and_hinglish_instructions(sample_exact_chart, monkeypatch):
    """Verify user language preference (Hindi or Hinglish) is reflected in system prompt."""
    settings = get_settings()
    monkeypatch.setattr(settings, "OPENAI_API_KEY", SecretStr("sk-dummy-mock-api-key-for-test"))

    mock_chat_completion = MagicMock()
    mock_chat_completion.choices = [MagicMock(message=MagicMock(content="AI reading response."))]
    mock_client = AsyncMock()
    mock_client.chat.completions.create.return_value = mock_chat_completion

    with patch("api.services.astrology_service.get_settings", return_value=settings), \
         patch("openai.AsyncOpenAI", return_value=mock_client):

        # Test Hindi
        await generate_astrology_reading(sample_exact_chart, TimeUncertaintyEnum.EXACT, "राहुल", lang="hi")
        hi_system_msg = mock_client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        assert "Respond in Hindi." in hi_system_msg

        # Test Hinglish
        mock_client.reset_mock()
        mock_client.chat.completions.create.return_value = mock_chat_completion
        await generate_astrology_reading(sample_exact_chart, TimeUncertaintyEnum.EXACT, "Rahul", lang="hinglish")
        hinglish_system_msg = mock_client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        assert "Respond in conversational Hinglish." in hinglish_system_msg


# ── 3. Error Handling, Timeouts, and Safe Fallback ────────────────────────────

@pytest.mark.asyncio
async def test_openai_api_error_falls_back_gracefully_to_deterministic_reading(sample_exact_chart, monkeypatch):
    """Verify that network errors or API failures trigger deterministic fallback without crashing."""
    settings = get_settings()
    monkeypatch.setattr(settings, "OPENAI_API_KEY", SecretStr("sk-dummy-mock-api-key-for-test"))

    mock_client = AsyncMock()
    # Simulate API connection timeout or failure
    mock_client.chat.completions.create.side_effect = RuntimeError("OpenAI API Connection Timeout / Network Error")

    with patch("api.services.astrology_service.get_settings", return_value=settings), \
         patch("openai.AsyncOpenAI", return_value=mock_client):

        # Should not raise RuntimeError, but catch and return fallback reading
        fallback_reading = await generate_astrology_reading(
            chart=sample_exact_chart,
            time_uncertainty=TimeUncertaintyEnum.EXACT,
            user_name="Aarav",
            lang="en"
        )

    assert fallback_reading is not None
    # Grounded in deterministic calculation
    assert "Namaste Aarav!" in fallback_reading
    assert "Ascendant (Lagna): Aquarius (Kumbha)" in fallback_reading
    assert "Moon Sign (Chandra Rashi): Libra (Tula)" in fallback_reading
    assert "Swati" in fallback_reading
    # Secrets must not appear
    assert "sk-dummy" not in fallback_reading


@pytest.mark.asyncio
async def test_missing_openai_key_triggers_fallback_directly(sample_exact_chart, monkeypatch):
    """Verify that when OPENAI_API_KEY is None or empty, fallback is returned without attempting API call."""
    settings = get_settings()
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)

    with patch("api.services.astrology_service.get_settings", return_value=settings), \
         patch("openai.AsyncOpenAI") as mock_openai_cls:

        reading = await generate_astrology_reading(
            chart=sample_exact_chart,
            time_uncertainty=TimeUncertaintyEnum.EXACT,
            user_name="Aarav",
            lang="en"
        )

    # AsyncOpenAI should never be instantiated when key is missing
    mock_openai_cls.assert_not_called()
    assert "Namaste Aarav!" in reading
    assert "Ascendant (Lagna): Aquarius (Kumbha)" in reading
    assert "Moon Sign (Chandra Rashi): Libra (Tula)" in reading
