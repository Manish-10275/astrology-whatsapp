"""Astrology engine integration, offline geocoding, and LLM-grounded interpretation."""

import re
import logging
from datetime import date, time, datetime, timezone
from typing import Optional, Tuple, Dict, Any, List

from astrology_engine.models import (
    ChartRequest,
    D1Chart,
    AstrologySystem,
    AyanamsaType,
    HouseSystemType,
    TimeUncertainty,
    AshtakootaResult,
    PanchangResult,
    TransitAnalysisResult,
    WesternChartAnalysis,
    VimshottariDashaResult,
)
from astrology_engine.chart import calculate_d1_chart
from astrology_engine.dasha import calculate_vimshottari_dasha
from astrology_engine.panchang import calculate_panchang
from astrology_engine.compatibility import calculate_ashtakoota
from astrology_engine.transits import calculate_transits
from astrology_engine.western import analyze_western_chart
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

HINGLISH_KEYWORDS = {
    "kya", "hai", "mera", "meri", "mere", "mujhe", "batao", "bataiye", "kundli",
    "milan", "shani", "dasha", "aaj", "kaise", "kaisa", "hoga", "shukriya",
    "dhanyawad", "namaste", "pranam", "kripya", "rashifal", "bhavishya", "grah"
}


def detect_language(text: str) -> str:
    """Detects whether text is Hindi (Devanagari), Hinglish, or English.
    
    Returns: 'hi' for Hindi, 'hinglish' for Hinglish, 'en' for English.
    """
    if not text:
        return "en"

    # Devanagari script detection (U+0900 to U+097F)
    if re.search(r"[\u0900-\u097f]", text):
        return "hi"

    # Hinglish keyword matching
    tokens = set(re.findall(r"\b[a-zA-Z]+\b", text.lower()))
    matches = tokens.intersection(HINGLISH_KEYWORDS)
    if len(matches) >= 2 or (len(matches) == 1 and len(tokens) <= 5):
        return "hinglish"

    return "en"


def resolve_birthplace(location_input: str) -> Tuple[float, float, str, str]:
    """Resolves city string to (latitude, longitude, formatted_location_name, timezone_name)."""
    cleaned = location_input.strip().lower()

    for city_key, data in OFFLINE_LOCATIONS.items():
        if city_key in cleaned:
            return data

    logger.warning("Unrecognized location '%s'; falling back to New Delhi coordinates.", location_input)
    return (28.6139, 77.2090, f"{location_input.title()} (Estimated Coordinates)", "Asia/Kolkata")


