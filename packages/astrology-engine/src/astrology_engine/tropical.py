"""Tropical (Western) planetary calculation engine."""

from typing import List, Tuple, Optional
from astrology_engine.adapter import SwissEphemerisAdapter, default_adapter
from astrology_engine.models import PlanetPosition, ZODIAC_SIGNS

TROPICAL_PLANET_NAMES = [
    "Sun", "Moon", "Mercury", "Venus", "Mars",
    "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto",
    "Rahu", "TrueNode"
]


def longitude_to_sign(lon: float) -> Tuple[int, str, str, float]:
    """Converts an absolute ecliptic longitude [0, 360) into zodiac sign details.
    
    Returns:
        (sign_number [1..12], sign_name, sign_sanskrit, degree_in_sign [0..30))
    """
    normalized_lon = lon % 360.0
    sign_index = int(normalized_lon // 30)
    degree_in_sign = normalized_lon - (sign_index * 30.0)
    sign_data = ZODIAC_SIGNS[sign_index]

    return (
        sign_data["number"],
        sign_data["name"],
        sign_data["sanskrit"],
        degree_in_sign
    )


def calculate_tropical_planet(
    jd_ut: float,
    planet_name: str,
    adapter: Optional[SwissEphemerisAdapter] = None
) -> PlanetPosition:
    """Calculates tropical position for a single planet."""
    eph = adapter or default_adapter

    lon, lat, dist, speed_lon, is_retro, ephe_mode = eph.calc_planet_ut(
        jd_ut=jd_ut,
        planet_name=planet_name,
        is_sidereal=False
    )

    sign_num, sign_name, sign_sanskrit, deg_in_sign = longitude_to_sign(lon)

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
        nakshatra=None,
        ephemeris_mode=ephe_mode
    )


def calculate_tropical_planets(
    jd_ut: float,
    planet_names: Optional[List[str]] = None,
    adapter: Optional[SwissEphemerisAdapter] = None
) -> List[PlanetPosition]:
    """Calculates tropical positions for all requested planets."""
    eph = adapter or default_adapter
    names = planet_names or TROPICAL_PLANET_NAMES
    return [calculate_tropical_planet(jd_ut, name, eph) for name in names]
