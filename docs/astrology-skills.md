# Astrology Skills Specification & Calculation Contracts

**Document Version:** 1.0.0  
**Phase:** Phase 0 (Planning & Architecture)  
**Status:** Approved for Architectural Baseline  

---

## 1. Architectural Guardrails for Astrology Skills

Every astrology skill in the platform is implemented as a **deterministic Python module** powered by the Swiss Ephemeris (`pyswisseph`) C-extension wrapper.

### The 4 Ironclad Rules:
1. **Zero LLM Calculations:** The LLM is prohibited from calculating degrees, ascendants, houses, dashas, or compatibility scores.
2. **Schema-Enforced I/O:** Every skill consumes a strictly validated Pydantic input contract and outputs a strictly validated Pydantic calculation payload.
3. **Traceability:** Every calculation returns an immutable signature (`calculation_hash`, `engine_version`, `ephemeris_flags`) stored in PostgreSQL for reproducibility and auditability.
4. **Tolerance Standard:** Planetary coordinates must match Swiss Ephemeris reference calculations within `0.001` arcseconds ($< 0.0000003^\circ$).

---

## 2. Core Skill 1: Birth-Chart Generation & Interpretation

### 2.1 Description
Calculates natal planetary longitudes, speeds, retrograde statuses, house cusps, ascendant (Lagna/Rising), Moon Nakshatra, and foundational timing indicators (Vedic Vimshottari Dasha or Western Major Aspects).

### 2.2 Input Contract (Pydantic Schema)
```python
from pydantic import BaseModel, Field, field_validator
from datetime import date, time
from typing import Optional, Literal
from enum import Enum

class AstrologySystem(str, Enum):
    VEDIC = "vedic"
    WESTERN = "western"

class TimeUncertainty(str, Enum):
    EXACT = "exact"
    APPROXIMATE_WINDOW = "approximate_window"
    UNKNOWN = "unknown"

class NatalChartInput(BaseModel):
    birth_date: date = Field(..., description="Date of birth in YYYY-MM-DD")
    birth_time: Optional[time] = Field(None, description="Time of birth in HH:MM:SS (local time)")
    time_uncertainty: TimeUncertainty = Field(default=TimeUncertainty.EXACT)
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Latitude in decimal degrees")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Longitude in decimal degrees")
    elevation_meters: float = Field(default=0.0, ge=-500.0, le=9000.0)
    timezone_name: str = Field(..., description="IANA timezone name, e.g., 'Asia/Kolkata'")
    system: AstrologySystem = Field(default=AstrologySystem.VEDIC)
    ayanamsa: Literal["lahiri", "kp", "raman"] = Field(default="lahiri")
    house_system: Literal["placidus", "whole_sign", "equal"] = Field(default="placidus")

    @field_validator("birth_date")
    def validate_historical_range(cls, v: date):
        if v.year < 1850 or v.year > 2100:
            raise ValueError("Birth date must be between 1850 and 2100 CE.")
        return v
```

### 2.3 Output Contract (Pydantic Schema)
```python
class PlanetPlacement(BaseModel):
    name: str                           # 'Sun', 'Moon', 'Mars', etc.
    longitude: float                    # 0.0 to 359.9999°
    sign: str                           # 'Aries', 'Taurus', etc.
    degree_in_sign: float               # 0.0 to 29.9999°
    house: Optional[int] = None         # 1 to 12 (None if time unknown)
    is_retrograde: bool
    speed: float                        # Degrees per day
    nakshatra: Optional[str] = None     # Vedic only (e.g., 'Rohini')
    nakshatra_pada: Optional[int] = None# Vedic only (1 to 4)

class HouseCusp(BaseModel):
    house_number: int                   # 1 to 12
    cusp_longitude: float
    sign: str

class VimshottariDasha(BaseModel):
    current_mahadasha: str             # e.g., 'Saturn'
    current_antardasha: str            # e.g., 'Mercury'
    start_date: date
    end_date: date

class WesternAspect(BaseModel):
    planet_1: str
    planet_2: str
    aspect_type: str                    # 'Conjunction', 'Trine', 'Square', etc.
    angle: float
    orb: float                          # Angular difference from exact aspect

class NatalChartOutput(BaseModel):
    system: AstrologySystem
    ayanamsa_used: Optional[str]
    house_system_used: Optional[str]
    julian_day_utc: float
    ascendant_degree: Optional[float]
    ascendant_sign: Optional[str]
    midheaven_degree: Optional[float]
    planets: list[PlanetPlacement]
    houses: list[HouseCusp]
    vedic_dasha: Optional[VimshottariDasha] = None
    western_aspects: Optional[list[WesternAspect]] = None
    time_uncertainty_flag: TimeUncertainty
    calculation_hash: str
```

