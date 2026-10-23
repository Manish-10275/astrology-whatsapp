"""Tests for Tropical planetary calculations."""

import pytest
from datetime import datetime
from zoneinfo import ZoneInfo

from astrology_engine.time_utils import compute_julian_day
from astrology_engine.tropical import (
    calculate_tropical_planet,
    calculate_tropical_planets,
    longitude_to_sign,
)


def test_j2000_tropical_sun():
    """At J2000.0 (2000-01-01 12:00:00 TT), the Sun's tropical geometric longitude
    according to Astrodienst Swiss Ephemeris is approx 280.3689° (Capricorn 10° 22').
    """
    utc_dt = datetime(2000, 1, 1, 12, 0, 0, tzinfo=ZoneInfo("UTC"))
    jd = compute_julian_day(utc_dt).jd_ut

    sun = calculate_tropical_planet(jd, "Sun")

    assert sun.name == "Sun"
    assert abs(sun.longitude - 280.3689) < 0.01  # < 0.01 degree tolerance
    assert sun.sign_name == "Capricorn"
    assert sun.sign_sanskrit == "Makara"
    assert sun.sign_number == 10
    assert abs(sun.degree_in_sign - 10.3689) < 0.01
    assert not sun.is_retrograde
    assert 0.98 < sun.distance_au < 0.99  # Near perihelion in January
    assert 0.95 < sun.speed_longitude < 1.05  # Approx 1 deg/day


def test_tropical_planets_list():
    """Verifies that calculate_tropical_planets calculates all major bodies."""
    utc_dt = datetime(2026, 10, 23, 12, 0, 0, tzinfo=ZoneInfo("UTC"))
    jd = compute_julian_day(utc_dt).jd_ut

    planets = calculate_tropical_planets(jd)
    planet_names = [p.name for p in planets]

    for expected in ["Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto", "Rahu"]:
        assert expected in planet_names

    # Longitudes must all be strictly within [0, 360)
    for p in planets:
        assert 0.0 <= p.longitude < 360.0
        assert 0.0 <= p.degree_in_sign < 30.0
        assert 1 <= p.sign_number <= 12


def test_longitude_to_sign_boundaries():
    """Tests zodiac sign boundary mapping at critical degree points."""
    # 0.0000° -> Aries 0°
    s_num, s_name, s_sans, deg = longitude_to_sign(0.0)
    assert s_num == 1 and s_name == "Aries" and abs(deg - 0.0) < 1e-6

    # 29.9999° -> Aries 29.9999°
    s_num, s_name, s_sans, deg = longitude_to_sign(29.9999)
    assert s_num == 1 and s_name == "Aries" and abs(deg - 29.9999) < 1e-4

    # 30.0000° -> Taurus 0°
    s_num, s_name, s_sans, deg = longitude_to_sign(30.0)
    assert s_num == 2 and s_name == "Taurus" and abs(deg - 0.0) < 1e-6

    # 359.5000° -> Pisces 29.5°
    s_num, s_name, s_sans, deg = longitude_to_sign(359.5)
    assert s_num == 12 and s_name == "Pisces" and abs(deg - 29.5) < 1e-6
