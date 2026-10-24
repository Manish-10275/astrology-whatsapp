"""Unit tests for Western astrology aspects, elements, and chart analysis."""

from datetime import date, time
import pytest
from astrology_engine.models import ChartRequest, AstrologySystem, PlanetPosition
from astrology_engine.chart import calculate_d1_chart
from astrology_engine.western import calculate_western_aspects, analyze_western_chart


def make_dummy_planet(name: str, longitude: float, sign_num: int) -> PlanetPosition:
    return PlanetPosition(
        name=name,
        longitude=longitude,
        latitude=0.0,
        distance_au=1.0,
        speed_longitude=1.0,
        is_retrograde=False,
        sign_number=sign_num,
        sign_name="Aries",
        degree_in_sign=longitude % 30.0,
    )


def test_western_aspects_conjunction_and_opposition():
    """Verify Conjunction (within 8° orb) and Opposition (180° +/- 8°)."""
    p1 = make_dummy_planet("Sun", 10.0, 1)
    p2 = make_dummy_planet("Moon", 14.0, 1)   # Conjunction: diff = 4° (orb <= 8°)
    p3 = make_dummy_planet("Mars", 192.0, 7)  # Opposition with Sun: diff = |10 - 192| = 182° -> 178° (orb 2°)

    aspects = calculate_western_aspects([p1, p2, p3])
    aspect_types = [a.aspect_type for a in aspects]

    assert "Conjunction" in aspect_types
    assert "Opposition" in aspect_types


def test_western_aspects_trine_and_square():
    """Verify Trine (120° +/- 8°) and Square (90° +/- 8°)."""
    p1 = make_dummy_planet("Venus", 15.0, 1)
    p2 = make_dummy_planet("Jupiter", 136.0, 5)  # Trine with Venus: diff = 121° (orb 1°)
    p3 = make_dummy_planet("Saturn", 107.0, 4)   # Square with Venus: diff = 92° (orb 2°)

    aspects = calculate_western_aspects([p1, p2, p3])
    aspect_types = [a.aspect_type for a in aspects]

    assert "Trine" in aspect_types
    assert "Square" in aspect_types


def test_western_chart_analysis_integration():
    """Verify Western chart analysis on a full tropical natal chart."""
    req = ChartRequest(
        birth_date=date(1995, 10, 24),
        birth_time=time(14, 30),
        latitude=51.5074,
        longitude=-0.1278,
        timezone_name="Europe/London",
        system=AstrologySystem.WESTERN,
    )
    d1 = calculate_d1_chart(req)
    analysis = analyze_western_chart(d1)

    assert len(analysis.aspects) > 0
    assert analysis.dominant_element in ["Fire", "Earth", "Air", "Water"]
    assert analysis.dominant_modality in ["Cardinal", "Fixed", "Mutable"]
