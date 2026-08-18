from typing import Dict, Any, List, Optional, Set
from datetime import datetime
from difflib import SequenceMatcher
import json
import re
from app.memory.database import db
from app.services.llm_service import llm_service
from app.services.geocoding_service import geocoding_service
from app.services.kundli_service import kundli_service
from app.rag.vector_store import vector_store
from app.rag.embeddings import EmbeddingsProvider
from app.prompts.templates import ASTROLOGER_PROMPT, MISSING_INFO_PROMPT
from app.config.settings import settings
from app.utils.logger import logger
from app.services.intent_service import classify_intent, get_response_contract
from app.services.claim_validator import validate_claims, build_claim_correction_instructions
from app.services.specificity_service import compute_chart_specificity, build_specificity_correction
from app.services.topic_service import (
    classify_topic, build_topic_emphasis, get_search_bias,
    build_explanation_footer, TOPIC_CHART_FACTORS, get_instant_suggestions,
    rank_favorable_periods, format_dasha_timeline_for_prompt,
    build_evidence_vote, format_evidence_vote_for_prompt,
    get_evidence_consensus_label, get_consensus_instruction
)
from app.services.dasha_api_service import dasha_api_service
from app.services.yoga_service import detect_yogas, format_yogas_for_prompt
from app.services.chat_explainer_service import is_explain_chart_request


