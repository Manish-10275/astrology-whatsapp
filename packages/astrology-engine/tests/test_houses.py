"""Tests for House cusps, Ascendant, and Midheaven calculations."""

import pytest
from datetime import datetime
from zoneinfo import ZoneInfo

from astrology_engine.time_utils import compute_julian_day
from astrology_engine.houses import (
    calculate_house_system_data,
    assign_houses_to_planets,
    get_house_for_whole_sign,
    get_house_for_longitude_cusps,
)
from astrology_engine.models import (
    HouseSystemType,
    PlanetPosition,
    AscendantInfo,
    HouseCusp,
)


def test_greenwich_houses_placidus():
    """At Greenwich (51.4769° N, 0.0° E) on 2000-01-01 12:00:00 UTC."""
    utc_dt = datetime(2000, 1, 1, 12, 0, 0, tzinfo=ZoneInfo("UTC"))
    jd = compute_julian_day(utc_dt).jd_ut

    houses, ascendant, midheaven = calculate_house_system_data(
        jd_ut=jd,
        latitude=51.4769,
        longitude=0.0,
        house_system=HouseSystemType.PLACIDUS,
        is_sidereal=False
    )

    assert len(houses) == 12
    # Tropical Ascendant for London at this moment is in early Aries (~24° Aries)
    assert ascendant.sign_name == "Aries"
    assert 20.0 < ascendant.degree_in_sign < 28.0

    # MC for London at local noon is in Capricorn (~279° / 9° Capricorn)
    assert midheaven.sign_name == "Capricorn"
    assert 5.0 < midheaven.degree_in_sign < 15.0


def test_whole_sign_houses_structure():
    """In Whole Sign houses:
    - House 1 cusp must equal 0° of the Ascendant sign.
    - Every subsequent house cusp must be exactly 30° apart.
    """
    utc_dt = datetime(2000, 1, 1, 12, 0, 0, tzinfo=ZoneInfo("UTC"))
    jd = compute_julian_day(utc_dt).jd_ut

    houses, ascendant, _ = calculate_house_system_data(
        jd_ut=jd,
        latitude=19.0760,
        longitude=72.8777,
        house_system=HouseSystemType.WHOLE_SIGN,
        is_sidereal=True
    )

    assert len(houses) == 12
    # For Sidereal Mumbai J2000: Ascendant is Gemini (sign 3)
    assert ascendant.sign_name == "Gemini"
    # House 1 cusp must be at 60.0° (Gemini 0°)
    assert abs(houses[0].cusp_longitude - 60.0) < 1e-4
    assert houses[0].sign_name == "Gemini"

    # House 2 must be Cancer (90.0°)
    assert abs(houses[1].cusp_longitude - 90.0) < 1e-4
    assert houses[1].sign_name == "Cancer"


def test_whole_sign_planet_assignment():
    """Tests that planets are assigned to houses based on their sign relative to Ascendant sign."""
    # Ascendant in Gemini (sign 3)
    # Planet A in Gemini (sign 3) -> House 1
    # Planet B in Cancer (sign 4) -> House 2
    # Planet C in Taurus (sign 2) -> House 12
    assert get_house_for_whole_sign(planet_sign_number=3, ascendant_sign_number=3) == 1
    assert get_house_for_whole_sign(planet_sign_number=4, ascendant_sign_number=3) == 2
    assert get_house_for_whole_sign(planet_sign_number=2, ascendant_sign_number=3) == 12
    assert get_house_for_whole_sign(planet_sign_number=9, ascendant_sign_number=3) == 7


def test_placidus_cusp_allocation_across_aries():
    """Tests house assignment when cusp boundary wraps around 0° Aries."""
    # Cusps: House 1 starts at 350°, House 2 starts at 20°, etc.
    cusps = [350.0, 20.0, 50.0, 80.0, 110.0, 140.0, 170.0, 200.0, 230.0, 260.0, 290.0, 320.0]

    # 355° should be in House 1
    assert get_house_for_longitude_cusps(355.0, cusps) == 1
    # 5° should be in House 1 (wraps across 0°)
    assert get_house_for_longitude_cusps(5.0, cusps) == 1
    # 25° should be in House 2
    assert get_house_for_longitude_cusps(25.0, cusps) == 2
    # 340° should be in House 12
    assert get_house_for_longitude_cusps(340.0, cusps) == 12
