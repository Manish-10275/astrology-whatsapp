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
    time_uncertainty: TimeUncertainty
    calculation_hash: str = Field(..., description="Deterministic sha256 checksum of input coordinates and time")
