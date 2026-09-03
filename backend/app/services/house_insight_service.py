"""
House Insight Service — powers the "tap a house to understand it" feature.
Deliberately self-contained: reuses kundli_service, vector_store, embeddings,
topic_service, and llm_service exactly as they already exist. No changes
required to any of those modules.

CACHING: previously this called the LLM fresh on EVERY click, even for the
same house in the same session. Now each house's generated insight is
cached in the session (session["house_insights_cache"], keyed by house
number) the first time it's computed, and served instantly from cache on
every subsequent click — no LLM call, no RAG retrieval, no delay. The
cache is invalidated automatically whenever birth details change and the
chart is recalculated (see session.py's update_session_info, which clears
house_insights_cache alongside the other chart-derived caches).
"""
import json
from typing import Dict, Any, Optional, List

from app.memory.database import db
from app.services.kundli_service import get_house_lord
from app.services.topic_service import get_house_for_sign, get_sign_for_house
from app.services.llm_service import llm_service
from app.rag.vector_store import vector_store
from app.rag.embeddings import EmbeddingsProvider
from app.config.settings import settings
from app.utils.logger import logger

_embeddings_provider = EmbeddingsProvider()

# Bump this if the shape/logic of a cached entry changes, so old cached
# entries are treated as a miss instead of served in a stale shape.
HOUSE_INSIGHT_CACHE_VERSION = 1

HOUSE_THEMES = {
    1: "self, personality, physical body, overall vitality",
    2: "wealth, family, speech, accumulated resources",
    3: "courage, siblings, communication, short journeys, skills",
    4: "home, mother, education, emotional foundation, property",
    5: "intelligence, children, creativity, romance, past-life merit",
    6: "service, competition, obstacles, health, debts, daily work",
    7: "marriage, partnership, business collaboration",
    8: "transformation, longevity, occult, sudden events",
    9: "fortune, dharma, higher learning, father, long journeys",
    10: "career, profession, public standing, authority",
    11: "gains, income, friendships, aspirations",
    12: "expenditure, foreign lands, spirituality, isolation, moksha",
}

HOUSE_SEARCH_BIAS = {
    1: "lagna ascendant first house personality body",
    2: "second house wealth family speech dhana",
    3: "third house siblings courage communication parakrama",
    4: "fourth house home mother education sukha bhava",
    5: "fifth house children intelligence creativity purva punya",
    6: "sixth house enemies disease debts service shatru",
    7: "seventh house marriage spouse partnership kalatra",
    8: "eighth house longevity transformation occult ayu bhava",
    9: "ninth house fortune father dharma bhagya",
    10: "tenth house career profession karma bhava",
    11: "eleventh house gains income friends labha",
    12: "twelfth house expenditure foreign moksha vyaya",
}

HOUSE_INSIGHT_PROMPT = """You are an experienced, warm Indian Vedic Astrologer. The user has tapped on one
specific house of their birth chart to understand it. Explain THIS house only, grounded strictly in the
verified chart facts and classical evidence given below.

Rules:
1. Respond STRICTLY in {language}.
   - English: warm English.
   - Hindi: polite Devanagari Hindi.
   - Hinglish: natural conversational Hinglish (Latin script).
2. Length: 3-5 sentences, under 90 words. Plain prose only, no bullet points, no headers.
3. Speak with grounded confidence. NEVER mention books, RAG, retrieval, sources, or "context" —
   attribute your reading to reading their Kundali directly.
4. Use ONLY the verified house facts below for placements — never invent a planet, sign, or house
   placement that isn't listed there.
5. Weave in the classical evidence naturally as supporting reasoning; never cite a source by name.
6. If no classical evidence was retrieved, rely on the verified facts and well-established classical
   principles for this house, and keep the reading slightly more general rather than inventing detail.

Verified House Facts (ground truth — do not contradict):
{house_facts}

Classical Evidence (informs your reasoning only — never mention this exists):
{evidence_context}

User's name: {name}

Write a short, natural explanation of this house now:
"""