def parse_birth_date(date_str: str) -> Optional[date]:
    """Parses various date string formats into a date object."""
    cleaned = date_str.strip()
    iso_match = re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$", cleaned)
    if iso_match:
        try:
            return date(int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3)))
        except ValueError:
            return None

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

    ayanamsa = AyanamsaType.LAHIRI if system == AstrologySystem.VEDIC else None
    house_sys = HouseSystemType.WHOLE_SIGN if system == AstrologySystem.VEDIC else HouseSystemType.PLACIDUS

    request = ChartRequest(
        birth_date=birth_date,
        birth_time=birth_time,
        latitude=latitude,
        longitude=longitude,
        timezone_name=timezone_name,
        system=system,
        ayanamsa=ayanamsa,
        house_system=house_sys,
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


def format_western_reading(chart: D1Chart, user_name: Optional[str] = None, lang: str = "en") -> str:
    """Formats a deterministic Western Astrology chart interpretation."""
    analysis = analyze_western_chart(chart)
    greeting = f"Hello {user_name}! ✨" if user_name else "Hello! ✨"

    if lang == "hi":
        lines = [
            f"{greeting} यहाँ आपकी पाश्चात्य जन्म कुंडली (Western Natal Chart) का विस्तृत विश्लेषण प्रस्तुत है:\n",
            f"☀️ **सूर्य राशि (Sun Sign): {analysis.sun_sign}** - आपका मूल व्यक्तित्व, जीवन ऊर्जा और पहचान।",
            f"🌙 **चंद्र राशि (Moon Sign): {analysis.moon_sign}** - आपकी आंतरिक भावनाएं, मन और अंतर्ज्ञान।",
        ]
        if analysis.ascendant_sign:
            lines.append(f"🌅 **उदय लग्न (Ascendant / Rising): {analysis.ascendant_sign}** - दुनिया के सामने आपका दृष्टिकोण और पहली छाप।")
        lines.extend([
            f"\n🔥 **प्रमुख तत्व (Dominant Element):** {analysis.dominant_element}",
            f"⚡ **प्रमुख प्रवृत्ति (Dominant Modality):** {analysis.dominant_modality}",
            "\n📐 **प्रमुख पहलू (Major Aspects):**",
        ])
        for aspect in analysis.aspects[:5]:
            lines.append(f"• {aspect.aspect_type.title()} {aspect.planet_1} & {aspect.planet_2} (Orb: {aspect.orb:.1f}°)")
        lines.append("\n🔮 *आप अपने दैनिक राशिफल, गोचर या किसी भी प्रश्न के लिए कभी भी संदेश भेज सकते हैं!*")
        return "\n".join(lines)

    lines = [
        f"{greeting} Here is your authentic Western Natal Chart reading:\n",
        f"☀️ **Sun in {analysis.sun_sign}:** Your core identity, vitality, and conscious ego.",
        f"🌙 **Moon in {analysis.moon_sign}:** Your emotional landscape, instinctive reactions, and inner soul.",
    ]
    if analysis.ascendant_sign:
        lines.append(f"🌅 **Rising Sign (Ascendant) in {analysis.ascendant_sign}:** The lens through which you experience the outer world.")
    else:
        lines.append("🌅 **Rising Sign:** Unknown (Birth time withheld; houses not calculated).")

    lines.extend([
        f"\n🎨 **Cosmic Signature:**",
        f"• **Dominant Element:** {analysis.dominant_element} ({analysis.element_distribution.get(analysis.dominant_element.lower(), 0)} placements)",
        f"• **Dominant Modality:** {analysis.dominant_modality} ({analysis.modality_distribution.get(analysis.dominant_modality.lower(), 0)} placements)",
        f"\n📐 **Major Astrological Aspects:**",
    ])
    for aspect in analysis.aspects[:5]:
        lines.append(f"• **{aspect.planet_1} {aspect.aspect_type.title()} {aspect.planet_2}:** {aspect.significance}")

    lines.append("\n🔮 *Feel free to ask about your daily forecast, planetary transits, or compatibility!*")
    return "\n".join(lines)


async def generate_astrology_reading(
    chart: D1Chart,
    time_uncertainty: TimeUncertaintyEnum,
    user_name: Optional[str] = None,
    lang: str = "en"
) -> str:
    """Generates an authentic natural language interpretation of verified chart calculations."""
    if chart.system == AstrologySystem.WESTERN:
        return format_western_reading(chart, user_name, lang)

    settings = get_settings()
    facts_text = format_chart_facts_for_llm(chart, time_uncertainty)

    if settings.OPENAI_API_KEY and settings.OPENAI_API_KEY.get_secret_value():
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY.get_secret_value())

            lang_instruction = "Respond in Hindi." if lang == "hi" else ("Respond in conversational Hinglish." if lang == "hinglish" else "Respond in English.")

            system_prompt = (
                f"You are an authentic, deeply insightful, and empathetic Vedic Astrologer on WhatsApp. {lang_instruction} "
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

    # Deterministic fallback interpreter
    moon_p = next((p for p in chart.planets if p.name == "Moon"), None)
    sun_p = next((p for p in chart.planets if p.name == "Sun"), None)
    jupiter_p = next((p for p in chart.planets if p.name == "Jupiter"), None)

    if lang == "hi":
        greeting = f"नमस्ते {user_name}! 🕉️" if user_name else "नमस्ते! 🕉️"
        lines = [
            f"{greeting} यहाँ आपकी प्रामाणिक वैदिक जन्म कुंडली (Kundli) का विवरण है:\n",
        ]
        if chart.ascendant and time_uncertainty != TimeUncertaintyEnum.UNKNOWN:
            lines.append(f"🌅 **लग्न (Ascendant): {chart.ascendant.sign_sanskrit} ({chart.ascendant.sign_name})**\nआपका लग्न आपके व्यक्तित्व, शारीरिक स्वास्थ्य और जीवन दृष्टिकोण का प्रतिनिधित्व करता है।\n")
        else:
            lines.append("🌅 **लग्न (Ascendant): अज्ञात**\nसटीक जन्म समय उपलब्ध न होने के कारण भाव और लग्न रोके गए हैं। आपके ग्रह और नक्षत्र 100% सटीक हैं।\n")

        if moon_p:
            nak_name = moon_p.nakshatra.name if moon_p.nakshatra else "Unknown"
            lines.append(f"🌙 **चंद्र राशि: {moon_p.sign_sanskrit} ({moon_p.sign_name})**\n• **नक्षत्र:** {nak_name}\nचंद्रमा आपके मन, विचारों और भावनात्मक स्थिरता का प्रतीक है।\n")
        if sun_p:
            lines.append(f"☀️ **सूर्य राशि: {sun_p.sign_sanskrit} ({sun_p.sign_name})**\nसूर्य आपकी आत्मा की शक्ति और आत्मविश्वास का प्रतिनिधित्व करता है।\n")
        if jupiter_p:
            lines.append(f"✨ **बृहस्पति (गुरु) का प्रभाव:**\nगुरु {jupiter_p.sign_sanskrit} राशि में ज्ञान, विवेक और भाग्य में वृद्धि करते हैं।\n")
        lines.append("🔮 *दैनिक राशिफल, विंशोत्तरी दशा, या गोचर जानने के लिए कभी भी प्रश्न पूछें!*")
        return "\n".join(lines)

    elif lang == "hinglish":
        greeting = f"Namaste {user_name}! 🕉️" if user_name else "Namaste! 🕉️"
        lines = [
            f"{greeting} Yeh rahi aapki authentic Vedic Birth Chart (Kundli) reading:\n",
        ]
        if chart.ascendant and time_uncertainty != TimeUncertaintyEnum.UNKNOWN:
            lines.append(f"🌅 **Ascendant (Lagna): {chart.ascendant.sign_sanskrit} ({chart.ascendant.sign_name})**\nAapka lagna aapki personality, energy aur approach ko dikhata hai.\n")
        else:
            lines.append("🌅 **Ascendant (Lagna): Withheld**\nExact birth time missing hone ki wajah se lagna withhold kiya gaya hai. Planets aur Nakshatra 100% accurate hain.\n")

        if moon_p:
            nak_name = moon_p.nakshatra.name if moon_p.nakshatra else "Unknown"
            lines.append(f"🌙 **Moon Sign (Chandra Rashi): {moon_p.sign_sanskrit} ({moon_p.sign_name})**\n• **Nakshatra:** {nak_name}\nChandra aapke mann aur emotions ka prateek hai. Yeh aapko emotional clarity deta hai.\n")
        if sun_p:
            lines.append(f"☀️ **Sun Sign (Surya Rashi): {sun_p.sign_sanskrit} ({sun_p.sign_name})**\nSurya aapki inner confidence aur leadership strength ko show karta hai.\n")
        if jupiter_p:
            lines.append(f"✨ **Guru (Jupiter) Presence:**\nJupiter {jupiter_p.sign_sanskrit} mein wisdom aur prosperity promote karta hai.\n")
        lines.append("🔮 *Dasha, Daily Horoscope ya Transits check karne ke liye reply karein!*")
        return "\n".join(lines)

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
        "\n🔮 *Would you like to explore your planetary transits, ask a specific question, or check compatibility? Just message me anytime!*"
    )

    return "\n".join(reading_lines)


