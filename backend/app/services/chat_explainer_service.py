from typing import Dict, List, Optional
from app.services.kundli_service import get_house_lord, ZODIAC_SIGNS_ORDER
from app.services.topic_service import get_house_for_sign

HOUSE_MEANINGS = {
    1: "personality, body, identity", 2: "wealth, family, speech",
    3: "communication, courage, siblings", 4: "home, mother, education, property",
    5: "intelligence, education, creativity, romance", 6: "competition, service, obstacles",
    7: "marriage, partnerships", 8: "transformation, uncertainty",
    9: "fortune, higher education, dharma", 10: "career",
    11: "gains, friends, networks", 12: "foreign connections, expenditure, isolation, spirituality",
}

EXPLAIN_CHART_TRIGGERS = (
    "explain my chart", "explain chart", "explain my kundli", "explain kundli",
    "poori kundli", "puri kundli", "full kundli", "meri kundli explain",
    "analyse my chart", "analyze my chart", "chart explanation", "explain my birth chart",
)


def is_explain_chart_request(message_text: str) -> bool:
    q = message_text.strip().lower()
    return any(t in q for t in EXPLAIN_CHART_TRIGGERS)


def build_full_chart_data(planets: List[dict], ascendant_sign: str, dasha_info: Optional[dict],
                            moon_nakshatra: Optional[dict], yoga_text: str) -> str:
    """Deterministic full-chart breakdown — every planet, every house,
    every house lord, conjunctions, nakshatra, current Dasha. No LLM
    involved; this is pure calculation, matching what the doc calls for."""
    lines = []

    lines.append(f"LAGNA (Ascendant): {ascendant_sign}")

    lines.append("\nALL PLANETS:")
    planet_house = {}
    for p in planets:
        name = p.get("name")
        sign = p.get("sign_name", "")
        house = get_house_for_sign(sign, ascendant_sign)
        retro = " (retrograde)" if str(p.get("isRetro", "")).lower() == "true" else ""
        lines.append(f"- {name}: {sign}, House {house}{retro}")
        if house:
            planet_house.setdefault(house, []).append(name)

    lines.append("\nALL 12 HOUSES:")
    for house_num in range(1, 13):
        lord = get_house_lord(house_num, ascendant_sign)
        occupants = planet_house.get(house_num, [])
        occ_str = f", occupied by {', '.join(occupants)}" if occupants else ", unoccupied"
        lines.append(f"- House {house_num} ({HOUSE_MEANINGS[house_num]}): ruled by {lord}{occ_str}")

    conjunctions = [f"House {h}: {', '.join(names)}" for h, names in planet_house.items() if len(names) >= 2]
    if conjunctions:
        lines.append("\nCONJUNCTIONS (2+ planets in same house):")
        for c in conjunctions:
            lines.append(f"- {c}")

    if moon_nakshatra:
        lines.append(f"\nMOON NAKSHATRA: {moon_nakshatra.get('name', 'Unknown')}"
                      f" (Lord: {moon_nakshatra.get('lord', 'Unknown')}, Pada: {moon_nakshatra.get('pada', '?')})")

    if dasha_info:
        maha = dasha_info.get("current_mahadasha", {})
        antar = dasha_info.get("current_antardasha", {})
        if maha:
            dasha_line = f"\nCURRENT DASHA: Mahadasha={maha.get('lord')}"
            if antar:
                dasha_line += f", Antardasha={antar.get('lord')}"
            lines.append(dasha_line)

    if yoga_text:
        lines.append(f"\nYOGAS PRESENT: {yoga_text}")

    return "\n".join(lines)