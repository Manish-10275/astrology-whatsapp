"""Navamsa (D9) divisional chart calculation engine.

Calculates the 9-fold division (Navamsa) of the natal chart according to classical
Brihat Parasara Hora Shastra principles (108 continuous Nakshatra-pada Navamsas).
"""

from typing import List, Optional
from astrology_engine.models import (
    D1Chart,
    NavamsaPlanet,
    NavamsaChart,
    ZODIAC_SIGNS,
)

NAVAMSA_SPAN = 40.0 / 3.0 / 4.0  # 3° 20' = 3.3333333333333335 degrees


def calculate_navamsa_planet(
    name: str,
    longitude: float,
) -> NavamsaPlanet:
    """Calculates D9 Navamsa sign and degree for a single celestial body."""
    norm_long = longitude % 360.0

    d1_sign_num = int(norm_long / 30.0) + 1
    d1_sign_name = ZODIAC_SIGNS[d1_sign_num - 1]["name"]

    # Each 3° 20' step from 0° Aries advances exactly 1 sign in the 108-Navamsa zodiac cycle
    navamsa_step = int(norm_long / NAVAMSA_SPAN)
    d9_sign_num = (navamsa_step % 12) + 1
    d9_sign_info = ZODIAC_SIGNS[d9_sign_num - 1]

    # Pada within the D1 sign (1 to 9)
    pada_in_sign = (int((norm_long % 30.0) / NAVAMSA_SPAN)) + 1

    # Degree within the Navamsa (0 to 30)
    deg_in_step = norm_long % NAVAMSA_SPAN
    deg_in_navamsa = deg_in_step * 9.0

    # Vargottama check: Same sign in both D1 and D9
    is_vargottama = (d1_sign_num == d9_sign_num)

    return NavamsaPlanet(
        name=name,
        d1_sign_number=d1_sign_num,
        d1_sign_name=d1_sign_name,
        d9_sign_number=d9_sign_num,
        d9_sign_name=d9_sign_info["name"],
        d9_sign_sanskrit=d9_sign_info["sanskrit"],
        d9_pada=pada_in_sign,
        degree_in_navamsa=round(deg_in_navamsa, 2),
        is_vargottama=is_vargottama,
    )


def calculate_navamsa_chart(natal_chart: D1Chart) -> NavamsaChart:
    """Calculates the complete Navamsa (D9) chart for all natal planets and ascendant.
    
    Args:
        natal_chart: The validated D1 natal chart.
    
    Returns:
        Structured NavamsaChart with Vargottama detections.
    """
    planets_d9: List[NavamsaPlanet] = []
    vargottama_names: List[str] = []

    for p in natal_chart.planets:
        np = calculate_navamsa_planet(p.name, p.longitude)
        planets_d9.append(np)
        if np.is_vargottama:
            vargottama_names.append(p.name)

    asc_d9: Optional[NavamsaPlanet] = None
    if natal_chart.ascendant:
        asc_d9 = calculate_navamsa_planet("Ascendant", natal_chart.ascendant.longitude)
        if asc_d9.is_vargottama:
            vargottama_names.append("Ascendant")

    return NavamsaChart(
        ascendant=asc_d9,
        planets=planets_d9,
        vargottama_planets=vargottama_names,
    )
