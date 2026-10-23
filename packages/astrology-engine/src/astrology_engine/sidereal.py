"""Sidereal (Vedic) planetary calculation engine with Nakshatra determination."""

from typing import List, Tuple, Optional
from astrology_engine.adapter import SwissEphemerisAdapter, default_adapter
from astrology_engine.models import (
    PlanetPosition,
    NakshatraInfo,
    AyanamsaType,
    NAKSHATRAS,
    NAKSHATRA_LORDS,
)
from astrology_engine.tropical import longitude_to_sign

VEDIC_PLANET_NAMES = [
    "Sun", "Moon", "Mars", "Mercury", "Jupiter",
    "Venus", "Saturn", "Rahu"
]

ONE_NAKSHATRA_DEGREES = 360.0 / 27.0        # 13.333333333333334° (13° 20')
ONE_PADA_DEGREES = ONE_NAKSHATRA_DEGREES / 4.0  # 3.3333333333333335° (3° 20')


def calculate_nakshatra(sidereal_lon: float) -> NakshatraInfo:
    """Computes the Nakshatra (lunar mansion), pada, and planetary ruler for a sidereal longitude."""
    normalized_lon = sidereal_lon % 360.0
    nak_index = int(normalized_lon // ONE_NAKSHATRA_DEGREES)
    if nak_index >= 27:
        nak_index = 26

    degrees_into_nak = normalized_lon - (nak_index * ONE_NAKSHATRA_DEGREES)
    pada_index = int(degrees_into_nak // ONE_PADA_DEGREES) + 1
    if pada_index > 4:
        pada_index = 4

    name = NAKSHATRAS[nak_index]
    ruler = NAKSHATRA_LORDS[nak_index]

    return NakshatraInfo(
        name=name,
        number=nak_index + 1,
        ruler=ruler,
        pada=pada_index,
        degrees_into_nakshatra=degrees_into_nak
    )


def calculate_sidereal_planet(
    jd_ut: float,
    planet_name: str,
    ayanamsa: AyanamsaType = AyanamsaType.LAHIRI,
    adapter: Optional[SwissEphemerisAdapter] = None
) -> PlanetPosition:
    """Calculates sidereal position and Nakshatra for a single planet using the given ayanamsa."""
    eph = adapter or default_adapter

    lon, lat, dist, speed_lon, is_retro, ephe_mode = eph.calc_planet_ut(
        jd_ut=jd_ut,
        planet_name=planet_name,
        is_sidereal=True,
        ayanamsa=ayanamsa.value
    )

    sign_num, sign_name, sign_sanskrit, deg_in_sign = longitude_to_sign(lon)
    nakshatra = calculate_nakshatra(lon)

    return PlanetPosition(
        name=planet_name,
        longitude=lon,
        latitude=lat,
        distance_au=dist,
        speed_longitude=speed_lon,
        is_retrograde=is_retro,
        sign_number=sign_num,
        sign_name=sign_name,
        sign_sanskrit=sign_sanskrit,
        degree_in_sign=deg_in_sign,
        house=None,
        nakshatra=nakshatra,
        ephemeris_mode=ephe_mode
    )


def calculate_sidereal_planets(
    jd_ut: float,
    ayanamsa: AyanamsaType = AyanamsaType.LAHIRI,
    include_ketu: bool = True,
    adapter: Optional[SwissEphemerisAdapter] = None
) -> List[PlanetPosition]:
    """Calculates sidereal positions for the Vedic Navagraha (9 planets including Rahu and Ketu)."""
    eph = adapter or default_adapter
    eph.set_sidereal_mode(ayanamsa.value)

    planets: List[PlanetPosition] = []

    # Calculate 7 classical planets + Rahu
    for name in VEDIC_PLANET_NAMES:
        pos = calculate_sidereal_planet(jd_ut, name, ayanamsa, eph)
        planets.append(pos)

    # In Vedic astrology, Ketu is exactly opposite Rahu (180 degrees apart)
    if include_ketu:
        rahu = next((p for p in planets if p.name == "Rahu"), None)
        if rahu:
            ketu_lon = (rahu.longitude + 180.0) % 360.0
            sign_num, sign_name, sign_sanskrit, deg_in_sign = longitude_to_sign(ketu_lon)
            ketu_nakshatra = calculate_nakshatra(ketu_lon)

            ketu_pos = PlanetPosition(
                name="Ketu",
                longitude=ketu_lon,
                latitude=-rahu.latitude,
                distance_au=rahu.distance_au,
                speed_longitude=rahu.speed_longitude,
                is_retrograde=rahu.is_retrograde,
                sign_number=sign_num,
                sign_name=sign_name,
                sign_sanskrit=sign_sanskrit,
                degree_in_sign=deg_in_sign,
                house=None,
                nakshatra=ketu_nakshatra,
                ephemeris_mode=rahu.ephemeris_mode
            )
            planets.append(ketu_pos)

    return planets
