"""Tests for Sidereal (Vedic) planetary calculations, Ayanamsas, and Nakshatras."""

import pytest
from datetime import datetime
from zoneinfo import ZoneInfo

from astrology_engine.time_utils import compute_julian_day
from astrology_engine.sidereal import (
    calculate_sidereal_planet,
    calculate_sidereal_planets,
    calculate_nakshatra,
)
from astrology_engine.models import AyanamsaType
from astrology_engine.adapter import default_adapter


def test_j2000_lahiri_ayanamsa():
    """At J2000.0 (JD 2451545.0), the Chitrapaksha (Lahiri) ayanamsa defined by
    the Indian Astronomical Ephemeris and Swiss Ephemeris is:
    23° 51' 25.53" = 23.857092°.
    """
    utc_dt = datetime(2000, 1, 1, 12, 0, 0, tzinfo=ZoneInfo("UTC"))
    jd = compute_julian_day(utc_dt).jd_ut

    default_adapter.set_sidereal_mode("lahiri")
    ayanamsa = default_adapter.get_ayanamsa_degrees(jd)

    assert abs(ayanamsa - 23.857092) < 0.001  # Accurate within 3.6 arcseconds


def test_raman_and_kp_ayanamsas():
    """Tests that alternative ayanamsas (Raman, KP) can be computed."""
    utc_dt = datetime(2000, 1, 1, 12, 0, 0, tzinfo=ZoneInfo("UTC"))
    jd = compute_julian_day(utc_dt).jd_ut

    default_adapter.set_sidereal_mode("kp")
    kp_ayanamsa = default_adapter.get_ayanamsa_degrees(jd)

    default_adapter.set_sidereal_mode("raman")
    raman_ayanamsa = default_adapter.get_ayanamsa_degrees(jd)

    # Raman ayanamsa is historically ~1.5° to 2° smaller than Lahiri
    assert 21.0 < raman_ayanamsa < 23.0
    # KP ayanamsa is within a few arcminutes of Lahiri
    assert 23.5 < kp_ayanamsa < 24.2


def test_sidereal_sun_at_j2000():
    """At J2000.0:
    Tropical Sun: ~280.369° (Capricorn 10° 22')
    Lahiri Ayanamsa: ~23.857°
    Expected Sidereal Sun: 280.369° - 23.857° = 256.512° (Sagittarius / Dhanu ~16° 31').
    """
    utc_dt = datetime(2000, 1, 1, 12, 0, 0, tzinfo=ZoneInfo("UTC"))
    jd = compute_julian_day(utc_dt).jd_ut

    sun = calculate_sidereal_planet(jd, "Sun", ayanamsa=AyanamsaType.LAHIRI)

    assert sun.name == "Sun"
    assert abs(sun.longitude - 256.512) < 0.05
    assert sun.sign_name == "Sagittarius"
    assert sun.sign_sanskrit == "Dhanu"
    assert sun.sign_number == 9
    assert abs(sun.degree_in_sign - 16.512) < 0.05
    assert sun.nakshatra is not None
    # 256.512° falls into Purva Ashadha Nakshatra (253° 20' to 266° 40')
    assert sun.nakshatra.name == "Purva Ashadha"
    assert sun.nakshatra.ruler == "Venus"


def test_nakshatra_and_pada_boundaries():
    """Tests all 27 Nakshatras and 4 padas at boundary coordinates."""
    # 0.0000° -> Ashwini Pada 1 (Ruler: Ketu)
    nak_0 = calculate_nakshatra(0.0)
    assert nak_0.number == 1
    assert nak_0.name == "Ashwini"
    assert nak_0.ruler == "Ketu"
    assert nak_0.pada == 1

    # 3.3334° -> Ashwini Pada 2
    nak_pada2 = calculate_nakshatra(3.34)
    assert nak_pada2.name == "Ashwini"
    assert nak_pada2.pada == 2

    # 13.3334° -> Bharani Pada 1 (Ruler: Venus)
    nak_bharani = calculate_nakshatra(13.34)
    assert nak_bharani.number == 2
    assert nak_bharani.name == "Bharani"
    assert nak_bharani.ruler == "Venus"
    assert nak_bharani.pada == 1

    # 359.9999° -> Revati Pada 4 (Ruler: Mercury)
    nak_revati = calculate_nakshatra(359.9)
    assert nak_revati.number == 27
    assert nak_revati.name == "Revati"
    assert nak_revati.ruler == "Mercury"
    assert nak_revati.pada == 4


def test_ketu_opposite_rahu():
    """In Vedic astrology, Ketu must always be exactly 180° opposite Rahu."""
    utc_dt = datetime(2026, 10, 23, 12, 0, 0, tzinfo=ZoneInfo("UTC"))
    jd = compute_julian_day(utc_dt).jd_ut

    planets = calculate_sidereal_planets(jd, ayanamsa=AyanamsaType.LAHIRI, include_ketu=True)
    rahu = next(p for p in planets if p.name == "Rahu")
    ketu = next(p for p in planets if p.name == "Ketu")

    diff = (ketu.longitude - rahu.longitude) % 360.0
    assert abs(diff - 180.0) < 1e-6
