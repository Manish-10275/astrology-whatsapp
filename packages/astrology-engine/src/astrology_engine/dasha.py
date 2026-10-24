"""Vimshottari Dasha calculation engine.

Calculates the 120-year Vimshottari Mahadasha and Antardasha cycle based on the natal
Moon's verified sidereal position and Nakshatra.
"""

from datetime import date, datetime, timedelta
from typing import Optional, List, Dict
from astrology_engine.models import (
    MahadashaPeriod,
    AntardashaPeriod,
    VimshottariDashaResult,
    NAKSHATRAS,
    NAKSHATRA_LORDS,
)

# Standard Vimshottari Dasha durations in solar years (sum = 120)
VIMSHOTTARI_CYCLE_LORDS: List[str] = [
    "Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury"
]

VIMSHOTTARI_YEARS: Dict[str, float] = {
    "Ketu": 7.0,
    "Venus": 20.0,
    "Sun": 6.0,
    "Moon": 10.0,
    "Mars": 7.0,
    "Rahu": 18.0,
    "Jupiter": 16.0,
    "Saturn": 19.0,
    "Mercury": 17.0,
}

DAYS_PER_YEAR: float = 365.25
NAKSHATRA_SPAN_DEGREES: float = 40.0 / 3.0  # 13° 20' = 13.333333333333334°


def calculate_vimshottari_dasha(
    moon_longitude: float,
    birth_date: date,
    as_of_date: Optional[date] = None,
) -> VimshottariDashaResult:
    """Calculates Vimshottari Mahadashas and Antardashas from natal Moon longitude.
    
    Args:
        moon_longitude: Sidereal longitude of the natal Moon in degrees [0, 360).
        birth_date: Date of birth (start of life cycle).
        as_of_date: Reference date to determine the currently running Dasha (default: today).
    
    Returns:
        Structured VimshottariDashaResult containing all 9 Mahadasha periods and sub-periods.
    """
    b_date = birth_date.date() if isinstance(birth_date, datetime) else birth_date
    as_of = (as_of_date.date() if isinstance(as_of_date, datetime) else as_of_date) or date.today()
    normalized_long = moon_longitude % 360.0

    nak_index = int(normalized_long / NAKSHATRA_SPAN_DEGREES)
    nak_name = NAKSHATRAS[nak_index]
    first_lord = NAKSHATRA_LORDS[nak_index]

    # Degree traversed into the current Nakshatra
    degrees_into_nak = normalized_long - (nak_index * NAKSHATRA_SPAN_DEGREES)
    fraction_traversed = degrees_into_nak / NAKSHATRA_SPAN_DEGREES
    fraction_remaining = max(0.0, min(1.0, 1.0 - fraction_traversed))

    pada = int(degrees_into_nak / (NAKSHATRA_SPAN_DEGREES / 4.0)) + 1
    pada = max(1, min(4, pada))

    # Balance of first Mahadasha remaining at birth
    first_lord_total_years = VIMSHOTTARI_YEARS[first_lord]
    first_dasha_balance_years = fraction_remaining * first_lord_total_years

    # Build sequence of 9 Mahadashas starting from first_lord
    lord_start_idx = VIMSHOTTARI_CYCLE_LORDS.index(first_lord)
    mahadashas: List[MahadashaPeriod] = []

    current_start_date = b_date
    current_mahadasha_name: Optional[str] = None
    current_antardasha_name: Optional[str] = None

    for i in range(len(VIMSHOTTARI_CYCLE_LORDS)):
        ruler = VIMSHOTTARI_CYCLE_LORDS[(lord_start_idx + i) % len(VIMSHOTTARI_CYCLE_LORDS)]
        full_years = VIMSHOTTARI_YEARS[ruler]

        if i == 0:
            duration_years = first_dasha_balance_years
        else:
            duration_years = full_years

        duration_days = duration_years * DAYS_PER_YEAR
        end_date = current_start_date + timedelta(days=round(duration_days))

        # Calculate Antardashas within this Mahadasha
        antardashas = _calculate_antardashas(
            mahadasha_ruler=ruler,
            mahadasha_start=current_start_date,
            mahadasha_end=end_date,
            is_first_dasha=(i == 0),
            fraction_remaining=fraction_remaining,
        )

        # Check if as_of falls within this Mahadasha
        if current_start_date <= as_of <= end_date:
            current_mahadasha_name = ruler
            for ad in antardashas:
                if ad.start_date <= as_of <= ad.end_date:
                    current_antardasha_name = ad.ruler
                    break

        mahadashas.append(
            MahadashaPeriod(
                ruler=ruler,
                start_date=current_start_date,
                end_date=end_date,
                duration_years=round(duration_years, 3),
                antardashas=antardashas,
            )
        )
        current_start_date = end_date

    # Fallback if as_of is before birth or past 120 years
    if current_mahadasha_name is None and mahadashas:
        if as_of < b_date:
            current_mahadasha_name = mahadashas[0].ruler
            current_antardasha_name = mahadashas[0].antardashas[0].ruler if mahadashas[0].antardashas else None
        else:
            current_mahadasha_name = mahadashas[-1].ruler
            current_antardasha_name = mahadashas[-1].antardashas[-1].ruler if mahadashas[-1].antardashas else None

    return VimshottariDashaResult(
        birth_date=b_date,
        moon_longitude=round(normalized_long, 4),
        nakshatra_name=nak_name,
        nakshatra_pada=pada,
        first_dasha_balance_years=round(first_dasha_balance_years, 3),
        mahadashas=mahadashas,
        current_mahadasha=current_mahadasha_name,
        current_antardasha=current_antardasha_name,
    )