class ChatService:
    def __init__(self):
        self.embeddings_provider = EmbeddingsProvider()

    def _format_history_for_llm(self, history: List[Dict[str, str]]) -> str:
        formatted = []
        for msg in history:
            if msg["role"] == "system":
                continue
            role_name = "User" if msg["role"] == "user" else "Astrologer"
            formatted.append(f"{role_name}: {msg['content']}")
        return "\n".join(formatted)

    def _to_24h(self, time_str: str) -> str:
        if not time_str:
            return ""
        try:
            from dateutil import parser as dateutil_parser
            parsed = dateutil_parser.parse(time_str.strip(), fuzzy=True)
            return parsed.strftime("%H:%M")
        except Exception:
            try:
                parsed_time = datetime.strptime(time_str.strip(), "%I:%M %p")
                return parsed_time.strftime("%H:%M")
            except ValueError:
                return time_str

    def _fetch_and_cache_kundli(self, session_id: str, session: Dict) -> str:
        # Fetches Kundli + real Dasha once, pre-computes yoga_text, everything downstream reads from cache
        try:
            coords = geocoding_service.geocode(session.get("birth_place"))
            if not coords:
                logger.warning(f"Could not geocode birth_place: {session.get('birth_place')}")
                return "No chart data available."

            lat, lon = coords
            time_24h = self._to_24h(session.get("birth_time", ""))

            kundli_data = kundli_service.fetch_kundli(
                name=session.get("name") or "User",
                date=session.get("dob"), time=time_24h, latitude=lat, longitude=lon,
            )
            if kundli_data:
                dasha_info = kundli_service.get_real_or_calculated_dasha(
                    kundli_data, session.get("dob"), time_24h, lat, lon
                )
                kundli_str = kundli_service.summarize_kundli(kundli_data, dob=session.get("dob"))
                chart_data = kundli_service.extract_chart_data(kundli_data)
                chart_json = json.dumps(chart_data) if chart_data else None
                dasha_json = json.dumps(dasha_info) if dasha_info else None
                full_raw_json = json.dumps(kundli_data, ensure_ascii=False)

                yoga_text = ""
                if chart_data:
                    try:
                        yogas = detect_yogas(chart_data.get("planets", []), chart_data.get("ascendant_sign", ""))
                        yoga_text = format_yogas_for_prompt(yogas)
                    except Exception as yoga_err:
                        logger.error(f"Yoga pre-computation failed: {yoga_err}")

                updates = {
                    "kundli_data": kundli_str,
                    "kundli_raw": chart_json,
                    "kundli_dasha": dasha_json,
                    "kundli_full_raw": full_raw_json,
                    "latitude": lat,
                    "longitude": lon,
                    "yoga_text": yoga_text,
                    "topic_cache": None,
                    "dasha_tree_raw": None,
                }
                db.update_session(session_id, updates)
                session.update(updates)
                logger.info("Kundli data fetched and cached (summary + chart + dasha + full raw + yoga)")
                return kundli_str
        except Exception as kundli_err:
            logger.error(f"Kundli fetch failed: {kundli_err}")

        return "No chart data available."

    def _get_rag_context(self, message_text: str, topic: Optional[str] = None):
        # Generic fallback RAG. Returns (context_str, rag_hits).
        try:
            from app.services.topic_service import TOPIC_RELEVANT_BOOKS

            search_query = message_text.strip()
            if topic:
                bias = get_search_bias(topic)
                if bias:
                    search_query = f"{search_query} {bias}"
            preferred_sources = TOPIC_RELEVANT_BOOKS.get(topic) if topic else None

            query_vector = self.embeddings_provider.get_embedding(search_query)
            hits = vector_store.dual_retrieve(
                topic_query=search_query,
                global_query=message_text,
                query_vector_topic=query_vector,
                query_vector_global=self.embeddings_provider.get_embedding(message_text),
                preferred_sources=preferred_sources,
                top_k_each=6,
                final_top_k=settings.TOP_K_RETRIEVAL,
                alpha=settings.HYBRID_ALPHA,
            )

            relevant_hits = [h for h in hits if h["score"] >= settings.MIN_RAG_RELEVANCE]
            if not relevant_hits:
                return "No reference available.", []

            context_chunks, rag_hits = [], []
            for i, hit in enumerate(relevant_hits):
                source = hit["metadata"].get("source", "Unknown")
                page = hit["metadata"].get("page")
                page_label = f", Page: {page}" if page is not None else ""
                context_chunks.append(
                    f"--- Context {i+1} [Source: {source}{page_label}, relevance: {hit['score']:.2f}] ---\n{hit['text']}\n"
                )
                rag_hits.append({
                    "source": source, "page": page,
                    "score": hit["score"], "text": hit["text"]
                })

            logger.info(f"[RAG] generic retrieval hits={len(rag_hits)} query='{search_query}'")
            return "\n".join(context_chunks), rag_hits
        except Exception as rag_err:
            logger.error(f"RAG failed: {rag_err}")
            return "No reference available.", []

    def _build_framework_query(self, message_text: str, topic: Optional[str] = None) -> str:
        # Ask the knowledge base what classical factors should be examined
        parts = [
            message_text.strip(),
            "classical astrology principles rules indications relevant factors"
        ]
        if topic:
            bias = get_search_bias(topic)
            if bias:
                parts.append(bias)
        return " ".join(p for p in parts if p).strip()

    def _extract_referenced_factors(self, rag_hits: List[Dict[str, Any]]) -> Dict[str, Set[str]]:
        # Extract only entities explicitly mentioned by retrieved evidence
        houses: Set[str] = set()
        planets: Set[str] = set()
        charts: Set[str] = set()
        concepts: Set[str] = set()

        planet_names = [
            "Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus",
            "Saturn", "Rahu", "Ketu", "Ascendant"
        ]
        house_pattern = re.compile(r"\b(1[0-2]|[1-9])(?:st|nd|rd|th)\s+house\b", re.IGNORECASE)
        chart_pattern = re.compile(r"\bD(?:1|7|9|10|24)\b", re.IGNORECASE)

        for hit in rag_hits:
            text = hit.get("text", "") or ""
            lower = text.lower()

            for planet in planet_names:
                if planet.lower() in lower:
                    planets.add(planet)

            for match in house_pattern.finditer(text):
                houses.add(match.group(1))

            for match in chart_pattern.finditer(text):
                charts.add(match.group(0).upper())

            for phrase in (
                "7th lord", "10th lord", "6th lord", "8th lord",
                "9th lord", "11th lord", "2nd lord", "12th lord",
                "lagna lord", "mahadasha", "antardasha", "dasha", "transit"
            ):
                if phrase in lower:
                    concepts.add(phrase)

        return {"houses": houses, "planets": planets, "charts": charts, "concepts": concepts}

    def _build_targeted_kundli_facts(self, referenced: Dict[str, Set[str]], session: Dict) -> str:
        # Surface only chart facts corresponding to the retrieved framework
        cached_raw = session.get("kundli_raw")
        cached_dasha = session.get("kundli_dasha")
        if not cached_raw:
            return ""

        try:
            parsed = json.loads(cached_raw)
            planets = parsed.get("planets", []) or []
            ascendant_sign = parsed.get("ascendant_sign")
            dasha_info = json.loads(cached_dasha) if cached_dasha else None
        except Exception as e:
            logger.error(f"Failed to parse cached chart data for RAG-first context: {e}")
            return ""

        from app.services.topic_service import get_house_for_sign
        from app.services.kundli_service import get_house_lord

        houses = referenced.get("houses", set())
        planets_wanted = referenced.get("planets", set())
        charts = referenced.get("charts", set())
        concepts = referenced.get("concepts", set())
        lines: List[str] = []

        if ascendant_sign and ("Ascendant" in planets_wanted or houses or "lagna lord" in concepts):
            lines.append(f"Ascendant: {ascendant_sign}")

        if houses and ascendant_sign:
            lines.append("Relevant house facts (selected from retrieved classical evidence):")
            for house_str in sorted(houses, key=lambda x: int(x)):
                house_num = int(house_str)
                lord = get_house_lord(house_num, ascendant_sign)
                occupants = [
                    p.get("name") for p in planets
                    if p.get("name")
                    and get_house_for_sign(p.get("sign_name", ""), ascendant_sign) == house_num
                ]
                occupant_str = f", occupied by {', '.join(occupants)}" if occupants else ""
                lord_str = f"ruled by {lord}" if lord else "lord undetermined"
                lines.append(f"- House {house_num}: {lord_str}{occupant_str}")

        if planets_wanted:
            lines.append("Relevant planet facts (selected from retrieved classical evidence):")
            for planet_name in sorted(planets_wanted):
                if planet_name == "Ascendant":
                    continue
                match = next((p for p in planets if p.get("name") == planet_name), None)
                if not match:
                    continue
                sign = match.get("sign_name", "")
                house = get_house_for_sign(sign, ascendant_sign) if ascendant_sign else None
                house_str = f", house {house}" if house else ""
                retro = " (retrograde)" if str(match.get("isRetro", "")).lower() == "true" else ""
                lines.append(f"- {planet_name}: {sign}{house_str}{retro}")

        if dasha_info and ("dasha" in concepts or "mahadasha" in concepts or "antardasha" in concepts or not lines):
            maha = dasha_info.get("current_mahadasha", {}) or {}
            antar = dasha_info.get("current_antardasha", {}) or {}
            if maha:
                dasha_line = f"Current Dasha: Mahadasha={maha.get('lord')}"
                if antar:
                    dasha_line += f", Antardasha={antar.get('lord')}"
                lines.append(dasha_line)

        if charts:
            lines.append("Divisional charts referenced by classical evidence: " + ", ".join(sorted(charts)))

        return "\n".join(lines)

    def _build_personalized_rag_query(self, message_text: str, topic: Optional[str], targeted_facts: str) -> str:
        # Create a second-stage RAG query using actual chart facts
        parts = [message_text.strip(), "classical astrology interpretation"]
        if topic:
            parts.append(f"topic: {topic}")
        if targeted_facts:
            parts.append("chart configuration:")
            parts.append(targeted_facts)
        return " ".join(p for p in parts if p).strip()

    def _get_rag_first_context(self, message_text: str, topic: Optional[str], session: Dict):
        # Two-stage RAG: Stage 1 retrieves framework -> factors, Stage 2 retrieves personalized evidence
        try:
            from app.services.topic_service import TOPIC_RELEVANT_BOOKS

            framework_query = self._build_framework_query(message_text, topic)
            preferred_sources = TOPIC_RELEVANT_BOOKS.get(topic) if topic else None

            framework_hits = vector_store.dual_retrieve(
                topic_query=framework_query,
                global_query=message_text,
                query_vector_topic=self.embeddings_provider.get_embedding(framework_query),
                query_vector_global=self.embeddings_provider.get_embedding(message_text),
                preferred_sources=preferred_sources,
                top_k_each=6,
                final_top_k=settings.TOP_K_RETRIEVAL,
                alpha=settings.HYBRID_ALPHA,
            )

            framework_hits = [h for h in framework_hits if h["score"] >= settings.MIN_RAG_RELEVANCE]

            if not framework_hits:
                logger.info("[RAGFirst] no sufficiently relevant framework chunks")
                return "No reference available.", [], ""

            framework_rag_hits = []
            framework_chunks = []

            for i, hit in enumerate(framework_hits):
                source = hit["metadata"].get("source", "Unknown")
                page = hit["metadata"].get("page")
                page_label = f", Page: {page}" if page is not None else ""

                framework_chunks.append(
                    f"--- Classical Principle {i+1} [Source: {source}{page_label}, relevance: {hit['score']:.2f}] ---\n{hit['text']}\n"
                )
                framework_rag_hits.append({
                    "source": source, "page": page, "score": hit["score"],
                    "text": hit["text"], "stage": "framework",
                })

            referenced = self._extract_referenced_factors(framework_rag_hits)
            targeted_facts = self._build_targeted_kundli_facts(referenced, session)

            logger.info(
                f"[RAGFirst] framework factors houses={referenced['houses']} "
                f"planets={referenced['planets']} charts={referenced['charts']} concepts={referenced['concepts']}"
            )

            personalized_query = self._build_personalized_rag_query(message_text, topic, targeted_facts)
            personalized_vector = self.embeddings_provider.get_embedding(personalized_query)

            personalized_hits = vector_store.dual_retrieve(
                topic_query=personalized_query,
                global_query=personalized_query,
                query_vector_topic=personalized_vector,
                query_vector_global=personalized_vector,
                preferred_sources=preferred_sources,
                top_k_each=8,
                final_top_k=settings.TOP_K_RETRIEVAL,
                alpha=settings.HYBRID_ALPHA,
            )

            personalized_hits = [h for h in personalized_hits if h["score"] >= settings.MIN_RAG_RELEVANCE]

            personalized_rag_hits = []
            personalized_chunks = []

            for i, hit in enumerate(personalized_hits):
                source = hit["metadata"].get("source", "Unknown")
                page = hit["metadata"].get("page")
                page_label = f", Page: {page}" if page is not None else ""

                personalized_chunks.append(
                    f"--- Personalized Evidence {i+1} [Source: {source}{page_label}, relevance: {hit['score']:.2f}] ---\n{hit['text']}\n"
                )
                personalized_rag_hits.append({
                    "source": source, "page": page, "score": hit["score"],
                    "text": hit["text"], "stage": "personalized",
                })

            all_hits = framework_rag_hits + personalized_rag_hits

            if personalized_chunks:
                context = "\n".join(framework_chunks) + "\n" + "\n".join(personalized_chunks)
            else:
                context = "\n".join(framework_chunks)

            logger.info(f"[RAGFirst] framework={len(framework_rag_hits)}, personalized={len(personalized_rag_hits)}")

            return context, all_hits, targeted_facts

        except Exception as e:
            logger.error(f"RAG-first context build failed: {e}")
            return "No reference available.", [], ""

    def _is_followup_retrieval_question(self, message_text: str, history: List[Dict[str, str]]) -> bool:
        # Detect short evidence-seeking follow-ups such as 'why?'
        if not history:
            return False

        q = message_text.strip().lower()
        triggers = ("why", "how", "explain", "what makes", "what indicates", "reason", "kaise", "kyun", "kyon", "kyu", "kyun hai")

        if q in triggers:
            return True
        if len(q.split()) <= 8 and any(q.startswith(trigger) for trigger in triggers):
            return True
        return False

    def _get_previous_assistant_answer(self, history: List[Dict[str, str]]) -> str:
        for msg in reversed(history):
            if msg.get("role") == "assistant":
                return msg.get("content", "")
        return ""

    def _get_followup_rag_context(self, message_text: str, topic: Optional[str], history: List[Dict[str, str]]):
        # Retrieve evidence specifically supporting the previous answer
        previous_answer = self._get_previous_assistant_answer(history)
        if not previous_answer:
            return "", []

        query = (
            f"{message_text}\nPrevious answer:\n{previous_answer}\n"
            "Retrieve classical evidence supporting or qualifying the claims made in the previous answer."
        )

        try:
            from app.services.topic_service import TOPIC_RELEVANT_BOOKS

            preferred_sources = TOPIC_RELEVANT_BOOKS.get(topic) if topic else None

            hits = vector_store.dual_retrieve(
                topic_query=query,
                global_query=message_text,
                query_vector_topic=self.embeddings_provider.get_embedding(query),
                query_vector_global=self.embeddings_provider.get_embedding(message_text),
                preferred_sources=preferred_sources,
                top_k_each=6,
                final_top_k=settings.TOP_K_RETRIEVAL,
                alpha=settings.HYBRID_ALPHA,
            )

            hits = [h for h in hits if h["score"] >= settings.MIN_RAG_RELEVANCE]

            chunks, rag_hits = [], []

            for i, hit in enumerate(hits):
                source = hit["metadata"].get("source", "Unknown")
                page = hit["metadata"].get("page")
                page_label = f", Page: {page}" if page is not None else ""

                chunks.append(
                    f"--- Follow-up Evidence {i+1} [Source: {source}{page_label}, relevance: {hit['score']:.2f}] ---\n{hit['text']}\n"
                )
                rag_hits.append({
                    "source": source, "page": page, "score": hit["score"],
                    "text": hit["text"], "stage": "followup",
                })

            logger.info(f"[FollowUpRAG] retrieved {len(rag_hits)} supporting chunks")
            return "\n".join(chunks), rag_hits

        except Exception as e:
            logger.error(f"Follow-up RAG failed: {e}")
            return "", []

    def _get_topic_cache(self, session: Dict, topic: str) -> Optional[Dict]:
        raw = session.get("topic_cache")
        if not raw:
            return None
        try:
            cache = json.loads(raw)
            return cache.get(topic)
        except Exception:
            return None

    def _save_topic_cache(self, session_id: str, session: Dict, topic: str, bundle: Dict):
        try:
            raw = session.get("topic_cache")
            cache = json.loads(raw) if raw else {}
            cache[topic] = bundle
            cache_json = json.dumps(cache, ensure_ascii=False)
            db.update_session(session_id, {"topic_cache": cache_json})
            session["topic_cache"] = cache_json
        except Exception as e:
            logger.error(f"Failed to save topic cache for '{topic}': {e}")

    def _get_topic_bundle(self, session_id: str, session: Dict, topic: Optional[str], language: str) -> Dict[str, Any]:
        # Returns cached bundle if already computed this session, else computes once and caches
        empty = {"emphasis": "", "divisional": "", "consistency": "", "missing_evidence": "", "timeline": "", "evidence_vote": None, "consensus_label": "LOW"}
        if not topic:
            return empty

        cached = self._get_topic_cache(session, topic)
        if cached is not None:
            logger.info(f"Using cached topic bundle for '{topic}'")
            if "evidence_vote" not in cached:
                cached["evidence_vote"] = None
            if "consensus_label" not in cached:
                cached["consensus_label"] = get_evidence_consensus_label(cached.get("evidence_vote"))
            return cached

        bundle = dict(empty)
        try:
            cached_raw = session.get("kundli_raw")
            cached_dasha = session.get("kundli_dasha")
            if cached_raw:
                parsed = json.loads(cached_raw)
                planets = parsed.get("planets", [])
                ascendant_sign = parsed.get("ascendant_sign")
                dasha_info = json.loads(cached_dasha) if cached_dasha else None

                if planets and ascendant_sign:
                    bundle["emphasis"] = build_topic_emphasis(topic, planets, ascendant_sign, None)

                from app.services.topic_service import build_consistency_check, build_consistency_note, build_missing_evidence_note
                check = build_consistency_check(topic, planets, ascendant_sign, dasha_info)
                bundle["consistency"] = build_consistency_note(check, topic)

                yoga_text_for_vote = session.get("yoga_text") or ""
                vote = build_evidence_vote(topic, planets, ascendant_sign, dasha_info, yoga_text=yoga_text_for_vote)
                bundle["evidence_vote"] = vote

                consensus_label = get_evidence_consensus_label(vote)
                bundle["consensus_label"] = consensus_label

                vote_text = format_evidence_vote_for_prompt(vote, topic)
                if vote_text:
                    bundle["consistency"] = (
                        f"{bundle['consistency']}\n\n{vote_text}\n\n{get_consensus_instruction(consensus_label)}"
                        if bundle["consistency"] else f"{vote_text}\n\n{get_consensus_instruction(consensus_label)}"
                    )

                config = TOPIC_CHART_FACTORS.get(topic, {})
                chart_code = config.get("divisional_chart")
                if chart_code:
                    kundli_data = self._get_full_kundli_response(session_id, session)
                    if kundli_data:
                        purpose_map = {"D9": "marriage", "D10": "career", "D24": "education", "D7": "children"}
                        bundle["divisional"] = kundli_service.summarize_divisional_chart(
                            kundli_data, chart_code, purpose_map.get(chart_code, chart_code)
                        )

                bundle["missing_evidence"] = build_missing_evidence_note(topic, planets, ascendant_sign, dasha_info, bundle["divisional"])

            bundle["timeline"] = self._get_dasha_timeline(session_id, session, topic, language)
        except Exception as e:
            logger.error(f"Topic bundle build failed for '{topic}': {e}")

        self._save_topic_cache(session_id, session, topic, bundle)
        return bundle

    def _get_dasha_timeline(self, session_id: str, session: Dict, topic: Optional[str], language: str) -> str:
        if not topic:
            return ""
        try:
            cached_tree_raw = session.get("dasha_tree_raw")
            dasha_tree = None
            if cached_tree_raw:
                try:
                    dasha_tree = json.loads(cached_tree_raw)
                except Exception:
                    dasha_tree = None

            if dasha_tree is None:
                time_24h = self._to_24h(session.get("birth_time", ""))
                coords_lat = session.get("latitude")
                coords_lon = session.get("longitude")
                if not (coords_lat and coords_lon):
                    return ""

                kundli_raw_full = self._get_full_kundli_response(session_id, session)
                ascendant_data = kundli_service.get_ascendant_data(kundli_raw_full) if kundli_raw_full else None
                if not ascendant_data:
                    logger.warning("Could not extract ascendant_data — skipping dasha timeline")
                    return ""

                dasha_tree = dasha_api_service.fetch_dasha_tree(
                    date=session.get("dob"), time=time_24h,
                    latitude=coords_lat, longitude=coords_lon,
                    ascendant_data=ascendant_data,
                )
                if not dasha_tree:
                    return ""

                tree_json = json.dumps(dasha_tree, ensure_ascii=False)
                db.update_session(session_id, {"dasha_tree_raw": tree_json})
                session["dasha_tree_raw"] = tree_json

            upcoming = dasha_api_service.get_upcoming_periods(dasha_tree, months_ahead=60)
            favorable = rank_favorable_periods(upcoming, topic)
            timeline_str = format_dasha_timeline_for_prompt(upcoming, favorable, language)
            logger.info(f"Dasha timeline built for topic '{topic}': {len(upcoming)} periods, {len(favorable)} favorable")
            return timeline_str
        except Exception as dasha_err:
            logger.error(f"Dasha timeline fetch failed: {dasha_err}")
            return ""

    def _get_yoga_text(self, session: Dict) -> str:
        return session.get("yoga_text") or ""

    def _build_final_kundli_data(self, kundli_str: str, topic_emphasis: str, divisional_text: str,
                                   yoga_text: str, missing_evidence: str = "") -> str:
        parts = [p for p in [kundli_str, topic_emphasis, divisional_text, yoga_text, missing_evidence] if p]
        return "\n\n".join(parts)

    def _get_recent_assistant_texts(self, session_id: str, limit: int = 5) -> List[str]:
        history = db.get_history(session_id, limit=20)
        assistant_msgs = [m["content"] for m in history if m["role"] == "assistant"]
        return assistant_msgs[-limit:]

    def _similarity_ratio(self, text_a: str, text_b: str) -> float:
        a = text_a.strip().lower()
        b = text_b.strip().lower()
        if not a or not b:
            return 0.0
        return SequenceMatcher(None, a, b).ratio()

    def _is_too_similar(self, response_text: str, recent_texts: List[str], threshold: float = 0.75) -> Optional[str]:
        for prior in recent_texts:
            if self._similarity_ratio(response_text, prior) >= threshold:
                return prior
        return None

    def _get_repeat_topic_hint(self, session: Dict, topic: Optional[str]) -> str:
        if not topic:
            return ""
        try:
            raw = session.get("topic_memory")
            if not raw:
                return ""
            memory = json.loads(raw)
            prior_summary = memory.get(topic)
            if not prior_summary:
                return ""
            return (
                f"IMPORTANT — Avoid repetition: You already answered a {topic} question earlier "
                f"in this conversation, with reasoning along these lines: \"{prior_summary}\". "
                f"This new question is related but distinct — answer what's SPECIFICALLY being "
                f"asked now. Do not restate the same facts/wording again; build on or add to what "
                f"was already said, or focus on a different angle (timing, specific action, etc.)."
            )
        except Exception as e:
            logger.error(f"Repeat-topic hint build failed: {e}")
            return ""

    def _get_user_memory_block(self, session: Dict, current_topic: Optional[str]) -> str:
        try:
            raw = session.get("topic_memory")
            if not raw:
                return ""
            memory = json.loads(raw)
            if not memory:
                return ""
            lines = []
            for topic, summary in memory.items():
                if topic == current_topic:
                    continue
                lines.append(f"- {topic.capitalize()}: {summary}")
            if not lines:
                return ""
            return "Earlier in this conversation, you already discussed:\n" + "\n".join(lines)
        except Exception as e:
            logger.error(f"Failed to build user memory block: {e}")
            return ""

    def _update_topic_memory(self, session_id: str, session: Dict, topic: Optional[str], response_text: str):
        if not topic or not response_text:
            return
        try:
            raw = session.get("topic_memory")
            memory = json.loads(raw) if raw else {}
            truncated = response_text.strip().replace("\n", " ")
            if len(truncated) > 150:
                truncated = truncated[:150].rsplit(" ", 1)[0] + "..."
            memory[topic] = truncated
            memory_json = json.dumps(memory, ensure_ascii=False)
            db.update_session(session_id, {"topic_memory": memory_json})
            session["topic_memory"] = memory_json
            logger.info(f"Updated topic_memory['{topic}']")
        except Exception as e:
            logger.error(f"Failed to update topic memory: {e}")

    def _safe_generate_followups(self, response_text: str, language: str) -> List[str]:
        try:
            return llm_service.generate_followups(response_text, language) or []
        except Exception as followup_err:
            logger.error(f"Follow-up suggestion generation failed: {followup_err}")
            return []

    def _try_explain_chart(self, session_id: str, session: Dict, message_text: str, language: str) -> Optional[str]:
        # Shared full-chart-explanation handler for non-streaming path
        cached_kundli = session.get("kundli_data")
        if not cached_kundli:
            self._fetch_and_cache_kundli(session_id, session)

        full_chart_data = self._build_full_chart_explanation(session)
        context_str, _ = self._get_rag_context(
            "houses planets lords yogas nakshatra dasha meaning explanation", None
        )

        try:
            prompt = EXPLAIN_CHART_PROMPT.format(
                name=session.get("name") or "Friend", language=language,
                full_chart_data=full_chart_data or "No chart data available.",
                context=context_str or "No book context."
            )
            return llm_service.generate(prompt=prompt, temperature=0.5)
        except Exception as gen_err:
            logger.error(f"Chart explanation generation failed: {gen_err}")
            return "Mujhe samajhne mein kuch pareshani ho gayi."

    # ------------------------------------------------------------------
    # NON-STREAMING — POST /api/chat
    # ------------------------------------------------------------------
    def process_chat_message(self, session_id: str, message_text: str) -> Dict[str, Any]:
        logger.info(f"Processing chat message for session: {session_id}")
        try:
            session = db.get_or_create_session(session_id)
            history = db.get_history(session_id, limit=10)
            history_text = self._format_history_for_llm(history)

            profile_complete = bool(session.get("dob") and session.get("birth_time") and session.get("birth_place"))

            if profile_complete:
                logger.info("Profile already complete — skipping extraction step")
                is_astrology = True
                language = session.get("language", "Hinglish")
                db.add_message(session_id, "user", message_text)
                missing_fields = []
            else:
                try:
                    extracted = llm_service.extract_profile_details(message_text, history_text)
                except Exception as extract_err:
                    logger.error(f"Profile extraction failed: {extract_err}")
                    extracted = {"dob": None, "birth_time": None, "birth_place": None, "language": "Hinglish", "is_astrology_query": True}

                updates = {}
                for key in ["dob", "birth_time", "birth_place"]:
                    if extracted.get(key):
                        updates[key] = extracted[key]
                        session[key] = extracted[key]
                if extracted.get("language"):
                    updates["language"] = extracted["language"]
                    session["language"] = extracted["language"]
                if updates:
                    db.update_session(session_id, updates)

                language = session.get("language", "Hinglish")
                db.add_message(session_id, "user", message_text)

                is_astrology = extracted.get("is_astrology_query", True)
                missing_fields = []
                if not session.get("dob"):
                    missing_fields.append(("Date of Birth", "dob"))
                if not session.get("birth_time"):
                    missing_fields.append(("Birth Time", "birth_time"))
                if not session.get("birth_place"):
                    missing_fields.append(("Birth Place", "birth_place"))

                if is_astrology and missing_fields:
                    next_missing_name, _ = missing_fields[0]
                    try:
                        prompt = MISSING_INFO_PROMPT.format(missing_detail=next_missing_name, language=language)
                        response_text = llm_service.generate(prompt=prompt, temperature=0.3)
                    except Exception as llm_err:
                        logger.error(f"LLM failed: {llm_err}")
                        response_text = f"Kripya apna {next_missing_name} batayein."
                    db.add_message(session_id, "assistant", response_text)
                    return {
                        "session_id": session_id, "message": response_text,
                        "dob": session.get("dob"), "birth_time": session.get("birth_time"),
                        "birth_place": session.get("birth_place"), "language": language
                    }

            # Explain-chart requests handled here regardless of whether the
            # profile was already complete or just completed this turn (bug fix).
            if is_astrology and not missing_fields and is_explain_chart_request(message_text):
                logger.info("Explain-chart request detected — full chart mode")
                response_text = self._try_explain_chart(session_id, session, message_text, language)
                db.add_message(session_id, "assistant", response_text)
                return {
                    "session_id": session_id, "message": response_text,
                    "dob": session.get("dob"), "birth_time": session.get("birth_time"),
                    "birth_place": session.get("birth_place"), "language": language,
                    "suggestions": []
                }

            topic = classify_topic(message_text) if (is_astrology and not missing_fields) else None
            intent = classify_intent(message_text) if (is_astrology and not missing_fields) else "general"
            response_contract = get_response_contract(intent)

            context_str = ""
            rag_hits: List[Dict[str, Any]] = []
            targeted_facts = ""

            kundli_str = "No chart data available."
            if is_astrology and not missing_fields:
                cached_kundli = session.get("kundli_data")
                kundli_str = cached_kundli if cached_kundli else self._fetch_and_cache_kundli(session_id, session)

            # RAG-first: the knowledge base determines which chart factors matter before those facts are supplied to the LLM
            if is_astrology and not missing_fields:
                if self._is_followup_retrieval_question(message_text, history):
                    context_str, rag_hits = self._get_followup_rag_context(message_text, topic, history)

                if not rag_hits:
                    context_str, rag_hits, targeted_facts = self._get_rag_first_context(message_text, topic, session)

                logger.info(f"[RAGPipeline] hits={len(rag_hits)} targeted_facts={'yes' if targeted_facts else 'no'}")

            yoga_text = self._get_yoga_text(session) if (is_astrology and not missing_fields) else ""

            topic_emphasis = divisional_text = consistency_note = missing_evidence = dasha_timeline_str = ""
            evidence_vote = None
            if is_astrology and not missing_fields and topic:
                bundle = self._get_topic_bundle(session_id, session, topic, language)
                topic_emphasis = bundle["emphasis"]
                divisional_text = bundle["divisional"]
                consistency_note = bundle["consistency"]
                missing_evidence = bundle["missing_evidence"]
                dasha_timeline_str = bundle["timeline"]
                evidence_vote = bundle.get("evidence_vote")

            final_kundli_data = self._build_final_kundli_data(kundli_str, topic_emphasis, divisional_text, yoga_text, missing_evidence)
            if targeted_facts:
                final_kundli_data = f"{final_kundli_data}\n\n{targeted_facts}" if final_kundli_data else targeted_facts

            user_memory = self._get_user_memory_block(session, topic) if (is_astrology and not missing_fields) else ""

            try:
                astrologer_prompt = ASTROLOGER_PROMPT.format(
                    name=session.get("name") or "Friend",
                    language=language, dob=session.get("dob") or "Not provided",
                    birth_time=session.get("birth_time") or "Not provided",
                    birth_place=session.get("birth_place") or "Not provided",
                    context=context_str or "No book context.", kundli_data=final_kundli_data,
                    user_memory=user_memory or "No prior topics discussed yet.",
                    consistency_note=consistency_note or "No specific conflict detected.",
                    dasha_timeline=dasha_timeline_str or "No timeline data available.",
                    response_contract=response_contract,
                    history=history_text, query=message_text
                )
                response_text = llm_service.generate(prompt=astrologer_prompt, temperature=0.6)

                if is_astrology and not missing_fields:
                    recent_texts = self._get_recent_assistant_texts(session_id)
                    similar_to = self._is_too_similar(response_text, recent_texts)

                    claim_failures = validate_claims(response_text, dasha_timeline_str, evidence_vote)

                    specificity_score = compute_chart_specificity(response_text)
                    specificity_correction = build_specificity_correction(specificity_score)
                    if specificity_correction:
                        logger.info(f"[Specificity] response flagged as generic: ratio={specificity_score['specificity_ratio']}")

                    if similar_to or claim_failures or specificity_correction:
                        retry_prompt = astrologer_prompt
                        if similar_to:
                            retry_prompt += (
                                f"\n\nIMPORTANT: Your previous response was very similar to this one:\n"
                                f"\"{similar_to}\"\n"
                                f"Express the same astrological reasoning but do NOT repeat the same wording. "
                                f"Focus specifically on what's different about the CURRENT question."
                            )
                        if claim_failures:
                            logger.info(f"Claim validation found {len(claim_failures)} issue(s) — regenerating with corrections")
                            retry_prompt += "\n\n" + build_claim_correction_instructions(claim_failures)
                        if specificity_correction:
                            retry_prompt += "\n\n" + specificity_correction

                        response_text = llm_service.generate(prompt=retry_prompt, temperature=0.75)

                        remaining = validate_claims(response_text, dasha_timeline_str, evidence_vote)
                        if remaining:
                            logger.warning(f"Claim validation still found {len(remaining)} issue(s) after regeneration")
            except Exception as gen_err:
                logger.error(f"Generation failed: {gen_err}")
                response_text = "Mujhe samajhne mein kuch pareshani ho gayi."

            db.add_message(session_id, "assistant", response_text)

            if is_astrology and not missing_fields:
                try:
                    trace = self._build_reasoning_trace(session, topic, rag_hits, targeted_facts)
                    db.update_session(session_id, {"last_reasoning_trace": json.dumps(trace)})
                except Exception as trace_err:
                    logger.error(f"Reasoning trace caching failed: {trace_err}")
                self._update_topic_memory(session_id, session, topic, response_text)

            suggestions = []
            if response_text and len(response_text) > 20:
                suggestions = self._safe_generate_followups(response_text, language)

            return {
                "session_id": session_id, "message": response_text,
                "dob": session.get("dob"), "birth_time": session.get("birth_time"),
                "birth_place": session.get("birth_place"), "language": language,
                "suggestions": suggestions
            }

        except Exception as e:
            logger.error(f"Chat processing error: {e}")
            return {"session_id": session_id, "message": "Kripya dobara koshish karein.",
                    "dob": None, "birth_time": None, "birth_place": None, "language": "Hinglish"}

    # ------------------------------------------------------------------
    # STREAMING — POST /api/chat/stream
    # ------------------------------------------------------------------
    def process_chat_message_stream(self, session_id: str, message_text: str):
        logger.info(f"Processing chat message (stream) for session: {session_id}")
        try:
            session = db.get_or_create_session(session_id)
            history = db.get_history(session_id, limit=10)
            history_text = self._format_history_for_llm(history)

            profile_complete = bool(session.get("dob") and session.get("birth_time") and session.get("birth_place"))

            if profile_complete:
                logger.info("Profile already complete — skipping extraction step")
                is_astrology = True
                language = session.get("language", "Hinglish")
                db.add_message(session_id, "user", message_text)
                missing_fields = []
            else:
                try:
                    extracted = llm_service.extract_profile_details(message_text, history_text)
                except Exception as extract_err:
                    logger.error(f"Profile extraction failed: {extract_err}")
                    extracted = {"dob": None, "birth_time": None, "birth_place": None, "language": "Hinglish", "is_astrology_query": True}

                updates = {}
                for key in ["dob", "birth_time", "birth_place"]:
                    if extracted.get(key):
                        updates[key] = extracted[key]
                        session[key] = extracted[key]
                if extracted.get("language"):
                    updates["language"] = extracted["language"]
                    session["language"] = extracted["language"]
                if updates:
                    db.update_session(session_id, updates)

                language = session.get("language", "Hinglish")
                db.add_message(session_id, "user", message_text)

                is_astrology = extracted.get("is_astrology_query", True)
                missing_fields = []
                if not session.get("dob"):
                    missing_fields.append(("Date of Birth", "dob"))
                if not session.get("birth_time"):
                    missing_fields.append(("Birth Time", "birth_time"))
                if not session.get("birth_place"):
                    missing_fields.append(("Birth Place", "birth_place"))

                if is_astrology and missing_fields:
                    next_missing_name, _ = missing_fields[0]
                    prompt = MISSING_INFO_PROMPT.format(missing_detail=next_missing_name, language=language)
                    full_text = ""
                    try:
                        for token in llm_service.generate_stream(prompt=prompt, temperature=0.3):
                            full_text += token
                            yield {"type": "chunk", "text": token}
                    except Exception as llm_err:
                        logger.error(f"LLM stream failed: {llm_err}")
                        full_text = f"Kripya apna {next_missing_name} batayein."
                        yield {"type": "chunk", "text": full_text}

                    db.add_message(session_id, "assistant", full_text)
                    yield {"type": "done", "session_id": session_id, "message": full_text,
                           "dob": session.get("dob"), "birth_time": session.get("birth_time"),
                           "birth_place": session.get("birth_place"), "language": language}
                    return

            # Explain-chart requests handled here regardless of whether the
            # profile was already complete or just completed this turn (bug fix).
            if is_astrology and not missing_fields and is_explain_chart_request(message_text):
                logger.info("Explain-chart request detected — full chart mode (streaming)")
                cached_kundli = session.get("kundli_data")
                if not cached_kundli:
                    self._fetch_and_cache_kundli(session_id, session)

                full_chart_data = self._build_full_chart_explanation(session)
                context_str, _ = self._get_rag_context(
                    "houses planets lords yogas nakshatra dasha meaning explanation", None
                )

                prompt = EXPLAIN_CHART_PROMPT.format(
                    name=session.get("name") or "Friend", language=language,
                    full_chart_data=full_chart_data or "No chart data available.",
                    context=context_str or "No book context."
                )

                full_text = ""
                try:
                    for token in llm_service.generate_stream(prompt=prompt, temperature=0.5):
                        full_text += token
                        yield {"type": "chunk", "text": token}
                except Exception as gen_err:
                    logger.error(f"Chart explanation streaming failed: {gen_err}")
                    full_text = "Mujhe samajhne mein kuch pareshani ho gayi."
                    yield {"type": "chunk", "text": full_text}

                db.add_message(session_id, "assistant", full_text)
                yield {"type": "done", "session_id": session_id, "message": full_text,
                       "dob": session.get("dob"), "birth_time": session.get("birth_time"),
                       "birth_place": session.get("birth_place"), "language": language,
                       "suggestions": []}
                return

            topic = classify_topic(message_text) if (is_astrology and not missing_fields) else None
            intent = classify_intent(message_text) if (is_astrology and not missing_fields) else "general"
            response_contract = get_response_contract(intent)

            context_str = ""
            rag_hits: List[Dict[str, Any]] = []
            targeted_facts = ""

            kundli_str = "No chart data available."
            if is_astrology and not missing_fields:
                cached_kundli = session.get("kundli_data")
                kundli_str = cached_kundli if cached_kundli else self._fetch_and_cache_kundli(session_id, session)

            if is_astrology and not missing_fields:
                if self._is_followup_retrieval_question(message_text, history):
                    context_str, rag_hits = self._get_followup_rag_context(message_text, topic, history)

                if not rag_hits:
                    context_str, rag_hits, targeted_facts = self._get_rag_first_context(message_text, topic, session)

                logger.info(f"[RAGPipeline] hits={len(rag_hits)} targeted_facts={'yes' if targeted_facts else 'no'}")

            yoga_text = self._get_yoga_text(session) if (is_astrology and not missing_fields) else ""

            topic_emphasis = divisional_text = consistency_note = missing_evidence = dasha_timeline_str = ""
            evidence_vote = None
            if is_astrology and not missing_fields and topic:
                bundle = self._get_topic_bundle(session_id, session, topic, language)
                topic_emphasis = bundle["emphasis"]
                divisional_text = bundle["divisional"]
                consistency_note = bundle["consistency"]
                missing_evidence = bundle["missing_evidence"]
                dasha_timeline_str = bundle["timeline"]
                evidence_vote = bundle.get("evidence_vote")

            final_kundli_data = self._build_final_kundli_data(kundli_str, topic_emphasis, divisional_text, yoga_text, missing_evidence)
            if targeted_facts:
                final_kundli_data = f"{final_kundli_data}\n\n{targeted_facts}" if final_kundli_data else targeted_facts

            user_memory = ""
            repeat_hint = ""
            if is_astrology and not missing_fields:
                user_memory = self._get_user_memory_block(session, topic)
                repeat_hint = self._get_repeat_topic_hint(session, topic)

            astrologer_prompt = ASTROLOGER_PROMPT.format(
                name=session.get("name") or "Friend",
                language=language, dob=session.get("dob") or "Not provided",
                birth_time=session.get("birth_time") or "Not provided",
                birth_place=session.get("birth_place") or "Not provided",
                context=context_str or "No book context.", kundli_data=final_kundli_data,
                user_memory=user_memory or "No prior topics discussed yet.",
                consistency_note=consistency_note or "No specific conflict detected.",
                dasha_timeline=dasha_timeline_str or "No timeline data available.",
                response_contract=response_contract,
                history=history_text, query=message_text
            )
            if repeat_hint:
                astrologer_prompt += f"\n\n{repeat_hint}"

            gen_temperature = 0.75 if repeat_hint else 0.6

            full_text = ""
            try:
                for token in llm_service.generate_stream(prompt=astrologer_prompt, temperature=gen_temperature):
                    full_text += token
                    yield {"type": "chunk", "text": token}
            except Exception as gen_err:
                logger.error(f"Streaming generation failed: {gen_err}")
                full_text = "Mujhe samajhne mein kuch pareshani ho gayi."
                yield {"type": "chunk", "text": full_text}

            db.add_message(session_id, "assistant", full_text)

            # Claim validation + specificity check are LOG-ONLY here — tokens
            # are already streamed, so there's nothing left to regenerate cleanly.
            if is_astrology and not missing_fields:
                try:
                    claim_failures = validate_claims(full_text, dasha_timeline_str, evidence_vote)
                    if claim_failures:
                        logger.warning(f"Claim validation found {len(claim_failures)} issue(s) in streamed response (not corrected — log only): {claim_failures}")

                    specificity_score = compute_chart_specificity(full_text)
                    if specificity_score["is_generic"]:
                        logger.warning(f"[Specificity] streamed response flagged as generic: ratio={specificity_score['specificity_ratio']} (not corrected — log only)")
                except Exception as validate_err:
                    logger.error(f"Claim validation failed: {validate_err}")

            if is_astrology and not missing_fields:
                try:
                    trace = self._build_reasoning_trace(session, topic, rag_hits, targeted_facts)
                    db.update_session(session_id, {"last_reasoning_trace": json.dumps(trace)})
                except Exception as trace_err:
                    logger.error(f"Reasoning trace caching failed: {trace_err}")
                self._update_topic_memory(session_id, session, topic, full_text)

            suggestions = get_instant_suggestions(topic, language)

            yield {"type": "done", "session_id": session_id, "message": full_text,
                   "dob": session.get("dob"), "birth_time": session.get("birth_time"),
                   "birth_place": session.get("birth_place"), "language": language,
                   "suggestions": suggestions}

        except Exception as e:
            logger.error(f"Chat streaming error: {e}")
            fallback = "Kripya dobara koshish karein."
            yield {"type": "chunk", "text": fallback}
            yield {"type": "done", "session_id": session_id, "message": fallback,
                   "dob": None, "birth_time": None, "birth_place": None, "language": "Hinglish"}

    def _build_reasoning_trace(self, session: Dict, topic: Optional[str],
                                rag_hits: Optional[List[Dict[str, Any]]] = None, targeted_facts: str = "") -> list:
        # Builds an auditable trace of the RAG-first pipeline
        if not topic and not rag_hits:
            return []

        try:
            rag_hits = rag_hits or []
            referenced = self._extract_referenced_factors(rag_hits)

            houses = sorted(referenced.get("houses", set()), key=lambda x: int(x))
            planets = sorted(referenced.get("planets", set()))
            charts = sorted(referenced.get("charts", set()))
            concepts = sorted(referenced.get("concepts", set()))

            steps = []

            framework_lines = []
            if houses:
                house_labels = []
                for h in houses:
                    n = int(h)
                    suffix = "st" if n == 1 else "nd" if n == 2 else "rd" if n == 3 else "th"
                    house_labels.append(f"{h}{suffix}")
                framework_lines.append(f"Houses: {', '.join(house_labels)}")
            if planets:
                framework_lines.append(f"Planets: {', '.join(planets)}")
            if charts:
                framework_lines.append(f"Divisional charts: {', '.join(charts)}")
            if concepts:
                framework_lines.append(f"Concepts: {', '.join(concepts)}")

            if framework_lines:
                framework_detail = (
                    "RAG retrieved classical sources and identified the following factors as relevant:\n"
                    + "\n".join(f"• {line}" for line in framework_lines)
                )
            else:
                framework_detail = "RAG retrieved classical sources, but no specific chart factors were confidently identified."

            steps.append({"step": 1, "title": "Classical Framework Retrieved", "detail": framework_detail, "type": "rag"})

            if targeted_facts:
                chart_detail = (
                    "The user's Kundli was examined for the factors identified by the retrieved classical sources.\n\n"
                    + targeted_facts
                )
            else:
                chart_detail = "No targeted chart facts were identified from the retrieved classical framework."

            steps.append({"step": 2, "title": "Relevant Chart Factors", "detail": chart_detail, "type": "chart"})

            personalized_hits = [hit for hit in rag_hits if hit.get("stage") == "personalized"]
            if personalized_hits:
                personalized_sources = []
                seen_personalized = set()
                for hit in personalized_hits:
                    source = hit.get("source", "Unknown source")
                    page = hit.get("page")
                    key = (source, page)
                    if key in seen_personalized:
                        continue
                    seen_personalized.add(key)
                    reference = f"{source} — Page {page}" if page is not None else source
                    personalized_sources.append(f"• {reference}")

                personalized_detail = (
                    "A second retrieval pass used the actual chart facts identified in Stage 1 "
                    "to find classical evidence specific to this chart configuration."
                )
                if personalized_sources:
                    personalized_detail += "\n\n" + "\n".join(personalized_sources)
            else:
                personalized_detail = "No additional personalized evidence was retrieved."

            steps.append({"step": 3, "title": "Personalized Evidence Retrieved", "detail": personalized_detail, "type": "personalized_rag"})

            dasha_detail = ""
            try:
                cached_dasha = session.get("kundli_dasha")
                if cached_dasha:
                    dasha_info = json.loads(cached_dasha)
                    maha = dasha_info.get("current_mahadasha", {}) or {}
                    antar = dasha_info.get("current_antardasha", {}) or {}
                    maha_lord = maha.get("lord") or maha.get("name") or maha.get("planet")
                    antar_lord = antar.get("lord") or antar.get("name") or antar.get("planet")
                    if maha_lord:
                        dasha_detail = f"Mahadasha: {maha_lord}"
                    if antar_lord:
                        dasha_detail += f"\nAntardasha: {antar_lord}"
            except Exception as dasha_err:
                logger.warning(f"Could not build Dasha reasoning trace: {dasha_err}")

            if not dasha_detail:
                dasha_detail = "Current Dasha information was not available in the cached chart data."

            steps.append({"step": 4, "title": "Dasha & Timing", "detail": dasha_detail, "type": "dasha"})

            reference_lines = []
            seen_references = set()
            for hit in rag_hits:
                source = hit.get("source", "Unknown source")
                page = hit.get("page")
                score = hit.get("score")
                stage = hit.get("stage")
                reference_key = (source, page, stage)
                if reference_key in seen_references:
                    continue
                seen_references.add(reference_key)
                reference = f"{source} — Page {page}" if page is not None else source
                if score is not None:
                    try:
                        reference += f" (relevance: {float(score):.2f})"
                    except (TypeError, ValueError):
                        pass
                if stage:
                    reference += f" [{stage}]"
                reference_lines.append(f"• {reference}")

            evidence_detail = "\n".join(reference_lines) if reference_lines else "No classical references were available."
            steps.append({"step": 5, "title": "Classical Evidence", "detail": evidence_detail, "type": "evidence"})

            synthesis_lines = []
            try:
                if topic:
                    topic_cache = self._get_topic_cache(session, topic)
                    if topic_cache:
                        evidence_vote = topic_cache.get("evidence_vote")
                        consistency = topic_cache.get("consistency", "")
                        consensus_label = topic_cache.get("consensus_label")

                        if isinstance(evidence_vote, dict):
                            for v in evidence_vote.get("votes", []):
                                direction = "Supportive" if v["vote"] > 0 else ("Challenging" if v["vote"] < 0 else "Neutral")
                                synthesis_lines.append(f"{v['source']}: {direction}")
                            confidence = evidence_vote.get("confidence_pct")
                            verdict = evidence_vote.get("verdict")
                            if confidence is not None:
                                synthesis_lines.append(f"Overall confidence: {confidence}%")
                            if verdict:
                                synthesis_lines.append(f"Overall verdict: {verdict}")
                        elif evidence_vote:
                            synthesis_lines.append(str(evidence_vote))

                        if consensus_label:
                            synthesis_lines.append(f"Evidence consensus: {consensus_label}")

                        if consistency:
                            synthesis_lines.append(f"\nSignal consistency:\n{consistency}")
            except Exception as evidence_err:
                logger.warning(f"Could not build evidence synthesis trace: {evidence_err}")

            if not synthesis_lines:
                synthesis_lines.append(
                    "The final interpretation combines the retrieved classical evidence "
                    "with the relevant Kundli and Dasha information."
                )

            steps.append({"step": 6, "title": "Evidence Synthesis", "detail": "\n".join(synthesis_lines), "type": "synthesis"})

            logger.info(f"[RAGFirst] Reasoning trace built: {len(steps)} steps")
            return steps

        except Exception as e:
            logger.error(f"RAG-first reasoning trace build failed: {e}")
            return []

    def _get_full_kundli_response(self, session_id: str, session: Dict) -> Optional[Dict]:
        cached_full_raw = session.get("kundli_full_raw")
        if cached_full_raw:
            try:
                return json.loads(cached_full_raw)
            except Exception as e:
                logger.error(f"Failed to parse cached kundli_full_raw: {e}")

        self._fetch_and_cache_kundli(session_id, session)
        cached_full_raw = session.get("kundli_full_raw")
        if cached_full_raw:
            try:
                return json.loads(cached_full_raw)
            except Exception:
                return None
        return None

    def _build_full_chart_explanation(self, session: Dict) -> str:
        try:
            cached_raw = session.get("kundli_raw")
            cached_dasha = session.get("kundli_dasha")
            if not cached_raw:
                return ""
            parsed = json.loads(cached_raw)
            planets = parsed.get("planets", [])
            ascendant_sign = parsed.get("ascendant_sign")
            dasha_info = json.loads(cached_dasha) if cached_dasha else None
            yoga_text = session.get("yoga_text") or ""

            from app.services.chat_explainer_service import build_full_chart_data
            return build_full_chart_data(planets, ascendant_sign, dasha_info, None, yoga_text)
        except Exception as e:
            logger.error(f"Full chart explanation build failed: {e}")
            return ""


chat_service = ChatService()