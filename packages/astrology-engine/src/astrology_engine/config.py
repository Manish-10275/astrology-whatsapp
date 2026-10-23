"""Configuration settings for the Astrology Calculation Engine."""

import os
from pathlib import Path
from dataclasses import dataclass, field

@dataclass(frozen=True)
class EngineConfig:
    """Immutable engine configuration."""
    # Path to external Swiss Ephemeris data files (.se1)
    ephemeris_data_path: str = field(
        default_factory=lambda: os.getenv(
            "EPHEMERIS_DATA_PATH",
            str(Path(__file__).resolve().parent.parent.parent / "ephem_data")
        )
    )
    # Default ayanamsa for Vedic calculations (default Lahiri / Chitrapaksha)
    default_ayanamsa: str = "lahiri"
    # Default house system for Western calculations (default Placidus)
    default_western_house_system: str = "placidus"
    # Default house system for Vedic calculations (default Whole Sign)
    default_vedic_house_system: str = "whole_sign"
    # Supported date boundaries (CE)
    min_year: int = 1800
    max_year: int = 2100

DEFAULT_CONFIG = EngineConfig()
