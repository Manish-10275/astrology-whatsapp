"""Planetary Transits (Gochara) calculation and natal comparison engine."""

from datetime import date, datetime, timezone
from typing import Optional, List
from astrology_engine.models import (
    D1Chart,
    TransitPlanet,
    TransitAnalysisResult,
    AyanamsaType,
    ZODIAC_SIGNS,
)
from astrology_engine.adapter import SwissEphemerisAdapter, default_adapter
from astrology_engine.time_utils import compute_julian_day
from astrology_engine.sidereal import calculate_sidereal_planets

# Classical Gochara auspicious houses from natal Moon
AUSPICIOUS_HOUSES_FROM_MOON = {
    "Sun": {3, 6, 10, 11},
    "Moon": {1, 3, 6, 7, 10, 11},
    "Mars": {3, 6, 11},
    "Mercury": {2, 4, 6, 8, 10, 11},
    "Jupiter": {2, 5, 7, 9, 11},
    "Venus": {1, 2, 3, 4, 5, 8, 9, 11, 12},
    "Saturn": {3, 6, 11},
    "Rahu": {3, 6, 11},
    "Ketu": {3, 6, 11},
}

TRANSIT_KEY_EFFECTS = {
    ("Jupiter", True): "Brings divine wisdom, expansion, auspicious developments, and good fortune.",
    ("Jupiter", False): "Encourages internal introspection, consolidation, and careful financial planning.",
    ("Saturn", True): "Strengthens discipline, endurance, work ethic, and provides solid foundations.",
    ("Saturn", False): "Tests patience, imposes lessons of responsibility, and requires steady diligence.",
    ("Sun", True): "Enhances vitality, social status, career recognition, and administrative power.",
    ("Sun", False): "Advises avoiding ego conflicts, conserving physical energy, and practicing humility.",
    ("Mars", True): "Boosts courage, competitive vigor, initiative, and productive energy.",
    ("Mars", False): "Cautions against impulsiveness, rash decisions, and temper flare-ups.",
    ("Venus", True): "Enhances creative expression, relationship harmony, prosperity, and comfort.",
    ("Venus", False): "Calls for financial moderation and realistic expectations in relationships.",
    ("Mercury", True): "Sharpens intellect, communications, business acumen, and learning agility.",
    ("Mercury", False): "Advises double-checking contracts and avoiding misunderstandings.",
}


def calculate_transits(
    natal_chart: D1Chart,
    transit_datetime: Optional[datetime] = None,
    adapter: Optional[SwissEphemerisAdapter] = None,
) -> TransitAnalysisResult:
    """Calculates planetary transit positions and compares them against natal chart placements.
    
    Args:
        natal_chart: The user's natal D1 chart.
        transit_datetime: Timestamp for transits (default: current UTC).
        adapter: Optional ephemeris adapter.
    
    Returns:
        Structured TransitAnalysisResult including Sade Sati status and planetary transit impacts.
    """
    eph = adapter or default_adapter
    t_dt = transit_datetime or datetime.now(timezone.utc)
    if t_dt.tzinfo is None:
        t_dt = t_dt.replace(tzinfo=timezone.utc)

    jd_info = compute_julian_day(t_dt, eph)

    ayanamsa_type = AyanamsaType(natal_chart.ayanamsa_used) if natal_chart.ayanamsa_used else AyanamsaType.LAHIRI
    transit_raw = calculate_sidereal_planets(
        jd_ut=jd_info.jd_ut,
        ayanamsa=ayanamsa_type,
        include_ketu=True,
        adapter=eph,
    )

    # Identify natal Moon
    natal_moon = next((p for p in natal_chart.planets if p.name == "Moon"), None)
    if not natal_moon:
        raise ValueError("Natal chart does not contain a Moon placement; cannot compute Gochara transits.")

    natal_moon_sign = natal_moon.sign_number
    natal_asc_sign = natal_chart.ascendant.sign_number if natal_chart.ascendant else None

    transit_planets: List[TransitPlanet] = []
    sade_sati_active = False
    sade_sati_phase: Optional[str] = None
    jupiter_transit_favorable = False

    for tp in transit_raw:
        h_moon = ((tp.sign_number - natal_moon_sign) % 12) + 1
        h_asc = (((tp.sign_number - natal_asc_sign) % 12) + 1) if natal_asc_sign else None

        ausp_set = AUSPICIOUS_HOUSES_FROM_MOON.get(tp.name, {3, 6, 11})
        is_auspicious = h_moon in ausp_set

        # Sade Sati check for Saturn (transiting 12th, 1st, or 2nd from natal Moon)
        if tp.name == "Saturn":
            if h_moon == 12:
                sade_sati_active = True
                sade_sati_phase = "Rising"
            elif h_moon == 1:
                sade_sati_active = True
                sade_sati_phase = "Peak"
            elif h_moon == 2:
                sade_sati_active = True
                sade_sati_phase = "Setting"

        # Jupiter blessing check
        if tp.name == "Jupiter" and h_moon in {2, 5, 7, 9, 11}:
            jupiter_transit_favorable = True

        effects = TRANSIT_KEY_EFFECTS.get(
            (tp.name, is_auspicious),
            f"Transiting House {h_moon} relative to natal Moon in {tp.sign_name}."
        )

        transit_planets.append(
            TransitPlanet(
                name=tp.name,
                sign_number=tp.sign_number,
                sign_name=tp.sign_name,
                sign_sanskrit=tp.sign_sanskrit,
                degree_in_sign=round(tp.degree_in_sign, 2),
                house_from_moon=h_moon,
                house_from_ascendant=h_asc,
                is_retrograde=tp.is_retrograde,
                is_auspicious=is_auspicious,
                key_effects=effects,
            )
        )

    # Compose summary
    summary_parts = []
    if sade_sati_active:
        summary_parts.append(f"🪐 Shani Sade Sati is active ({sade_sati_phase} Phase) — focus on steady discipline.")
    else:
        summary_parts.append("🪐 No Shani Sade Sati active.")

    if jupiter_transit_favorable:
        summary_parts.append("✨ Guru (Jupiter) is in a supportive transit position from your Moon, bringing auspicious grace.")

    return TransitAnalysisResult(
        transit_date=t_dt.date(),
        planets=transit_planets,
        sade_sati_active=sade_sati_active,
        sade_sati_phase=sade_sati_phase,
        jupiter_transit_favorable=jupiter_transit_favorable,
        summary=" ".join(summary_parts),
    )
