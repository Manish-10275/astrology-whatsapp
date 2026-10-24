"""Typed request and response models for the Astrology Calculation Engine."""

from datetime import date, time, datetime
from enum import Enum
from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator, model_validator


class AstrologySystem(str, Enum):
    VEDIC = "vedic"
    WESTERN = "western"


class AyanamsaType(str, Enum):
    LAHIRI = "lahiri"
    KRISHNAMURTI = "kp"
    RAMAN = "raman"


class HouseSystemType(str, Enum):
    PLACIDUS = "placidus"
    WHOLE_SIGN = "whole_sign"
    EQUAL = "equal"


class TimeUncertainty(str, Enum):
    EXACT = "exact"
    APPROXIMATE_WINDOW = "approximate_window"
    UNKNOWN = "unknown"


ZODIAC_SIGNS = [
    {"number": 1, "name": "Aries", "sanskrit": "Mesha", "element": "Fire", "ruler": "Mars"},
    {"number": 2, "name": "Taurus", "sanskrit": "Vrishabha", "element": "Earth", "ruler": "Venus"},
    {"number": 3, "name": "Gemini", "sanskrit": "Mithuna", "element": "Air", "ruler": "Mercury"},
    {"number": 4, "name": "Cancer", "sanskrit": "Karka", "element": "Water", "ruler": "Moon"},
    {"number": 5, "name": "Leo", "sanskrit": "Simha", "element": "Fire", "ruler": "Sun"},
    {"number": 6, "name": "Virgo", "sanskrit": "Kanya", "element": "Earth", "ruler": "Mercury"},
    {"number": 7, "name": "Libra", "sanskrit": "Tula", "element": "Air", "ruler": "Venus"},
    {"number": 8, "name": "Scorpio", "sanskrit": "Vrischika", "element": "Water", "ruler": "Mars"},
    {"number": 9, "name": "Sagittarius", "sanskrit": "Dhanu", "element": "Fire", "ruler": "Jupiter"},
    {"number": 10, "name": "Capricorn", "sanskrit": "Makara", "element": "Earth", "ruler": "Saturn"},
    {"number": 11, "name": "Aquarius", "sanskrit": "Kumbha", "element": "Air", "ruler": "Saturn"},
    {"number": 12, "name": "Pisces", "sanskrit": "Meena", "element": "Water", "ruler": "Jupiter"},
]

NAKSHATRAS = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni",
    "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha",
    "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishta", "Shatabhisha",
    "Purva Bhadrapada", "Uttara Bhadrapada", "Revati"
]

NAKSHATRA_LORDS = [
    "Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu",
    "Jupiter", "Saturn", "Mercury"
] * 3  # Repeats 3 times for 27 nakshatras


class JulianDayInfo(BaseModel):
    jd_ut: float = Field(..., description="Julian Day in Universal Time (UT1)")
    jd_et: float = Field(..., description="Julian Day in Ephemeris Time (ET/TDB)")
    delta_t: float = Field(..., description="Delta T correction in seconds (ET - UT)")
    utc_datetime: datetime = Field(..., description="Normalized UTC datetime")


class NakshatraInfo(BaseModel):
    name: str = Field(..., description="Nakshatra name (e.g., 'Rohini')")
    number: int = Field(..., ge=1, le=27, description="Nakshatra index (1 to 27)")
    ruler: str = Field(..., description="Vimshottari planetary ruler")
    pada: int = Field(..., ge=1, le=4, description="Pada quarter (1 to 4)")
    degrees_into_nakshatra: float = Field(..., ge=0.0, le=13.3334)


class PlanetPosition(BaseModel):
    name: str = Field(..., description="Planet name (e.g., 'Sun', 'Moon', 'Mars')")
    longitude: float = Field(..., ge=0.0, lt=360.0, description="Ecliptic longitude in degrees [0, 360)")
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Ecliptic latitude in degrees [-90, 90]")
    distance_au: float = Field(..., description="Distance from Earth in Astronomical Units")
    speed_longitude: float = Field(..., description="Daily speed in longitude (degrees/day)")
    is_retrograde: bool = Field(..., description="True if planetary speed is negative")
    sign_number: int = Field(..., ge=1, le=12, description="Zodiac sign number (1=Aries .. 12=Pisces)")
    sign_name: str = Field(..., description="Western sign name")
    sign_sanskrit: Optional[str] = Field(None, description="Vedic Sanskrit sign name")
    degree_in_sign: float = Field(..., ge=0.0, lt=30.0, description="Degree within the current sign [0, 30)")
    house: Optional[int] = Field(None, ge=1, le=12, description="House number (1 to 12) if birth time is known")
    nakshatra: Optional[NakshatraInfo] = Field(None, description="Nakshatra details (Vedic only)")
    ephemeris_mode: str = Field(default="moshier", description="'swiss' if using .se1 files, 'moshier' if using built-in Moshier analytical ephemeris")


