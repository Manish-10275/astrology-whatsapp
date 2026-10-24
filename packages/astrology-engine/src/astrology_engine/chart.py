"""High-level D1 chart generator for Vedic and Western astrology."""

import hashlib
from typing import Optional, Dict, List
from astrology_engine.adapter import SwissEphemerisAdapter, default_adapter
from astrology_engine.models import (
    ChartRequest,
    D1Chart,
    AstrologySystem,
    TimeUncertainty,
)
from astrology_engine.time_utils import (
    validate_coordinates,
    compute_utc_datetime,
    compute_julian_day,
)
from astrology_engine.tropical import calculate_tropical_planets
from astrology_engine.sidereal import calculate_sidereal_planets
from astrology_engine.houses import (
    calculate_house_system_data,
    assign_houses_to_planets,
)


def generate_calculation_hash(request: ChartRequest) -> str:
    """Generates a reproducible SHA-256 hash identifying the calculation parameters."""
    raw_str = (
        f"{request.system.value}:"
        f"{request.ayanamsa.value if request.ayanamsa else 'NONE'}:"
        f"{request.house_system.value}:"
        f"{request.birth_date.isoformat()}:"
        f"{request.birth_time.isoformat() if request.birth_time else 'UNKNOWN'}:"
        f"{request.latitude:.4f}:"
        f"{request.longitude:.4f}:"
        f"{request.timezone_name}:"
        f"fold={request.fold}"
    )
    return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()


def calculate_d1_chart(
    request: ChartRequest,
    adapter: Optional[SwissEphemerisAdapter] = None
) -> D1Chart:
    """Calculates a complete, structured D1 chart according to Vedic or Western specifications."""
    eph = adapter or default_adapter

    # 1. Physical validation
    validate_coordinates(request.latitude, request.longitude)

    # 2. Timezone and UTC conversion
    utc_dt, is_approximated = compute_utc_datetime(
        birth_date=request.birth_date,
        birth_time=request.birth_time,
        timezone_name=request.timezone_name,
        longitude=request.longitude,
        timezone_offset_seconds=request.timezone_offset_seconds,
        fold=request.fold,
        time_uncertainty=request.time_uncertainty
    )

    # 3. Compute Julian Day and Delta T
    jd_info = compute_julian_day(utc_dt, eph)
    calc_hash = generate_calculation_hash(request)

    # Effective uncertainty
    effective_uncertainty = (
        TimeUncertainty.UNKNOWN if is_approximated else request.time_uncertainty
    )

    is_vedic = request.system == AstrologySystem.VEDIC
    ayanamsa_degrees: Optional[float] = None
    ayanamsa_name: Optional[str] = None

    if is_vedic:
        ayanamsa_name = request.ayanamsa.value
        ayanamsa_degrees = eph.get_ayanamsa_degrees(jd_info.jd_ut, ayanamsa=ayanamsa_name)
        raw_planets = calculate_sidereal_planets(
            jd_ut=jd_info.jd_ut,
            ayanamsa=request.ayanamsa,
            include_ketu=True,
            adapter=eph
        )
    else:
        raw_planets = calculate_tropical_planets(
            jd_ut=jd_info.jd_ut,
            adapter=eph
        )

    # 4. Houses and Ascendant calculation
    houses = []
    ascendant = None
    midheaven = None

    if effective_uncertainty != TimeUncertainty.UNKNOWN:
        houses, ascendant, midheaven = calculate_house_system_data(
            jd_ut=jd_info.jd_ut,
            latitude=request.latitude,
            longitude=request.longitude,
            house_system=request.house_system,
            is_sidereal=is_vedic,
            ayanamsa=ayanamsa_name,
            adapter=eph
        )
        final_planets = assign_houses_to_planets(
            planets=raw_planets,
            ascendant=ascendant,
            houses=houses,
            house_system=request.house_system
        )
    else:
        # Birth time unknown: houses and ascendant withheld
        final_planets = [p.model_copy(update={"house": None}) for p in raw_planets]

    # 5. Build houses_map (house_number -> list of planet names)
    houses_map: Dict[int, List[str]] = {i: [] for i in range(1, 13)}
    for p in final_planets:
        if p.house is not None and 1 <= p.house <= 12:
            houses_map[p.house].append(p.name)

    ephemeris_mode = raw_planets[0].ephemeris_mode if raw_planets else "moshier"

    return D1Chart(
        system=request.system,
        ayanamsa_used=ayanamsa_name,
        ayanamsa_degrees=ayanamsa_degrees,
        house_system_used=request.house_system,
        julian_day=jd_info,
        ascendant=ascendant,
        midheaven=midheaven,
        houses=houses,
        planets=final_planets,
        houses_map=houses_map,
        ephemeris_mode=ephemeris_mode,
        time_uncertainty=effective_uncertainty,
        calculation_hash=calc_hash
    )
