"""Astrology Calculation Engine.

A deterministic astronomical and astrological calculation package for Vedic and Western astrology.
"""

from astrology_engine.models import (
    AstrologySystem,
    AyanamsaType,
    HouseSystemType,
    TimeUncertainty,
    ChartRequest,
    D1Chart,
    PlanetPosition,
    HouseCusp,
    AscendantInfo,
    MidheavenInfo,
    NakshatraInfo,
    JulianDayInfo,
    ZODIAC_SIGNS,
    NAKSHATRAS,
    NAKSHATRA_LORDS,
    AntardashaPeriod,
    MahadashaPeriod,
    VimshottariDashaResult,
    TithiInfo,
    YogaInfo,
    KaranaInfo,
    PanchangResult,
    KootaScore,
    AshtakootaResult,
    TransitPlanet,
    TransitAnalysisResult,
    NavamsaPlanet,
    NavamsaChart,
    WesternAspect,
    WesternChartAnalysis,
)
from astrology_engine.chart import calculate_d1_chart, generate_calculation_hash
from astrology_engine.dasha import calculate_vimshottari_dasha
from astrology_engine.panchang import calculate_panchang
from astrology_engine.compatibility import calculate_ashtakoota
from astrology_engine.transits import calculate_transits
from astrology_engine.navamsa import calculate_navamsa_chart, calculate_navamsa_planet
from astrology_engine.western import calculate_western_aspects, analyze_western_chart
from astrology_engine.time_utils import (
    compute_utc_datetime,
    compute_julian_day,
    resolve_timezone,
    validate_coordinates,
    validate_date_range,
)
from astrology_engine.tropical import (
    calculate_tropical_planet,
    calculate_tropical_planets,
    longitude_to_sign,
)
from astrology_engine.sidereal import (
    calculate_sidereal_planet,
    calculate_sidereal_planets,
    calculate_nakshatra,
)
from astrology_engine.houses import (
    calculate_house_system_data,
    assign_houses_to_planets,
    get_house_for_longitude_cusps,
    get_house_for_whole_sign,
)
from astrology_engine.adapter import (
    SwissEphemerisAdapter,
    default_adapter,
)
from astrology_engine.exceptions import (
    AstrologyEngineError,
    EphemerisError,
    MissingEphemerisDataError,
    UnsupportedDateRangeError,
    InvalidCoordinatesError,
    TimezoneResolutionError,
    TimeUncertaintyError,
)

__version__ = "0.1.0"

__all__ = [
    # Enums & Models
    "AstrologySystem",
    "AyanamsaType",
    "HouseSystemType",
    "TimeUncertainty",
    "ChartRequest",
    "D1Chart",
    "PlanetPosition",
    "HouseCusp",
    "AscendantInfo",
    "MidheavenInfo",
    "NakshatraInfo",
    "JulianDayInfo",
    "ZODIAC_SIGNS",
    "NAKSHATRAS",
    "NAKSHATRA_LORDS",
    "AntardashaPeriod",
    "MahadashaPeriod",
    "VimshottariDashaResult",
    "TithiInfo",
    "YogaInfo",
    "KaranaInfo",
    "PanchangResult",
    "KootaScore",
    "AshtakootaResult",
    "TransitPlanet",
    "TransitAnalysisResult",
    "NavamsaPlanet",
    "NavamsaChart",
    "WesternAspect",
    "WesternChartAnalysis",
    # Chart API
    "calculate_d1_chart",
    "generate_calculation_hash",
    "calculate_vimshottari_dasha",
    "calculate_panchang",
    "calculate_ashtakoota",
    "calculate_transits",
    "calculate_navamsa_chart",
    "calculate_navamsa_planet",
    "calculate_western_aspects",
    "analyze_western_chart",
    # Astronomical & Geocoding Utilities
    "compute_utc_datetime",
    "compute_julian_day",
    "resolve_timezone",
    "validate_coordinates",
    "validate_date_range",
    # Tropical & Sidereal Calculators
    "calculate_tropical_planet",
    "calculate_tropical_planets",
    "calculate_sidereal_planet",
    "calculate_sidereal_planets",
    "calculate_nakshatra",
    "longitude_to_sign",
    # House Calculators
    "calculate_house_system_data",
    "assign_houses_to_planets",
    "get_house_for_longitude_cusps",
    "get_house_for_whole_sign",
    # Adapter
    "SwissEphemerisAdapter",
    "default_adapter",
    # Exceptions
    "AstrologyEngineError",
    "EphemerisError",
    "MissingEphemerisDataError",
    "UnsupportedDateRangeError",
    "InvalidCoordinatesError",
    "TimezoneResolutionError",
    "TimeUncertaintyError",
]
