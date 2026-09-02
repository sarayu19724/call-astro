# Direct chart-fact answering — bypasses RAG and LLM generation entirely
import json
from typing import Optional, Dict
from app.services.kundli_service import kundli_service

PLANET_NAME_MAP = {
    "sun": "Sun", "moon": "Moon", "mars": "Mars", "mercury": "Mercury",
    "jupiter": "Jupiter", "venus": "Venus", "saturn": "Saturn",
    "rahu": "Rahu", "ketu": "Ketu",
}

RESPONSE_TEMPLATES = {

    "birth_details": {
        "English": "Your birth details: {dob}, {birth_time}, {birth_place}.",
        "Hindi": "आपका जन्म विवरण: {dob}, {birth_time}, {birth_place}।",
        "Hinglish": "Aapke birth details: {dob}, {birth_time}, {birth_place}.",
    },
}


def _extract_planet_from_message(message: str) -> Optional[str]:
    text = message.lower()
    for key, proper in PLANET_NAME_MAP.items():
        if key in text:
            return proper
    return None


def _get_fresh_chart(session: Dict) -> Optional[Dict]:
    """Re-derive planets/ascendant DIRECTLY from kundli_full_raw (the
    untouched Kundli API response) rather than trusting the separately
    cached kundli_raw field, which can drift from the raw payload."""
    cached_full_raw = session.get("kundli_full_raw")
    if cached_full_raw:
        try:
            full_raw = json.loads(cached_full_raw)
            fresh = kundli_service.extract_chart_data(full_raw)
            if fresh and fresh.get("ascendant_sign"):
                return fresh
        except Exception:
            pass

    cached_raw = session.get("kundli_raw")
    if cached_raw:
        try:
            return json.loads(cached_raw)
        except Exception:
            return None
    return None


def answer_chart_fact(fact_type: str, message_text: str, session: Dict, language: str = "Hinglish") -> Optional[str]:
    # Returns a direct answer string, or None to fall back to the normal pipeline
    templates = RESPONSE_TEMPLATES.get(fact_type, {})
    template = templates.get(language, templates.get("Hinglish"))
    if not template:
        return None

    try:
        if fact_type in ("ascendant", "moon_sign", "sun_sign"):
            parsed = _get_fresh_chart(session)
            if not parsed:
                return None

            if fact_type == "ascendant":
                sign = parsed.get("ascendant_sign")
            else:
                planet_name = "Moon" if fact_type == "moon_sign" else "Sun"
                match = next((p for p in parsed.get("planets", []) if p.get("name") == planet_name), None)
                sign = match.get("sign_name") if match else None

            if not sign:
                return None
            return template.format(sign=sign)

        if fact_type == "planet_position":
            parsed = _get_fresh_chart(session)
            if not parsed:
                return None
            planet = _extract_planet_from_message(message_text)
            if not planet:
                return None
            match = next((p for p in parsed.get("planets", []) if p.get("name") == planet), None)
            if not match:
                return None
            sign = match.get("sign_name", "")

            from app.services.topic_service import get_house_for_sign
            ascendant_sign = parsed.get("ascendant_sign")
            house = get_house_for_sign(sign, ascendant_sign) if ascendant_sign else None
            house_str = f" ({house}th house)" if house else ""
            return template.format(planet=planet, sign=sign, house_str=house_str)

        if fact_type == "current_dasha":
            cached_dasha = session.get("kundli_dasha")
            if not cached_dasha:
                return None
            dasha_info = json.loads(cached_dasha)
            maha = dasha_info.get("current_mahadasha", {}).get("lord")
            antar = dasha_info.get("current_antardasha", {}).get("lord")
            if not maha:
                return None
            antar_str = f", {antar} Antardasha" if antar else ""
            return template.format(maha=maha, antar_str=antar_str)

        if fact_type == "birth_details":
            dob = session.get("dob")
            birth_time = session.get("birth_time")
            birth_place = session.get("birth_place")
            if not (dob and birth_time and birth_place):
                return None
            return template.format(dob=dob, birth_time=birth_time, birth_place=birth_place)

    except Exception:
        return None

    return None