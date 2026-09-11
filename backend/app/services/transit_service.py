import json
from datetime import datetime, date
from typing import Dict, List, Optional, Any
from app.utils.logger import logger
from app.services.kundli_service import kundli_service, ZODIAC_SIGNS_ORDER

# Daily in-memory & database transit cache
_TRANSIT_CACHE: Dict[str, Any] = {}
_TRANSIT_RAG_CACHE: Dict[str, List[Dict[str, Any]]] = {}
_EMBEDDINGS_PROVIDER = None


def _get_embeddings_provider():
    global _EMBEDDINGS_PROVIDER
    if _EMBEDDINGS_PROVIDER is None:
        try:
            from app.rag.embeddings import EmbeddingsProvider
            _EMBEDDINGS_PROVIDER = EmbeddingsProvider()
        except Exception as e:
            logger.error(f"Failed to load EmbeddingsProvider: {e}")
    return _EMBEDDINGS_PROVIDER

ZODIAC = ZODIAC_SIGNS_ORDER

NAKSHATRAS = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra", "Punarvasu", "Pushya", "Ashlesha",
    "Magha", "Purva Phalguni", "Uttara Phalguni", "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha",
    "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishta", "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada", "Revati"
]

BENEFIC_HOUSES_FROM_MOON = {
    "Sun": [3, 6, 10, 11],
    "Moon": [1, 3, 6, 7, 10, 11],
    "Mars": [3, 6, 11],
    "Mercury": [2, 4, 6, 8, 10, 11],
    "Jupiter": [2, 5, 7, 9, 11],
    "Venus": [1, 2, 3, 4, 5, 8, 9, 11, 12],
    "Saturn": [3, 6, 11],
    "Rahu": [3, 6, 10, 11],
    "Ketu": [3, 6, 11],
}

HOUSE_NAMES = {
    1: "1st House (Self, Health & Vitality)",
    2: "2nd House (Wealth, Family & Speech)",
    3: "3rd House (Courage, Siblings & Skills)",
    4: "4th House (Home, Mother & Peace of Mind)",
    5: "5th House (Intellect, Romance & Creativity)",
    6: "6th House (Daily Work, Health & Overcoming Obstacles)",
    7: "7th House (Partnerships, Marriage & Business)",
    8: "8th House (Transformation, Longevity & Deep Insights)",
    9: "9th House (Higher Wisdom, Fortune & Dharma)",
    10: "10th House (Career, Public Image & Leadership)",
    11: "11th House (Gains, Friendships & Aspirations)",
    12: "12th House (Expenses, Spirituality & Solitude)",
}


