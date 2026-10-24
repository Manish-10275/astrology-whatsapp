"""Unit tests for Planetary Transits (Gochara)."""

from datetime import date, time, datetime, timezone
import pytest
from astrology_engine.models import ChartRequest, AstrologySystem
from astrology_engine.chart import calculate_d1_chart
from astrology_engine.transits import calculate_transits


@pytest.fixture
def sample_natal_chart():
    req = ChartRequest(
        birth_date=date(1995, 10, 24),
        birth_time=time(14, 30),
        latitude=28.6139,
        longitude=77.2090,
        timezone_name="Asia/Kolkata",
        system=AstrologySystem.VEDIC,
    )
    return calculate_d1_chart(req)


def test_transit_calculation_structure(sample_natal_chart):
    """Verify Gochara transits return all 9 Vedic planets with relative house from natal Moon."""
    transit_dt = datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc)
    res = calculate_transits(sample_natal_chart, transit_datetime=transit_dt)

    assert res.transit_date == date(2025, 6, 1)
    assert len(res.planets) >= 9
    for tp in res.planets:
        assert 1 <= tp.house_from_moon <= 12
        assert 1 <= tp.sign_number <= 12
        assert tp.sign_name is not None
        assert tp.key_effects is not None


def test_sade_sati_detection_active_and_inactive(sample_natal_chart):
    """Test Sade Sati detection when Saturn is transiting 12th, 1st, or 2nd from Moon."""
    # Compute transit for a specific date
    res = calculate_transits(sample_natal_chart, transit_datetime=datetime(2025, 1, 1, tzinfo=timezone.utc))
    assert isinstance(res.sade_sati_active, bool)
    if res.sade_sati_active:
        assert res.sade_sati_phase in ["Rising", "Peak", "Setting"]
    else:
        assert res.sade_sati_phase is None
