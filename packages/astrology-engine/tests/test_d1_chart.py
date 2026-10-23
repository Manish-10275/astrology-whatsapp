"""Tests for the high-level D1 chart generator."""

import pytest
from datetime import date, time

from astrology_engine.models import (
    ChartRequest,
    AstrologySystem,
    HouseSystemType,
    AyanamsaType,
    TimeUncertainty,
)
from astrology_engine.chart import calculate_d1_chart


def test_complete_vedic_d1_chart():
    """Generates a complete Vedic D1 chart and verifies structure, Lagna, Navagraha, and houses."""
    request = ChartRequest(
        birth_date=date(1992, 8, 15),
        birth_time=time(14, 30, 0),
        time_uncertainty=TimeUncertainty.EXACT,
        latitude=18.9388,
        longitude=72.8354,
        timezone_name="Asia/Kolkata",
        system=AstrologySystem.VEDIC,
        ayanamsa=AyanamsaType.LAHIRI,
        house_system=HouseSystemType.WHOLE_SIGN
    )

    chart = calculate_d1_chart(request)

    assert chart.system == AstrologySystem.VEDIC
    assert chart.ayanamsa_used == "lahiri"
    assert chart.ayanamsa_degrees is not None and 23.5 < chart.ayanamsa_degrees < 24.2
    assert chart.ascendant is not None
    assert chart.ascendant.nakshatra is not None
    assert len(chart.houses) == 12
    # Vedic Navagraha: 9 planets (Sun, Moon, Mars, Mercury, Jupiter, Venus, Saturn, Rahu, Ketu)
    assert len(chart.planets) == 9

    # Verify that every planet has a valid house (1 to 12)
    for p in chart.planets:
        assert p.house is not None
        assert 1 <= p.house <= 12
        assert p.nakshatra is not None

    # Verify calculation hash repeatability
    chart2 = calculate_d1_chart(request)
    assert chart.calculation_hash == chart2.calculation_hash
    assert chart.ascendant.longitude == chart2.ascendant.longitude


def test_complete_western_d1_chart():
    """Generates a complete Western D1 chart and verifies structure, Placidus houses, and planets."""
    request = ChartRequest(
        birth_date=date(1990, 5, 12),
        birth_time=time(9, 15, 0),
        time_uncertainty=TimeUncertainty.EXACT,
        latitude=40.7128,
        longitude=-74.0060,
        timezone_name="America/New_York",
        system=AstrologySystem.WESTERN,
        house_system=HouseSystemType.PLACIDUS
    )

    chart = calculate_d1_chart(request)

    assert chart.system == AstrologySystem.WESTERN
    assert chart.ayanamsa_used is None
    assert chart.ascendant is not None
    assert chart.midheaven is not None
    assert len(chart.houses) == 12
    # Western list includes outer planets: Uranus, Neptune, Pluto, Nodes
    assert len(chart.planets) >= 11

    for p in chart.planets:
        assert p.house is not None
        assert 1 <= p.house <= 12


def test_unknown_birth_time_withholds_houses():
    """When birth time is unknown:
    - Ascendant is None
    - Midheaven is None
    - Houses list is empty
    - Planets have house = None
    """
    request = ChartRequest(
        birth_date=date(1985, 11, 25),
        birth_time=None,
        time_uncertainty=TimeUncertainty.UNKNOWN,
        latitude=28.6139,
        longitude=77.2090,
        timezone_name="Asia/Kolkata",
        system=AstrologySystem.VEDIC
    )

    chart = calculate_d1_chart(request)

    assert chart.time_uncertainty == TimeUncertainty.UNKNOWN
    assert chart.ascendant is None
    assert chart.midheaven is None
    assert len(chart.houses) == 0

    for p in chart.planets:
        assert p.house is None
        # Planets still have valid signs and nakshatras
        assert 1 <= p.sign_number <= 12
        assert p.nakshatra is not None
