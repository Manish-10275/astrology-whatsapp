"""Vedic Panchang calculation engine (Tithi, Vara, Nakshatra, Yoga, Karana)."""

from datetime import date, datetime
from typing import Optional, Tuple
from astrology_engine.models import (
    TithiInfo,
    YogaInfo,
    KaranaInfo,
    NakshatraInfo,
    PanchangResult,
    NAKSHATRAS,
    NAKSHATRA_LORDS,
)
from astrology_engine.adapter import SwissEphemerisAdapter, default_adapter

TITHI_NAMES = [
    "Pratipada", "Dwitiya", "Tritiya", "Chaturthi", "Panchami",
    "Shasthi", "Saptami", "Ashtami", "Navami", "Dashami",
    "Ekadashi", "Dwadashi", "Trayodashi", "Chaturdashi", "Purnima",
    "Pratipada", "Dwitiya", "Tritiya", "Chaturthi", "Panchami",
    "Shasthi", "Saptami", "Ashtami", "Navami", "Dashami",
    "Ekadashi", "Dwadashi", "Trayodashi", "Chaturdashi", "Amavasya"
]

YOGA_NAMES = [
    "Vishkambha", "Priti", "Ayushman", "Saubhagya", "Shobhana",
    "Atiganda", "Sukarma", "Dhriti", "Shoola", "Ganda",
    "Vriddhi", "Dhruva", "Vyaghata", "Harshana", "Vajra",
    "Siddhi", "Vyatipata", "Variyan", "Parigha", "Shiva",
    "Siddha", "Sadhya", "Shubha", "Shukla", "Brahma",
    "Indra", "Vaidhriti"
]

REPEATING_KARANAS = [
    "Bava", "Balava", "Kaulava", "Taitila", "Gara", "Vanija", "Vishti (Bhadra)"
]

VARAS = [
    ("Somavara", "Moon"),
    ("Mangalavara", "Mars"),
    ("Budhavara", "Mercury"),
    ("Guruvara", "Jupiter"),
    ("Shukravara", "Venus"),
    ("Shanivara", "Saturn"),
    ("Ravivara", "Sun"),
]

NAKSHATRA_SPAN = 40.0 / 3.0  # 13.333333333333334 degrees


def calculate_panchang(
    sun_longitude: float,
    moon_longitude: float,
    target_date: date,
    sunrise_iso: Optional[str] = None,
    sunset_iso: Optional[str] = None,
) -> PanchangResult:
    """Calculates all 5 limbs of the Panchang (Tithi, Vara, Nakshatra, Yoga, Karana).
    
    Args:
        sun_longitude: Sidereal/tropical longitude of the Sun [0, 360).
        moon_longitude: Sidereal/tropical longitude of the Moon [0, 360).
        target_date: Date for which Panchang is calculated.
        sunrise_iso: Optional local sunrise timestamp.
        sunset_iso: Optional local sunset timestamp.
    
    Returns:
        Structured PanchangResult with all 5 limbs.
    """
    # 1. Vara (Day of week)
    weekday_idx = target_date.weekday()  # Monday = 0, Sunday = 6
    vara_name, vara_lord = VARAS[weekday_idx]

    # 2. Tithi (Moon - Sun difference in 12-degree steps)
    separation = (moon_longitude - sun_longitude) % 360.0
    tithi_num = int(separation / 12.0) + 1
    tithi_num = max(1, min(30, tithi_num))
    tithi_name = TITHI_NAMES[tithi_num - 1]
    paksha = "Shukla" if tithi_num <= 15 else "Krishna"
    tithi_pct = ((separation % 12.0) / 12.0) * 100.0

    tithi_info = TithiInfo(
        number=tithi_num,
        name=tithi_name,
        paksha=paksha,
        completed_percentage=round(tithi_pct, 2),
    )

    # 3. Nakshatra (Moon longitude in 13° 20' steps)
    norm_moon = moon_longitude % 360.0
    nak_idx = int(norm_moon / NAKSHATRA_SPAN)
    nak_name = NAKSHATRAS[nak_idx]
    nak_ruler = NAKSHATRA_LORDS[nak_idx]
    deg_in_nak = norm_moon - (nak_idx * NAKSHATRA_SPAN)
    pada = int(deg_in_nak / (NAKSHATRA_SPAN / 4.0)) + 1
    pada = max(1, min(4, pada))

    nakshatra_info = NakshatraInfo(
        name=nak_name,
        number=nak_idx + 1,
        ruler=nak_ruler,
        pada=pada,
        degrees_into_nakshatra=round(deg_in_nak, 4),
    )

    # 4. Yoga (Sum of Sun and Moon in 13° 20' steps)
    sum_long = (sun_longitude + moon_longitude) % 360.0
    yoga_idx = int(sum_long / NAKSHATRA_SPAN)
    yoga_idx = max(0, min(26, yoga_idx))
    yoga_name = YOGA_NAMES[yoga_idx]
    yoga_pct = ((sum_long % NAKSHATRA_SPAN) / NAKSHATRA_SPAN) * 100.0

    yoga_info = YogaInfo(
        number=yoga_idx + 1,
        name=yoga_name,
        completed_percentage=round(yoga_pct, 2),
    )

    # 5. Karana (Half of a Tithi: 6-degree steps)
    karana_idx = int(separation / 6.0) + 1
    karana_idx = max(1, min(60, karana_idx))

    if karana_idx == 1:
        karana_name = "Kimstughna"
    elif karana_idx == 58:
        karana_name = "Shakuni"
    elif karana_idx == 59:
        karana_name = "Chatushpada"
    elif karana_idx == 60:
        karana_name = "Naga"
    else:
        # Repeating karanas (2 to 57)
        r_idx = (karana_idx - 2) % 7
        karana_name = REPEATING_KARANAS[r_idx]

    is_vishti = (karana_name == "Vishti (Bhadra)")

    karana_info = KaranaInfo(
        number=karana_idx,
        name=karana_name,
        is_vishti=is_vishti,
    )

    return PanchangResult(
        date=target_date,
        vara=vara_name,
        vara_lord=vara_lord,
        tithi=tithi_info,
        nakshatra=nakshatra_info,
        yoga=yoga_info,
        karana=karana_info,
        sunrise_iso=sunrise_iso,
        sunset_iso=sunset_iso,
    )
