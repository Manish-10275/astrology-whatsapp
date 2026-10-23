"""Thread-safe Swiss Ephemeris adapter."""

import threading
from typing import Tuple, List, Optional
import swisseph as swe

from astrology_engine.config import DEFAULT_CONFIG
from astrology_engine.exceptions import EphemerisError, MissingEphemerisDataError

# Lock to ensure thread safety across concurrent calculations
_EPHEMERIS_LOCK = threading.Lock()

PLANET_IDS = {
    "Sun": swe.SUN,
    "Moon": swe.MOON,
    "Mercury": swe.MERCURY,
    "Venus": swe.VENUS,
    "Mars": swe.MARS,
    "Jupiter": swe.JUPITER,
    "Saturn": swe.SATURN,
    "Uranus": swe.URANUS,
    "Neptune": swe.NEPTUNE,
    "Pluto": swe.PLUTO,
    "Rahu": swe.MEAN_NODE,
    "TrueNode": swe.TRUE_NODE,
}

AYANAMSA_CODES = {
    "lahiri": swe.SIDM_LAHIRI,
    "kp": swe.SIDM_KRISHNAMURTI,
    "raman": swe.SIDM_RAMAN,
}

HOUSE_SYSTEM_CODES = {
    "placidus": b"P",
    "whole_sign": b"W",
    "equal": b"A",
}


class SwissEphemerisAdapter:
    """Encapsulates low-level calls to the Swiss Ephemeris C-extension."""

    def __init__(self, ephe_path: Optional[str] = None):
        self.ephe_path = ephe_path or DEFAULT_CONFIG.ephemeris_data_path
        self._init_path()

    def _init_path(self) -> None:
        with _EPHEMERIS_LOCK:
            try:
                swe.set_ephe_path(self.ephe_path)
            except Exception as e:
                raise EphemerisError(f"Failed to set ephemeris path '{self.ephe_path}': {e}") from e

    def get_julian_day(self, year: int, month: int, day: int, decimal_hour_utc: float) -> float:
        """Calculates Julian Day in Universal Time (UT1)."""
        with _EPHEMERIS_LOCK:
            try:
                return float(swe.julday(year, month, day, decimal_hour_utc, swe.GREG_CAL))
            except Exception as e:
                raise EphemerisError(f"Julian day computation failed for {year}-{month}-{day}: {e}") from e

    def get_delta_t(self, jd_ut: float) -> float:
        """Returns Delta T in seconds (Ephemeris Time - Universal Time)."""
        with _EPHEMERIS_LOCK:
            try:
                return float(swe.deltat(jd_ut)) * 86400.0  # swe.deltat returns days; convert to seconds
            except Exception as e:
                raise EphemerisError(f"Delta T computation failed for JD {jd_ut}: {e}") from e

    def set_sidereal_mode(self, ayanamsa: str) -> None:
        """Sets the sidereal mode / ayanamsa."""
        ayanamsa_lower = ayanamsa.lower()
        if ayanamsa_lower not in AYANAMSA_CODES:
            raise EphemerisError(f"Unsupported ayanamsa '{ayanamsa}'. Supported: {list(AYANAMSA_CODES.keys())}")
        code = AYANAMSA_CODES[ayanamsa_lower]
        with _EPHEMERIS_LOCK:
            try:
                swe.set_sid_mode(code)
            except Exception as e:
                raise EphemerisError(f"Failed to set sidereal mode {ayanamsa}: {e}") from e

    def get_ayanamsa_degrees(self, jd_ut: float) -> float:
        """Returns the ayanamsa value in degrees for a given Julian Day."""
        with _EPHEMERIS_LOCK:
            try:
                return float(swe.get_ayanamsa_ut(jd_ut))
            except Exception as e:
                raise EphemerisError(f"Failed to get ayanamsa for JD {jd_ut}: {e}") from e

    def calc_planet_ut(
        self,
        jd_ut: float,
        planet_name: str,
        is_sidereal: bool = False
    ) -> Tuple[float, float, float, float, bool]:
        """Calculates planetary position.
        
        Returns:
            (longitude, latitude, distance_au, speed_longitude, is_retrograde)
        """
        if planet_name not in PLANET_IDS:
            raise EphemerisError(f"Unknown planet '{planet_name}'. Supported: {list(PLANET_IDS.keys())}")

        planet_id = PLANET_IDS[planet_name]
        flags = swe.FLG_SWIEPH | swe.FLG_SPEED
        if is_sidereal:
            flags |= swe.FLG_SIDEREAL

        with _EPHEMERIS_LOCK:
            try:
                # swe.calc_ut returns (coords_tuple, return_flags, error_message)
                coords, return_flags, err = swe.calc_ut(jd_ut, planet_id, flags)
            except Exception as e:
                raise EphemerisError(f"Calculation failed for planet {planet_name} at JD {jd_ut}: {e}") from e

        # Check for calculation error
        if coords is None or len(coords) < 6:
            raise EphemerisError(f"Invalid coordinate return for planet {planet_name}: {err}")

        lon = float(coords[0]) % 360.0
        lat = float(coords[1])
        dist = float(coords[2])
        speed_lon = float(coords[3])
        is_retrograde = speed_lon < 0.0

        return lon, lat, dist, speed_lon, is_retrograde

    def calc_houses(
        self,
        jd_ut: float,
        lat: float,
        lon: float,
        house_system: str,
        is_sidereal: bool = False
    ) -> Tuple[List[float], float, float]:
        """Calculates house cusps, Ascendant, and Midheaven.
        
        Args:
            jd_ut: Julian Day in UT1
            lat: Latitude (-90 to 90)
            lon: Longitude (-180 to 180)
            house_system: 'placidus', 'whole_sign', or 'equal'
            is_sidereal: True to compute sidereal cusps and ascendant
            
        Returns:
            (cusps_1_to_12, ascendant_degree, mc_degree)
        """
        hsys_lower = house_system.lower()
        if hsys_lower not in HOUSE_SYSTEM_CODES:
            raise EphemerisError(f"Unsupported house system '{house_system}'. Supported: {list(HOUSE_SYSTEM_CODES.keys())}")

        hsys_code = HOUSE_SYSTEM_CODES[hsys_lower]
        flags = swe.FLG_SIDEREAL if is_sidereal else 0

        with _EPHEMERIS_LOCK:
            try:
                # swe.houses_ex returns (cusps_tuple, ascmc_tuple)
                cusps, ascmc = swe.houses_ex(jd_ut, lat, lon, hsys_code, flags)
            except Exception as e:
                raise EphemerisError(f"Failed to calculate houses for JD {jd_ut}, lat {lat}, lon {lon}: {e}") from e

        house_cusps = [float(cusps[i]) % 360.0 for i in range(1, 13)]
        ascendant = float(ascmc[0]) % 360.0
        midheaven = float(ascmc[1]) % 360.0

        return house_cusps, ascendant, midheaven

    def close(self) -> None:
        """Closes Swiss Ephemeris handles and releases resources."""
        with _EPHEMERIS_LOCK:
            try:
                swe.close()
            except Exception:
                pass


# Shared default singleton adapter
default_adapter = SwissEphemerisAdapter()