def format_dasha_reading(
    birth_date: date,
    birth_time: Optional[time],
    latitude: float,
    longitude: float,
    timezone_name: str,
    target_dt: Optional[datetime] = None,
    lang: str = "en"
) -> str:
    """Calculates Vimshottari Dasha and returns the active Mahadasha and Antardasha report."""
    chart = compute_astrology_chart(
        birth_date=birth_date,
        birth_time=birth_time,
        latitude=latitude,
        longitude=longitude,
        timezone_name=timezone_name,
        system=AstrologySystem.VEDIC
    )
    moon = next((p for p in chart.planets if p.name == "Moon"), None)
    if not moon:
        return "Could not compute Moon position for Dasha calculation."

    check_dt = target_dt or datetime.now(timezone.utc)
    as_of_date = check_dt.date() if isinstance(check_dt, datetime) else check_dt
    dasha_result = calculate_vimshottari_dasha(
        moon_longitude=moon.longitude,
        birth_date=birth_date,
        as_of_date=as_of_date
    )

    active_md = next((m for m in dasha_result.mahadashas if m.start_date <= as_of_date <= m.end_date), None)
    if not active_md and dasha_result.mahadashas:
        active_md = dasha_result.mahadashas[0]

    active_ad = None
    if active_md and active_md.antardashas:
        active_ad = next((a for a in active_md.antardashas if a.start_date <= as_of_date <= a.end_date), None)
        if not active_ad:
            active_ad = active_md.antardashas[0]

    md_ruler = active_md.ruler if active_md else (dasha_result.current_mahadasha or "Unknown")
    ad_ruler = active_ad.ruler if active_ad else (dasha_result.current_antardasha or "Unknown")

    md_dates = f"{active_md.start_date.strftime('%d %b %Y')} to {active_md.end_date.strftime('%d %b %Y')}" if active_md else ""
    ad_dates = f"{active_ad.start_date.strftime('%d %b %Y')} to {active_ad.end_date.strftime('%d %b %Y')}" if active_ad else ""

    if lang in ("hi", "hinglish"):
        return (
            f"⏳ **विंशोत्तरी दशा (Vimshottari Dasha Analysis)**\n\n"
            f"🌙 **जन्म नक्षत्र (Birth Nakshatra):** {dasha_result.nakshatra_name}\n"
            f"👑 **सक्रिय महादशा (Active Mahadasha):** {md_ruler}\n"
            f"📅 अवधि (Period): {md_dates}\n\n"
            f"🌟 **सक्रिय अंतर्दशा (Active Antardasha):** {ad_ruler}\n"
            f"📅 अवधि (Period): {ad_dates}\n\n"
            f"💡 **मार्गदर्शन:** वर्तमान समय में {md_ruler}-{ad_ruler} का प्रभाव आपके जीवन की दिशा और निर्णयों को आकार दे रहा है। संयम और एकाग्रता रखें।"
        )

    return (
        f"⏳ **Vimshottari Dasha Report**\n\n"
        f"🌙 **Birth Nakshatra:** {dasha_result.nakshatra_name}\n"
        f"👑 **Current Mahadasha:** {md_ruler}\n"
        f"📅 Duration: {md_dates}\n\n"
        f"🌟 **Current Antardasha:** {ad_ruler}\n"
        f"📅 Duration: {ad_dates}\n\n"
        f"💡 **Cosmic Focus:** You are currently navigating the planetary cycle of **{md_ruler}-{ad_ruler}**. "
        f"This phase emphasizes themes associated with {md_ruler} as your macro-influence and {ad_ruler} as your micro-influencer."
    )