### 2.4 Missing Information Behavior
- **If `birth_time` is `None` or `time_uncertainty == UNKNOWN`:**
  - `ascendant_degree`, `ascendant_sign`, `midheaven_degree`, and `houses` are returned as `None` or empty list.
  - In Western: Coordinates are computed for 12:00:00 (Noon) local time. Solar houses (Sun degree as 1st house cusp) are optionally generated.
  - In Vedic: Coordinates are computed for 12:00:00 local time. Chandra Kundali (Moon sign as 1st house) is designated as the primary reference frame.
  - Flag `time_uncertainty_flag = "unknown"` alerts the LLM interpreter to state that rising sign and house-specific outcomes are withheld.

---

## 3. Core Skill 2: Daily Horoscopes

### 3.1 Description
Provides astrological forecasts for the current day.
- **Mode A (Personalized Transit):** Used when the user has an active birth profile. Compares current planetary transits against their specific natal planets and houses.
- **Mode B (General Zodiac):** Used when the user has only provided a Sun sign or Moon sign without birth date/time.

### 3.2 Input Contract
```python
class DailyHoroscopeInput(BaseModel):
    target_date: date = Field(default_factory=date.today)
    user_birth_profile_id: Optional[str] = None
    fallback_sign: Optional[str] = None # e.g., 'Leo', used if no birth profile
    system: AstrologySystem = Field(default=AstrologySystem.VEDIC)
```

### 3.3 Output Contract
```python
class TransitHighlight(BaseModel):
    transiting_planet: str
    aspect_or_house: str                # e.g., "Transiting 10th House" or "Trine Natal Sun"
    theme: str                          # 'Career', 'Relationships', 'Vitality'
    favorable: bool

class DailyHoroscopeOutput(BaseModel):
    target_date: date
    is_personalized: bool
    moon_sign_today: str
    moon_nakshatra_today: Optional[str]
    vedic_tithi: Optional[str]          # Lunar day (e.g., 'Shukla Navami')
    highlights: list[TransitHighlight]
    raw_transit_positions: list[PlanetPlacement]
```

### 3.4 Logic Distinction
- **Vedic Personalized:** Evaluates Moon's daily transit (*Chandra Gochara*) relative to natal Moon (e.g., transit through 6th, 8th, or 12th house indicates caution; *Chandrashtama* days flagged). Computes daily *Tara Bala* (birth star vs transiting star).
- **Western Personalized:** Evaluates current transiting Moon, Sun, and Mars aspects to natal planets with tight 1°–2° orbs.
- **General Zodiac Fallback:** Evaluates Sun-sign or Moon-sign transits without house-cusp specificity.

---

## 4. Core Skill 3: Compatibility Matching

### 4.1 Description
Computes quantitative and qualitative relationship compatibility between Profile A and Profile B.

### 4.2 Vedic Compatibility: Ashtakoota (36 Gunas) & Manglik Dosha
The Swiss Ephemeris calculates both profiles' Moon longitudes and Janma Nakshatras to evaluate the 8 Kootas:

| Koota | Meaning | Max Points | Evaluation Basis |
| :--- | :--- | :--- | :--- |
| **Varna** | Spiritual & ego compatibility | 1.0 | Nakshatra caste hierarchy |
| **Vashya** | Mutual attraction & power balance | 2.0 | Zodiac sign animal classification |
| **Tara** | Longevity, health & luck | 3.0 | Count from one birth star to another mod 9 |
| **Yoni** | Physical & sexual harmony | 4.0 | Animal symbol compatibility |
| **Graha Maitri** | Psychological & intellectual friendship | 5.0 | Friendship of Moon sign ruling planets |
| **Gana** | Temperament (Deva, Manushya, Rakshasa)| 6.0 | Nakshatra temperament classification |
| **Bhakoot** | Emotional health & family welfare | 7.0 | Moon sign distance (2/12, 6/8, 9/5 cautions)|
| **Nadi** | Genetic compatibility & lineage health | 8.0 | Adi, Madhya, Antya Nadi (Same Nadi = 0)|
| **TOTAL** | **Maximum Composite Score** | **36.0** | Score $\ge 18$ considered favorable |

**Manglik Dosha (Kuja Dosha) Rule:** Mars placed in 1st, 2nd (South Indian tradition), 4th, 7th, 8th, or 12th house from Lagna/Moon. If both are Manglik or specific cancellation conditions apply (Mars in own sign/exalted), the Dosha is mitigated.

### 4.3 Western Compatibility: Synastry & Aspect Harmony
Evaluates mutual cross-aspects:
- **Luminaries:** Sun conjunct/trine Moon (core harmony).
- **Romantic & Physical:** Venus trine/sextile Mars (attraction).
- **Communication:** Mercury conjunct/trine Mercury (intellectual flow).
- **Structure & Longevity:** Saturn aspects to Sun/Moon (commitment vs heaviness).
- **Harmonious Score:** Weighted percentage calculated from positive (trine/sextile) vs challenging (square/opposition) cross-aspects.

