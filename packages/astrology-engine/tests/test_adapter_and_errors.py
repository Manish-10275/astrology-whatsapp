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
    """Verifies that concurrent calculations across threads produce consistent results without data corruption."""
    request = ChartRequest(
        birth_date=date(1992, 8, 15),
        birth_time=time(14, 30),
        latitude=18.9388,
        longitude=72.8354,
        timezone_name="Asia/Kolkata",
        system=AstrologySystem.VEDIC,
        house_system=HouseSystemType.WHOLE_SIGN
    )

    def worker(_):
        return calculate_d1_chart(request)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(worker, range(16)))

    first_hash = results[0].calculation_hash
    first_asc_lon = results[0].ascendant.longitude

    for res in results[1:]:
        assert res.calculation_hash == first_hash
        assert res.ascendant.longitude == first_asc_lon
