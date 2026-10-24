"""Unit tests for Ashtakoota (36-Guna) Vedic Marriage Compatibility."""

import pytest
from astrology_engine.compatibility import calculate_ashtakoota


def test_ashtakoota_identical_chart():
    """Identical Moon longitudes should yield high compatibility score (28/36) across the first 7 kootas."""
    res = calculate_ashtakoota(
        groom_moon_longitude=45.0,  # Rohini
        bride_moon_longitude=45.0,
    )
    assert res.total_score == 28.0
    assert len(res.kootas) == 8
    assert res.verdict == "Highly Auspicious"
    # Same sign and exact same nakshatra & pada has Nadi dosha without cancellation
    assert res.nadi_dosha is True
    assert res.nadi_dosha_cancelled is False


def test_ashtakoota_nadi_cancellation_distinct_padas():
    """Same Nakshatra (Rohini) but distinct Padas cancels Nadi Dosha, granting full 8 points."""
    # Rohini spans 40.0° to 53.3333° (each pada is 3.3333°)
    # Pada 1: 40.0° to 43.3333° -> e.g. 41.0°
    # Pada 2: 43.3333° to 46.6667° -> e.g. 45.0°
    res = calculate_ashtakoota(
        groom_moon_longitude=41.0,  # Rohini Pada 1
        bride_moon_longitude=45.0,  # Rohini Pada 2
    )
    assert res.nadi_dosha is True
    assert res.nadi_dosha_cancelled is True
    nadi = next(k for k in res.kootas if k.name == "Nadi")
    assert nadi.obtained_points == 8.0
    assert any("distinct Padas" in exc for exc in res.dosha_exceptions)


def test_ashtakoota_varna_scoring():
    """Brahmin Groom (Cancer Moon, ~100°) vs Kshatriya Bride (Leo Moon, ~130°) yields 1 pt; reverse yields 0."""
    res_favorable = calculate_ashtakoota(
        groom_moon_longitude=100.0,  # Cancer (Brahmin)
        bride_moon_longitude=130.0,  # Leo (Kshatriya)
    )
    varna_koota = next(k for k in res_favorable.kootas if k.name == "Varna")
    assert varna_koota.obtained_points == 1.0

    res_unfavorable = calculate_ashtakoota(
        groom_moon_longitude=130.0,  # Leo (Kshatriya)
        bride_moon_longitude=100.0,  # Cancer (Brahmin)
    )
    varna_unfav = next(k for k in res_unfavorable.kootas if k.name == "Varna")
    assert varna_unfav.obtained_points == 0.0


def test_ashtakoota_nadi_dosha_and_different_nadis():
    """Different Nadis give full 8 points, same Nadi gives 0 points unless cancelled."""
    # Ashwini (Nakshatra 1, Adi) vs Bharani (Nakshatra 2, Madhya)
    res_diff = calculate_ashtakoota(
        groom_moon_longitude=5.0,   # Ashwini (Adi Nadi)
        bride_moon_longitude=20.0,  # Bharani (Madhya Nadi)
    )
    nadi_diff = next(k for k in res_diff.kootas if k.name == "Nadi")
    assert nadi_diff.obtained_points == 8.0
    assert res_diff.nadi_dosha is False


def test_ashtakoota_bhakoot_dosha_cancellation():
    """Aries (Mars) and Scorpio (Mars) have a 6/8 distance, but same lord Mars cancels Bhakoot dosha."""
    res = calculate_ashtakoota(
        groom_moon_longitude=10.0,   # Aries (ruled by Mars)
        bride_moon_longitude=220.0,  # Scorpio (ruled by Mars)
    )
    bhakoot = next(k for k in res.kootas if k.name == "Bhakoot")
    assert bhakoot.obtained_points == 7.0
    assert res.bhakoot_dosha is True
    assert res.bhakoot_dosha_cancelled is True
    assert any("ruled by Mars" in exc for exc in res.dosha_exceptions)


def test_ashtakoota_total_score_boundaries_and_verdicts():
    """Verify total score is always within [0, 36] and verdict aligns with points."""
    res = calculate_ashtakoota(
        groom_moon_longitude=15.0,
        bride_moon_longitude=85.0,
    )
    assert 0.0 <= res.total_score <= 36.0
    assert 0.0 <= res.percentage <= 100.0
    assert res.verdict in ["Highly Auspicious", "Auspicious", "Acceptable", "Inauspicious"]