def _calculate_antardashas(
    mahadasha_ruler: str,
    mahadasha_start: date,
    mahadasha_end: date,
    is_first_dasha: bool,
    fraction_remaining: float,
) -> List[AntardashaPeriod]:
    """Calculates all 9 Antardasha sub-periods for a Mahadasha."""
    maha_idx = VIMSHOTTARI_CYCLE_LORDS.index(mahadasha_ruler)
    maha_years = VIMSHOTTARI_YEARS[mahadasha_ruler]

    # Standard durations for all 9 antardashas in full cycle
    full_durations: List[tuple[str, float]] = []
    for j in range(len(VIMSHOTTARI_CYCLE_LORDS)):
        antar_lord = VIMSHOTTARI_CYCLE_LORDS[(maha_idx + j) % len(VIMSHOTTARI_CYCLE_LORDS)]
        antar_years = VIMSHOTTARI_YEARS[antar_lord]
        duration_days = (maha_years * antar_years / 120.0) * DAYS_PER_YEAR
        full_durations.append((antar_lord, duration_days))

    if not is_first_dasha:
        # Standard sequential layout
        antardashas: List[AntardashaPeriod] = []
        cur_start = mahadasha_start
        for lord, d_days in full_durations:
            cur_end = cur_start + timedelta(days=round(d_days))
            if cur_end > mahadasha_end or lord == full_durations[-1][0]:
                cur_end = mahadasha_end
            antardashas.append(
                AntardashaPeriod(
                    ruler=lord,
                    start_date=cur_start,
                    end_date=cur_end,
                    duration_days=round((cur_end - cur_start).days, 1),
                )
            )
            cur_start = cur_end
        return antardashas

    # For the first Mahadasha, only the remaining portion applies
    # Find which Antardashas have elapsed before birth and proportionally allocate
    total_maha_days = maha_years * DAYS_PER_YEAR
    days_elapsed_before_birth = total_maha_days * (1.0 - fraction_remaining)

    antardashas = []
    cur_elapsed = 0.0
    cur_start = mahadasha_start

    for lord, d_days in full_durations:
        cur_elapsed += d_days
        if cur_elapsed <= days_elapsed_before_birth:
            # Already passed before birth
            continue
        elif cur_elapsed - d_days < days_elapsed_before_birth < cur_elapsed:
            # Active at the moment of birth: partial remaining
            remaining_in_ad = cur_elapsed - days_elapsed_before_birth
            cur_end = cur_start + timedelta(days=round(remaining_in_ad))
            antardashas.append(
                AntardashaPeriod(
                    ruler=lord,
                    start_date=cur_start,
                    end_date=cur_end,
                    duration_days=round(remaining_in_ad, 1),
                )
            )
            cur_start = cur_end
        else:
            # Fully in the future
            cur_end = cur_start + timedelta(days=round(d_days))
            if cur_end > mahadasha_end:
                cur_end = mahadasha_end
            antardashas.append(
                AntardashaPeriod(
                    ruler=lord,
                    start_date=cur_start,
                    end_date=cur_end,
                    duration_days=round((cur_end - cur_start).days, 1),
                )
            )
            cur_start = cur_end

    if antardashas:
        antardashas[-1].end_date = mahadasha_end

    return antardashas