def format_transits_reading(
    birth_date: date,
    birth_time: Optional[time],
    latitude: float,
    longitude: float,
    timezone_name: str,
    time_uncertainty: TimeUncertaintyEnum = TimeUncertaintyEnum.EXACT,
    lang: str = "en"
) -> str:
    """Calculates Gochara (transits) and Sade Sati for natal chart."""
    chart = compute_astrology_chart(
        birth_date=birth_date,
        birth_time=birth_time,
        latitude=latitude,
        longitude=longitude,
        timezone_name=timezone_name,
        time_uncertainty=time_uncertainty,
        system=AstrologySystem.VEDIC
    )
    transit_result = calculate_transits(chart)

    lines = ["🪐 **Planetary Transits & Gochara Analysis**\n"]

    if transit_result.sade_sati_active:
        lines.append(f"⚠️ **Shani Sade Sati Status: ACTIVE ({transit_result.sade_sati_phase})**")
        lines.append(f"• {transit_result.summary}\n")
    else:
        lines.append("✅ **Shani Sade Sati Status: INACTIVE**")
        lines.append("• Saturn is currently not transiting your 12th, 1st, or 2nd house from natal Moon.\n")

    lines.append("🌟 **Key Planetary Transits Today:**")
    for t_planet in transit_result.planets:
        if t_planet.name in ("Jupiter", "Saturn", "Rahu", "Mars", "Sun"):
            house_str = f"House {t_planet.house_from_moon} from Moon" if t_planet.house_from_moon else ""
            status_icon = "✨" if t_planet.is_auspicious else "🔸"
            lines.append(
                f"{status_icon} **{t_planet.name}** in {t_planet.sign_name} ({t_planet.sign_sanskrit or ''}) - {house_str}\n"
                f"  {t_planet.key_effects}"
            )

    return "\n".join(lines)


