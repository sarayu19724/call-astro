"""
Hybrid Topic Router — 3-layer classification pipeline for AstroTalk.

Layer 1: Keyword match          (< 1ms,   zero API cost)
Layer 2: Semantic vector sim    (< 50ms,  zero API cost — reuses existing embeddings model)
Layer 3: LLM structured output  (< 1.5s,  small token cost — only when L1+L2 both fail)

Returns a TopicResult dataclass that carries enough context to enrich the
"HOW I REACHED THIS" reasoning panel with:
  - which classification method was used
  - confidence score
  - detected astrological concepts (Ashtakavarga, Bindus, Kakshya, etc.)
  - house numbers mentioned in the query
  - a one-sentence LLM-generated summary (Layer 3 only)
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from typing import List, Optional, TYPE_CHECKING

import numpy as np

from app.utils.logger import logger

if TYPE_CHECKING:
    from app.rag.embeddings import EmbeddingsProvider

# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class TopicResult:
    topic: Optional[str]                # "career" | "marriage" | "health" | "finance" | "education" | None
    method: str                         # "keyword" | "semantic" | "llm" | "none"
    confidence: float                   # 0.0 – 1.0
    llm_summary: Optional[str] = None  # LLM-generated 1-line description (Layer 3 only)
    detected_houses: List[int] = field(default_factory=list)
    detected_concepts: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Layer 1 — keyword map (fast O(1) lookup)
# ---------------------------------------------------------------------------

_KEYWORD_MAP: dict[str, str] = {
    # career
    "career": "career", "job": "career", "profession": "career", "naukri": "career",
    "business": "career", "work": "career", "kaam": "career", "promotion": "career",
    "government job": "career", "sarkari": "career", "dasamsa": "career", "d10": "career",
    "rozgar": "career", "vyapar": "career", "udyog": "career",

    # marriage
    "marriage": "marriage", "shaadi": "marriage", "spouse": "marriage", "wife": "marriage",
    "husband": "marriage", "partner": "marriage", "relationship": "marriage", "vivah": "marriage",
    "shadi": "marriage", "navamsa": "marriage", "d9": "marriage", "love": "marriage",
    "rishta": "marriage", "dulha": "marriage", "dulhan": "marriage", "married": "marriage",
    "wedding": "marriage", "bride": "marriage", "groom": "marriage",

    # health
    "health": "health", "sehat": "health", "illness": "health", "disease": "health",
    "body": "health", "bimari": "health", "rog": "health", "aushadhi": "health",
    "doctor": "health", "hospital": "health", "surgery": "health", "cancer": "health",
    

    # abroad
    "abroad": "abroad", "foreign": "abroad", "visa": "abroad", "immigration": "abroad",
    "country": "abroad", "settle": "abroad", "bidesh": "abroad", "videsh": "abroad", "relocate": "abroad",
    "homeland": "abroad",

    # remedies
    "remedy": "remedies", "remedies": "remedies", "gemstone": "remedies", "mantra": "remedies",
    "pooja": "remedies", "puja": "remedies", "upay": "remedies", "donate": "remedies",

    # muhurta
    "muhurta": "muhurta", "muhurat": "muhurta", "auspicious": "muhurta", "timing": "muhurta",
    "shubh": "muhurta", "date": "muhurta",

    # finance
    "money": "finance", "finance": "finance", "paisa": "finance", "wealth": "finance",
    "income": "finance", "dhan": "finance", "paise": "finance", "loan": "finance",
    "debt": "finance", "investment": "finance", "property": "finance", "savings": "finance",
    "aamdani": "finance", "arthik": "finance",

    # children / progeny / parenthood
    "kids": "children", "kid": "children", "child": "children", "children": "children",
    "bacche": "children", "baccha": "children", "baby": "children", "santana": "children",
    "santan": "children", "parenthood": "children", "pregnancy": "children", "progeny": "children",
    "pregnant": "children", "conceive": "children", "conceiving": "children", "son": "children", "daughter": "children",

    # education
    "education": "education", "study": "education", "padhai": "education", "exam": "education",
    "school": "education", "college": "education", "university": "education", "degree": "education",
    "shiksha": "education", "vidya": "education", "pariksha": "education",
}


def _keyword_classify(text: str) -> Optional[str]:
    text_lower = text.lower()
    for kw, topic in _KEYWORD_MAP.items():
        if kw in text_lower:
            return topic
    return None


# ---------------------------------------------------------------------------
# Layer 2 — semantic anchor phrases (cosine similarity against embeddings)
# ---------------------------------------------------------------------------

_TOPIC_ANCHORS: dict[str, list[str]] = {
    "career": [
        "job career profession business work",
        "10th house Saturn career growth promotion",
        "what work should I do profession income",
        "dasamsa chart career timing",
    ],
    "marriage": [
        "marriage spouse partner love relationship",
        "7th house Venus Jupiter marriage timing",
        "when will I get married love life",
        "navamsa chart spouse qualities",
    ],
    "health": [
        "health disease illness body 6th house",
        "medical issue surgery hospital doctor",
        "physical strength weakness injury accident",
        "mental peace anxiety stress",
    ],

    "abroad": [
        "abroad foreign settlement visa immigration 12th house 9th house Rahu",
        "settle in another country move relocate homeland",
        "bidesh videsh travel journey",
    ],
    "remedies": [
        "remedy gemstone mantra pooja puja upay donation",
        "how to reduce bad effects of malefic planets",
        "stone ratna pacify appease",
    ],
    "muhurta": [
        "muhurta auspicious timing date shubh muhurat",
        "best time to start buy inaugurate",
        "panchang tithi nakshatra favorable time",
    ],
    "finance": [
        "money wealth income finance gains 11th house 2nd house",
        "dhan labha Jupiter Venus Mercury financial",
        "property investment savings loan debt",
    ],
    "education": [
        "education study exam college Mercury Jupiter 5th house",
        "degree school university padhai shiksha",
    ],
}

# Cache: topic -> mean anchor embedding vector
_anchor_cache: dict[str, np.ndarray] = {}
_anchor_counts: dict[str, int] = {}
_anchor_cache_ready = threading.Event()  # signals when cache is built


def _build_anchor_cache(embeddings_provider: "EmbeddingsProvider") -> None:
    """Embed all anchor phrases and cache the mean vector per topic.
    Called in a background thread at startup — never blocks a user request."""
    global _anchor_cache
    if _anchor_cache_ready.is_set():
        return  # already built

    logger.info("HybridRouter: building semantic anchor cache in background…")
    cache = {}
    for topic, phrases in _TOPIC_ANCHORS.items():
        try:
            vecs = []
            for phrase in phrases:
                vec = embeddings_provider.get_embedding(phrase)
                vecs.append(np.array(vec, dtype=np.float32))
            cache[topic] = np.mean(vecs, axis=0)
            _anchor_counts[topic] = len(vecs)
        except Exception as e:
            logger.warning(f"HybridRouter: failed to embed anchors for '{topic}': {e}")

    _anchor_cache.update(cache)
    _anchor_cache_ready.set()
    logger.info(f"HybridRouter: anchor cache ready for topics: {list(_anchor_cache.keys())}")


def prewarm_anchor_cache(embeddings_provider: "EmbeddingsProvider") -> None:
    """Launch background thread to pre-warm the semantic anchor cache.
    Call this once from app startup so the cache is ready by the time
    users start asking questions."""
    t = threading.Thread(
        target=_build_anchor_cache,
        args=(embeddings_provider,),
        daemon=True,
        name="hybrid-router-prewarm",
    )
    t.start()
    logger.info("HybridRouter: anchor cache pre-warm thread started.")


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def _semantic_classify(
    text: str,
    embeddings_provider: "EmbeddingsProvider",
    threshold: float = 0.50,
) -> tuple[Optional[str], float]:
    """Return (topic, confidence) or (None, 0.0) if below threshold.
    Skipped gracefully if the anchor cache hasn't been built yet."""
    try:
        # Skip Layer 2 entirely if cache not ready — don't block the user
        if not _anchor_cache_ready.is_set():
            logger.debug("HybridRouter L2: anchor cache not ready yet, skipping semantic layer.")
            return None, 0.0

        query_vec = np.array(embeddings_provider.get_embedding(text), dtype=np.float32)
        best_topic, best_score = None, 0.0

        for topic, anchor_vec in _anchor_cache.items():
            score = _cosine_similarity(query_vec, anchor_vec)
            if score > best_score:
                best_score = score
                best_topic = topic

        if best_score >= threshold:
            return best_topic, round(best_score, 3)
        return None, round(best_score, 3)
    except Exception as e:
        logger.warning(f"HybridRouter Layer 2 error: {e}")
        return None, 0.0


