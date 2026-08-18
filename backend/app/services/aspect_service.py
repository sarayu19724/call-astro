"""
Aspect Service — deterministic classical (Parashari) full-aspect
calculations. No LLM, no RAG: pure house-math from already-cached
chart data, used by chart_activation_service.py's SCORE_ASPECTING factor.
"""
from typing import List, Dict, Optional
from app.services.topic_service import get_house_for_sign

# Every planet casts a full aspect on the 7th house from its own placement.
# These three additionally cast special full aspects on the listed houses,
# counted inclusively from the planet's own house (e.g. Mars in house 1
# aspects houses 4 and 8, in addition to its universal 7th-house aspect).
SPECIAL_ASPECTS: Dict[str, set] = {
    "Mars": {4, 8},
    "Jupiter": {5, 9},
    "Saturn": {3, 10},
}


def get_planets_aspecting_house(house_num: int, planets: List[dict], ascendant_sign: Optional[str]) -> List[str]:
    """Returns the list of planet names that classically aspect the given
    house number, based on each planet's current sign placement.

    house_num: target house (1-12)
    planets: list of {"name": ..., "sign_name": ..., ...} dicts (cached chart data)
    ascendant_sign: the chart's Lagna sign, needed to convert sign -> house
    """
    if not ascendant_sign or not planets or not house_num:
        return []

    aspecting: List[str] = []

    for p in planets:
        name = p.get("name")
        sign = p.get("sign_name", "")
        if not name or not sign:
            continue

        planet_house = get_house_for_sign(sign, ascendant_sign)
        if not planet_house:
            continue

        # Houses are counted inclusively (planet's own house = count 1),
        # so the universal 7th-house aspect corresponds to count == 7.
        count = ((house_num - planet_house) % 12) + 1

        aspect_counts = {7} | SPECIAL_ASPECTS.get(name, set())

        if count in aspect_counts:
            aspecting.append(name)

    return aspecting