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
from app.services.claim_validator import validate_claims, build_claim_correction_instructions, build_streamed_correction_note
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


TOPIC_BUNDLE_LOGIC_VERSION = 3
FRAMEWORK_CACHE_VERSION = 1

DEDUP_SIMILARITY_THRESHOLD = 0.90

FRAMEWORK_MAX_HITS_BASE = 6
PERSONALIZED_MAX_HITS_BASE = 6
COMPARISON_MAX_HITS_PER_BRANCH_BASE = 3

DEPTH_MIN_HITS = 3
DEPTH_MAX_HITS = 12

MONTH_NAME_TO_NUM = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
    'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12,
}

COMPARISON_HINT_WORDS = (" or ", " ya ", " vs ", " versus ", "अथवा", " ki jagah ", " nahi to ")

STAGE_TO_BUCKET = {
    "framework": "classical_rule",
    "personalized": "classical_rule",
    "comparison": "classical_rule",
    "followup": "classical_rule",
}

BUCKET_LABELS = {
    "classical_rule": "Classical Rules (from retrieved books)",
    "dasha_timing": "Dasha / Timing Evidence",
    "yoga": "Yoga Evidence",
    "chart_fact": "Verified Chart Facts",
}

PLANET_NAMES = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"]

# --- Evidence Sufficiency Gate thresholds ---
# Deterministic count of independent evidence signals available for this
# specific answer. Below MIN_SUFFICIENT_SIGNALS, the model is instructed to
# hedge explicitly rather than sound confident on thin evidence.
MIN_SUFFICIENT_SIGNALS = 2
MIN_UNIQUE_SOURCES_FOR_STRONG = 2


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

    def _build_temporal_context(self) -> str:
        today_str = datetime.now().strftime("%d %B %Y")
        return (
            f"CURRENT DATE: {today_str}\n\n"
            "TEMPORAL RULE (apply to every date/period you mention):\n"
            "- Never describe a date or period BEFORE the current date above as upcoming, "
            "forthcoming, or something that 'will' happen — it has already occurred or passed.\n"
            "- If retrieved classical evidence or a Dasha sub-period points to a window that has "
            "already passed, say so explicitly (e.g. 'this window has already passed') instead of "
            "presenting it as a future prediction.\n"
            "- For questions using words like 'when', 'next', 'upcoming', or 'in the coming "
            "months/years', only present periods that START AFTER the current date above as "
            "genuine future possibilities.\n"
            "- A past period from retrieved evidence can still be used as historical/contextual "
            "explanation (e.g. 'the chart showed favorable signs during that window, and the "
            "current period continues that trend'), just never framed as something yet to happen."
        )

    def _check_past_date_claims(self, response_text: str) -> Optional[str]:
        if not response_text:
            return None
        now = datetime.now()
        year_pattern = re.compile(r'\b(20\d{2})\b')
        issues: List[str] = []
        seen_spans = set()

        for match in year_pattern.finditer(response_text):
            year = int(match.group(1))
            span_key = match.start()
            if span_key in seen_spans:
                continue
            seen_spans.add(span_key)

            context_start = max(0, match.start() - 40)
            context = response_text[context_start:match.end()]
            context_lower = context.lower()

            found_month = None
            for name, num in MONTH_NAME_TO_NUM.items():
                if name in context_lower:
                    found_month = num
                    break

            is_past = False
            if found_month is not None:
                if (year, found_month) < (now.year, now.month):
                    is_past = True
            else:
                if year < now.year:
                    is_past = True

            if is_past:
                snippet = context.strip()
                issues.append(f"\"{snippet}\" — this refers to a period that has already passed")

        if not issues:
            return None

        return (
            f"TEMPORAL VIOLATION DETECTED (current date: {now.strftime('%d %B %Y')}) — the response "
            f"referenced at least one date/period that has already passed as if it were still upcoming:\n"
            + "\n".join(f"- {i}" for i in issues)
            + "\nRewrite the response: explicitly mark any already-passed period as past (e.g. 'this "
            "window has already passed'), and only present periods starting after the current date "
            "as genuine future predictions."
        )

    def _get_verified_planet_house_map(self, session: Dict) -> Optional[Dict[str, Any]]:
        cached_raw = session.get("kundli_raw")
        if not cached_raw:
            return None
        try:
            parsed = json.loads(cached_raw)
            planets = parsed.get("planets", []) or []
            ascendant_sign = parsed.get("ascendant_sign")
        except Exception:
            return None
        if not ascendant_sign or not planets:
            return None

        from app.services.topic_service import get_house_for_sign

        result: Dict[str, Any] = {"ascendant": ascendant_sign, "planets": {}}
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
        return result

    def _build_verified_chart_block(self, session: Dict) -> str:
        chart = self._get_verified_planet_house_map(session)
        if not chart:
            return ""

        lines = [f"Ascendant (Lagna): {chart['ascendant']}"]
        for name, info in chart["planets"].items():
            house_str = f", house {info['house']}" if info["house"] else ""
            retro = " (retrograde)" if info["retro"] else ""
            lines.append(f"{name}: {info['sign']}{house_str}{retro}")

        return (
            "ACTUAL VERIFIED CHART PLACEMENTS (this is the user's real chart — the ONLY source of "
            "truth for where each planet actually is):\n" + "\n".join(lines) +
            "\n\nHARD RULE: retrieved classical text may describe a rule using a DIFFERENT house "
            "placement for a planet as a general/illustrative example (e.g. 'if Mercury is in the "
            "10th house...'). If that placement doesn't match the VERIFIED list above, it is NOT a "
            "description of this user's actual chart — never state a planet's house placement that "
            "contradicts the verified list above."
        )

    def _build_evidence_buckets(self, rag_hits: List[Dict[str, Any]], session: Dict,
                                  dasha_timeline_str: str) -> str:
        buckets: Dict[str, List[str]] = {"classical_rule": [], "dasha_timing": [], "yoga": []}

        for hit in rag_hits:
            bucket = STAGE_TO_BUCKET.get(hit.get("stage"), "classical_rule")
            source = hit.get("source", "Unknown")
            page = hit.get("page")
            page_label = f", p.{page}" if page is not None else ""
            snippet = (hit.get("text") or "").strip()
            if len(snippet) > 220:
                snippet = snippet[:220].rsplit(" ", 1)[0] + "..."
            buckets[bucket].append(f"[{source}{page_label}] {snippet}")

        yoga_text = session.get("yoga_text") or ""
        if yoga_text:
            buckets["yoga"].append(yoga_text.strip())

        if dasha_timeline_str:
            buckets["dasha_timing"].append(dasha_timeline_str.strip())
        else:
            cached_dasha = session.get("kundli_dasha")
            if cached_dasha:
                try:
                    dasha_info = json.loads(cached_dasha)
                    maha = dasha_info.get("current_mahadasha", {}) or {}
                    antar = dasha_info.get("current_antardasha", {}) or {}
                    maha_lord = maha.get("lord") or maha.get("name") or maha.get("planet")
                    antar_lord = antar.get("lord") or antar.get("name") or antar.get("planet")
                    if maha_lord:
                        line = f"Current Mahadasha: {maha_lord}"
                        if antar_lord:
                            line += f", Antardasha: {antar_lord}"
                        buckets["dasha_timing"].append(line)
                except Exception:
                    pass

        sections = []
        for key in ("classical_rule", "dasha_timing", "yoga"):
            items = buckets[key]
            if not items:
                continue
            label = BUCKET_LABELS[key]
            body = "\n".join(f"- {item}" for item in items)
            sections.append(f"[{label}]\n{body}")

        if not sections:
            return ""
        return "EVIDENCE BY TYPE (each category below is a distinct KIND of signal — do not blend " \
               "a classical rule with a Dasha timing fact as if they were the same type of evidence):\n\n" \
               + "\n\n".join(sections)

    def _build_structured_evidence_table(self, rag_hits: List[Dict[str, Any]], session: Dict,
                                           referenced: Dict[str, Set[str]]) -> str:
        chart = self._get_verified_planet_house_map(session)
        if not chart:
            return ""

        planets_of_interest = referenced.get("planets", set()) or set(chart["planets"].keys())

        rows: List[str] = []
        for planet_name in sorted(planets_of_interest):
            if planet_name not in chart["planets"]:
                continue
            info = chart["planets"][planet_name]
            house = info["house"]
            if not house:
                continue
            fact_str = f"{planet_name} in {info['sign']} ({house}th house)"
            if info["retro"]:
                fact_str += " (retrograde)"

            matched_rule = None
            matched_source = None
            house_pattern = re.compile(rf"\b{house}(?:st|nd|rd|th)\s+house\b", re.IGNORECASE)
            for hit in rag_hits:
                text = hit.get("text", "") or ""
                if planet_name.lower() not in text.lower():
                    continue
                if not house_pattern.search(text):
                    continue
                snippet = text.strip()
                if len(snippet) > 180:
                    snippet = snippet[:180].rsplit(" ", 1)[0] + "..."
                matched_rule = snippet
                page = hit.get("page")
                matched_source = f"{hit.get('source', 'Unknown')}" + (f", p.{page}" if page is not None else "")
                break

            if matched_rule:
                rows.append(f"| {fact_str} | {matched_rule} | {matched_source} |")
            else:
                rows.append(f"| {fact_str} | No retrieved rule matches this exact placement — do not invent one | — |")

        if not rows:
            return ""

        header = "| VERIFIED FACT | MATCHING RETRIEVED RULE | SOURCE |\n|---|---|---|"
        return (
            "STRUCTURED FACT -> RULE TABLE (use ONLY these rows for chart-specific claims about the "
            "planets listed — if a row says no rule matches, do not describe that placement using a "
            "rule from elsewhere in the retrieved text):\n\n" + header + "\n" + "\n".join(rows)
        )

    # ------------------------------------------------------------------
    # EVIDENCE SUFFICIENCY GATE
    # Deterministic count of independent evidence signals available for
    # THIS specific answer: unique RAG sources, verified chart-fact rows
    # with a matched rule, presence of Dasha/timing data, and presence of
    # an evidence vote. Below MIN_SUFFICIENT_SIGNALS, a single explicit
    # hedging instruction is injected — never multiple competing
    # instructions, and never an LLM judgment call, so it can't itself
    # introduce inconsistency.
    # ------------------------------------------------------------------
    def _compute_evidence_sufficiency(self, rag_hits: List[Dict[str, Any]], evidence_table: str,
                                        dasha_timeline_str: str, evidence_vote: Optional[Dict],
                                        session: Dict) -> Dict[str, Any]:
        unique_sources = set()
        for hit in rag_hits:
            unique_sources.add((hit.get("source"), hit.get("page")))

        matched_rule_rows = 0
        if evidence_table:
            for line in evidence_table.splitlines():
                if line.startswith("|") and "No retrieved rule matches" not in line and "VERIFIED FACT" not in line and "---" not in line:
                    matched_rule_rows += 1

        has_timing = bool(dasha_timeline_str) or bool(session.get("kundli_dasha"))
        has_vote = evidence_vote is not None

        signal_count = 0
        signal_count += 1 if unique_sources else 0
        signal_count += 1 if matched_rule_rows > 0 else 0
        signal_count += 1 if has_timing else 0
        signal_count += 1 if has_vote else 0

        is_sufficient = signal_count >= MIN_SUFFICIENT_SIGNALS and len(unique_sources) >= 1
        is_strong = len(unique_sources) >= MIN_UNIQUE_SOURCES_FOR_STRONG and matched_rule_rows > 0

        return {
            "unique_source_count": len(unique_sources),
            "matched_rule_rows": matched_rule_rows,
            "has_timing": has_timing,
            "has_vote": has_vote,
            "signal_count": signal_count,
            "is_sufficient": is_sufficient,
            "is_strong": is_strong,
        }

    def _build_sufficiency_instruction(self, sufficiency: Dict[str, Any]) -> str:
        if sufficiency["is_strong"]:
            return (
                "EVIDENCE SUFFICIENCY: Strong — multiple independent sources and a matched chart-to-rule "
                "pairing are available. You may state the answer with grounded, direct confidence."
            )
        if sufficiency["is_sufficient"]:
            return (
                "EVIDENCE SUFFICIENCY: Adequate but limited — some independent evidence is available "
                f"(unique sources: {sufficiency['unique_source_count']}, matched chart facts: "
                f"{sufficiency['matched_rule_rows']}). State the answer clearly but avoid absolute or "
                "guaranteed language."
            )
        return (
            "EVIDENCE SUFFICIENCY: LOW — only "
            f"{sufficiency['unique_source_count']} unique retrieved source(s) and "
            f"{sufficiency['matched_rule_rows']} matched chart-to-rule pairing(s) are available for this "
            "specific question. Do NOT present a confident, single-answer verdict. Explicitly acknowledge "
            "the limited evidence (e.g. 'based on limited textual evidence' or 'this needs a fuller "
            "reading of your chart'), and lean on general classical principles and the verified chart "
            "placements rather than manufacturing certainty."
        )

    # ------------------------------------------------------------------
    # EVIDENCE-TO-CLAIM MAPPING
    # Pure post-hoc analysis — no new LLM call. Splits the final response
    # into sentences and labels each as "grounded" (overlaps with a
    # verified chart fact, a matched rule, or Dasha data) or "interpretive"
    # (no direct evidence overlap — narrative/connective text). Purely for
    # transparency in the reasoning trace; never fed back into generation.
    # ------------------------------------------------------------------
    def _map_evidence_to_claims(self, response_text: str, session: Dict,
                                  rag_hits: List[Dict[str, Any]], evidence_table: str) -> List[Dict[str, str]]:
        if not response_text:
            return []

        chart = self._get_verified_planet_house_map(session)
        chart_terms: Set[str] = set()
        if chart:
            chart_terms.add(chart["ascendant"].lower())
            for name, info in chart["planets"].items():
                chart_terms.add(name.lower())
                chart_terms.add(info["sign"].lower())
                if info["house"]:
                    chart_terms.add(f"{info['house']}th house")
                    chart_terms.add(f"house {info['house']}")

        rule_terms: Set[str] = set()
        for hit in rag_hits:
            text = (hit.get("text") or "").lower()
            for planet in PLANET_NAMES:
                if planet.lower() in text:
                    rule_terms.add(planet.lower())
            for match in re.finditer(r"\b(1[0-2]|[1-9])(?:st|nd|rd|th)\s+house\b", text):
                rule_terms.add(f"{match.group(1)}th house")

        dasha_terms: Set[str] = set()
        cached_dasha = session.get("kundli_dasha")
        if cached_dasha:
            try:
                dasha_info = json.loads(cached_dasha)
                maha = dasha_info.get("current_mahadasha", {}) or {}
                antar = dasha_info.get("current_antardasha", {}) or {}
                for lord_field in (maha.get("lord"), maha.get("name"), maha.get("planet"),
                                    antar.get("lord"), antar.get("name"), antar.get("planet")):
                    if lord_field:
                        dasha_terms.add(str(lord_field).lower())
            except Exception:
                pass

        sentences = re.split(r'(?<=[.!?])\s+', response_text.strip())
        sentences = [s.strip() for s in sentences if s.strip()]

        mapped: List[Dict[str, str]] = []
        for sentence in sentences:
            s_lower = sentence.lower()
            matched_chart = [t for t in chart_terms if t in s_lower]
            matched_rule = [t for t in rule_terms if t in s_lower]
            matched_dasha = [t for t in dasha_terms if t in s_lower]

            if matched_chart or matched_rule or matched_dasha:
                basis_parts = []
                if matched_chart:
                    basis_parts.append(f"chart fact ({', '.join(sorted(set(matched_chart))[:3])})")
                if matched_rule:
                    basis_parts.append(f"retrieved rule mentions ({', '.join(sorted(set(matched_rule))[:3])})")
                if matched_dasha:
                    basis_parts.append(f"Dasha data ({', '.join(sorted(set(matched_dasha))[:3])})")
                mapped.append({
                    "sentence": sentence,
                    "label": "grounded",
                    "basis": "; ".join(basis_parts),
                })
            else:
                mapped.append({
                    "sentence": sentence,
                    "label": "interpretive",
                    "basis": "no direct overlap with verified chart facts, retrieved rule text, or Dasha data — narrative/connective or general astrological reasoning",
                })

        return mapped

    def _format_claim_mapping_for_trace(self, mapping: List[Dict[str, str]]) -> str:
        if not mapping:
            return "No response text was available to map."

        grounded_count = sum(1 for m in mapping if m["label"] == "grounded")
        total = len(mapping)
        lines = [f"{grounded_count} of {total} sentence(s) are directly grounded in retrieved evidence or verified chart facts.\n"]
        for m in mapping:
            tag = "✓ GROUNDED" if m["label"] == "grounded" else "○ INTERPRETIVE"
            lines.append(f"[{tag}] \"{m['sentence']}\"")
            lines.append(f"   basis: {m['basis']}")
        return "\n".join(lines)

    def _chunk_text_for_streaming(self, text: str, words_per_chunk: int = 6):
        words = text.split(' ')
        buf: List[str] = []
        for w in words:
            buf.append(w)
            if len(buf) >= words_per_chunk:
                yield ' '.join(buf) + ' '
                buf = []
        if buf:
            yield ' '.join(buf)

    def _compute_retrieval_depth(self, message_text: str, query_understanding: Dict[str, Any]) -> Dict[str, int]:
        comparison = query_understanding.get("comparison") or []
        requires_timing = bool(query_understanding.get("requires_timing"))
        life_area = (query_understanding.get("life_area") or "").strip().lower()
        word_count = len(message_text.split())

        complexity = 1.0

        if len(comparison) >= 2:
            complexity += 0.6
        if requires_timing:
            complexity += 0.3
        if word_count > 18:
            complexity += 0.3
        if not life_area or life_area == "general":
            complexity -= 0.3

        complexity = max(0.5, min(complexity, 2.0))

        def _scaled(base: int) -> int:
            return max(DEPTH_MIN_HITS, min(DEPTH_MAX_HITS, round(base * complexity)))

        depth = {
            "framework_max": _scaled(FRAMEWORK_MAX_HITS_BASE),
            "personalized_max": _scaled(PERSONALIZED_MAX_HITS_BASE),
            "comparison_max_per_branch": _scaled(COMPARISON_MAX_HITS_PER_BRANCH_BASE),
            "complexity": round(complexity, 2),
        }
        logger.info(
            f"[AdaptiveDepth] complexity={depth['complexity']} "
            f"(comparison={len(comparison)}, timing={requires_timing}, words={word_count}, life_area='{life_area}') "
            f"-> framework={depth['framework_max']}, personalized={depth['personalized_max']}, "
            f"comparison_per_branch={depth['comparison_max_per_branch']}"
        )
        return depth

    def _dedupe_hits(self, hits: List[Dict[str, Any]], max_hits: int) -> List[Dict[str, Any]]:
        if not hits:
            return []

        kept: List[Dict[str, Any]] = []

        for hit in hits:
            text = (hit.get("text") or "").strip().lower()
            if not text:
                continue

            is_duplicate = False
            for kept_hit in kept:
                kept_text = (kept_hit.get("text") or "").strip().lower()
                if not kept_text:
                    continue

                similarity = SequenceMatcher(None, text, kept_text).ratio()
                if similarity >= DEDUP_SIMILARITY_THRESHOLD:
                    is_duplicate = True
                    break

            if not is_duplicate:
                kept.append(hit)

            if len(kept) >= max_hits:
                break

        if len(hits) > len(kept):
            logger.info(f"[EvidenceDedup] {len(hits)} hits -> {len(kept)} after semantic dedup (max={max_hits})")

        return kept

    def _fetch_and_cache_kundli(self, session_id: str, session: Dict) -> str:
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
                    "framework_cache": None,
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

    def _understand_query_intent(self, message_text: str, history_text: str) -> Dict[str, Any]:
        prompt = f"""You are a query-understanding layer for a Vedic astrology assistant.
Do NOT answer the astrology question and do NOT name any houses, planets, or astrological rules.
Only restate what the user is asking about in plain language, and classify its structure.

Conversation history (for context only):
{history_text or "None"}

User's current message:
"{message_text}"

If the user is comparing two or more options (e.g. "job or business", "abroad or stay in India",
"job or business or higher studies", "government job or private job"), list EVERY option
mentioned in "comparison" as short plain-English labels (max 3 items). If it's not a comparison
question, use an empty list. Watch for "or" / "ya" / "अथवा" connecting multiple options — even
in Hindi/Hinglish phrasing.

Respond with ONLY valid JSON in this exact shape, no markdown, no extra text:
{{"life_area": "one short label, e.g. career, marriage, finance, health, education, foreign_travel, general",
  "restated_intent": "one plain sentence restating what the user wants to know, in English",
  "comparison": ["option A", "option B"],
  "requires_timing": true}}
"""
        default: Dict[str, Any] = {"life_area": "", "restated_intent": "", "comparison": [], "requires_timing": False}
        try:
            raw = llm_service.generate(prompt=prompt, json_format=True, temperature=0.0)
            cleaned = raw.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            parsed = json.loads(cleaned.strip())

            life_area = str(parsed.get("life_area", "")).strip() or "general"
            restated = str(parsed.get("restated_intent", "")).strip()
            if not restated:
                raise ValueError("empty restated_intent")

            raw_comparison = parsed.get("comparison", [])
            comparison = (
                [str(c).strip() for c in raw_comparison if str(c).strip()][:3]
                if isinstance(raw_comparison, list) else []
            )
            requires_timing = bool(parsed.get("requires_timing", False))

            return {
                "life_area": life_area,
                "restated_intent": restated,
                "comparison": comparison,
                "requires_timing": requires_timing,
            }
        except Exception as e:
            logger.warning(f"Query-understanding LLM call failed, falling back to keyword topic: {e}")
            return default

    def _get_intent_cache(self, session: Dict) -> Optional[Dict]:
        raw = session.get("intent_cache")
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None

    def _save_intent_cache(self, session_id: str, session: Dict, query_understanding: Dict[str, Any], fast_topic: Optional[str]):
        try:
            entry = dict(query_understanding)
            entry["fast_topic"] = fast_topic
            entry_json = json.dumps(entry, ensure_ascii=False)
            db.update_session(session_id, {"intent_cache": entry_json})
            session["intent_cache"] = entry_json
        except Exception as e:
            logger.error(f"Failed to save intent cache: {e}")

    def _get_query_understanding_cached(self, session_id: str, message_text: str, history_text: str, session: Dict) -> Dict[str, Any]:
        fast_topic = classify_topic(message_text)
        cached = self._get_intent_cache(session)
        looks_comparative = any(w in f" {message_text.lower()} " for w in COMPARISON_HINT_WORDS)

        if cached and fast_topic and cached.get("fast_topic") == fast_topic and not looks_comparative:
            logger.info(f"[IntentCache] HIT — reusing cached intent for topic '{fast_topic}' (LLM call skipped)")
            return {
                "life_area": cached.get("life_area", fast_topic),
                "restated_intent": cached.get("restated_intent", ""),
                "comparison": [],
                "requires_timing": cached.get("requires_timing", False),
            }

        logger.info(
            f"[IntentCache] MISS (fast_topic='{fast_topic}', "
            f"cached_topic='{cached.get('fast_topic') if cached else None}', "
            f"comparative={looks_comparative}) — calling LLM"
        )
        query_understanding = self._understand_query_intent(message_text, history_text)
        self._save_intent_cache(session_id, session, query_understanding, fast_topic)
        return query_understanding

    def _resolve_topic(self, message_text: str, query_understanding: Dict[str, Any]) -> Optional[str]:
        life_area = (query_understanding.get("life_area") or "").strip().lower()

        if life_area and life_area in TOPIC_CHART_FACTORS:
            logger.info(f"[TopicResolution] using life_area='{life_area}' as topic (primary)")
            return life_area

        fallback = classify_topic(message_text)
        logger.info(
            f"[TopicResolution] life_area='{life_area or 'none'}' not in TOPIC_CHART_FACTORS — "
            f"falling back to keyword classify_topic()='{fallback}'"
        )
        return fallback

    def _build_framework_query(self, message_text: str, topic: Optional[str] = None, life_area: str = "") -> str:
        parts = [
            message_text.strip(),
            "classical astrology principles rules indications relevant factors"
        ]
        if life_area and life_area != "general":
            parts.append(life_area.replace("_", " "))
        if topic:
            bias = get_search_bias(topic)
            if bias:
                parts.append(bias)
        return " ".join(p for p in parts if p).strip()

    def _extract_referenced_factors(self, rag_hits: List[Dict[str, Any]]) -> Dict[str, Set[str]]:
        houses: Set[str] = set()
        planets: Set[str] = set()
        charts: Set[str] = set()
        concepts: Set[str] = set()

        planet_names = PLANET_NAMES + ["Ascendant"]
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

    def _build_personalized_rag_query(self, message_text: str, topic: Optional[str], targeted_facts: str, life_area: str = "") -> str:
        parts = [message_text.strip(), "classical astrology interpretation"]
        if life_area and life_area != "general":
            parts.append(f"life area: {life_area}")
        if topic:
            parts.append(f"topic: {topic}")
        if targeted_facts:
            parts.append("chart configuration:")
            parts.append(targeted_facts)
        return " ".join(p for p in parts if p).strip()

    def _get_framework_cache(self, session: Dict, topic: str) -> Optional[Dict]:
        raw = session.get("framework_cache")
        if not raw:
            return None
        try:
            cache = json.loads(raw)
            entry = cache.get(topic)
            if not entry or entry.get("_version") != FRAMEWORK_CACHE_VERSION:
                return None
            return entry
        except Exception:
            return None

    def _save_framework_cache(self, session_id: str, session: Dict, topic: str,
                                referenced: Dict[str, Set[str]], targeted_facts: str, framework_context: str):
        try:
            raw = session.get("framework_cache")
            cache = json.loads(raw) if raw else {}
            cache[topic] = {
                "_version": FRAMEWORK_CACHE_VERSION,
                "houses": sorted(referenced.get("houses", set()), key=lambda x: int(x)),
                "planets": sorted(referenced.get("planets", set())),
                "charts": sorted(referenced.get("charts", set())),
                "concepts": sorted(referenced.get("concepts", set())),
                "targeted_facts": targeted_facts,
                "framework_context": framework_context,
            }
            cache_json = json.dumps(cache, ensure_ascii=False)
            db.update_session(session_id, {"framework_cache": cache_json})
            session["framework_cache"] = cache_json
        except Exception as e:
            logger.error(f"Failed to save framework cache for '{topic}': {e}")

    def _get_rag_first_context(self, session_id: str, message_text: str, topic: Optional[str], session: Dict,
                                 query_understanding: Optional[Dict[str, Any]] = None):
        try:
            from app.services.topic_service import TOPIC_RELEVANT_BOOKS

            qu = query_understanding or {}
            life_area = qu.get("life_area") or ""
            comparison = qu.get("comparison") or []

            depth = self._compute_retrieval_depth(message_text, qu)

            preferred_sources = TOPIC_RELEVANT_BOOKS.get(topic) if topic else None
            seen_keys: set = set()

            framework_cached = self._get_framework_cache(session, topic) if topic else None
            framework_rag_hits: List[Dict[str, Any]] = []
            framework_chunks: List[str] = []

            if framework_cached:
                logger.info(f"[FrameworkCache] HIT for topic '{topic}' — skipping framework RAG retrieval")
                referenced: Dict[str, Set[str]] = {
                    "houses": set(framework_cached.get("houses", [])),
                    "planets": set(framework_cached.get("planets", [])),
                    "charts": set(framework_cached.get("charts", [])),
                    "concepts": set(framework_cached.get("concepts", [])),
                }
                targeted_facts = framework_cached.get("targeted_facts", "")
                cached_context = framework_cached.get("framework_context", "")
                if cached_context:
                    framework_chunks.append(cached_context)
            else:
                framework_query = self._build_framework_query(message_text, topic, life_area)
                framework_hits_raw = vector_store.dual_retrieve(
                    topic_query=framework_query,
                    global_query=message_text,
                    query_vector_topic=self.embeddings_provider.get_embedding(framework_query),
                    query_vector_global=self.embeddings_provider.get_embedding(message_text),
                    preferred_sources=preferred_sources,
                    top_k_each=depth["framework_max"],
                    final_top_k=depth["framework_max"],
                    alpha=settings.HYBRID_ALPHA,
                )
                framework_hits_raw = [h for h in framework_hits_raw if h["score"] >= settings.MIN_RAG_RELEVANCE]

                referenced = {"houses": set(), "planets": set(), "charts": set(), "concepts": set()}
                targeted_facts = ""

                if not framework_hits_raw:
                    logger.info("[RAGFirst] no sufficiently relevant framework chunks — continuing with comparison/personalized retrieval anyway")
                else:
                    pre_dedup_hits = []
                    for hit in framework_hits_raw:
                        source = hit["metadata"].get("source", "Unknown")
                        page = hit["metadata"].get("page")
                        pre_dedup_hits.append({
                            "source": source, "page": page, "score": hit["score"],
                            "text": hit["text"], "stage": "framework",
                        })

                    framework_rag_hits = self._dedupe_hits(pre_dedup_hits, depth["framework_max"])

                    for i, hit in enumerate(framework_rag_hits):
                        seen_keys.add((hit["source"], hit["page"]))
                        page_label = f", Page: {hit['page']}" if hit["page"] is not None else ""
                        framework_chunks.append(
                            f"--- Classical Principle {i+1} [Source: {hit['source']}{page_label}, relevance: {hit['score']:.2f}] ---\n{hit['text']}\n"
                        )

                    referenced = self._extract_referenced_factors(framework_rag_hits)
                    targeted_facts = self._build_targeted_kundli_facts(referenced, session)

                    logger.info(
                        f"[RAGFirst] framework factors houses={referenced['houses']} "
                        f"planets={referenced['planets']} charts={referenced['charts']} concepts={referenced['concepts']}"
                    )

                if not targeted_facts:
                    targeted_facts = self._build_targeted_kundli_facts(referenced, session)

                if topic:
                    self._save_framework_cache(session_id, session, topic, referenced, targeted_facts, "\n".join(framework_chunks))

            comparison_hits: List[Dict[str, Any]] = []
            if len(comparison) >= 2:
                comparison_facts_blocks = []
                for branch in comparison:
                    branch_query = f"{branch} {life_area} astrology classical rules houses planets significance".strip()
                    try:
                        branch_vector = self.embeddings_provider.get_embedding(branch_query)
                        branch_results = vector_store.hybrid_search(
                            query=branch_query, query_vector=branch_vector,
                            top_k=depth["comparison_max_per_branch"] + 1,
                            alpha=settings.HYBRID_ALPHA
                        )
                    except Exception as e:
                        logger.error(f"[Comparison] retrieval failed for branch '{branch}': {e}")
                        continue

                    branch_rag_hits_raw = []
                    for hit in branch_results:
                        if hit["score"] < settings.MIN_RAG_RELEVANCE:
                            continue
                        source = hit["metadata"].get("source", "Unknown")
                        page = hit["metadata"].get("page")
                        key = (source, page)
                        if key in seen_keys:
                            continue
                        branch_rag_hits_raw.append({
                            "source": source, "page": page, "score": hit["score"],
                            "text": hit["text"], "stage": "comparison", "branch": branch,
                        })

                    branch_rag_hits = self._dedupe_hits(branch_rag_hits_raw, depth["comparison_max_per_branch"])
                    for hit in branch_rag_hits:
                        seen_keys.add((hit["source"], hit["page"]))
                        comparison_hits.append(hit)

                    if branch_rag_hits:
                        branch_referenced = self._extract_referenced_factors(branch_rag_hits)
                        branch_facts = self._build_targeted_kundli_facts(branch_referenced, session)
                        if branch_facts:
                            comparison_facts_blocks.append(f"--- Chart facts relevant to '{branch}' ---\n{branch_facts}")
                if comparison_facts_blocks:
                    comparison_instruction = (
                        f"\n\nCOMPARATIVE QUESTION DETECTED: the user is weighing {' vs '.join(comparison)}. "
                        f"For EACH option below, go through the retrieved classical rules and state whether "
                        f"this chart satisfies, partially satisfies, or does not satisfy each rule. Then give "
                        f"an overall lean (which option the chart currently supports more strongly) — do not "
                        f"just pick one option without showing the comparison.\n\n" + "\n\n".join(comparison_facts_blocks)
                    )
                    targeted_facts = f"{targeted_facts}\n{comparison_instruction}" if targeted_facts else comparison_instruction

            personalized_query = self._build_personalized_rag_query(message_text, topic, targeted_facts, life_area)
            personalized_vector = self.embeddings_provider.get_embedding(personalized_query)

            personalized_hits_raw = vector_store.dual_retrieve(
                topic_query=personalized_query,
                global_query=personalized_query,
                query_vector_topic=personalized_vector,
                query_vector_global=personalized_vector,
                preferred_sources=preferred_sources,
                top_k_each=depth["personalized_max"] + 2,
                final_top_k=depth["personalized_max"] + 2,
                alpha=settings.HYBRID_ALPHA,
            )
            personalized_hits_raw = [h for h in personalized_hits_raw if h["score"] >= settings.MIN_RAG_RELEVANCE]

            pre_dedup_personalized = []
            for hit in personalized_hits_raw:
                source = hit["metadata"].get("source", "Unknown")
                page = hit["metadata"].get("page")
                key = (source, page)
                if key in seen_keys:
                    continue
                pre_dedup_personalized.append({
                    "source": source, "page": page, "score": hit["score"],
                    "text": hit["text"], "stage": "personalized",
                })

            personalized_rag_hits = self._dedupe_hits(pre_dedup_personalized, depth["personalized_max"])

            personalized_chunks = []
            for i, hit in enumerate(personalized_rag_hits):
                seen_keys.add((hit["source"], hit["page"]))
                page_label = f", Page: {hit['page']}" if hit["page"] is not None else ""
                personalized_chunks.append(
                    f"--- Personalized Evidence {i+1} [Source: {hit['source']}{page_label}, relevance: {hit['score']:.2f}] ---\n{hit['text']}\n"
                )

            comparison_chunks = []
            for hit in comparison_hits:
                page_label = f", Page: {hit['page']}" if hit.get("page") is not None else ""
                comparison_chunks.append(
                    f"--- Comparison Evidence ({hit['branch']}) [Source: {hit['source']}{page_label}, relevance: {hit['score']:.2f}] ---\n{hit['text']}\n"
                )

            all_hits = framework_rag_hits + comparison_hits + personalized_rag_hits

            context_parts = []
            if framework_chunks:
                context_parts.append("\n".join(framework_chunks))
            if comparison_chunks:
                context_parts.append("\n".join(comparison_chunks))
            if personalized_chunks:
                context_parts.append("\n".join(personalized_chunks))
            context = "\n".join(p for p in context_parts if p) or "No reference available."

            logger.info(
                f"[RAGFirst] framework_cached={bool(framework_cached)}, depth_complexity={depth['complexity']}, "
                f"comparison={len(comparison_hits)}, personalized={len(personalized_rag_hits)}"
            )

            return context, all_hits, targeted_facts, referenced

        except Exception as e:
            logger.error(f"RAG-first context build failed: {e}", exc_info=True)
            return "No reference available.", [], "", {"houses": set(), "planets": set(), "charts": set(), "concepts": set()}

    def _is_followup_retrieval_question(self, message_text: str, history: List[Dict[str, str]]) -> bool:
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
            entry = cache.get(topic)
            if not entry:
                return None
            if entry.get("_version") != TOPIC_BUNDLE_LOGIC_VERSION:
                logger.info(
                    f"Topic cache for '{topic}' is stale "
                    f"(v{entry.get('_version')} != v{TOPIC_BUNDLE_LOGIC_VERSION}) — recomputing"
                )
                return None
            return entry
        except Exception:
            return None

    def _save_topic_cache(self, session_id: str, session: Dict, topic: str, bundle: Dict):
        try:
            raw = session.get("topic_cache")
            cache = json.loads(raw) if raw else {}
            bundle_to_store = dict(bundle)
            bundle_to_store["_version"] = TOPIC_BUNDLE_LOGIC_VERSION
            cache[topic] = bundle_to_store
            cache_json = json.dumps(cache, ensure_ascii=False)
            db.update_session(session_id, {"topic_cache": cache_json})
            session["topic_cache"] = cache_json
        except Exception as e:
            logger.error(f"Failed to save topic cache for '{topic}': {e}")

    def _get_topic_bundle(self, session_id: str, session: Dict, topic: Optional[str], language: str) -> Dict[str, Any]:
        empty = {"emphasis": "", "divisional": "", "consistency": "", "missing_evidence": "", "evidence_vote": None, "consensus_label": "LOW"}
        if not topic:
            return empty

        cached = self._get_topic_cache(session, topic)
        if cached is not None:
            logger.info(f"Using cached topic bundle for '{topic}'")
            return {k: cached.get(k, empty[k]) for k in empty}

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
        except Exception as e:
            logger.error(f"Topic bundle build failed for '{topic}': {e}", exc_info=True)

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

    def _prepare_common_context(self, session_id: str, message_text: str, history: List[Dict[str, str]],
                                  history_text: str, session: Dict, language: str):
        query_understanding = self._get_query_understanding_cached(session_id, message_text, history_text, session)
        logger.info(
            f"[QueryUnderstanding] life_area='{query_understanding['life_area']}' "
            f"restated='{query_understanding['restated_intent']}' "
            f"comparison={query_understanding.get('comparison')} "
            f"requires_timing={query_understanding.get('requires_timing')}"
        )

        topic = self._resolve_topic(message_text, query_understanding)
        intent = classify_intent(message_text)
        response_contract = get_response_contract(intent)

        cached_kundli = session.get("kundli_data")
        kundli_str = cached_kundli if cached_kundli else self._fetch_and_cache_kundli(session_id, session)

        context_str = ""
        rag_hits: List[Dict[str, Any]] = []
        targeted_facts = ""
        referenced: Dict[str, Set[str]] = {"houses": set(), "planets": set(), "charts": set(), "concepts": set()}

        if self._is_followup_retrieval_question(message_text, history):
            context_str, rag_hits = self._get_followup_rag_context(message_text, topic, history)
        if not rag_hits:
            context_str, rag_hits, targeted_facts, referenced = self._get_rag_first_context(
                session_id, message_text, topic, session, query_understanding
            )
        logger.info(f"[RAGPipeline] hits={len(rag_hits)} targeted_facts={'yes' if targeted_facts else 'no'}")

        yoga_text = self._get_yoga_text(session)

        topic_emphasis = divisional_text = consistency_note = missing_evidence = ""
        evidence_vote = None
        if topic:
            bundle = self._get_topic_bundle(session_id, session, topic, language)
            topic_emphasis = bundle["emphasis"]
            divisional_text = bundle["divisional"]
            consistency_note = bundle["consistency"]
            missing_evidence = bundle["missing_evidence"]
            evidence_vote = bundle.get("evidence_vote")

        dasha_timeline_str = ""
        requires_timing = bool(query_understanding.get("requires_timing"))
        if topic and requires_timing:
            dasha_timeline_str = self._get_dasha_timeline(session_id, session, topic, language)
            logger.info(f"[TimingGate] requires_timing=True — Dasha timeline fetched/reused for topic '{topic}'")
        else:
            logger.info(f"[TimingGate] requires_timing={requires_timing}, topic={topic} — skipping Dasha timeline retrieval")

        final_kundli_data = self._build_final_kundli_data(kundli_str, topic_emphasis, divisional_text, yoga_text, missing_evidence)
        if targeted_facts:
            final_kundli_data = f"{final_kundli_data}\n\n{targeted_facts}" if final_kundli_data else targeted_facts

        verified_block = self._build_verified_chart_block(session)
        if verified_block:
            final_kundli_data = f"{final_kundli_data}\n\n{verified_block}" if final_kundli_data else verified_block

        bucketed_evidence = self._build_evidence_buckets(rag_hits, session, dasha_timeline_str)
        if bucketed_evidence:
            final_kundli_data = f"{final_kundli_data}\n\n{bucketed_evidence}" if final_kundli_data else bucketed_evidence

        evidence_table = self._build_structured_evidence_table(rag_hits, session, referenced)
        if evidence_table:
            final_kundli_data = f"{final_kundli_data}\n\n{evidence_table}" if final_kundli_data else evidence_table

        # --- Evidence Sufficiency Gate ---
        sufficiency = self._compute_evidence_sufficiency(rag_hits, evidence_table, dasha_timeline_str, evidence_vote, session)
        sufficiency_instruction = self._build_sufficiency_instruction(sufficiency)
        final_kundli_data = f"{final_kundli_data}\n\n{sufficiency_instruction}" if final_kundli_data else sufficiency_instruction
        logger.info(
            f"[SufficiencyGate] sources={sufficiency['unique_source_count']} "
            f"matched_rows={sufficiency['matched_rule_rows']} signals={sufficiency['signal_count']} "
            f"sufficient={sufficiency['is_sufficient']} strong={sufficiency['is_strong']}"
        )

        user_memory = self._get_user_memory_block(session, topic)
        repeat_hint = self._get_repeat_topic_hint(session, topic)

        return {
            "query_understanding": query_understanding,
            "topic": topic,
            "response_contract": response_contract,
            "context_str": context_str,
            "rag_hits": rag_hits,
            "targeted_facts": targeted_facts,
            "referenced": referenced,
            "evidence_table": evidence_table,
            "bucketed_evidence": bucketed_evidence,
            "sufficiency": sufficiency,
            "final_kundli_data": final_kundli_data,
            "user_memory": user_memory,
            "repeat_hint": repeat_hint,
            "consistency_note": consistency_note,
            "dasha_timeline_str": dasha_timeline_str,
            "evidence_vote": evidence_vote,
        }

    def _build_astrologer_prompt(self, session: Dict, language: str, history_text: str,
                                   message_text: str, ctx: Dict[str, Any]) -> str:
        prompt = ASTROLOGER_PROMPT.format(
            name=session.get("name") or "Friend",
            language=language, dob=session.get("dob") or "Not provided",
            birth_time=session.get("birth_time") or "Not provided",
            birth_place=session.get("birth_place") or "Not provided",
            context=ctx["context_str"] or "No book context.", kundli_data=ctx["final_kundli_data"],
            user_memory=ctx["user_memory"] or "No prior topics discussed yet.",
            consistency_note=ctx["consistency_note"] or "No specific conflict detected.",
            dasha_timeline=ctx["dasha_timeline_str"] or "No timeline data available.",
            response_contract=ctx["response_contract"],
            history=history_text, query=message_text
        )
        if ctx["repeat_hint"]:
            prompt += f"\n\n{ctx['repeat_hint']}"
        prompt += f"\n\n{self._build_temporal_context()}"
        return prompt

    def _generate_and_validate(self, session_id: str, session: Dict, astrologer_prompt: str,
                                 dasha_timeline_str: str, evidence_vote) -> str:
        response_text = llm_service.generate(prompt=astrologer_prompt, temperature=0.6)

        recent_texts = self._get_recent_assistant_texts(session_id)
        similar_to = self._is_too_similar(response_text, recent_texts)

        verify_planets, verify_ascendant = [], None
        cached_raw_for_verify = session.get("kundli_raw")
        if cached_raw_for_verify:
            try:
                parsed_verify = json.loads(cached_raw_for_verify)
                verify_planets = parsed_verify.get("planets", [])
                verify_ascendant = parsed_verify.get("ascendant_sign")
            except Exception:
                pass

        claim_failures = validate_claims(
            response_text, dasha_timeline_str, evidence_vote,
            planets=verify_planets, ascendant_sign=verify_ascendant
        )

        specificity_score = compute_chart_specificity(response_text)
        specificity_correction = build_specificity_correction(specificity_score)
        if specificity_correction:
            logger.info(f"[Specificity] response flagged as generic: ratio={specificity_score['specificity_ratio']}")

        temporal_correction = self._check_past_date_claims(response_text)
        if temporal_correction:
            logger.info("[TemporalCheck] response flagged a past date/period presented as upcoming")

        if similar_to or claim_failures or specificity_correction or temporal_correction:
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
            if temporal_correction:
                retry_prompt += "\n\n" + temporal_correction

            response_text = llm_service.generate(prompt=retry_prompt, temperature=0.75)

            remaining_claims = validate_claims(
                response_text, dasha_timeline_str, evidence_vote,
                planets=verify_planets, ascendant_sign=verify_ascendant
            )
            remaining_temporal = self._check_past_date_claims(response_text)
            if remaining_claims:
                logger.warning(f"Claim validation still found {len(remaining_claims)} issue(s) after regeneration")
            if remaining_temporal:
                logger.warning("Temporal check still found a past-as-upcoming date after regeneration")

        return response_text

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

            if not is_astrology or missing_fields:
                db.add_message(session_id, "assistant", "Kripya dobara koshish karein.")
                return {"session_id": session_id, "message": "Kripya dobara koshish karein.",
                        "dob": session.get("dob"), "birth_time": session.get("birth_time"),
                        "birth_place": session.get("birth_place"), "language": session.get("language", "Hinglish")}

            ctx = self._prepare_common_context(session_id, message_text, history, history_text, session, language)
            topic = ctx["topic"]

            try:
                astrologer_prompt = self._build_astrologer_prompt(session, language, history_text, message_text, ctx)
                response_text = self._generate_and_validate(
                    session_id, session, astrologer_prompt, ctx["dasha_timeline_str"], ctx["evidence_vote"]
                )
            except Exception as gen_err:
                logger.error(f"Generation failed: {gen_err}")
                response_text = "Mujhe samajhne mein kuch pareshani ho gayi."

            db.add_message(session_id, "assistant", response_text)

            claim_mapping = self._map_evidence_to_claims(response_text, session, ctx["rag_hits"], ctx["evidence_table"])

            try:
                trace = self._build_reasoning_trace(session, topic, ctx["rag_hits"], ctx["targeted_facts"], response_text,
                                                     ctx["query_understanding"], ctx.get("evidence_table", ""), ctx.get("bucketed_evidence", ""),
                                                     ctx.get("sufficiency"), claim_mapping)
                db.update_session(session_id, {"last_reasoning_trace": json.dumps(trace)})
            except Exception as trace_err:
                logger.error(f"Reasoning trace caching failed: {trace_err}", exc_info=True)
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

            if not is_astrology or missing_fields:
                fallback = "Kripya dobara koshish karein."
                yield {"type": "chunk", "text": fallback}
                db.add_message(session_id, "assistant", fallback)
                yield {"type": "done", "session_id": session_id, "message": fallback,
                       "dob": session.get("dob"), "birth_time": session.get("birth_time"),
                       "birth_place": session.get("birth_place"), "language": session.get("language", "Hinglish")}
                return

            ctx = self._prepare_common_context(session_id, message_text, history, history_text, session, language)
            topic = ctx["topic"]

            try:
                astrologer_prompt = self._build_astrologer_prompt(session, language, history_text, message_text, ctx)
                full_text = self._generate_and_validate(
                    session_id, session, astrologer_prompt, ctx["dasha_timeline_str"], ctx["evidence_vote"]
                )
            except Exception as gen_err:
                logger.error(f"Streaming generation failed: {gen_err}")
                full_text = "Mujhe samajhne mein kuch pareshani ho gayi."

            for chunk in self._chunk_text_for_streaming(full_text):
                yield {"type": "chunk", "text": chunk}

            db.add_message(session_id, "assistant", full_text)

            claim_mapping = self._map_evidence_to_claims(full_text, session, ctx["rag_hits"], ctx["evidence_table"])

            try:
                trace = self._build_reasoning_trace(session, topic, ctx["rag_hits"], ctx["targeted_facts"], full_text,
                                                     ctx["query_understanding"], ctx.get("evidence_table", ""), ctx.get("bucketed_evidence", ""),
                                                     ctx.get("sufficiency"), claim_mapping)
                db.update_session(session_id, {"last_reasoning_trace": json.dumps(trace)})
            except Exception as trace_err:
                logger.error(f"Reasoning trace caching failed: {trace_err}", exc_info=True)
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

    def _build_reasoning_trace(
        self,
        session: Dict,
        topic: Optional[str],
        rag_hits: Optional[List[Dict[str, Any]]] = None,
        targeted_facts: str = "",
        response_text: str = "",
        query_understanding: Optional[Dict[str, Any]] = None,
        evidence_table: str = "",
        bucketed_evidence: str = "",
        sufficiency: Optional[Dict[str, Any]] = None,
        claim_mapping: Optional[List[Dict[str, str]]] = None,
    ) -> list:
        if not topic and not rag_hits and not (query_understanding and query_understanding.get("restated_intent")):
            return []

        try:
            rag_hits = rag_hits or []
            referenced = self._extract_referenced_factors(rag_hits)

            houses = sorted(referenced.get("houses", set()), key=lambda x: int(x))
            planets = sorted(referenced.get("planets", set()))
            charts = sorted(referenced.get("charts", set()))
            concepts = sorted(referenced.get("concepts", set()))

            steps = []

            qu = query_understanding or {}
            life_area = qu.get("life_area", "")
            restated = qu.get("restated_intent", "")
            comparison = qu.get("comparison") or []
            requires_timing = qu.get("requires_timing", False)
            if restated:
                topic_source = "LLM life_area (primary)" if (life_area and life_area.strip().lower() == topic) else "keyword fallback"
                qu_detail = f"What the system understood you're asking:\n\"{restated}\""
                if life_area:
                    qu_detail += f"\n\nLife area: {life_area}"
                qu_detail += f"\n\nTopic used for chart analysis: {topic or 'none'} ({topic_source})"
                if comparison:
                    qu_detail += f"\n\nComparing: {' vs '.join(comparison)}"
                qu_detail += f"\n\nTiming/Dasha relevant: {'Yes' if requires_timing else 'No'}"
                if not requires_timing:
                    qu_detail += " (Dasha timeline retrieval was skipped for this question)"
            else:
                qu_detail = (
                    "Query understanding was not available for this response — "
                    f"falling back to keyword-based topic classification (topic: {topic or 'none'})."
                )
            steps.append({"step": 1, "title": "Query Understanding", "detail": qu_detail, "type": "query_understanding"})

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

            framework_hit_count = len([h for h in rag_hits if h.get("stage") == "framework"])
            if framework_lines:
                framework_detail = (
                    "RAG retrieved classical sources and identified the following factors as relevant:\n"
                    + "\n".join(f"• {line}" for line in framework_lines)
                )
            elif framework_hit_count == 0:
                framework_detail = "No classical sources scored above the relevance threshold (or framework was reused from cache)."
            else:
                framework_detail = "RAG retrieved classical sources, but no specific house/planet/concept factors were confidently identified."

            steps.append({"step": 2, "title": "Classical Framework Retrieved", "detail": framework_detail, "type": "rag"})

            if targeted_facts:
                chart_detail = "The user's Kundli was examined for the factors identified by retrieved classical sources.\n\n" + targeted_facts
            else:
                chart_detail = "No targeted chart facts were identified from the retrieved classical framework."
            steps.append({"step": 3, "title": "Relevant Chart Factors", "detail": chart_detail, "type": "chart"})

            bucket_detail = bucketed_evidence if bucketed_evidence else "No bucketed evidence categories were populated for this question."
            steps.append({"step": 4, "title": "Evidence Bucketed by Type", "detail": bucket_detail, "type": "buckets"})

            table_detail = evidence_table if evidence_table else "No structured fact-to-rule pairing was produced (no matching retrieved rule text for the verified placements checked)."
            steps.append({"step": 5, "title": "Structured Fact → Rule Table", "detail": table_detail, "type": "fact_rule_table"})

            # NEW — Evidence Sufficiency Gate step
            if sufficiency:
                sufficiency_lines = [
                    f"Unique retrieved sources: {sufficiency['unique_source_count']}",
                    f"Matched chart-fact-to-rule pairings: {sufficiency['matched_rule_rows']}",
                    f"Dasha/timing data available: {'Yes' if sufficiency['has_timing'] else 'No'}",
                    f"Evidence vote available: {'Yes' if sufficiency['has_vote'] else 'No'}",
                    f"Total independent signal count: {sufficiency['signal_count']}",
                    "",
                    "Verdict: " + ("STRONG — confident language permitted" if sufficiency['is_strong']
                                    else "SUFFICIENT — clear but non-absolute language" if sufficiency['is_sufficient']
                                    else "LOW — model was instructed to hedge explicitly"),
                ]
                sufficiency_detail = "\n".join(sufficiency_lines)
            else:
                sufficiency_detail = "Evidence sufficiency was not computed for this response."
            steps.append({"step": 6, "title": "Evidence Sufficiency Gate", "detail": sufficiency_detail, "type": "sufficiency"})

            personalized_hits = [hit for hit in rag_hits if hit.get("stage") == "personalized"]
            comparison_hits_trace = [hit for hit in rag_hits if hit.get("stage") == "comparison"]

            evidence_lines = []
            if personalized_hits:
                seen_p = set()
                p_sources = []
                for hit in personalized_hits:
                    key = (hit.get("source"), hit.get("page"))
                    if key in seen_p:
                        continue
                    seen_p.add(key)
                    ref = f"{hit.get('source', 'Unknown source')} — Page {hit.get('page')}" if hit.get("page") is not None else hit.get("source", "Unknown source")
                    p_sources.append(f"• {ref}")
                evidence_lines.append("Personalized retrieval (ranked, deduplicated, adaptive depth):")
                evidence_lines.extend(p_sources)

            if comparison_hits_trace:
                by_branch: Dict[str, List[str]] = {}
                seen_c = set()
                for hit in comparison_hits_trace:
                    branch = hit.get("branch", "unknown")
                    key = (branch, hit.get("source"), hit.get("page"))
                    if key in seen_c:
                        continue
                    seen_c.add(key)
                    ref = f"{hit.get('source', 'Unknown source')} — Page {hit.get('page')}" if hit.get("page") is not None else hit.get("source", "Unknown source")
                    by_branch.setdefault(branch, []).append(f"  • {ref}")
                evidence_lines.append("\nComparative retrieval (separate query per option):")
                for branch, refs in by_branch.items():
                    evidence_lines.append(f"{branch}:")
                    evidence_lines.extend(refs)

            evidence_detail_step7 = "\n".join(evidence_lines) if evidence_lines else "No additional personalized or comparative evidence was retrieved."
            steps.append({"step": 7, "title": "Personalized + Comparative Evidence Retrieved", "detail": evidence_detail_step7, "type": "personalized_rag"})

            consensus_label = None
            evidence_vote = None
            consistency = ""

            try:
                if topic:
                    topic_cache = self._get_topic_cache(session, topic)
                    if topic_cache:
                        evidence_vote = topic_cache.get("evidence_vote")
                        consistency = topic_cache.get("consistency", "")
                        consensus_label = topic_cache.get("consensus_label")
            except Exception as evidence_err:
                logger.warning(f"Could not build evidence consensus trace: {evidence_err}")

            consensus_lines = []
            if consensus_label:
                consensus_lines.append(f"Evidence confidence: {consensus_label}")
            else:
                consensus_lines.append("Evidence confidence: Not available (no life-area topic classified)")

            if isinstance(evidence_vote, dict):
                votes = evidence_vote.get("votes", [])
                supportive = sum(1 for v in votes if v.get("vote", 0) > 0)
                challenging = sum(1 for v in votes if v.get("vote", 0) < 0)
                neutral = sum(1 for v in votes if v.get("vote", 0) == 0)
                if votes:
                    consensus_lines.append(f"• Supportive: {supportive}")
                    consensus_lines.append(f"• Challenging: {challenging}")
                    consensus_lines.append(f"• Neutral: {neutral}")
                confidence = evidence_vote.get("confidence_pct")
                if confidence is not None:
                    consensus_lines.append(f"• Confidence score: {confidence}%")
                verdict = evidence_vote.get("verdict")
                if verdict:
                    consensus_lines.append(f"• Verdict: {verdict}")

            if not rag_hits:
                consensus_lines.append(
                    "\nNote: No classical text evidence was retrieved for this specific question. "
                    "The confidence above reflects chart placement, Dasha timing, and Yoga signals only."
                )
            if consistency:
                consensus_lines.append(f"\nSignal consistency:\n{consistency}")

            steps.append({"step": 8, "title": "Evidence Consensus", "detail": "\n".join(consensus_lines), "type": "consensus"})

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

            timeline_note = (
                "\n\n(Timing-Gated Retrieval: the full upcoming Dasha timeline was fetched because this "
                "question was classified as requiring timing.)"
                if (query_understanding or {}).get("requires_timing")
                else "\n\n(Timing-Gated Retrieval: this question wasn't classified as needing timing, so the "
                     "full timeline retrieval was skipped — only the current Mahadasha/Antardasha above is shown.)"
            )
            dasha_detail += timeline_note
            steps.append({"step": 9, "title": "Dasha & Timing", "detail": dasha_detail, "type": "dasha"})

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
                if hit.get("branch"):
                    reference += f" (option: {hit['branch']})"
                reference_lines.append(f"• {reference}")

            evidence_detail_step10 = "\n".join(reference_lines) if reference_lines else "No classical references were available."
            steps.append({"step": 10, "title": "Classical Evidence (Ranked, Deduplicated, Adaptive Depth)", "detail": evidence_detail_step10, "type": "evidence"})

            synthesis_detail = (
                "The final interpretation combines the bucketed evidence (classical rule / Dasha timing / "
                "Yoga, kept as distinct categories), the structured Fact→Rule table (verified placements "
                "paired only with rules that match them exactly), the Evidence Sufficiency Gate's confidence "
                "calibration, verified chart placements, comparative branch analysis, timing-gated Dasha "
                "data, and current-date temporal filtering."
            )
            steps.append({"step": 11, "title": "Evidence Synthesis", "detail": synthesis_detail, "type": "synthesis"})

            specificity_lines = []
            if response_text:
                try:
                    score = compute_chart_specificity(response_text)
                    verdict = "GENERIC" if score.get("is_generic") else "SPECIFIC"
                    specificity_lines.append(f"Status: {verdict}")
                    specificity_lines.append(f"Chart-specific references: {score['entity_count']}")
                    specificity_lines.append(f"Word count: {score['word_count']}")
                    specificity_lines.append(f"Specificity ratio: {score['specificity_ratio']:.1%}")
                    specificity_lines.append(f"Generic filler matches: {score['filler_count']}")
                except Exception as spec_err:
                    logger.warning(f"Could not compute chart specificity for trace: {spec_err}")
                    specificity_lines.append("Status: Not available")
            else:
                specificity_lines.append("Status: Not available — no response text supplied")

            steps.append({"step": 12, "title": "Chart-Specificity Check", "detail": "\n".join(specificity_lines), "type": "specificity"})

            # NEW — Evidence-to-Claim Mapping step
            mapping_detail = self._format_claim_mapping_for_trace(claim_mapping or [])
            steps.append({"step": 13, "title": "Evidence-to-Claim Mapping", "detail": mapping_detail, "type": "claim_mapping"})

            logger.info(f"[TRACE] Reasoning trace built: {len(steps)} steps — titles: {[s['title'] for s in steps]}")
            return steps

        except Exception as e:
            logger.error(f"RAG-first reasoning trace build FAILED entirely: {e}", exc_info=True)
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


chat_service = ChatService()