class HouseCusp(BaseModel):
    house_number: int = Field(..., ge=1, le=12, description="House number (1 to 12)")
    cusp_longitude: float = Field(..., ge=0.0, lt=360.0, description="Ecliptic longitude of house cusp")
    sign_number: int = Field(..., ge=1, le=12)
    sign_name: str
    sign_sanskrit: Optional[str] = None
    degree_in_sign: float = Field(..., ge=0.0, lt=30.0)


class AscendantInfo(BaseModel):
    longitude: float = Field(..., ge=0.0, lt=360.0, description="Ascendant / Lagna longitude")
    sign_number: int = Field(..., ge=1, le=12)
    sign_name: str
    sign_sanskrit: Optional[str] = None
    degree_in_sign: float = Field(..., ge=0.0, lt=30.0)
    nakshatra: Optional[NakshatraInfo] = None


class MidheavenInfo(BaseModel):
    longitude: float = Field(..., ge=0.0, lt=360.0, description="Midheaven (Medium Coeli / MC) longitude")
    sign_number: int = Field(..., ge=1, le=12)
    sign_name: str
    sign_sanskrit: Optional[str] = None
    degree_in_sign: float = Field(..., ge=0.0, lt=30.0)


class ChartRequest(BaseModel):
    birth_date: date = Field(..., description="Date of birth (YYYY-MM-DD)")
    birth_time: Optional[time] = Field(None, description="Local birth time (HH:MM:SS)")
    time_uncertainty: TimeUncertainty = Field(default=TimeUncertainty.EXACT)
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Latitude in decimal degrees")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Longitude in decimal degrees")
    elevation_meters: float = Field(default=0.0, ge=-500.0, le=9000.0)
    timezone_name: str = Field(..., description="IANA timezone identifier (e.g. 'Asia/Kolkata') or 'LMT' for Local Mean Time")
    timezone_offset_seconds: Optional[int] = Field(None, description="Optional explicit UTC offset in seconds override")
    fold: int = Field(default=0, ge=0, le=1, description="Disambiguates duplicate local times during daylight saving fall-back (0 for first occurrence, 1 for second)")
    system: AstrologySystem = Field(default=AstrologySystem.VEDIC)
    ayanamsa: AyanamsaType = Field(default=AyanamsaType.LAHIRI)
    house_system: HouseSystemType = Field(default=HouseSystemType.WHOLE_SIGN)

    @field_validator("birth_date")
    def validate_historical_date_range(cls, v: date) -> date:
        if v.year < 1800 or v.year > 2100:
            raise ValueError(f"Birth year {v.year} is outside supported range (1800 to 2100 CE).")
        return v

    @model_validator(mode="after")
    def validate_time_uncertainty(self):
        if self.birth_time is None and self.time_uncertainty == TimeUncertainty.EXACT:
            self.time_uncertainty = TimeUncertainty.UNKNOWN
        return self


class D1Chart(BaseModel):
    system: AstrologySystem
    ayanamsa_used: Optional[str] = None
    ayanamsa_degrees: Optional[float] = None
    house_system_used: HouseSystemType
    julian_day: JulianDayInfo
    ascendant: Optional[AscendantInfo] = None
    midheaven: Optional[MidheavenInfo] = None
    houses: list[HouseCusp] = Field(default_factory=list)
    planets: list[PlanetPosition] = Field(default_factory=list)
    houses_map: dict[int, list[str]] = Field(default_factory=dict, description="Map of house number -> list of planet names")
    ephemeris_mode: str = Field(default="moshier", description="'swiss' if using .se1 files, 'moshier' if using built-in Moshier analytical ephemeris")
    time_uncertainty: TimeUncertainty
    calculation_hash: str = Field(..., description="Deterministic sha256 checksum of input coordinates and time")


# ============================================================================
# Vimshottari Dasha Models
# ============================================================================

class AntardashaPeriod(BaseModel):
    ruler: str = Field(..., description="Antardasha planetary ruler")
    start_date: date = Field(..., description="Start date of Antardasha")
    end_date: date = Field(..., description="End date of Antardasha")
    duration_days: float = Field(..., description="Duration in days")


class MahadashaPeriod(BaseModel):
    ruler: str = Field(..., description="Mahadasha planetary ruler")
    start_date: date = Field(..., description="Start date of Mahadasha")
    end_date: date = Field(..., description="End date of Mahadasha")
    duration_years: float = Field(..., description="Duration in years")
    antardashas: list[AntardashaPeriod] = Field(default_factory=list)


class VimshottariDashaResult(BaseModel):
    birth_date: date
    moon_longitude: float
    nakshatra_name: str
    nakshatra_pada: int
    first_dasha_balance_years: float = Field(..., description="Remaining years of first Mahadasha at birth")
    mahadashas: list[MahadashaPeriod] = Field(default_factory=list)
    current_mahadasha: Optional[str] = None
    current_antardasha: Optional[str] = None


