"""Ashtakoota (36-Guna) Vedic Marriage Compatibility Engine.

Calculates the 8 Kootas (Varna, Vashya, Tara, Yoni, Graha Maitri, Gana, Bhakoot, Nadi)
based on both individuals' verified Moon Nakshatras and Rashis.
"""

from typing import Tuple, List, Dict
from astrology_engine.models import (
    KootaScore,
    AshtakootaResult,
    ZODIAC_SIGNS,
    NAKSHATRAS,
)

# 1. Varna mapping (1 to 12) -> (Brahmin=4, Kshatriya=3, Vaishya=2, Shudra=1)
SIGN_VARNA = {
    4: 4, 8: 4, 12: 4,   # Cancer, Scorpio, Pisces -> Brahmin
    1: 3, 5: 3, 9: 3,    # Aries, Leo, Sagittarius -> Kshatriya
    2: 2, 6: 2, 10: 2,   # Taurus, Virgo, Capricorn -> Vaishya
    3: 1, 7: 1, 11: 1,   # Gemini, Libra, Aquarius -> Shudra
}

# 2. Vashya category by sign
SIGN_VASHYA = {
    1: "Chatushpada", 2: "Chatushpada", 3: "Manava", 4: "Jalachara",
    5: "Vanachara", 6: "Manava", 7: "Manava", 8: "Keeta",
    9: "Manava", 10: "Chatushpada", 11: "Manava", 12: "Jalachara",
}

# 3. Yoni animal mapping for each of the 27 Nakshatras (1-based index)
NAKSHATRA_YONI = {
    1: "Horse", 2: "Elephant", 3: "Sheep", 4: "Serpent", 5: "Serpent", 6: "Dog",
    7: "Cat", 8: "Sheep", 9: "Cat", 10: "Rat", 11: "Rat", 12: "Cow",
    13: "Buffalo", 14: "Tiger", 15: "Buffalo", 16: "Tiger", 17: "Deer", 18: "Deer",
    19: "Dog", 20: "Monkey", 21: "Mongoose", 22: "Monkey", 23: "Lion", 24: "Horse",
    25: "Lion", 26: "Cow", 27: "Elephant",
}

YONI_ENEMY_PAIRS = {
    ("Horse", "Buffalo"), ("Buffalo", "Horse"),
    ("Elephant", "Lion"), ("Lion", "Elephant"),
    ("Sheep", "Monkey"), ("Monkey", "Sheep"),
    ("Serpent", "Mongoose"), ("Mongoose", "Serpent"),
    ("Dog", "Deer"), ("Deer", "Dog"),
    ("Cat", "Rat"), ("Rat", "Cat"),
    ("Cow", "Tiger"), ("Tiger", "Cow"),
}

# 4. Planetary friendships for Graha Maitri
SIGN_LORDS = {
    1: "Mars", 2: "Venus", 3: "Mercury", 4: "Moon",
    5: "Sun", 6: "Mercury", 7: "Venus", 8: "Mars",
    9: "Jupiter", 10: "Saturn", 11: "Saturn", 12: "Jupiter"
}

PLANET_FRIENDS = {
    "Sun": {"friends": {"Moon", "Mars", "Jupiter"}, "neutrals": {"Mercury"}, "enemies": {"Venus", "Saturn"}},
    "Moon": {"friends": {"Sun", "Mercury"}, "neutrals": {"Mars", "Jupiter", "Venus", "Saturn"}, "enemies": set()},
    "Mars": {"friends": {"Sun", "Moon", "Jupiter"}, "neutrals": {"Venus", "Saturn"}, "enemies": {"Mercury"}},
    "Mercury": {"friends": {"Sun", "Venus"}, "neutrals": {"Mars", "Jupiter", "Saturn"}, "enemies": {"Moon"}},
    "Jupiter": {"friends": {"Sun", "Moon", "Mars"}, "neutrals": {"Saturn"}, "enemies": {"Mercury", "Venus"}},
    "Venus": {"friends": {"Mercury", "Saturn"}, "neutrals": {"Mars", "Jupiter"}, "enemies": {"Sun", "Moon"}},
    "Saturn": {"friends": {"Mercury", "Venus"}, "neutrals": {"Jupiter"}, "enemies": {"Sun", "Moon", "Mars"}},
}

