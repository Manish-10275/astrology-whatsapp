"""Astrology engine integration, offline geocoding, and LLM-grounded interpretation."""

import re
import logging
from datetime import date, time, datetime
from typing import Optional, Tuple, Dict, Any

from astrology_engine.models import (
    ChartRequest,
    D1Chart,
    AstrologySystem,
    AyanamsaType,
    HouseSystemType,
    TimeUncertainty,
)
from astrology_engine.chart import calculate_d1_chart
from api.db.models.birth_profile import TimeUncertaintyEnum
from api.config import get_settings

logger = logging.getLogger("api.services.astrology")

# Comprehensive offline geocoding database for common cities
OFFLINE_LOCATIONS: Dict[str, Tuple[float, float, str, str]] = {
    # India
    "new delhi": (28.6139, 77.2090, "New Delhi, India", "Asia/Kolkata"),
    "delhi": (28.6139, 77.2090, "New Delhi, India", "Asia/Kolkata"),
    "mumbai": (19.0760, 72.8777, "Mumbai, India", "Asia/Kolkata"),
    "bombay": (19.0760, 72.8777, "Mumbai, India", "Asia/Kolkata"),
    "bangalore": (12.9716, 77.5946, "Bengaluru, India", "Asia/Kolkata"),
    "bengaluru": (12.9716, 77.5946, "Bengaluru, India", "Asia/Kolkata"),
    "kolkata": (22.5726, 88.3639, "Kolkata, India", "Asia/Kolkata"),
    "calcutta": (22.5726, 88.3639, "Kolkata, India", "Asia/Kolkata"),
    "chennai": (13.0827, 80.2707, "Chennai, India", "Asia/Kolkata"),
    "madras": (13.0827, 80.2707, "Chennai, India", "Asia/Kolkata"),
    "hyderabad": (17.3850, 78.4867, "Hyderabad, India", "Asia/Kolkata"),
    "pune": (18.5204, 73.8567, "Pune, India", "Asia/Kolkata"),
    "ahmedabad": (23.0225, 72.5714, "Ahmedabad, India", "Asia/Kolkata"),
    "jaipur": (26.9124, 75.7873, "Jaipur, India", "Asia/Kolkata"),
    "lucknow": (26.8467, 80.9462, "Lucknow, India", "Asia/Kolkata"),
    "varanasi": (25.3176, 82.9739, "Varanasi, India", "Asia/Kolkata"),
    "chandigarh": (30.7333, 76.7794, "Chandigarh, India", "Asia/Kolkata"),
    # International
    "london": (51.5074, -0.1278, "London, United Kingdom", "Europe/London"),
    "new york": (40.7128, -74.0060, "New York, USA", "America/New_York"),
    "san francisco": (37.7749, -122.4194, "San Francisco, USA", "America/Los_Angeles"),
    "dubai": (25.2048, 55.2708, "Dubai, UAE", "Asia/Dubai"),
    "singapore": (1.3521, 103.8198, "Singapore", "Asia/Singapore"),
    "sydney": (-33.8688, 151.2093, "Sydney, Australia", "Australia/Sydney"),
    "toronto": (43.6532, -79.3832, "Toronto, Canada", "America/Toronto"),
    "tokyo": (35.6762, 139.6503, "Tokyo, Japan", "Asia/Tokyo"),
}


def resolve_birthplace(location_input: str) -> Tuple[float, float, str, str]:
    """Resolves city string to (latitude, longitude, formatted_location_name, timezone_name)."""
    cleaned = location_input.strip().lower()

    # Direct match or substring match in offline lookup table
    for city_key, data in OFFLINE_LOCATIONS.items():
        if city_key in cleaned:
            return data

    # Default fallback to New Delhi if unresolvable in offline test mode
    logger.warning("Unrecognized location '%s'; falling back to New Delhi coordinates.", location_input)
    return (28.6139, 77.2090, f"{location_input.title()} (Estimated Coordinates)", "Asia/Kolkata")


