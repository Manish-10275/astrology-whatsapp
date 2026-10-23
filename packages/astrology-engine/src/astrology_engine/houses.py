"""House calculation and planet-to-house allocation engine."""

from typing import List, Tuple, Optional
from astrology_engine.adapter import SwissEphemerisAdapter, default_adapter
from astrology_engine.models import (
    HouseCusp,
    AscendantInfo,
    MidheavenInfo,
    HouseSystemType,
    PlanetPosition,
)
from astrology_engine.tropical import longitude_to_sign
from astrology_engine.sidereal import calculate_nakshatra


def get_house_for_longitude_cusps(lon: float, cusps: List[float]) -> int:
    """Determines which house contains a given longitude based on 12 cusp boundaries.
    
    Cusps must be a list of 12 floats representing house cusps 1 to 12.
    """
    normalized_lon = lon % 360.0

    for i in range(12):
        cusp_current = cusps[i]
        cusp_next = cusps[(i + 1) % 12]

        if cusp_current < cusp_next:
            if cusp_current <= normalized_lon < cusp_next:
                return i + 1
        else:
            # House spans across 0° Aries (e.g. from 345° to 15°)
            if normalized_lon >= cusp_current or normalized_lon < cusp_next:
                return i + 1

    return 1  # Fallback to house 1 for edge cases


def get_house_for_whole_sign(planet_sign_number: int, ascendant_sign_number: int) -> int:
    """Calculates Whole Sign house number based on sign numbers (1=Aries to 12=Pisces)."""
    return ((planet_sign_number - ascendant_sign_number) % 12) + 1


def calculate_house_system_data(
    jd_ut: float,
    latitude: float,
    longitude: float,
    house_system: HouseSystemType = HouseSystemType.PLACIDUS,
    is_sidereal: bool = False,
    adapter: Optional[SwissEphemerisAdapter] = None
) -> Tuple[List[HouseCusp], AscendantInfo, MidheavenInfo]:
    """Calculates house cusps, Ascendant (Lagna), and Midheaven (MC)."""
    eph = adapter or default_adapter

    cusps_deg, asc_deg, mc_deg = eph.calc_houses(
        jd_ut=jd_ut,
        lat=latitude,
        lon=longitude,
        house_system=house_system.value,
        is_sidereal=is_sidereal
    )

    # Build 12 HouseCusp models
    houses: List[HouseCusp] = []
    for idx, c_deg in enumerate(cusps_deg, start=1):
        s_num, s_name, s_sans, deg_in_s = longitude_to_sign(c_deg)
        houses.append(
            HouseCusp(
                house_number=idx,
                cusp_longitude=c_deg,
                sign_number=s_num,
                sign_name=s_name,
                sign_sanskrit=s_sans,
                degree_in_sign=deg_in_s
            )
        )

    # Build AscendantInfo
    asc_s_num, asc_s_name, asc_s_sans, asc_deg_in_s = longitude_to_sign(asc_deg)
    asc_nak = calculate_nakshatra(asc_deg) if is_sidereal else None
    ascendant = AscendantInfo(
        longitude=asc_deg,
        sign_number=asc_s_num,
        sign_name=asc_s_name,
        sign_sanskrit=asc_s_sans,
        degree_in_sign=deg_in_s if False else asc_deg_in_s,
        nakshatra=asc_nak
    )

    # Build MidheavenInfo
    mc_s_num, mc_s_name, mc_s_sans, mc_deg_in_s = longitude_to_sign(mc_deg)
    midheaven = MidheavenInfo(
        longitude=mc_deg,
        sign_number=mc_s_num,
        sign_name=mc_s_name,
        sign_sanskrit=mc_s_sans,
        degree_in_sign=mc_deg_in_s
    )

    return houses, ascendant, midheaven


def assign_houses_to_planets(
    planets: List[PlanetPosition],
    ascendant: Optional[AscendantInfo],
    houses: List[HouseCusp],
    house_system: HouseSystemType
) -> List[PlanetPosition]:
    """Assigns the computed house number to each planet."""
    if not ascendant or not houses:
        # Birth time is unknown; cannot assign houses
        return [p.model_copy(update={"house": None}) for p in planets]

    cusp_longitudes = [h.cusp_longitude for h in houses]
    updated_planets: List[PlanetPosition] = []

    for planet in planets:
        if house_system == HouseSystemType.WHOLE_SIGN:
            house_num = get_house_for_whole_sign(planet.sign_number, ascendant.sign_number)
        else:
            house_num = get_house_for_longitude_cusps(planet.longitude, cusp_longitudes)

        updated_planets.append(planet.model_copy(update={"house": house_num}))

    return updated_planets