# ============================================================================
# Panchang Models
# ============================================================================

class TithiInfo(BaseModel):
    number: int = Field(..., ge=1, le=30, description="Tithi number (1 to 30)")
    name: str = Field(..., description="Tithi name (e.g. Pratipada, Ekadashi, Purnima)")
    paksha: Literal["Shukla", "Krishna"] = Field(..., description="Waxing (Shukla) or Waning (Krishna)")
    completed_percentage: float = Field(..., ge=0.0, le=100.0)


class YogaInfo(BaseModel):
    number: int = Field(..., ge=1, le=27, description="Yoga index (1 to 27)")
    name: str = Field(..., description="Yoga name (e.g. Vishkambha, Siddhi)")
    completed_percentage: float = Field(..., ge=0.0, le=100.0)


class KaranaInfo(BaseModel):
    number: int = Field(..., ge=1, le=60, description="Karana half-tithi index (1 to 60)")
    name: str = Field(..., description="Karana name (e.g. Bava, Balava, Vishti/Bhadra)")
    is_vishti: bool = Field(default=False, description="True if inauspicious Vishti/Bhadra Karana")


class PanchangResult(BaseModel):
    date: date
    vara: str = Field(..., description="Day of week (Ravivara, Somavara, etc.)")
    vara_lord: str = Field(..., description="Planetary lord of the day")
    tithi: TithiInfo
    nakshatra: NakshatraInfo
    yoga: YogaInfo
    karana: KaranaInfo
    sunrise_iso: Optional[str] = None
    sunset_iso: Optional[str] = None


# ============================================================================
# Ashtakoota Compatibility Models
# ============================================================================

class KootaScore(BaseModel):
    name: str = Field(..., description="Name of Koota (e.g., Nadi, Bhakoot)")
    obtained_points: float = Field(..., ge=0.0, le=8.0)
    max_points: float = Field(..., ge=1.0, le=8.0)
    description: str
    status: Literal["Excellent", "Good", "Average", "Inauspicious"] = "Good"


class AshtakootaResult(BaseModel):
    total_score: float = Field(..., ge=0.0, le=36.0, description="Total score out of 36 gunas")
    max_score: float = 36.0
    percentage: float = Field(..., ge=0.0, le=100.0)
    verdict: Literal["Highly Auspicious", "Auspicious", "Acceptable", "Inauspicious"]
    kootas: list[KootaScore]
    nadi_dosha: bool = False
    nadi_dosha_cancelled: bool = False
    bhakoot_dosha: bool = False
    bhakoot_dosha_cancelled: bool = False
    dosha_exceptions: list[str] = Field(default_factory=list)
    groom_moon_sign: str
    groom_nakshatra: str
    bride_moon_sign: str
    bride_nakshatra: str


# ============================================================================
# Transits (Gochara) Models
# ============================================================================

class TransitPlanet(BaseModel):
    name: str
    sign_number: int
    sign_name: str
    sign_sanskrit: Optional[str] = None
    degree_in_sign: float
    house_from_moon: int = Field(..., ge=1, le=12)
    house_from_ascendant: Optional[int] = Field(None, ge=1, le=12)
    is_retrograde: bool
    is_auspicious: bool = True
    key_effects: str


class TransitAnalysisResult(BaseModel):
    transit_date: date
    planets: list[TransitPlanet]
    sade_sati_active: bool = False
    sade_sati_phase: Optional[Literal["Rising", "Peak", "Setting"]] = None
    jupiter_transit_favorable: bool = False
    summary: str


# ============================================================================
# Navamsa (D9) Models
# ============================================================================

class NavamsaPlanet(BaseModel):
    name: str
    d1_sign_number: int
    d1_sign_name: str
    d9_sign_number: int
    d9_sign_name: str
    d9_sign_sanskrit: Optional[str] = None
    d9_pada: int
    degree_in_navamsa: float
    is_vargottama: bool = False


class NavamsaChart(BaseModel):
    ascendant: Optional[NavamsaPlanet] = None
    planets: list[NavamsaPlanet]
    vargottama_planets: list[str] = Field(default_factory=list)


# ============================================================================
# Western Astrology Aspect Models
# ============================================================================

class WesternAspect(BaseModel):
    planet1: str
    planet2: str
    aspect_type: Literal["Conjunction", "Sextile", "Square", "Trine", "Opposition"]
    angle_degrees: float
    orb_degrees: float
    is_harmonious: bool
    interpretation: str


class WesternChartAnalysis(BaseModel):
    planets: list[PlanetPosition]
    houses: list[HouseCusp]
    ascendant: Optional[AscendantInfo] = None
    midheaven: Optional[MidheavenInfo] = None
    aspects: list[WesternAspect]
    dominant_element: str
    dominant_modality: str

