"""Astronomical benchmark validation suite against established reference data."""

import pytest
from datetime import date, time, datetime
from zoneinfo import ZoneInfo

from astrology_engine.models import (
    ChartRequest,
    AstrologySystem,
    HouseSystemType,
    AyanamsaType,
    TimeUncertainty,
)
from astrology_engine.chart import calculate_d1_chart
from astrology_engine.time_utils import compute_julian_day
from astrology_engine.tropical import calculate_tropical_planet
from astrology_engine.sidereal import calculate_sidereal_planet


def test_benchmark_j2000_astrodienst_reference():
    """Benchmark Case 1: Standard J2000.0 Reference Epoch.
    
    Source: Astrodienst Swiss Ephemeris official test suite (swetest) & USNO Astronomical Almanac.
    Reference Epoch: 2000-01-01 12:00:00 UTC (JD 2451545.0)
    
    Expected Values:
    - Tropical Sun: 280.3689° (Capricorn 10° 22' 08")
    - Tropical Moon: 223.3238° (Scorpio 13° 19' 26", speed ~12.06°/day)
    - Lahiri Ayanamsa: 23° 51' 25.53" (23.857092°)
    - Sidereal Sun (Lahiri): 256.5118° (Sagittarius 16° 30' 42")
    - Sidereal Moon (Lahiri): 199.4667° (Libra 19° 28' 00", Swati Nakshatra, Pada 4)
    - Planetary Tolerance: 0.005° (18 arcseconds)
    - Lunar Tolerance: 0.01° (36 arcseconds, accounting for rapid lunar speed ~0.55°/hr)
    """
    utc_dt = datetime(2000, 1, 1, 12, 0, 0, tzinfo=ZoneInfo("UTC"))
    jd = compute_julian_day(utc_dt).jd_ut

    # 1. Sun verification
    trop_sun = calculate_tropical_planet(jd, "Sun")
    assert abs(trop_sun.longitude - 280.3689) < 0.005, (
        f"Tropical Sun expected ~280.3689°, got {trop_sun.longitude}"
    )

    sid_sun = calculate_sidereal_planet(jd, "Sun", ayanamsa=AyanamsaType.LAHIRI)
    assert abs(sid_sun.longitude - 256.5118) < 0.005, (
        f"Sidereal Sun expected ~256.5118°, got {sid_sun.longitude}"
    )

    # 2. Moon verification (fastest moving body)
    trop_moon = calculate_tropical_planet(jd, "Moon")
    assert abs(trop_moon.longitude - 223.3238) < 0.01, (
        f"Tropical Moon expected ~223.3238°, got {trop_moon.longitude}"
    )
    assert trop_moon.sign_name == "Scorpio"

    sid_moon = calculate_sidereal_planet(jd, "Moon", ayanamsa=AyanamsaType.LAHIRI)
    assert abs(sid_moon.longitude - 199.4667) < 0.01, (
        f"Sidereal Moon expected ~199.4667°, got {sid_moon.longitude}"
    )
    assert sid_moon.sign_name == "Libra"
    assert sid_moon.sign_sanskrit == "Tula"
    assert sid_moon.nakshatra is not None
    assert sid_moon.nakshatra.name == "Swati"
    assert sid_moon.nakshatra.pada == 4
    assert sid_moon.nakshatra.ruler == "Rahu"


def test_benchmark_gandhi_vedic_natal_chart():
    """Benchmark Case 2: Mahatma Gandhi's Natal Chart.
    
    Source: 'Notable Horoscopes' by Dr. B.V. Raman; Indian Astrological Reference Data.
    Date: 1869-10-02
    Time: 07:11:00 LMT (Local Mean Time, Porbandar, India: 21° 38' N, 69° 36' E).
    Historical note: In 1869 prior to Indian Standard Time (enacted 1906), local clocks
    followed Porbandar LMT (+4:38:31). Setting timezone_name='LMT' validates historical accuracy.
    
    Expected Vedic Placements (Lahiri Sidereal):
    - Lagna (Ascendant): Libra (Tula ~4° 23')
    - Moon: Cancer (Karka), in Aslesha Nakshatra (ruler: Mercury)
    - Sun: Virgo (Kanya), in Hasta Nakshatra (ruler: Moon)
    - Mars: Libra (Tula), conjunct Ascendant
    - Jupiter: Aries (Mesha)
    - Saturn: Scorpio (Vrischika)
    - Rahu: Cancer (Karka), Ketu: Capricorn (Makara)
    """
    request = ChartRequest(
        birth_date=date(1869, 10, 2),
        birth_time=time(7, 11, 0),
        time_uncertainty=TimeUncertainty.EXACT,
        latitude=21.6417,
        longitude=69.6293,
        timezone_name="LMT",
        system=AstrologySystem.VEDIC,
        ayanamsa=AyanamsaType.LAHIRI,
        house_system=HouseSystemType.WHOLE_SIGN
    )

    chart = calculate_d1_chart(request)

    # Ascendant must be Libra (Tula)
    assert chart.ascendant is not None
    assert chart.ascendant.sign_name == "Libra", f"Expected Libra Lagna, got {chart.ascendant.sign_name}"
    assert chart.ascendant.sign_sanskrit == "Tula"

    # Find planets
    planets_by_name = {p.name: p for p in chart.planets}

    # Moon in Cancer / Aslesha
    moon = planets_by_name["Moon"]
    assert moon.sign_name == "Cancer"
    assert moon.sign_sanskrit == "Karka"
    assert moon.nakshatra is not None and moon.nakshatra.name == "Ashlesha"

    # Sun in Virgo / Hasta
    sun = planets_by_name["Sun"]
    assert sun.sign_name == "Virgo"
    assert sun.sign_sanskrit == "Kanya"
    assert sun.nakshatra is not None and sun.nakshatra.name == "Hasta"

    # Jupiter in Aries
    jupiter = planets_by_name["Jupiter"]
    assert jupiter.sign_name == "Aries"

    # Saturn in Scorpio
    saturn = planets_by_name["Saturn"]
    assert saturn.sign_name == "Scorpio"

    # Rahu in Cancer, Ketu in Capricorn
    rahu = planets_by_name["Rahu"]
    ketu = planets_by_name["Ketu"]
    assert rahu.sign_name == "Cancer"
    assert ketu.sign_name == "Capricorn"


def test_benchmark_apollo_11_moon_landing():
    """Benchmark Case 3: Apollo 11 Lunar Module Landing.
    
    Source: NASA Historical Mission Records / JPL Horizons.
    Date: 1969-07-20 20:17:40 UTC
    Coordinates: 0° N, 0° E (Prime Meridian reference)
    
    Expected Tropical Placements:
    - Sun: Cancer (approx 28° Cancer = ~118°)
    - Moon: Libra (approx 6° Libra = ~186°)
    """
    utc_dt = datetime(1969, 7, 20, 20, 17, 40, tzinfo=ZoneInfo("UTC"))
    jd = compute_julian_day(utc_dt).jd_ut

    sun = calculate_tropical_planet(jd, "Sun")
    moon = calculate_tropical_planet(jd, "Moon")

    assert sun.sign_name == "Cancer"
    assert abs(sun.longitude - 118.0) < 1.0

    assert moon.sign_name == "Libra"
    # Moon at 1969-07-20 20:17:40 UTC was at 187° 52' 47" (~187.88° / Libra 7° 53')
    assert abs(moon.longitude - 187.88) < 0.05
