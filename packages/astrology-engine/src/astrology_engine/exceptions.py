"""Custom domain exceptions for the Astrology Calculation Engine."""

class AstrologyEngineError(Exception):
    """Base exception for all astrology calculation engine errors."""
    pass


class EphemerisError(AstrologyEngineError):
    """Raised when an error occurs during Swiss Ephemeris C-level computation."""
    pass


class MissingEphemerisDataError(AstrologyEngineError):
    """Raised when required ephemeris data files (.se1) are missing from the configured path."""
    pass


class UnsupportedDateRangeError(AstrologyEngineError):
    """Raised when a date falls outside the supported ephemeris range (1800 to 2100 CE)."""
    pass


class InvalidCoordinatesError(AstrologyEngineError):
    """Raised when geographic coordinates are invalid (latitude must be -90..90, longitude -180..180)."""
    pass


class TimezoneResolutionError(AstrologyEngineError):
    """Raised when timezone lookup fails or an invalid timezone identifier is provided."""
    pass


class TimeUncertaintyError(AstrologyEngineError):
    """Raised when an operation requiring exact birth time is attempted with an unknown birth time."""
    pass
