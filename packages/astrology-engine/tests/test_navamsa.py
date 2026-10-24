"""Unit tests for Navamsa (D9) divisional chart calculations."""

from datetime import date, time
import pytest
from astrology_engine.models import ChartRequest, AstrologySystem
from astrology_engine.chart import calculate_d1_chart
from astrology_engine.navamsa import calculate_navamsa_planet, calculate_navamsa_chart


def test_navamsa_movable_sign_aries():
    """Aries 0° to 3°20' maps to Aries Navamsa (1st pada of Aries), making it Vargottama."""
    p = calculate_navamsa_planet(name="Sun", longitude=1.5)
    assert p.d1_sign_number == 1
    assert p.d1_sign_name == "Aries"
    assert p.d9_sign_number == 1
    assert p.d9_sign_name == "Aries"
    assert p.d9_pada == 1
    assert p.is_vargottama is True


def test_navamsa_fixed_sign_taurus():
    """Taurus (Fixed sign) begins from Capricorn (10th sign of zodiac).
    Taurus 0° to 3°20' (30° to 33°20' in zodiac) should map to Capricorn (sign 10).
    """
    p = calculate_navamsa_planet(name="Moon", longitude=31.0)
    assert p.d1_sign_number == 2
    assert p.d1_sign_name == "Taurus"
    assert p.d9_sign_number == 10
    assert p.d9_sign_name == "Capricorn"
    assert p.d9_pada == 1
    assert p.is_vargottama is False


def test_navamsa_dual_sign_gemini():
    """Gemini (Dual sign) begins from Libra (7th sign of zodiac).
    Gemini 0° to 3°20' (60° to 63°20') should map to Libra (sign 7).
    """
    p = calculate_navamsa_planet(name="Mercury", longitude=61.0)
    assert p.d1_sign_number == 3
    assert p.d1_sign_name == "Gemini"
    assert p.d9_sign_number == 7
    assert p.d9_sign_name == "Libra"


def test_navamsa_chart_integration():
    """Verify D9 chart calculation on full D1 natal chart."""
    req = ChartRequest(
        birth_date=date(1995, 10, 24),
        birth_time=time(14, 30),
        latitude=28.6139,
        longitude=77.2090,
        timezone_name="Asia/Kolkata",
        system=AstrologySystem.VEDIC,
    )
    d1 = calculate_d1_chart(req)
    d9 = calculate_navamsa_chart(d1)

    assert len(d9.planets) == len(d1.planets)
    assert d9.ascendant is not None
    assert isinstance(d9.vargottama_planets, list)
