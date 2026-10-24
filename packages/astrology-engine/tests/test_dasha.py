"""Unit tests for Vimshottari Dasha calculations."""

from datetime import date
import pytest
from astrology_engine.dasha import calculate_vimshottari_dasha, VIMSHOTTARI_YEARS


def test_dasha_beginning_of_ashwini():
    """Moon at 0° (beginning of Ashwini) should yield Ketu Mahadasha with full 7-year balance."""
    res = calculate_vimshottari_dasha(
        moon_longitude=0.0,
        birth_date=date(1990, 1, 1),
        as_of_date=date(1990, 1, 1),
    )
    assert res.nakshatra_name == "Ashwini"
    assert res.nakshatra_pada == 1
    assert res.mahadashas[0].ruler == "Ketu"
    # Full 7.0 years
    assert abs(res.first_dasha_balance_years - 7.0) < 0.05
    assert res.current_mahadasha == "Ketu"


def test_dasha_halfway_into_nakshatra():
    """Moon halfway through Rohini (Moon-ruled, 10-year Dasha) should have ~50% balance (~5 years)."""
    # Rohini is Nakshatra index 3 (4th nakshatra), spans 40° to 53°20' (40.0 to 53.3333°)
    # Midpoint of Rohini is 40.0 + 6.66667 = 46.6667°
    res = calculate_vimshottari_dasha(
        moon_longitude=46.6667,
        birth_date=date(2000, 1, 1),
        as_of_date=date(2000, 1, 1),
    )
    assert res.nakshatra_name == "Rohini"
    assert res.mahadashas[0].ruler == "Moon"
    assert abs(res.first_dasha_balance_years - 5.0) < 0.1


def test_dasha_full_120_year_cycle():
    """Verify all 9 Mahadashas appear in fixed sequence and total duration from birth is ~120 years."""
    res = calculate_vimshottari_dasha(
        moon_longitude=0.0,
        birth_date=date(1990, 1, 1),
    )
    assert len(res.mahadashas) == 9
    expected_rulers = ["Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury"]
    actual_rulers = [m.ruler for m in res.mahadashas]
    assert actual_rulers == expected_rulers

    # Total days span ~120 years (120 * 365.25 = 43830 days)
    total_days = (res.mahadashas[-1].end_date - res.mahadashas[0].start_date).days
    assert abs(total_days - (120 * 365.25)) < 15


def test_antardashas_breakdown():
    """Each full Mahadasha must contain exactly 9 Antardashas starting with its own ruler."""
    res = calculate_vimshottari_dasha(
        moon_longitude=120.0,  # Magha (Ketu)
        birth_date=date(2000, 1, 1),
    )
    # Check 2nd Mahadasha (Venus, full 20 years)
    venus_maha = res.mahadashas[1]
    assert venus_maha.ruler == "Venus"
    assert len(venus_maha.antardashas) == 9
    assert venus_maha.antardashas[0].ruler == "Venus"
    assert venus_maha.antardashas[1].ruler == "Sun"
    assert venus_maha.antardashas[-1].ruler == "Ketu"
    assert venus_maha.antardashas[-1].end_date == venus_maha.end_date


def test_active_dasha_lookup():
    """Correctly identifies running Mahadasha and Antardasha for a future date."""
    res = calculate_vimshottari_dasha(
        moon_longitude=0.0,  # Ketu full 7 years (1990 to 1997), then Venus 20 years (1997 to 2017)
        birth_date=date(1990, 1, 1),
        as_of_date=date(2005, 6, 1),  # Inside Venus Mahadasha
    )
    assert res.current_mahadasha == "Venus"
    assert res.current_antardasha is not None