def parse_birth_date(date_str: str) -> Optional[date]:
    """Parses various date string formats into a date object."""
    cleaned = date_str.strip()
    # Support YYYY-MM-DD
    iso_match = re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$", cleaned)
    if iso_match:
        try:
            return date(int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3)))
        except ValueError:
            return None

    # Support DD-MM-YYYY
    dmy_match = re.match(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$", cleaned)
    if dmy_match:
        try:
            return date(int(dmy_match.group(3)), int(dmy_match.group(2)), int(dmy_match.group(1)))
        except ValueError:
            return None

    return None


def parse_birth_time(time_str: str) -> Tuple[Optional[time], TimeUncertaintyEnum]:
    """Parses birth time string. Returns (time_obj, uncertainty_enum)."""
    cleaned = time_str.strip().lower()

    if cleaned in ("unknown", "no", "not sure", "dont know", "don't know", "skip", "none"):
        return None, TimeUncertaintyEnum.UNKNOWN

    # Check 12-hour format with am/pm (e.g., "2:30 pm", "08:15am")
    ampm_match = re.match(r"^(\d{1,2}):(\d{2})\s*(am|pm)$", cleaned)
    if ampm_match:
        hours = int(ampm_match.group(1))
        minutes = int(ampm_match.group(2))
        period = ampm_match.group(3)
        if period == "pm" and hours < 12:
            hours += 12
        elif period == "am" and hours == 12:
            hours = 0
        try:
            return time(hours, minutes), TimeUncertaintyEnum.EXACT
        except ValueError:
            return None, TimeUncertaintyEnum.UNKNOWN

    # Check 24-hour format (e.g., "14:30", "08:15")
    match_24 = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$", cleaned)
    if match_24:
        hours = int(match_24.group(1))
        minutes = int(match_24.group(2))
        seconds = int(match_24.group(3) or 0)
        try:
            return time(hours, minutes, seconds), TimeUncertaintyEnum.EXACT
        except ValueError:
            return None, TimeUncertaintyEnum.UNKNOWN

    return None, TimeUncertaintyEnum.UNKNOWN


def compute_astrology_chart(
    birth_date: date,
    birth_time: Optional[time],
    latitude: float,
    longitude: float,
    timezone_name: str,
    time_uncertainty: TimeUncertaintyEnum = TimeUncertaintyEnum.EXACT,
    system: AstrologySystem = AstrologySystem.VEDIC
) -> D1Chart:
    """Invokes the deterministic calculation engine to compute natal chart positions."""
    engine_uncertainty = (
        TimeUncertainty.UNKNOWN
        if time_uncertainty == TimeUncertaintyEnum.UNKNOWN
        else TimeUncertainty.EXACT
    )

    request = ChartRequest(
        birth_date=birth_date,
        birth_time=birth_time,
        latitude=latitude,
        longitude=longitude,
        timezone_name=timezone_name,
        system=system,
        ayanamsa=AyanamsaType.LAHIRI,
        house_system=HouseSystemType.WHOLE_SIGN,
        time_uncertainty=engine_uncertainty
    )

    return calculate_d1_chart(request)


def format_chart_facts_for_llm(chart: D1Chart, time_uncertainty: TimeUncertaintyEnum) -> str:
    """Formats verified calculation facts into a structured prompt block for the LLM."""
    ayanamsa_str = chart.ayanamsa_used.upper() if chart.ayanamsa_used else "NONE"
    offset_str = f"{chart.ayanamsa_degrees:.4f}°" if chart.ayanamsa_degrees is not None else "0.0°"
    lines = [
        f"Astrological System: {chart.system.value.upper()}",
        f"Ayanamsa: {ayanamsa_str} (Offset: {offset_str})",
        f"Ephemeris Mode: {chart.ephemeris_mode.upper()}",
    ]

    if time_uncertainty != TimeUncertaintyEnum.UNKNOWN and chart.ascendant:
        lines.append(
            f"Ascendant (Lagna): {chart.ascendant.sign_name} ({chart.ascendant.sign_sanskrit}) at {chart.ascendant.degree_in_sign:.2f}°"
        )
        if chart.ascendant.nakshatra:
            lines.append(
                f"Ascendant Nakshatra: {chart.ascendant.nakshatra.name} (Pada {chart.ascendant.nakshatra.pada}, Lord: {chart.ascendant.nakshatra.ruler})"
            )
    else:
        lines.append("Ascendant (Lagna): UNKNOWN (Exact birth time was not provided; houses not calculated)")

    lines.append("\nPlanetary Placements:")
    for planet in chart.planets:
        p_str = f"- {planet.name}: {planet.sign_name} ({planet.sign_sanskrit}) at {planet.degree_in_sign:.2f}°"
        if planet.is_retrograde:
            p_str += " [RETROGRADE]"
        if planet.house:
            p_str += f", House {planet.house}"
        if planet.nakshatra:
            p_str += f", Nakshatra: {planet.nakshatra.name} (Pada {planet.nakshatra.pada}, Ruler: {planet.nakshatra.ruler})"
        lines.append(p_str)

    return "\n".join(lines)


async def generate_astrology_reading(
    chart: D1Chart,
    time_uncertainty: TimeUncertaintyEnum,
    user_name: Optional[str] = None
) -> str:
    """Generates an authentic natural language interpretation of verified chart calculations."""
    settings = get_settings()
    facts_text = format_chart_facts_for_llm(chart, time_uncertainty)

    # If OpenAI API Key is available, invoke OpenAI for natural language synthesis
    if settings.OPENAI_API_KEY and settings.OPENAI_API_KEY.get_secret_value():
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY.get_secret_value())

            system_prompt = (
                "You are an authentic, deeply insightful, and empathetic Vedic Astrologer on WhatsApp. "
                "You are interpreting a newly calculated birth chart for a client. "
                "CRITICAL RULES:\n"
                "1. Strictly base your analysis on the verified calculation facts provided below.\n"
                "2. NEVER invent, hallucinate, or alter any planetary sign, degree, house, or placement.\n"
                "3. If Ascendant is UNKNOWN, explicitly explain that planetary positions and Nakshatras are accurate, but house placements and Lagna depend on birth time.\n"
                "4. Structure your response clearly for WhatsApp: Warm Greeting -> Core Vedic Signatures (Lagna/Moon/Sun) -> Key Strengths & Planetary Powers -> Practical Guidance.\n"
                "5. Use appropriate emojis and bullet points for readability. Keep length within 350 words."
            )

            user_prompt = (
                f"Client Name: {user_name or 'Seeker'}\n\n"
                f"Verified Chart Calculations:\n{facts_text}\n\n"
                "Please deliver their personalized birth chart reading."
            )

            response = await client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                max_tokens=600,
            )
            return response.choices[0].message.content.strip()
        except Exception as exc:
            logger.error("OpenAI interpretation failed, falling back to deterministic template: %s", exc)

    # Deterministic fallback interpreter (zero LLM hallucinations)
    # Find Moon, Sun, Ascendant
    moon_p = next((p for p in chart.planets if p.name == "Moon"), None)
    sun_p = next((p for p in chart.planets if p.name == "Sun"), None)
    jupiter_p = next((p for p in chart.planets if p.name == "Jupiter"), None)

    greeting = f"Namaste {user_name}! 🕉️" if user_name else "Namaste! 🕉️"
    
    reading_lines = [
        f"{greeting} Here is your authentic Vedic Birth Chart (Kundli) reading, based on high-precision astronomical calculations:\n",
    ]

    if chart.ascendant and time_uncertainty != TimeUncertaintyEnum.UNKNOWN:
        reading_lines.append(
            f"🌅 **Ascendant (Lagna): {chart.ascendant.sign_name} ({chart.ascendant.sign_sanskrit})**\n"
            f"Your rising sign reflects your physical vitality, worldly approach, and outer personality.\n"
        )
    else:
        reading_lines.append(
            "🌅 **Ascendant (Lagna): Withheld**\n"
            "Because an exact birth time was not provided, houses and Ascendant are withheld to ensure accuracy. Your Moon and planetary sign placements remain 100% precise.\n"
        )

    if moon_p:
        nak_name = moon_p.nakshatra.name if moon_p.nakshatra else "Unknown"
        nak_ruler = moon_p.nakshatra.ruler if moon_p.nakshatra else "Unknown"
        reading_lines.append(
            f"🌙 **Moon Sign (Chandra Rashi): {moon_p.sign_name} ({moon_p.sign_sanskrit})**\n"
            f"• **Nakshatra:** {nak_name} (Ruled by {nak_ruler})\n"
            f"Your Moon represents your emotional foundation, subconscious mind, and intuition. "
            f"In {moon_p.sign_name}, you process life with sensitivity and depth.\n"
        )

    if sun_p:
        reading_lines.append(
            f"☀️ **Sun Sign (Surya Rashi): {sun_p.sign_name} ({sun_p.sign_sanskrit})**\n"
            f"The Sun represents your core soul vitality, purpose, and inner confidence.\n"
        )

    if jupiter_p:
        reading_lines.append(
            f"✨ **Key Planetary Influence:**\n"
            f"Jupiter (Guru) in {jupiter_p.sign_name} brings wisdom, benevolence, and long-term expansion to your life path."
        )

    reading_lines.append(
        "\n🔮 *Would you like to explore your planetary transits, ask a specific question, or view another profile? Just message me anytime!*"
    )

    return "\n".join(reading_lines)