def format_panchang_reading(
    latitude: float,
    longitude: float,
    timezone_name: str,
    target_dt: Optional[datetime] = None,
    lang: str = "en"
) -> str:
    """Calculates Vedic Panchang for the specified location and time."""
    now_dt = target_dt or datetime.now(timezone.utc)
    target_date = now_dt.date() if isinstance(now_dt, datetime) else now_dt

    chart = compute_astrology_chart(
        birth_date=target_date,
        birth_time=now_dt.time() if isinstance(now_dt, datetime) else time(12, 0),
        latitude=latitude,
        longitude=longitude,
        timezone_name=timezone_name,
        system=AstrologySystem.VEDIC
    )
    sun = next((p for p in chart.planets if p.name == "Sun"), None)
    moon = next((p for p in chart.planets if p.name == "Moon"), None)

    if not sun or not moon:
        return "Could not compute Sun and Moon positions for Panchang."

    panchang = calculate_panchang(
        sun_longitude=sun.longitude,
        moon_longitude=moon.longitude,
        target_date=target_date
    )

    date_str = panchang.date.strftime("%d %B %Y")
    tithi_name = f"{panchang.tithi.paksha} {panchang.tithi.name} (Tithi {panchang.tithi.number})"
    bhadra_warning = "⚠️ Bhadra (Vishti) active - avoid initiating critical ventures." if panchang.karana.is_vishti else "Favorable"

    if lang in ("hi", "hinglish"):
        return (
            f"📅 **दैनिक पंचांग (Daily Panchang)**\n"
            f"📍 दिनांक: {date_str}\n\n"
            f"🌞 **वार (Day):** {panchang.vara} (स्वामी: {panchang.vara_lord})\n"
            f"🌙 **तिथि (Tithi):** {tithi_name}\n"
            f"⭐ **नक्षत्र (Nakshatra):** {panchang.nakshatra.name} (पद {panchang.nakshatra.pada}, स्वामी: {panchang.nakshatra.ruler})\n"
            f"🧘 **योग (Yoga):** {panchang.yoga.name}\n"
            f"⚖️ **करण (Karana):** {panchang.karana.name} ({bhadra_warning})"
        )

    return (
        f"📅 **Vedic Panchang for {date_str}**\n\n"
        f"🌞 **Vara (Day):** {panchang.vara} (Lord: {panchang.vara_lord})\n"
        f"🌙 **Tithi:** {tithi_name}\n"
        f"⭐ **Nakshatra:** {panchang.nakshatra.name} (Pada {panchang.nakshatra.pada}, Ruler: {panchang.nakshatra.ruler})\n"
        f"🧘 **Yoga:** {panchang.yoga.name}\n"
        f"⚖️ **Karana:** {panchang.karana.name} ({bhadra_warning})"
    )


def format_compatibility_reading(
    person1_chart: D1Chart,
    person2_chart: D1Chart,
    name1: Optional[str] = None,
    name2: Optional[str] = None,
    lang: str = "en"
) -> str:
    """Calculates classical 36-Guna Ashtakoota compatibility between two charts."""
    moon1 = next((p for p in person1_chart.planets if p.name == "Moon"), None)
    moon2 = next((p for p in person2_chart.planets if p.name == "Moon"), None)

    if not moon1 or not moon2:
        return "Could not calculate compatibility: Moon positions missing from one or both charts."

    result = calculate_ashtakoota(groom_moon_longitude=moon1.longitude, bride_moon_longitude=moon2.longitude)

    p1 = name1 or "Person 1"
    p2 = name2 or "Person 2"

    lines = [
        f"💞 **Kundli Milan & Compatibility (Ashtakoota 36 Gunas)**\n",
        f"• **{p1}:** Moon in {moon1.sign_name} ({moon1.nakshatra.name if moon1.nakshatra else ''})",
        f"• **{p2}:** Moon in {moon2.sign_name} ({moon2.nakshatra.name if moon2.nakshatra else ''})\n",
        f"🏆 **Total Guna Score: {result.total_score:.1f} / 36.0** ({result.percentage:.1f}%)",
        f"📋 **Verdict:** {result.verdict}\n",
        "📊 **Detailed Guna Breakdown:**",
    ]

    for koota in result.kootas:
        lines.append(f"• {koota.name.title()}: {koota.obtained_points:.1f} / {koota.max_points:.1f} - {koota.description}")

    lines.append("\n⚖️ **Dosha & Exceptions Analysis:**")
    if result.nadi_dosha:
        if result.nadi_dosha_cancelled:
            lines.append("• 🛡️ **Nadi Dosha:** Present but classically CANCELLED due to different Padas or compatible Nakshatras.")
        else:
            lines.append("• ⚠️ **Nadi Dosha:** ACTIVE. Classical texts advise caution regarding physiological and lineage harmony.")
    else:
        lines.append("• ✅ **Nadi Dosha:** None. Complete physiological harmony.")

    if result.bhakoot_dosha:
        if result.bhakoot_dosha_cancelled:
            lines.append("• 🛡️ **Bhakoot Dosha:** Present but CANCELLED due to common planetary friendship.")
        else:
            lines.append("• ⚠️ **Bhakoot Dosha:** ACTIVE (6-8 or 9-5 axis). Requires emotional patience and open communication.")
    else:
        lines.append("• ✅ **Bhakoot Dosha:** None.")

    return "\n".join(lines)