# 5. Gana category by Nakshatra index (1 to 27)
NAKSHATRA_GANA = {
    1: "Deva", 2: "Manushya", 3: "Rakshasa", 4: "Manushya", 5: "Deva", 6: "Manushya",
    7: "Deva", 8: "Deva", 9: "Rakshasa", 10: "Rakshasa", 11: "Manushya", 12: "Manushya",
    13: "Deva", 14: "Rakshasa", 15: "Deva", 16: "Rakshasa", 17: "Deva", 18: "Rakshasa",
    19: "Rakshasa", 20: "Manushya", 21: "Manushya", 22: "Deva", 23: "Rakshasa", 24: "Rakshasa",
    25: "Manushya", 26: "Manushya", 27: "Deva",
}

# 6. Nadi category by Nakshatra index (1 to 27)
NAKSHATRA_NADI = {
    1: "Adi", 2: "Madhya", 3: "Antya",
    4: "Antya", 5: "Madhya", 6: "Adi",
    7: "Adi", 8: "Madhya", 9: "Antya",
    10: "Antya", 11: "Madhya", 12: "Adi",
    13: "Adi", 14: "Madhya", 15: "Antya",
    16: "Antya", 17: "Madhya", 18: "Adi",
    19: "Adi", 20: "Madhya", 21: "Antya",
    22: "Antya", 23: "Madhya", 24: "Adi",
    25: "Adi", 26: "Madhya", 27: "Antya",
}