def _get_verified_chart(session: Dict) -> Optional[Dict[str, Any]]:
    """Deterministic re-derivation of planet/house placements from the
    cached chart JSON — the single source of truth for this feature."""
    cached_raw = session.get("kundli_raw")
    if not cached_raw:
        return None
    try:
        parsed = json.loads(cached_raw)
    except Exception:
        return None

    planets = parsed.get("planets", []) or []
    ascendant_sign = parsed.get("ascendant_sign")
    if not ascendant_sign or not planets:
        return None

    result: Dict[str, Any] = {"ascendant": ascendant_sign, "planets": {}, "house_lords": {}}
    for p in planets:
        name = p.get("name")
        sign = p.get("sign_name", "")
        if not name or not sign:
            continue
        house = get_house_for_sign(sign, ascendant_sign)
        result["planets"][name] = {
            "house": house,
            "sign": sign,
            "retro": str(p.get("isRetro", "")).lower() == "true",
        }

    for house_num in range(1, 13):
        lord = get_house_lord(house_num, ascendant_sign)
        if lord:
            result["house_lords"][house_num] = lord

    return result


def build_house_facts(house_number: int, chart: Dict[str, Any]) -> Dict[str, Any]:
    ascendant_sign = chart["ascendant"]
    house_sign = get_sign_for_house(house_number, ascendant_sign)
    house_lord = chart["house_lords"].get(house_number)

    occupants = [
        name for name, info in chart["planets"].items()
        if info.get("house") == house_number
    ]

    lord_placement = None
    if house_lord and house_lord in chart["planets"]:
        info = chart["planets"][house_lord]
        lord_placement = {
            "planet": house_lord,
            "sign": info.get("sign"),
            "house": info.get("house"),
            "retro": info.get("retro", False),
        }

    return {
        "house_number": house_number,
        "sign": house_sign,
        "lord": house_lord,
        "occupants": occupants,
        "lord_placement": lord_placement,
        "theme": HOUSE_THEMES.get(house_number, ""),
    }


def format_house_facts_for_prompt(facts: Dict[str, Any]) -> str:
    lines = [
        f"House {facts['house_number']} (governs: {facts['theme']})",
        f"Sign on this house: {facts['sign']}",
        f"House lord: {facts['lord'] or 'unknown'}",
    ]
    if facts["occupants"]:
        lines.append(f"Planets occupying this house: {', '.join(facts['occupants'])}")
    else:
        lines.append("Planets occupying this house: none")

    lp = facts.get("lord_placement")
    if lp:
        retro = " (retrograde)" if lp.get("retro") else ""
        house_part = f", house {lp['house']}" if lp.get("house") else ""
        lines.append(f"House lord {lp['planet']} is placed in {lp['sign']}{house_part}{retro}")

    return "\n".join(lines)


def retrieve_house_evidence(house_number: int, facts: Dict[str, Any], top_k: int = 5) -> List[Dict[str, Any]]:
    bias = HOUSE_SEARCH_BIAS.get(house_number, f"{house_number}th house")
    lord = facts.get("lord") or ""
    occupants = " ".join(facts.get("occupants") or [])
    query = f"{bias} {lord} {occupants} classical astrology significance rules".strip()

    try:
        query_vector = _embeddings_provider.get_embedding(query)
        hits = vector_store.hybrid_search(
            query=query, query_vector=query_vector,
            top_k=top_k, alpha=settings.HYBRID_ALPHA,
        )
    except Exception as e:
        logger.error(f"[HouseInsight] retrieval failed for house {house_number}: {e}")
        return []

    relevant = [h for h in hits if h["score"] >= settings.MIN_RAG_RELEVANCE]
    rag_hits = []
    for hit in relevant:
        rag_hits.append({
            "source": hit["metadata"].get("source", "Unknown"),
            "page": hit["metadata"].get("page"),
            "score": hit["score"],
            "text": hit["text"],
        })
    return rag_hits


def build_evidence_context(rag_hits: List[Dict[str, Any]]) -> str:
    if not rag_hits:
        return "No specific classical passages were retrieved for this house."
    chunks = []
    for i, hit in enumerate(rag_hits):
        page_label = f", Page: {hit['page']}" if hit.get("page") is not None else ""
        chunks.append(f"--- Classical Source {i+1} [Source: {hit['source']}{page_label}] ---\n{hit['text']}\n")
    return "\n".join(chunks)


# ------------------------------------------------------------------
# CACHE HELPERS
# ------------------------------------------------------------------
def _get_house_cache_store(session: Dict) -> Dict[str, Any]:
    raw = session.get("house_insights_cache")
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _get_cached_house_insight(session: Dict, house_number: int) -> Optional[Dict[str, Any]]:
    store = _get_house_cache_store(session)
    entry = store.get(str(house_number))
    if not entry:
        return None
    if entry.get("_version") != HOUSE_INSIGHT_CACHE_VERSION:
        return None
    result = dict(entry)
    result.pop("_version", None)
    return result


