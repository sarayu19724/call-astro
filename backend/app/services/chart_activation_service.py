"""
Chart Fact Graph + Activation Scoring.

Deterministic (no LLM, no RAG) ranking of which planets are most
astrologically significant for a given topic, based on real chart data.
Named chart_activation_service.py to avoid colliding with the existing
chart_fact_service.py (direct chart-fact Q&A — unrelated, unused, left as-is).
"""
from typing import List, Dict, Optional
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


def compute_activation_scores(topic: str, planets: List[dict], ascendant_sign: str,
                                dasha_info: Optional[dict]) -> List[Dict]:
    config = TOPIC_CHART_FACTORS.get(topic)
    if not config or not planets or not ascendant_sign:
        return []

    key_house = config.get("house")
    significators = set(config.get("planets", []))
    house_lord = get_house_lord(key_house, ascendant_sign) if key_house else None
    aspecting_planets = set(get_planets_aspecting_house(key_house, planets, ascendant_sign)) if key_house else set()

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
        score = 0
        reasons = []

        if house_lord and name == house_lord:
            score += SCORE_HOUSE_LORD
            reasons.append(f"{key_house}th house lord")

        if name in significators:
            score += SCORE_SIGNIFICATOR
            reasons.append(f"significator for {topic}")

        if key_house and get_house_for_sign(sign, ascendant_sign) == key_house:
            score += SCORE_OCCUPANT
            reasons.append(f"occupies {key_house}th house")

        if name in aspecting_planets:
            score += SCORE_ASPECTING
            reasons.append(f"aspects {key_house}th house")

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


def get_top_activated_planets(topic: str, planets: List[dict], ascendant_sign: str,
                                dasha_info: Optional[dict], top_n: int = 3) -> List[Dict]:
    scored = compute_activation_scores(topic, planets, ascendant_sign, dasha_info)
    return scored[:top_n]


def format_activation_summary_for_prompt(topic: str, ranked: List[Dict]) -> str:
    if not ranked:
        return ""
    lines = [
        f"Factor Activation Ranking for {topic} (deterministic scoring — higher score means "
        f"more classically significant for THIS specific question, not general strength):"
    ]
    for i, r in enumerate(ranked, 1):
        reason_str = ", ".join(r["reasons"])
        lines.append(f"{i}. {r['planet']} — score {r['score']} ({reason_str})")
    lines.append(
        "Focus your interpretation primarily on the top-ranked factor(s) above. "
        "Do not give equal weight to planets not listed here just because they appear elsewhere in the chart."
    )
    return "\n".join(lines)