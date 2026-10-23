"""Tests for time conversions, timezone resolution, and Julian Day computations."""

import pytest
from datetime import date, time, datetime
from zoneinfo import ZoneInfo

from astrology_engine.time_utils import (
    compute_utc_datetime,
    compute_julian_day,
    resolve_timezone,
    validate_coordinates,
    validate_date_range,
)
from astrology_engine.models import TimeUncertainty
from astrology_engine.exceptions import (
    InvalidCoordinatesError,
    TimezoneResolutionError,
    UnsupportedDateRangeError,
)


def test_j2000_julian_day_reference():
    """J2000.0 standard astronomical epoch: 2000-01-01 12:00:00 UTC.
    
    Standard definition: Julian Day = 2451545.0.
    """
    utc_dt = datetime(2000, 1, 1, 12, 0, 0, tzinfo=ZoneInfo("UTC"))
    jd_info = compute_julian_day(utc_dt)

    assert abs(jd_info.jd_ut - 2451545.0) < 1e-6
    # Delta T at 2000-01-01 was approx 63.83 seconds
    assert 60.0 < jd_info.delta_t < 70.0
    assert jd_info.jd_et > jd_info.jd_ut


def test_timezone_resolution_mumbai_and_nyc():
    """Tests offline timezone resolution from coordinates."""
    tz_mumbai = resolve_timezone(19.0760, 72.8777)
    assert tz_mumbai == "Asia/Kolkata"

    tz_nyc = resolve_timezone(40.7128, -74.0060)
    assert tz_nyc == "America/New_York"

    tz_london = resolve_timezone(51.5074, -0.1278)
    assert tz_london in ("Europe/London", "Europe/Belfast")


def test_historical_daylight_saving_shifts():
    """New York DST test:
    - Summer (July 15): UTC-4 (EDT)
    - Winter (January 15): UTC-5 (EST)
    """
    utc_summer, _ = compute_utc_datetime(
        birth_date=date(2023, 7, 15),
        birth_time=time(14, 0, 0),
        timezone_name="America/New_York"
    )
    # 14:00 EDT -> 18:00 UTC
    assert utc_summer.hour == 18
    assert utc_summer.day == 15

    utc_winter, _ = compute_utc_datetime(
        birth_date=date(2023, 1, 15),
        birth_time=time(14, 0, 0),
        timezone_name="America/New_York"
    )
    # 14:00 EST -> 19:00 UTC
    assert utc_winter.hour == 19
    assert utc_winter.day == 15


def test_unknown_birth_time_approximation():
    """When birth time is unknown, compute_utc_datetime defaults to 12:00:00 local time."""
    utc_dt, is_approx = compute_utc_datetime(
        birth_date=date(1995, 8, 20),
        birth_time=None,
        timezone_name="Asia/Kolkata",
        time_uncertainty=TimeUncertainty.UNKNOWN
    )
    assert is_approx is True
    # 12:00 IST (UTC+5:30) -> 06:30 UTC
    assert utc_dt.hour == 6
    assert utc_dt.minute == 30


def test_coordinate_validation():
    """Invalid latitude or longitude must raise InvalidCoordinatesError."""
    with pytest.raises(InvalidCoordinatesError):
        validate_coordinates(95.0, 0.0)

    with pytest.raises(InvalidCoordinatesError):
        validate_coordinates(0.0, -185.0)

    # Valid coordinates should not raise
    validate_coordinates(18.9388, 72.8354)


def test_unsupported_date_ranges():
    """Years outside [1800, 2100] must raise UnsupportedDateRangeError."""
    with pytest.raises(UnsupportedDateRangeError):
        validate_date_range(date(1799, 12, 31))

    with pytest.raises(UnsupportedDateRangeError):
        validate_date_range(date(2101, 1, 1))

    # Valid date
    validate_date_range(date(2026, 10, 23))
