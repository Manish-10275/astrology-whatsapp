"""Western astrology interpretation, planetary aspects, and elemental weighting engine."""

from typing import List, Tuple, Dict
from collections import Counter
from astrology_engine.models import (
    D1Chart,
    PlanetPosition,
    WesternAspect,
    WesternChartAnalysis,
    ZODIAC_SIGNS,
)

ASPECT_DEFINITIONS = [
    ("Conjunction", 0.0, 8.0, True, "Fusion of planetary energies, intensifies both drives."),
    ("Sextile", 60.0, 6.0, True, "Harmonious flow of opportunity, cooperation, and talent."),
    ("Square", 90.0, 8.0, False, "Dynamic friction and tension driving personal growth and action."),
    ("Trine", 120.0, 8.0, True, "Effortless creative synergy, innate grace, and mutual support."),
    ("Opposition", 180.0, 8.0, False, "Polarity and relational tension requiring balance and awareness."),
]

ELEMENT_SIGNS = {
    "Fire": {1, 5, 9},
    "Earth": {2, 6, 10},
    "Air": {3, 7, 11},
    "Water": {4, 8, 12},
}

MODALITY_SIGNS = {
    "Cardinal": {1, 4, 7, 10},
    "Fixed": {2, 5, 8, 11},
    "Mutable": {3, 6, 9, 12},
}


def calculate_western_aspects(planets: List[PlanetPosition]) -> List[WesternAspect]:
    """Calculates all major Ptolemaic aspects among tropical planets within standard orbs."""
    aspects: List[WesternAspect] = []
    n = len(planets)

    for i in range(n):
        for j in range(i + 1, n):
            p1 = planets[i]
            p2 = planets[j]

            # Angular separation [0, 180]
            diff = abs(p1.longitude - p2.longitude)
            if diff > 180.0:
                diff = 360.0 - diff

            for aspect_name, target_angle, max_orb, is_harm, interp in ASPECT_DEFINITIONS:
                orb = abs(diff - target_angle)
                if orb <= max_orb:
                    aspects.append(
                        WesternAspect(
                            planet1=p1.name,
                            planet2=p2.name,
                            aspect_type=aspect_name,
                            angle_degrees=round(diff, 2),
                            orb_degrees=round(orb, 2),
                            is_harmonious=is_harm,
                            interpretation=f"{p1.name} in {aspect_name} with {p2.name} (orb {orb:.1f}°): {interp}",
                        )
                    )
                    break

    return aspects


def analyze_western_chart(d1_chart: D1Chart) -> WesternChartAnalysis:
    """Analyzes a Western chart: aspects, elemental weighting, and modality dominance."""
    aspects = calculate_western_aspects(d1_chart.planets)

    # Element and Modality counts
    element_counts: Dict[str, int] = Counter()
    modality_counts: Dict[str, int] = Counter()

    for p in d1_chart.planets:
        s_num = p.sign_number
        for elem, sign_set in ELEMENT_SIGNS.items():
            if s_num in sign_set:
                element_counts[elem] += 1
        for mod, sign_set in MODALITY_SIGNS.items():
            if s_num in sign_set:
                modality_counts[mod] += 1

    dom_element = element_counts.most_common(1)[0][0] if element_counts else "Unknown"
    dom_modality = modality_counts.most_common(1)[0][0] if modality_counts else "Unknown"

    return WesternChartAnalysis(
        planets=d1_chart.planets,
        houses=d1_chart.houses,
        ascendant=d1_chart.ascendant,
        midheaven=d1_chart.midheaven,
        aspects=aspects,
        dominant_element=dom_element,
        dominant_modality=dom_modality,
    )