def calculate_ashtakoota(
    groom_moon_longitude: float,
    bride_moon_longitude: float,
) -> AshtakootaResult:
    """Calculates full 36-guna Ashtakoota matching between Groom and Bride.
    
    Args:
        groom_moon_longitude: Sidereal Moon longitude of groom [0, 360).
        bride_moon_longitude: Sidereal Moon longitude of bride [0, 360).
    
    Returns:
        Structured AshtakootaResult containing individual koota scores, doshas, and verdict.
    """
    g_long = groom_moon_longitude % 360.0
    b_long = bride_moon_longitude % 360.0

    span = 40.0 / 3.0
    g_nak = int(g_long / span) + 1
    b_nak = int(b_long / span) + 1

    g_sign = int(g_long / 30.0) + 1
    b_sign = int(b_long / 30.0) + 1

    g_pada = int((g_long % span) / (span / 4.0)) + 1
    b_pada = int((b_long % span) / (span / 4.0)) + 1

    kootas: List[KootaScore] = []
    dosha_exceptions: List[str] = []

    # 1. Varna (Max: 1)
    g_varna = SIGN_VARNA[g_sign]
    b_varna = SIGN_VARNA[b_sign]
    varna_pts = 1.0 if g_varna >= b_varna else 0.0
    kootas.append(
        KootaScore(
            name="Varna",
            obtained_points=varna_pts,
            max_points=1.0,
            description="Work, spiritual ego, and social compatibility.",
            status="Excellent" if varna_pts == 1.0 else "Average",
        )
    )

    # 2. Vashya (Max: 2)
    g_vashya = SIGN_VASHYA[g_sign]
    b_vashya = SIGN_VASHYA[b_sign]
    if g_vashya == b_vashya:
        vashya_pts = 2.0
    elif (g_vashya, b_vashya) in [("Manava", "Jalachara"), ("Manava", "Chatushpada"), ("Chatushpada", "Jalachara")]:
        vashya_pts = 1.0
    elif g_vashya == "Vanachara" or b_vashya == "Vanachara":
        vashya_pts = 0.0
    else:
        vashya_pts = 0.5
    kootas.append(
        KootaScore(
            name="Vashya",
            obtained_points=vashya_pts,
            max_points=2.0,
            description="Mutual magnetic attraction and dominance harmony.",
            status="Excellent" if vashya_pts == 2.0 else "Good" if vashya_pts >= 1.0 else "Average",
        )
    )

    # 3. Tara (Max: 3)
    c_b_to_g = ((g_nak - b_nak) % 27) + 1
    c_g_to_b = ((b_nak - g_nak) % 27) + 1
    t1 = c_b_to_g % 9
    t2 = c_g_to_b % 9
    inauspicious = {3, 5, 7}
    g_ok = t1 not in inauspicious
    b_ok = t2 not in inauspicious
    if g_ok and b_ok:
        tara_pts = 3.0
    elif g_ok or b_ok:
        tara_pts = 1.5
    else:
        tara_pts = 0.0
    kootas.append(
        KootaScore(
            name="Tara",
            obtained_points=tara_pts,
            max_points=3.0,
            description="Destiny, well-being, and longevity harmony.",
            status="Excellent" if tara_pts == 3.0 else "Average" if tara_pts == 1.5 else "Inauspicious",
        )
    )

    # 4. Yoni (Max: 4)
    g_yoni = NAKSHATRA_YONI[g_nak]
    b_yoni = NAKSHATRA_YONI[b_nak]
    if g_yoni == b_yoni:
        yoni_pts = 4.0
    elif (g_yoni, b_yoni) in YONI_ENEMY_PAIRS:
        yoni_pts = 0.0
    else:
        yoni_pts = 2.0
    kootas.append(
        KootaScore(
            name="Yoni",
            obtained_points=yoni_pts,
            max_points=4.0,
            description="Physical intimacy, biological compatibility, and mutual affection.",
            status="Excellent" if yoni_pts == 4.0 else "Good" if yoni_pts >= 2.0 else "Inauspicious",
        )
    )

    # 5. Graha Maitri (Max: 5)
    g_lord = SIGN_LORDS[g_sign]
    b_lord = SIGN_LORDS[b_sign]
    if g_lord == b_lord:
        maitri_pts = 5.0
    else:
        rel_g_to_b = (
            "friend" if b_lord in PLANET_FRIENDS[g_lord]["friends"]
            else "enemy" if b_lord in PLANET_FRIENDS[g_lord]["enemies"]
            else "neutral"
        )
        rel_b_to_g = (
            "friend" if g_lord in PLANET_FRIENDS[b_lord]["friends"]
            else "enemy" if g_lord in PLANET_FRIENDS[b_lord]["enemies"]
            else "neutral"
        )
        pair = {rel_g_to_b, rel_b_to_g}
        if pair == {"friend"}:
            maitri_pts = 5.0
        elif pair == {"friend", "neutral"}:
            maitri_pts = 4.0
        elif pair == {"neutral"}:
            maitri_pts = 3.0
        elif pair == {"friend", "enemy"}:
            maitri_pts = 1.0
        elif pair == {"neutral", "enemy"}:
            maitri_pts = 0.5
        else:
            maitri_pts = 0.0
    kootas.append(
        KootaScore(
            name="Graha Maitri",
            obtained_points=maitri_pts,
            max_points=5.0,
            description="Intellectual friendship and psychological alignment of planetary rulers.",
            status="Excellent" if maitri_pts >= 4.0 else "Good" if maitri_pts >= 3.0 else "Average",
        )
    )

    # 6. Gana (Max: 6)
    g_gana = NAKSHATRA_GANA[g_nak]
    b_gana = NAKSHATRA_GANA[b_nak]
    if g_gana == b_gana:
        gana_pts = 6.0
    elif (g_gana == "Deva" and b_gana == "Manushya") or (g_gana == "Manushya" and b_gana == "Deva"):
        gana_pts = 5.0
    elif (g_gana == "Deva" and b_gana == "Rakshasa"):
        gana_pts = 1.0
    else:
        gana_pts = 0.0
    kootas.append(
        KootaScore(
            name="Gana",
            obtained_points=gana_pts,
            max_points=6.0,
            description="Temperamental disposition and behavioral synergy.",
            status="Excellent" if gana_pts >= 5.0 else "Inauspicious",
        )
    )

    # 7. Bhakoot (Max: 7)
    dist = ((g_sign - b_sign) % 12) + 1
    # Dosha occurs on 2/12, 6/8, 9/5
    bhakoot_dosha = dist in {2, 12, 6, 8, 5, 9}
    bhakoot_cancelled = False

    if not bhakoot_dosha:
        bhakoot_pts = 7.0
    else:
        # Check cancellation exceptions: same lord or mutual friends
        if g_lord == b_lord:
            bhakoot_cancelled = True
            bhakoot_pts = 7.0
            dosha_exceptions.append(f"Bhakoot Dosha cancelled: Both Moon signs are ruled by {g_lord}.")
        else:
            bhakoot_pts = 0.0

    kootas.append(
        KootaScore(
            name="Bhakoot",
            obtained_points=bhakoot_pts,
            max_points=7.0,
            description="Family welfare, economic prosperity, and emotional harmony.",
            status="Excellent" if bhakoot_pts == 7.0 else "Inauspicious",
        )
    )

    # 8. Nadi (Max: 8)
    g_nadi = NAKSHATRA_NADI[g_nak]
    b_nadi = NAKSHATRA_NADI[b_nak]
    nadi_dosha = (g_nadi == b_nadi)
    nadi_cancelled = False

    if not nadi_dosha:
        nadi_pts = 8.0
    else:
        # Nadi Dosha cancellation exceptions:
        # 1. Same Nakshatra but different Pada
        # 2. Same Moon sign but different Nakshatras
        if g_nak == b_nak and g_pada != b_pada:
            nadi_cancelled = True
            nadi_pts = 8.0
            dosha_exceptions.append("Nadi Dosha cancelled: Same Nakshatra with distinct Padas.")
        elif g_sign == b_sign and g_nak != b_nak:
            nadi_cancelled = True
            nadi_pts = 8.0
            dosha_exceptions.append("Nadi Dosha cancelled: Same Moon sign with distinct Nakshatras.")
        else:
            nadi_pts = 0.0

    kootas.append(
        KootaScore(
            name="Nadi",
            obtained_points=nadi_pts,
            max_points=8.0,
            description="Genetic health, physiological alignment, and progeny vitality.",
            status="Excellent" if nadi_pts == 8.0 else "Inauspicious",
        )
    )

    total_score = sum(k.obtained_points for k in kootas)
    percentage = (total_score / 36.0) * 100.0

    if total_score >= 28:
        verdict = "Highly Auspicious"
    elif total_score >= 21:
        verdict = "Auspicious"
    elif total_score >= 18:
        verdict = "Acceptable"
    else:
        verdict = "Inauspicious"

    return AshtakootaResult(
        total_score=round(total_score, 1),
        max_score=36.0,
        percentage=round(percentage, 1),
        verdict=verdict,
        kootas=kootas,
        nadi_dosha=nadi_dosha,
        nadi_dosha_cancelled=nadi_cancelled,
        bhakoot_dosha=bhakoot_dosha,
        bhakoot_dosha_cancelled=bhakoot_cancelled,
        dosha_exceptions=dosha_exceptions,
        groom_moon_sign=ZODIAC_SIGNS[g_sign - 1]["name"],
        groom_nakshatra=NAKSHATRAS[g_nak - 1],
        bride_moon_sign=ZODIAC_SIGNS[b_sign - 1]["name"],
        bride_nakshatra=NAKSHATRAS[b_nak - 1],
    )