# ---------------------------------------------------------------------------
# Layer 3 — LLM structured output (last resort)
# ---------------------------------------------------------------------------

_ROUTER_SYSTEM_PROMPT = (
    "You are a Vedic astrology query router. Your ONLY job is to classify what the user is asking about. "
    "Do NOT answer the question. Return ONLY valid JSON — no markdown, no explanation."
)

_ROUTER_USER_PROMPT = """Classify this astrology question into the following fields:

1. "topic" — MUST be exactly one of: "career", "marriage", "health", "finance", "education", "abroad", "remedies", "muhurta", or null if it's a general chart/planet/dasha question.
2. "houses" — list of house numbers (1-12) explicitly or implicitly relevant to this question. Empty list if none.
3. "concepts" — list of specific astrological concepts mentioned (e.g. "Ashtakavarga", "Bindu", "Kakshya", "Shodhana", "Mahadasha", "Antardasha", "Pratyantardasha", "Nakshatra", "Transit", "Yoga", "Lagna"). Empty list if none.
4. "summary" — one short sentence (max 15 words) describing what astrological topic this question is about.

Return ONLY this JSON shape:
{{"topic": "...", "houses": [...], "concepts": [...], "summary": "..."}}

User question: {message}"""


def _llm_classify(text: str) -> tuple[Optional[str], List[int], List[str], Optional[str]]:
    """Returns (topic, houses, concepts, summary). Falls back gracefully on any error."""
    try:
        from app.services.llm_service import llm_service
        prompt = _ROUTER_USER_PROMPT.format(message=text)
        raw = llm_service.generate(
            prompt=prompt,
            system_prompt=_ROUTER_SYSTEM_PROMPT,
            json_format=True,
            temperature=0.0,
        )
        data = json.loads(raw)
        topic = data.get("topic") or None
        if topic and topic not in _TOPIC_ANCHORS:
            topic = None
        houses = [int(h) for h in (data.get("houses") or []) if str(h).isdigit() and 1 <= int(h) <= 12]
        concepts = [str(c).strip() for c in (data.get("concepts") or []) if c]
        summary = data.get("summary") or None
        return topic, houses, concepts, summary
    except Exception as e:
        logger.warning(f"HybridRouter Layer 3 LLM error: {e}")
        return None, [], [], None


