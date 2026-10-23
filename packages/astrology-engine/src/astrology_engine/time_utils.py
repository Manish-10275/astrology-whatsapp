"""Date, time, timezone, and Julian Day conversions."""

from datetime import date, time, datetime, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Optional, Tuple
from timezonefinder import TimezoneFinder

from astrology_engine.exceptions import (
    InvalidCoordinatesError,
    TimezoneResolutionError,
    UnsupportedDateRangeError,
)
from astrology_engine.models import JulianDayInfo, TimeUncertainty
from astrology_engine.adapter import SwissEphemerisAdapter, default_adapter

_tz_finder: Optional[TimezoneFinder] = None


def get_timezone_finder() -> TimezoneFinder:
    """Lazy loader for TimezoneFinder to avoid overhead on imports."""
    global _tz_finder
    if _tz_finder is None:
        _tz_finder = TimezoneFinder()
    return _tz_finder


def resolve_timezone(lat: float, lon: float) -> str:
    """Resolves an IANA timezone name (e.g. 'Asia/Kolkata') from geographic coordinates."""
    validate_coordinates(lat, lon)
    tf = get_timezone_finder()
    tz_name = tf.timezone_at(lat=lat, lng=lon)
    if not tz_name:
        raise TimezoneResolutionError(f"Could not determine timezone for coordinates lat={lat}, lon={lon}")
    return tz_name


def validate_coordinates(lat: float, lon: float) -> None:
    """Validates that latitude and longitude fall within physical bounds."""
    if not (-90.0 <= lat <= 90.0):
        raise InvalidCoordinatesError(f"Latitude {lat} is out of bounds [-90, 90].")
    if not (-180.0 <= lon <= 180.0):
        raise InvalidCoordinatesError(f"Longitude {lon} is out of bounds [-180, 180].")


def validate_date_range(target_date: date, min_year: int = 1800, max_year: int = 2100) -> None:
    """Validates that a date falls within the supported astronomical range."""
    if target_date.year < min_year or target_date.year > max_year:
        raise UnsupportedDateRangeError(
            f"Date {target_date} year is outside supported range [{min_year}, {max_year}]."
        )


def compute_utc_datetime(
    birth_date: date,
    birth_time: Optional[time],
    timezone_name: str,
    longitude: Optional[float] = None,
    timezone_offset_seconds: Optional[int] = None,
    fold: int = 0,
    time_uncertainty: TimeUncertainty = TimeUncertainty.EXACT
) -> Tuple[datetime, bool]:
    """Converts a local date and time into an unambiguous UTC datetime.
    
    Supports:
    - Standard IANA timezone strings (e.g., 'Asia/Kolkata', 'America/New_York')
    - 'LMT' (Local Mean Time) calculated directly from longitude (longitude * 240 seconds)
    - Explicit timezone offset in seconds (e.g. 19800 for UTC+5:30)
    - Disambiguation of duplicate local times during daylight saving fall-back via `fold` (0 or 1)
    
    If birth_time is None or time_uncertainty is UNKNOWN, defaults to 12:00:00 (Noon) local time.
    
    Returns:
        (utc_datetime, is_time_approximated)
    """
    validate_date_range(birth_date)

    if timezone_offset_seconds is not None:
        tz = timezone(timedelta(seconds=timezone_offset_seconds))
    elif timezone_name.strip().upper() == "LMT":
        if longitude is None:
            raise TimezoneResolutionError("Longitude is required to compute Local Mean Time (LMT).")
        validate_coordinates(0.0, longitude)
        lmt_seconds = round(longitude * 240.0)
        tz = timezone(timedelta(seconds=lmt_seconds))
    else:
        try:
            tz = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as e:
            raise TimezoneResolutionError(f"Unknown IANA timezone: '{timezone_name}'") from e

    is_approximated = False
    if birth_time is None or time_uncertainty == TimeUncertainty.UNKNOWN:
        effective_time = time(12, 0, 0)
        is_approximated = True
    else:
        effective_time = birth_time.replace(fold=fold)

    # Combine date and time in the target local timezone
    local_dt = datetime.combine(birth_date, effective_time, tzinfo=tz)

    # Convert to UTC
    utc_dt = local_dt.astimezone(ZoneInfo("UTC"))
    return utc_dt, is_approximated


def compute_julian_day(
    utc_dt: datetime,
    adapter: Optional[SwissEphemerisAdapter] = None
) -> JulianDayInfo:
    """Computes high-precision Julian Day (UT1) and Ephemeris Time (ET/TDB) with Delta T."""
    eph = adapter or default_adapter

    decimal_hour = (
        utc_dt.hour
        + (utc_dt.minute / 60.0)
        + (utc_dt.second / 3600.0)
        + (utc_dt.microsecond / 3.6e9)
    )

    jd_ut = eph.get_julian_day(utc_dt.year, utc_dt.month, utc_dt.day, decimal_hour)
    delta_t = eph.get_delta_t(jd_ut)
    jd_et = jd_ut + (delta_t / 86400.0)

    return JulianDayInfo(
        jd_ut=jd_ut,
        jd_et=jd_et,
        delta_t=delta_t,
        utc_datetime=utc_dt
    )