class TransitService:
    def get_current_transits(self, target_date: Optional[str] = None) -> Dict[str, Any]:
        """Fetches and caches real-time planetary positions for today (or target_date)."""
        if not target_date:
            target_date = date.today().strftime("%d-%m-%Y")
        
        cache_key = f"transits_{target_date}"
        if cache_key in _TRANSIT_CACHE:
            return _TRANSIT_CACHE[cache_key]

        try:
            # Fetch real-time planetary positions for standard coordinates (New Delhi reference)
            kundli_raw = kundli_service.fetch_kundli(
                name="Transit",
                date=target_date,
                time="12:00",
                latitude=28.6139,
                longitude=77.2090,
                max_retries=0
            )

            if kundli_raw and "planetary_positions" in kundli_raw:
                planets = []
                positions = kundli_raw.get("planetary_positions", [])
                planet_lords = kundli_raw.get("planet_lords", {})

                for p in positions:
                    name = p.get("name")
                    if not name or name == "Ascendant":
                        continue
                    sign = p.get("sign_name", "")
                    is_retro = str(p.get("isRetro", "")).lower() == "true"
                    lord_info = planet_lords.get(name, {})
                    degree = lord_info.get("degree")

                    nak_name = ""
                    if degree is not None:
                        try:
                            nak_idx = int(float(degree) / (360.0 / 27.0)) % 27
                            nak_name = NAKSHATRAS[nak_idx]
                        except Exception:
                            pass

                    planets.append({
                        "name": name,
                        "sign": sign,
                        "is_retrograde": is_retro,
                        "degree": degree,
                        "nakshatra": nak_name
                    })

                result = {
                    "date": target_date,
                    "planets": planets,
                    "raw": kundli_raw
                }
                _TRANSIT_CACHE[cache_key] = result
                return result
        except Exception as e:
            logger.error(f"Error fetching real-time transits: {e}")

        # If real-time API unavailable, return gracefully — no stale hardcoded fallback
        logger.warning("Real-time transit API unavailable — transit overlay will be skipped")
        return {"available": False, "planets": [], "reason": "Real-time transit data unavailable — please check your connection"}

    def calculate_gochar_overlay(self, session: Dict, current_transits: Optional[Dict] = None) -> Dict[str, Any]:
        """Calculates transit house placements and Gochar impact for a profile.
        Returns structured transit data + rag_queries for RAG-based interpretation (no hardcoded strings).
        """
        if not current_transits:
            current_transits = self.get_current_transits()

        # If API is unavailable, propagate gracefully
        if not current_transits.get("planets"):
            return {"available": False, "reason": current_transits.get("reason", "Transit data unavailable")}

        kundli_raw_str = session.get("kundli_raw")
        if not kundli_raw_str:
            return {"available": False, "reason": "No natal chart available"}

        try:
            natal_data = json.loads(kundli_raw_str)
            natal_planets = natal_data.get("planets", [])
            natal_ascendant = natal_data.get("ascendant_sign", "")

            natal_moon_sign = ""
            for p in natal_planets:
                if p.get("name") == "Moon":
                    natal_moon_sign = p.get("sign_name") or p.get("sign") or ""
                    break

            if not natal_ascendant:
                return {"available": False, "reason": "Missing Ascendant sign"}

            # Whole-sign house counting from API-provided natal Lagna sign
            asc_idx = ZODIAC.index(natal_ascendant) if natal_ascendant in ZODIAC else 0
            moon_idx = ZODIAC.index(natal_moon_sign) if natal_moon_sign in ZODIAC else asc_idx

            transit_planets = current_transits.get("planets", [])
            transit_details = []

            # Build RAG queries for the major slow-moving planets so chat_service
            # can retrieve book passages at prompt time — NO hardcoded interpretation strings here
            rag_queries = []

            for tp in transit_planets:
                p_name = tp["name"]
                t_sign = tp["sign"]
                if t_sign not in ZODIAC:
                    continue

                t_idx = ZODIAC.index(t_sign)

                # Whole-sign house from Natal Ascendant (Lagna Gochar)
                lagna_house = (t_idx - asc_idx + 12) % 12 + 1

                # Whole-sign house from Natal Moon (Chandra Gochar)
                moon_house = (t_idx - moon_idx + 12) % 12 + 1

                is_benefic_from_moon = moon_house in BENEFIC_HOUSES_FROM_MOON.get(p_name, [])

                transit_details.append({
                    "name": p_name,
                    "current_sign": t_sign,
                    "degree": tp.get("degree"),
                    "nakshatra": tp.get("nakshatra"),
                    "is_retrograde": tp.get("is_retrograde", False),
                    "lagna_house": lagna_house,
                    "lagna_house_desc": HOUSE_NAMES.get(lagna_house, f"{lagna_house}th House"),
                    "moon_house": moon_house,
                    "is_favorable": is_benefic_from_moon,
                })

                # Generate a precise RAG query for major transiting planets
                if p_name in ("Jupiter", "Saturn", "Rahu", "Ketu", "Mars"):
                    retro_note = " retrograde" if tp.get("is_retrograde") else ""
                    rag_queries.append(
                        f"{p_name}{retro_note} transit {lagna_house}th house {natal_ascendant} ascendant effects"
                    )

            # Fetch authentic book insights via RAG (cached per date + Lagna)
            transit_insights = self.get_transit_rag_insights(
                natal_ascendant=natal_ascendant,
                rag_queries=rag_queries,
                target_date=current_transits.get("date", "")
            )

            return {
                "available": True,
                "profile_name": session.get("name", "User"),
                "relation": session.get("relation", "Self"),
                "natal_ascendant": natal_ascendant,
                "natal_moon_sign": natal_moon_sign,
                "transit_date": current_transits.get("date"),
                "transits": transit_details,
                # RAG queries for downstream LLM prompts
                "rag_queries": rag_queries,
                # Book-based insights for modal display & LLM grounding
                "transit_insights": transit_insights,
            }
        except Exception as e:
            logger.error(f"Failed to calculate Gochar overlay: {e}")
            return {"available": False, "error": str(e)}

    def get_transit_rag_insights(self, natal_ascendant: str, rag_queries: List[str], target_date: str) -> List[Dict[str, Any]]:
        """Retrieves authentic book passages for current transits from the knowledge base."""
        if not rag_queries or not natal_ascendant:
            return []

        cache_key = f"{target_date}_{natal_ascendant}"
        if cache_key in _TRANSIT_RAG_CACHE:
            return _TRANSIT_RAG_CACHE[cache_key]

        insights = []
        try:
            from app.rag.vector_store import vector_store
            from app.config.settings import settings
            from app.services.topic_service import TOPIC_RELEVANT_BOOKS

            transit_books = TOPIC_RELEVANT_BOOKS.get("timing_general", [])
            embedder = _get_embeddings_provider()
            if not embedder:
                return []

            seen_sources = set()
            for tq in rag_queries[:3]:
                try:
                    tq_vec = embedder.get_embedding(tq)
                    t_hits = vector_store.hybrid_search(
                        query=tq, query_vector=tq_vec,
                        top_k=2, alpha=settings.HYBRID_ALPHA,
                        preferred_sources=transit_books
                    )
                    for hit in t_hits:
                        if hit["score"] < settings.MIN_RAG_RELEVANCE:
                            continue
                        source = hit["metadata"].get("source", "Classical Text")
                        source_key = (source, hit["text"][:60])
                        if source_key in seen_sources:
                            continue
                        seen_sources.add(source_key)

                        book_name = source.rsplit(".", 1)[0].replace("_", " ").strip()
                        raw_text = " ".join(hit["text"].split())
                        snippet = raw_text[:200]
                        if len(raw_text) > 200:
                            snippet = snippet.rsplit(" ", 1)[0] + "..."

                        insights.append({
                            "book": book_name,
                            "snippet": snippet,
                            "score": round(hit["score"], 3),
                        })
                except Exception as q_err:
                    logger.warning(f"Transit RAG query failed for '{tq}': {q_err}")

            insights = insights[:3]
            _TRANSIT_RAG_CACHE[cache_key] = insights
        except Exception as e:
            logger.error(f"Error retrieving transit RAG insights: {e}")

        return insights



    def format_gochar_for_prompt(self, gochar_data: Dict) -> str:
        """Formats transit overlay into a concise, grounded prompt block for LLM inference.
        Includes transit_insights (RAG-retrieved book passages with citations) when available.
        """
        if not gochar_data or not gochar_data.get("available"):
            return "No real-time transit data available."

        lines = [
            f"=== Real-Time Planetary Transits (Gochar for {gochar_data.get('profile_name')}) ===",
            f"- Natal Lagna: {gochar_data.get('natal_ascendant')} | Natal Moon: {gochar_data.get('natal_moon_sign')}",
            "- Active Key Transits:"
        ]

        for t in gochar_data.get("transits", []):
            if t["name"] in ["Jupiter", "Saturn", "Rahu", "Ketu", "Mars", "Sun"]:
                fav = "Favorable" if t.get("is_favorable") else "Neutral/Challenging"
                lines.append(f"  * {t['name']} in {t['current_sign']} (Transiting {t['lagna_house_desc']} from Lagna, {t['moon_house']}th from Moon — {fav})")

        # Append RAG-retrieved book insights when available (populated by chat_service)
        insights = gochar_data.get("transit_insights", [])
        if insights:
            lines.append("\n- Transit Interpretations from Classical Texts:")
            for insight in insights:
                book = insight.get("book", "Classical Text")
                snippet = insight.get("snippet", "")
                if snippet:
                    lines.append(f'  [{book}]: "{snippet}"')

        return "\n".join(lines)



transit_service = TransitService()