# ---------------------------------------------------------------------------
# Concept & house detection (runs independently of topic, enriches the panel)
# ---------------------------------------------------------------------------

_CONCEPT_PATTERNS: list[tuple[str, str]] = [
    (r"\bashtakavarg[a]?\b", "Ashtakavarga"),
    (r"\bbindu[s]?\b", "Bindus"),
    (r"\bkakshya\b", "Kakshya"),
    (r"\bshodhana\b", "Shodhana"),
    (r"\btrikona\b", "Trikona"),
    (r"\bekadhipatya\b", "Ekadhipatya"),
    (r"\bsarvashtakavarga\b|\bsav\b", "Sarvashtakavarga"),
    (r"\bmahadasha\b|\bmaha dasha\b", "Mahadasha"),
    (r"\bantardasha\b|\bantar dasha\b", "Antardasha"),
    (r"\bpratyantardasha\b|\bpratyant[a]?\b", "Pratyantardasha"),
    (r"\bnakshatra\b", "Nakshatra"),
    (r"\btransit[s]?\b|\bgochar\b", "Transit/Gochar"),
    (r"\byoga[s]?\b", "Yoga"),
    (r"\blagna\b|\bascendant\b", "Lagna/Ascendant"),
    (r"\bvimshottari\b", "Vimshottari Dasha"),
    (r"\bjaimini\b", "Jaimini"),
    (r"\bchara dasa\b|\bchara dasha\b", "Chara Dasha"),
    (r"\batmakaraka\b", "Atmakaraka"),
    (r"\bnavamsa\b|\bd9\b", "Navamsa (D9)"),
    (r"\bdasamsa\b|\bd10\b", "Dasamsa (D10)"),
    (r"\bkendra\b", "Kendra"),
    (r"\btrikona\b", "Trikona"),
    (r"\bdusthana\b", "Dusthana"),
    (r"\baspect[s]?\b|\bdrishti\b", "Aspect/Drishti"),
    (r"\bretrograde\b|\bvakri\b", "Retrograde"),
    (r"\bexaltation\b|\buchcha\b", "Exaltation"),
    (r"\bdebilitation\b|\bneecha\b", "Debilitation"),
    (r"\bconjunction\b|\byuti\b", "Conjunction"),
    (r"\bpada\b", "Pada"),
]

