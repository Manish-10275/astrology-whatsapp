"""Unit tests for Vedic Panchang calculations."""

from datetime import date
import pytest
from astrology_engine.panchang import calculate_panchang


def test_panchang_shukla_pratipada():
    """When Moon is just ahead of Sun (e.g. 6° difference), Tithi is Shukla Pratipada."""
    res = calculate_panchang(
        sun_longitude=0.0,
        moon_longitude=6.0,
        target_date=date(2025, 4, 1),
    )
    assert res.tithi.number == 1
    assert res.tithi.name == "Pratipada"
    assert res.tithi.paksha == "Shukla"
    assert res.tithi.completed_percentage == 50.0  # 6 / 12 = 50%


def test_panchang_purnima():
    """When Moon is 174° to 180° ahead of Sun (15th 12° slice), Tithi is Purnima."""
    res = calculate_panchang(
        sun_longitude=0.0,
        moon_longitude=175.0,
        target_date=date(2025, 5, 12),
    )
    assert res.tithi.number == 15
    assert res.tithi.name == "Purnima"
    assert res.tithi.paksha == "Shukla"


def test_panchang_amavasya():
    """When Moon is 355° ahead of Sun (last 12° slice before conjunction), Tithi is Amavasya."""
    res = calculate_panchang(
        sun_longitude=10.0,
        moon_longitude=5.0,  # separation = (5 - 10) % 360 = 355°
        target_date=date(2025, 10, 20),
    )
    assert res.tithi.number == 30
    assert res.tithi.name == "Amavasya"
    assert res.tithi.paksha == "Krishna"


def test_panchang_yoga_and_karana():
    """Verify Yoga and Karana indices and Vishti detection."""
    # Sun at 0°, Moon at 6° -> separation = 6° -> Karana 1 (Kimstughna, fixed)
    res = calculate_panchang(
        sun_longitude=0.0,
        moon_longitude=3.0,
        target_date=date(2025, 1, 1),
    )
    assert res.karana.number == 1
    assert res.karana.name == "Kimstughna"
    assert res.karana.is_vishti is False

    # Yoga = (0 + 3) / 13.333 = 1 (Vishkambha)
    assert res.yoga.number == 1
    assert res.yoga.name == "Vishkambha"


def test_panchang_vishti_karana():
    """Karana 8 (1st half of Shukla Chaturthi, 42° to 48° separation) is Vishti (Bhadra)."""
    # (8 - 2) % 7 = 6 -> Vishti (Bhadra)
    res = calculate_panchang(
        sun_longitude=0.0,
        moon_longitude=44.0,
        target_date=date(2025, 6, 15),
    )
    assert res.karana.name == "Vishti (Bhadra)"
    assert res.karana.is_vishti is True


def test_panchang_vara():
    """Verify day of week (Vara) and lord mapping."""
    # 2025-01-05 is a Sunday -> Ravivara (Sun)
    res_sun = calculate_panchang(
        sun_longitude=260.0,
        moon_longitude=330.0,
        target_date=date(2025, 1, 5),
    )
    assert res_sun.vara == "Ravivara"
    assert res_sun.vara_lord == "Sun"

    # 2025-01-06 is a Monday -> Somavara (Moon)
    res_mon = calculate_panchang(
        sun_longitude=261.0,
        moon_longitude=342.0,
        target_date=date(2025, 1, 6),
    )
    assert res_mon.vara == "Somavara"
    assert res_mon.vara_lord == "Moon"