### 4.4 Compatibility Contracts
```python
class CompatibilityInput(BaseModel):
    profile_a: NatalChartInput
    profile_b: NatalChartInput
    system: AstrologySystem = Field(default=AstrologySystem.VEDIC)

class AshtakootaBreakdown(BaseModel):
    varna: float
    vashya: float
    tara: float
    yoni: float
    graha_maitri: float
    gana: float
    bhakoot: float
    nadi: float
    total_score: float                  # Out of 36.0
    is_favorable: bool                  # True if >= 18.0

class ManglikAnalysis(BaseModel):
    profile_a_is_manglik: bool
    profile_b_is_manglik: bool
    is_dosha_cancelled: bool
    mitigation_notes: str

class SynastryAspect(BaseModel):
    planet_a: str
    planet_b: str
    aspect_type: str
    orb: float
    harmony_weight: float               # Positive or negative impact

class CompatibilityOutput(BaseModel):
    system: AstrologySystem
    overall_score: float                # Vedic: Gunas (0-36); Western: Score (0-100%)
    ashtakoota: Optional[AshtakootaBreakdown] = None
    manglik: Optional[ManglikAnalysis] = None
    synastry_aspects: Optional[list[SynastryAspect]] = None
    calculation_hash: str
```

---

## 5. Core Skill 4: Planetary Transit Interpretation

### 5.1 Description
Computes the current or future positions of slow-moving planets (Saturn, Jupiter, Rahu/Ketu, Uranus, Neptune, Pluto) relative to natal chart houses and planetary coordinates.

### 5.2 Key Vedic Transits
- **Sade Sati:** Saturn's 7.5-year transit through the 12th, 1st, and 2nd houses from the natal Moon sign.
- **Guru Gochara:** Jupiter's transit through beneficial houses from natal Moon (2nd, 5th, 7th, 9th, 11th).
- **Ketu/Rahu Axis:** 18-month nodal transit through natal houses.

### 5.3 Key Western Transits
- Major outer planet transits (Pluto, Neptune, Uranus, Saturn, Jupiter) forming exact conjunctions, squares, oppositions, or trines to natal inner planets (Sun, Moon, Mercury, Venus, Mars, Ascendant, MC).

### 5.4 Transit Contracts
```python
class TransitInput(BaseModel):
    natal_chart: NatalChartInput
    query_date: date = Field(default_factory=date.today)
    specific_planet: Optional[str] = None # e.g., "Saturn" for Sade Sati query
    system: AstrologySystem = Field(default=AstrologySystem.VEDIC)

class ActiveTransit(BaseModel):
    transiting_planet: str
    transit_sign: str
    house_transited: Optional[int]
    aspect_to_natal_planet: Optional[str]
    orb: Optional[float]
    significance_level: Literal["major", "moderate", "subtle"]

class TransitOutput(BaseModel):
    system: AstrologySystem
    query_date: date
    is_sade_sati_active: Optional[bool] = None
    sade_sati_phase: Optional[str] = None # e.g., 'Rising (1st phase)', 'Peak (2nd)', 'Setting (3rd)'
    active_transits: list[ActiveTransit]
    calculation_hash: str
```

---

## 6. Astronomical Test Suite & Tolerance Benchmarks

All calculation modules must pass automated unit tests against established astronomical benchmarks:

```python
# Test Case 1: Standard Reference Epoch (J2000.0)
# Date: 2000-01-01 12:00:00 TT (Julian Day 2451545.0)
# Expected Tropical Positions (Swiss Ephemeris):
# Sun: 280.4606° (Capricorn 10° 27' 38")
# Moon: 219.0559° (Scorpio 9° 03' 21")

def test_j2000_ephemeris_tolerance():
    jd = 2451545.0
    sun_pos = calculate_planet_position(swe.SUN, jd, flags=swe.FLG_SWIEPH)
    assert abs(sun_pos.longitude - 280.4606) < 0.001

# Test Case 2: Vedic Lahiri Ayanamsa at J2000.0
# Expected Lahiri Ayanamsa: 23° 51' 25.53" (~23.85709°)
def test_lahiri_ayanamsa():
    jd = 2451545.0
    ayanamsa = calculate_ayanamsa(jd, swe.SE_SIDM_LAHIRI)
    assert abs(ayanamsa - 23.85709) < 0.001

# Test Case 3: Ashtakoota Guna Milan Benchmark
# Chart A: Moon in Rohini (Taurus) vs Chart B: Moon in Revati (Pisces)
# Verifies exact Guna scoring matching Brihat Parashara Hora Shastra rules.
```
