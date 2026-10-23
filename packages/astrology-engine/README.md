# Astrology Calculation Engine (`packages/astrology-engine`)

A deterministic astronomical and astrological calculation engine designed for high-accuracy Vedic and Western chart calculations.

## Capabilities

- **Julian Day & Ephemeris Time:** High-precision Julian Day conversion with $\Delta T$ ephemeris corrections.
- **Tropical Planetary Calculations:** Calculates Sun, Moon, Mercury, Venus, Mars, Jupiter, Saturn, Uranus, Neptune, Pluto, and Lunar Nodes (Mean & True) with ecliptic longitude, latitude, distance, speed, and retrograde status.
- **Sidereal Planetary Calculations:** Native support for Lahiri (Chitrapaksha) ayanamsa, with configurable Raman and Krishnamurti (KP) ayanamsas. Computes the 27 Nakshatras and 4 Padas.
- **Ascendant & Houses:** Accurate Ascendant (Lagna), Midheaven (MC), and house cusps using **Placidus** and **Whole Sign** systems.
- **Structured D1 Chart:** Generates comprehensive D1 chart representations with zodiac signs, house placements, and planetary dignities.
- **Timezone & Geocoding:** Deterministic IANA timezone lookup via `timezonefinder` and `zoneinfo`.

## Quickstart

```python
from datetime import date, time
from astrology_engine import (
    ChartRequest,
    AstrologySystem,
    HouseSystemType,
    calculate_d1_chart
)

request = ChartRequest(
    birth_date=date(1992, 8, 15),
    birth_time=time(14, 30),
    latitude=18.9388,
    longitude=72.8354,
    timezone_name="Asia/Kolkata",
    system=AstrologySystem.VEDIC,
    house_system=HouseSystemType.WHOLE_SIGN
)

chart = calculate_d1_chart(request)
print(f"Ascendant Sign: {chart.ascendant.sign.name} at {chart.ascendant.degree_in_sign:.2f}°")
for planet in chart.planets:
    print(f"{planet.name}: {planet.sign.name} {planet.degree_in_sign:.2f}° (House {planet.house})")
```
