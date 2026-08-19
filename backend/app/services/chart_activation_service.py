"""
Chart Fact Graph + Activation Scoring.

Deterministic (no LLM, no RAG) ranking of which planets are most
astrologically significant for a given question, based on real chart data.

Scoring now runs primarily off framework_factors (houses/planets/concepts
actually extracted from RETRIEVED classical text — see
chat_service._extract_referenced_factors), not a hardcoded topic->house
lookup. TOPIC_CHART_FACTORS is still consulted as a fallback/supplement
when the topic classifier matched something and RAG found few/no factors,
so the system degrades gracefully rather than going silent.
"""
from typing import List, Dict, Optional, Set
from app.services.topic_service import get_house_for_sign, TOPIC_CHART_FACTORS
from app.services.kundli_service import get_house_lord
from app.services.aspect_service import get_planets_aspecting_house
from app.utils.logger import logger

SIGN_LORDS = {
    "Aries": "Mars", "Taurus": "Venus", "Gemini": "Mercury", "Cancer": "Moon",
    "Leo": "Sun", "Virgo": "Mercury", "Libra": "Venus", "Scorpio": "Mars",
    "Sagittarius": "Jupiter", "Capricorn": "Saturn", "Aquarius": "Saturn", "Pisces": "Jupiter",
}

SCORE_HOUSE_LORD = 3
SCORE_SIGNIFICATOR = 3
SCORE_OCCUPANT = 2
SCORE_ASPECTING = 2
SCORE_MAHADASHA = 3
SCORE_ANTARDASHA = 2
SCORE_OWN_SIGN = 2
SCORE_RETROGRADE = 1


def _merge_factors(topic: Optional[str], framework_factors: Optional[Dict]) -> Dict[str, Set]:
    """Combines RAG-retrieved houses/planets/concepts with the topic's
    hardcoded config (if any) as a fallback. RAG-derived factors take
    priority; TOPIC_CHART_FACTORS only fills gaps when RAG found little."""
    houses: Set[int] = set()
    significators: Set[str] = set()

    if framework_factors:
        for h in framework_factors.get("houses", set()):
            try:
                houses.add(int(h))
            except (TypeError, ValueError):
                pass
        significators |= set(framework_factors.get("planets", set()))
        significators.discard("Ascendant")

    # Fallback augmentation — only kicks in when RAG surfaced nothing usable,
    # so a topic classified by keyword match still gets *some* grounding.
    if topic and not houses and not significators:
        config = TOPIC_CHART_FACTORS.get(topic)
        if config:
            if config.get("house"):
                houses.add(config["house"])
            significators |= set(config.get("planets", []))

    return {"houses": houses, "significators": significators}


def compute_activation_scores(
    planets: List[dict],
    ascendant_sign: str,
    dasha_info: Optional[dict],
    framework_factors: Optional[Dict] = None,
    topic: Optional[str] = None,
) -> List[Dict]:
    """Scores each chart planet's relevance using houses/planets/concepts
    ACTUALLY RETRIEVED from classical text (framework_factors), falling
    back to TOPIC_CHART_FACTORS only if framework_factors is empty."""
    if not planets or not ascendant_sign:
        return []

    merged = _merge_factors(topic, framework_factors)
    key_houses: Set[int] = merged["houses"]
    significators: Set[str] = merged["significators"]

    if not key_houses and not significators:
        return []

    house_lords = {h: get_house_lord(h, ascendant_sign) for h in key_houses}
    aspecting_by_house = {
        h: set(get_planets_aspecting_house(h, planets, ascendant_sign)) for h in key_houses
    }

    maha_lord = None
    antar_lord = None
    if dasha_info:
        maha = dasha_info.get("current_mahadasha", {}) or {}
        antar = dasha_info.get("current_antardasha", {}) or {}
        maha_lord = maha.get("lord") or maha.get("name") or maha.get("planet")
        antar_lord = antar.get("lord") or antar.get("name") or antar.get("planet")

    results = []
    for p in planets:
        name = p.get("name")
        if not name:
            continue
        sign = p.get("sign_name", "")
        planet_house = get_house_for_sign(sign, ascendant_sign) if ascendant_sign else None
        score = 0
        reasons = []

        for h, lord in house_lords.items():
            if lord and name == lord:
                score += SCORE_HOUSE_LORD
                reasons.append(f"{h}th house lord")

        if name in significators:
            score += SCORE_SIGNIFICATOR
            reasons.append("significator per retrieved classical text")

        if planet_house in key_houses:
            score += SCORE_OCCUPANT
            reasons.append(f"occupies {planet_house}th house")

        for h, aspecting_set in aspecting_by_house.items():
            if name in aspecting_set:
                score += SCORE_ASPECTING
                reasons.append(f"aspects {h}th house")

        if maha_lord and name == maha_lord:
            score += SCORE_MAHADASHA
            reasons.append("current Mahadasha lord")

        if antar_lord and name == antar_lord:
            score += SCORE_ANTARDASHA
            reasons.append("current Antardasha lord")

        if sign and SIGN_LORDS.get(sign) == name:
            score += SCORE_OWN_SIGN
            reasons.append(f"in own sign ({sign})")

        if str(p.get("isRetro", "")).lower() == "true":
            score += SCORE_RETROGRADE
            reasons.append("retrograde")

        if score > 0:
            results.append({"planet": name, "score": score, "reasons": reasons})

    results.sort(key=lambda r: r["score"], reverse=True)
    return results


def get_top_activated_planets(
    planets: List[dict],
    ascendant_sign: str,
    dasha_info: Optional[dict],
    framework_factors: Optional[Dict] = None,
    topic: Optional[str] = None,
    top_n: int = 3,
) -> List[Dict]:
    scored = compute_activation_scores(planets, ascendant_sign, dasha_info, framework_factors, topic)
    return scored[:top_n]


def format_activation_summary_for_prompt(ranked: List[Dict]) -> str:
    if not ranked:
        return ""
    lines = [
        "Factor Activation Ranking (deterministic scoring against houses/planets actually "
        "referenced by the retrieved classical text for THIS question — higher score means "
        "more classically significant here, not general chart strength):"
    ]
    for i, r in enumerate(ranked, 1):
        reason_str = ", ".join(r["reasons"])
        lines.append(f"{i}. {r['planet']} — score {r['score']} ({reason_str})")
    lines.append(
        "Focus your interpretation primarily on the top-ranked factor(s) above. "
        "Do not give equal weight to planets not listed here just because they appear elsewhere in the chart."
    )
    return "\n".join(lines)