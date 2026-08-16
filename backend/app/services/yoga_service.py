from typing import List, Dict, Optional
from app.services.kundli_service import get_house_lord, ZODIAC_SIGNS_ORDER, SIGN_LORDS
from app.services.topic_service import get_house_for_sign, get_sign_for_house

# Exaltation / own-sign / debilitation — fixed classical values, not guessed.
EXALTATION = {"Sun": "Aries", "Moon": "Taurus", "Mars": "Capricorn", "Mercury": "Virgo",
              "Jupiter": "Cancer", "Venus": "Pisces", "Saturn": "Libra"}
DEBILITATION = {"Sun": "Libra", "Moon": "Scorpio", "Mars": "Cancer", "Mercury": "Pisces",
                "Jupiter": "Capricorn", "Venus": "Virgo", "Saturn": "Aries"}
OWN_SIGNS = {
    "Sun": ["Leo"], "Moon": ["Cancer"], "Mars": ["Aries", "Scorpio"],
    "Mercury": ["Gemini", "Virgo"], "Jupiter": ["Sagittarius", "Pisces"],
    "Venus": ["Taurus", "Libra"], "Saturn": ["Capricorn", "Aquarius"],
}
KENDRA_HOUSES = {1, 4, 7, 10}
TRIKONA_HOUSES = {1, 5, 9}


def _find_planet(planets: List[dict], name: str) -> Optional[dict]:
    return next((p for p in planets if p.get("name") == name), None)


def detect_yogas(planets: List[dict], ascendant_sign: str) -> List[Dict[str, str]]:
    """Detects a set of well-known, deterministic classical yogas from
    planetary placements. Each result includes the yoga name and a short
    plain-language reason — computed, not LLM-guessed."""
    yogas = []
    moon = _find_planet(planets, "Moon")
    jupiter = _find_planet(planets, "Jupiter")
    sun = _find_planet(planets, "Sun")
    mercury = _find_planet(planets, "Mercury")
    mars = _find_planet(planets, "Mars")

    # Gajakesari Yoga — Jupiter in a kendra (1/4/7/10) FROM the Moon
    if moon and jupiter:
        moon_house = get_house_for_sign(moon.get("sign_name", ""), ascendant_sign)
        jup_house = get_house_for_sign(jupiter.get("sign_name", ""), ascendant_sign)
        if moon_house and jup_house:
            diff = ((jup_house - moon_house) % 12) + 1
            if diff in KENDRA_HOUSES:
                yogas.append({
                    "name": "Gajakesari Yoga",
                    "reason": f"Jupiter is in a kendra position from the Moon (Moon in house {moon_house}, Jupiter in house {jup_house})."
                })

    # Budhaditya Yoga — Sun and Mercury conjunct (same sign)
    if sun and mercury and sun.get("sign_name") == mercury.get("sign_name"):
        yogas.append({
            "name": "Budhaditya Yoga",
            "reason": f"Sun and Mercury are conjunct in {sun.get('sign_name')}, indicating sharp intellect."
        })

    # Chandra-Mangal Yoga — Moon and Mars conjunct (same sign)
    if moon and mars and moon.get("sign_name") == mars.get("sign_name"):
        yogas.append({
            "name": "Chandra-Mangal Yoga",
            "reason": f"Moon and Mars are conjunct in {moon.get('sign_name')}, often linked to financial drive."
        })

    # Dhana Yoga (simplified) — 2nd lord and 11th lord in mutual conjunction or exchange
    lord_2 = get_house_lord(2, ascendant_sign)
    lord_11 = get_house_lord(11, ascendant_sign)
    if lord_2 and lord_11 and lord_2 != lord_11:
        p2 = _find_planet(planets, lord_2)
        p11 = _find_planet(planets, lord_11)
        if p2 and p11 and p2.get("sign_name") == p11.get("sign_name"):
            yogas.append({
                "name": "Dhana Yoga",
                "reason": f"2nd lord ({lord_2}) and 11th lord ({lord_11}) are conjunct in {p2.get('sign_name')}, supporting wealth accumulation."
            })

    # Raj Yoga (simplified) — a kendra lord and a trikona lord conjunct in the same sign
    for kendra_h in KENDRA_HOUSES:
        for trikona_h in TRIKONA_HOUSES:
            if kendra_h == trikona_h:
                continue
            kl = get_house_lord(kendra_h, ascendant_sign)
            tl = get_house_lord(trikona_h, ascendant_sign)
            if not kl or not tl or kl == tl:
                continue
            pk = _find_planet(planets, kl)
            pt = _find_planet(planets, tl)
            if pk and pt and pk.get("sign_name") == pt.get("sign_name"):
                label = f"Raj Yoga ({kendra_h}th & {trikona_h}th lords)"
                if not any(y["name"] == label for y in yogas):
                    yogas.append({
                        "name": label,
                        "reason": f"{kendra_h}th lord ({kl}) and {trikona_h}th lord ({tl}) are conjunct in {pk.get('sign_name')}, a classical Raj Yoga combination."
                    })

    # Exaltation flags — for any of the 5 topic-relevant planets, if exalted
    for p in planets:
        pname = p.get("name")
        psign = p.get("sign_name")
        if pname in EXALTATION and EXALTATION[pname] == psign:
            yogas.append({
                "name": f"{pname} Exalted",
                "reason": f"{pname} is exalted in {psign}, its position of maximum classical strength."
            })
        elif pname in DEBILITATION and DEBILITATION[pname] == psign:
            yogas.append({
                "name": f"{pname} Debilitated",
                "reason": f"{pname} is debilitated in {psign}, its position of classical weakness."
            })

    return yogas


def format_yogas_for_prompt(yogas: List[Dict[str, str]]) -> str:
    if not yogas:
        return ""
    lines = ["Detected Yogas (classical planetary combinations, computed — not inferred):"]
    for y in yogas:
        lines.append(f"- {y['name']}: {y['reason']}")
    return "\n".join(lines)