def generate_daily_horoscope_for_profile(
    birth_date: date,
    birth_time: Optional[time],
    latitude: float,
    longitude: float,
    timezone_name: str,
    target_date: Optional[date] = None,
    user_name: Optional[str] = None,
    system: AstrologySystem = AstrologySystem.VEDIC,
    lang: str = "en"
) -> str:
    """Generates an authentic daily horoscope grounded in current transits relative to natal Moon."""
    chart = compute_astrology_chart(
        birth_date=birth_date,
        birth_time=birth_time,
        latitude=latitude,
        longitude=longitude,
        timezone_name=timezone_name,
        system=system
    )
    moon = next((p for p in chart.planets if p.name == "Moon"), None)
    sun = next((p for p in chart.planets if p.name == "Sun"), None)

    t_date = target_date or datetime.now(timezone.utc).date()
    t_dt = datetime.combine(t_date, time(12, 0)).replace(tzinfo=timezone.utc)
    transits = calculate_transits(chart, transit_datetime=t_dt)

    moon_sign = moon.sign_name if moon else "Zodiac"
    moon_sanskrit = moon.sign_sanskrit if moon else ""
    user_display = f"{user_name}" if user_name else "Friend"

    # Identify beneficial planetary transits today
    auspicious_count = sum(1 for t in transits.planets if t.is_auspicious)
    overall_tone = "highly auspicious and constructive" if auspicious_count >= 4 else "a day for mindful steady focus"

    if lang in ("hi", "hinglish"):
        return (
            f"✨ **दैनिक राशिफल (Daily Horoscope) — {t_date.strftime('%d %B %Y')}** ✨\n\n"
            f"नमस्ते {user_display}! 🕉️\n"
            f"🌙 **आपकी चंद्र राशि:** {moon_sanskrit} ({moon_sign})\n\n"
            f"🔮 **आज का ग्रह गोचर:**\n"
            f"आज का दिन आपके लिए {overall_tone} रहेगा। चंद्रमा और गुरु का गोचर आपके मानसिक संतुलन और निर्णयों में सहायक होगा।\n\n"
            f"💼 **करियर व धन:** आवश्यक कार्यों को प्राथमिकता दें। जल्दबाजी में निवेश से बचें।\n"
            f"❤️ **पारिवारिक व रिश्ते:** परिजनों के साथ मधुर संवाद बनाए रखें।\n"
            f"🌟 **शुभ सलाह:** आज भगवान शिव या अपने ईष्टदेव का स्मरण करें और जल अर्पित करें।"
        )

    return (
        f"✨ **Daily Horoscope for {t_date.strftime('%A, %d %B %Y')}** ✨\n\n"
        f"Greetings {user_display}! 🌟\n"
        f"🌙 **Moon Sign:** {moon_sign} ({moon_sanskrit})\n\n"
        f"🔮 **Planetary Alignment:**\n"
        f"Today's planetary transits suggest {overall_tone}. Transiting Moon and supporting planets bring "
        f"clarity to your emotional state and decision making.\n\n"
        f"💼 **Career & Focus:** Maintain structured discipline. Progress is favored through systematic action.\n"
        f"❤️ **Relationships:** Open, empathetic listening will strengthen personal harmony.\n"
        f"🌿 **Cosmic Tip:** Take 5 minutes today for mindfulness and deep breathing to center your planetary energy."
    )
