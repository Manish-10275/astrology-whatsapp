"""Tests for error handling, adapter edge cases, and thread safety."""

import pytest
import concurrent.futures
from datetime import date, time

from astrology_engine.models import ChartRequest, AstrologySystem, HouseSystemType
from astrology_engine.chart import calculate_d1_chart
from astrology_engine.adapter import SwissEphemerisAdapter
from astrology_engine.exceptions import (
    EphemerisError,
    InvalidCoordinatesError,
    UnsupportedDateRangeError,
    TimezoneResolutionError,
)


def test_invalid_house_system_error():
    """Attempting to use an unsupported house system code must raise EphemerisError."""
    adapter = SwissEphemerisAdapter()
    with pytest.raises(EphemerisError) as exc_info:
        adapter.calc_houses(2451545.0, 19.076, 72.877, house_system="invalid_code")
    assert "Unsupported house system" in str(exc_info.value)


def test_invalid_ayanamsa_error():
    """Attempting to set an invalid ayanamsa code must raise EphemerisError."""
    adapter = SwissEphemerisAdapter()
    with pytest.raises(EphemerisError) as exc_info:
        adapter.set_sidereal_mode("nonexistent_ayanamsa")
    assert "Unsupported ayanamsa" in str(exc_info.value)


def test_unknown_planet_name():
    """Attempting to calculate an unknown planet must raise EphemerisError."""
    adapter = SwissEphemerisAdapter()
    with pytest.raises(EphemerisError) as exc_info:
        adapter.calc_planet_ut(2451545.0, "Krypton")
    assert "Unknown planet" in str(exc_info.value)


def test_unknown_timezone_resolution_error():
    """Providing a bogus timezone string in ChartRequest must raise TimezoneResolutionError."""
    request = ChartRequest(
        birth_date=date(1995, 5, 10),
        birth_time=time(10, 0),
        latitude=10.0,
        longitude=20.0,
        timezone_name="Invalid/Fake_Zone",
        system=AstrologySystem.WESTERN
    )
    with pytest.raises(TimezoneResolutionError):
        calculate_d1_chart(request)


def test_thread_safety_concurrent_calculations():
    """Verifies that concurrent calculations across threads produce consistent results without data corruption
    or global C-state leakage between different ayanamsas.
    """
    req_lahiri = ChartRequest(
        birth_date=date(1992, 8, 15),
        birth_time=time(14, 30),
        latitude=18.9388,
        longitude=72.8354,
        timezone_name="Asia/Kolkata",
        system=AstrologySystem.VEDIC,
        ayanamsa="lahiri",
        house_system=HouseSystemType.WHOLE_SIGN
    )
    req_raman = ChartRequest(
        birth_date=date(1992, 8, 15),
        birth_time=time(14, 30),
        latitude=18.9388,
        longitude=72.8354,
        timezone_name="Asia/Kolkata",
        system=AstrologySystem.VEDIC,
        ayanamsa="raman",
        house_system=HouseSystemType.WHOLE_SIGN
    )

    def worker(idx):
        req = req_lahiri if idx % 2 == 0 else req_raman
        chart = calculate_d1_chart(req)
        if req.ayanamsa == "lahiri":
            assert abs(chart.ayanamsa_degrees - 23.79) < 0.05
            assert chart.ayanamsa_used == "lahiri"
        else:
            assert abs(chart.ayanamsa_degrees - 22.35) < 0.05
            assert chart.ayanamsa_used == "raman"
        return chart

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(worker, range(24)))

    assert len(results) == 24


def test_ephemeris_mode_observability():
    """Verifies that calculation engine explicitly observes and records whether Swiss Ephemeris
    files (.se1) or the built-in Moshier fallback ephemeris were used.
    """
    request = ChartRequest(
        birth_date=date(2000, 1, 1),
        birth_time=time(12, 0),
        latitude=51.5074,
        longitude=-0.1278,
        timezone_name="UTC",
        system=AstrologySystem.WESTERN
    )
    chart = calculate_d1_chart(request)

    # When .se1 files are not present on system PATH, engine must record fallback to 'moshier'
    assert chart.ephemeris_mode in ("moshier", "swiss")
    for planet in chart.planets:
        assert planet.ephemeris_mode in ("moshier", "swiss")
    
    # Sun and Moon represent physical bodies that reflect overall ephemeris mode
    sun = next(p for p in chart.planets if p.name == "Sun")
    assert sun.ephemeris_mode == chart.ephemeris_mode