_HOUSE_PATTERN = re.compile(r"\b(1[0-2]|[1-9])(st|nd|rd|th)?\s*house\b", re.IGNORECASE)


def _detect_concepts_and_houses(text: str) -> tuple[List[str], List[int]]:
    text_lower = text.lower()
    concepts = []
    for pattern, label in _CONCEPT_PATTERNS:
        if re.search(pattern, text_lower):
            concepts.append(label)

    house_matches = _HOUSE_PATTERN.findall(text)
    houses = list({int(m[0]) for m in house_matches})

    return concepts, sorted(houses)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def _adapt_anchor_cache(topic: str, text: str, embeddings_provider: "EmbeddingsProvider") -> None:
    """Background task: dynamically update the topic's mean anchor vector with a new query."""
    try:
        if not _anchor_cache_ready.is_set() or topic not in _anchor_cache:
            return
        
        # Embed the new user query
        new_vec = np.array(embeddings_provider.get_embedding(text), dtype=np.float32)
        
        # Perform rolling average update
        current_mean = _anchor_cache[topic]
        n = _anchor_counts.get(topic, 1)
        
        # New mean = (Current Mean * N + New Vector) / (N + 1)
        updated_mean = ((current_mean * n) + new_vec) / (n + 1)
        
        _anchor_cache[topic] = updated_mean
        _anchor_counts[topic] = n + 1
        
        logger.info(f"HybridRouter: Adaptive Cache updated for '{topic}'. New sample count: {n + 1}")
    except Exception as e:
        logger.warning(f"HybridRouter: Adaptive cache update failed: {e}")

def route_topic(message: str, embeddings_provider: "EmbeddingsProvider") -> TopicResult:
    """
    Classify a user message into a topic using the 3-layer hybrid pipeline.
    This is a synchronous function safe to call from both sync and async contexts.
    """
    if not message or not message.strip():
        return TopicResult(topic=None, method="none", confidence=0.0)

    # Always extract concepts & houses — these enrich the reasoning panel regardless of topic
    detected_concepts, detected_houses = _detect_concepts_and_houses(message)

    # ── Layer 1: keyword match ──────────────────────────────────────────────
    kw_topic = _keyword_classify(message)
    if kw_topic:
        logger.info(f"HybridRouter L1 (keyword): '{kw_topic}'")
        return TopicResult(
            topic=kw_topic,
            method="keyword",
            confidence=1.0,
            detected_houses=detected_houses,
            detected_concepts=detected_concepts,
        )

    # ── Layer 2: semantic similarity ────────────────────────────────────────
    sem_topic, sem_score = _semantic_classify(message, embeddings_provider)
    if sem_topic:
        logger.info(f"HybridRouter L2 (semantic): '{sem_topic}' @ {sem_score:.3f}")
        return TopicResult(
            topic=sem_topic,
            method="semantic",
            confidence=sem_score,
            detected_houses=detected_houses,
            detected_concepts=detected_concepts,
        )

    # ── Layer 3: LLM structured output ─────────────────────────────────────
    logger.info(f"HybridRouter L3 (LLM): classifying '{message[:60]}…'")
    llm_topic, llm_houses, llm_concepts, llm_summary = _llm_classify(message)

    # Merge LLM-detected houses & concepts with regex-detected ones
    all_houses = sorted(set(detected_houses + llm_houses))
    all_concepts = list(dict.fromkeys(detected_concepts + llm_concepts))

    logger.info(f"HybridRouter L3 result: topic='{llm_topic}', summary='{llm_summary}'")
    
    # Adaptive Cache Improvement: If Layer 3 found a valid topic, 
    # learn from it by updating the semantic anchors in the background
    if llm_topic:
        threading.Thread(
            target=_adapt_anchor_cache,
            args=(llm_topic, message, embeddings_provider),
            daemon=True,
            name="hybrid-router-adaptive"
        ).start()

    return TopicResult(
        topic=llm_topic,
        method="llm",
        confidence=0.75 if llm_topic else 0.3,
        llm_summary=llm_summary,
        detected_houses=all_houses,
        detected_concepts=all_concepts,
    )