def _save_house_insight_cache(session_id: str, session: Dict, house_number: int, result: Dict[str, Any]):
    try:
        store = _get_house_cache_store(session)
        entry_to_store = dict(result)
        entry_to_store["_version"] = HOUSE_INSIGHT_CACHE_VERSION
        store[str(house_number)] = entry_to_store
        store_json = json.dumps(store, ensure_ascii=False)
        db.update_session(session_id, {"house_insights_cache": store_json})
        session["house_insights_cache"] = store_json
        logger.info(f"[HouseInsightCache] cached house {house_number} for session {session_id}")
    except Exception as e:
        logger.error(f"Failed to save house insight cache for house {house_number}: {e}")


def generate_house_insight(session_id: str, house_number: int) -> Dict[str, Any]:
    if house_number < 1 or house_number > 12:
        return {"available": False, "reason": "invalid_house"}

    session = db.get_or_create_session(session_id)

    # --- CACHE CHECK: if this house was already explained for this chart,
    # return it instantly — no LLM call, no RAG retrieval. ---
    cached_result = _get_cached_house_insight(session, house_number)
    if cached_result is not None:
        logger.info(f"[HouseInsightCache] HIT for house {house_number}, session {session_id} — LLM skipped")
        return cached_result

    logger.info(f"[HouseInsightCache] MISS for house {house_number}, session {session_id} — generating fresh")

    chart = _get_verified_chart(session)
    if not chart:
        # Not cached — a missing chart is a transient state, not worth caching.
        return {"available": False, "reason": "no_chart_data"}

    facts = build_house_facts(house_number, chart)
    rag_hits = retrieve_house_evidence(house_number, facts)
    evidence_context = build_evidence_context(rag_hits)
    house_facts_text = format_house_facts_for_prompt(facts)

    language = session.get("language", "Hinglish")
    name = session.get("name") or "Friend"

    prompt = HOUSE_INSIGHT_PROMPT.format(
        language=language, house_facts=house_facts_text,
        evidence_context=evidence_context, name=name,
    )

    fallback_text = {
        "English": "I couldn't generate a reading for this house right now — please try again.",
        "Hindi": "अभी इस भाव के लिए विवरण उपलब्ध नहीं है — कृपया दोबारा प्रयास करें।",
        "Hinglish": "Abhi is bhaav ke baare mein jaankari generate nahi ho payi — kripya dobara koshish karein.",
    }.get(language, "Kripya dobara koshish karein.")

    generation_failed = False
    try:
        explanation = llm_service.generate(prompt=prompt, temperature=0.6).strip() or fallback_text
    except Exception as e:
        logger.error(f"[HouseInsight] LLM generation failed for house {house_number}: {e}")
        explanation = fallback_text
        generation_failed = True

    dasha_summary = None
    cached_dasha = session.get("kundli_dasha")
    if cached_dasha:
        try:
            dasha_info = json.loads(cached_dasha)
            maha = dasha_info.get("current_mahadasha", {}) or {}
            antar = dasha_info.get("current_antardasha", {}) or {}
            if maha.get("lord"):
                dasha_summary = f"{maha['lord']} Mahadasha"
                if antar.get("lord"):
                    dasha_summary += f" → {antar['lord']} Antardasha"
        except Exception:
            pass

    sources = []
    seen = set()
    for hit in rag_hits:
        key = (hit["source"], hit["page"])
        if key in seen:
            continue
        seen.add(key)
        sources.append({"source": hit["source"], "page": hit["page"]})

    result = {
        "available": True,
        "house_number": house_number,
        "sign": facts["sign"],
        "lord": facts["lord"],
        "occupants": facts["occupants"],
        "theme": facts["theme"],
        "current_dasha": dasha_summary,
        "explanation": explanation,
        "sources": sources,
    }

    # Only cache a SUCCESSFUL generation — if the LLM failed and we fell
    # back to the generic "please try again" text, don't lock that in;
    # let the next click retry the real generation instead.
    if not generation_failed:
        _save_house_insight_cache(session_id, session, house_number, result)

    return result