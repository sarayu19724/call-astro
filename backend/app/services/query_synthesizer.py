"""
Universal Query Synthesizer & Mode Classifier

Two responsibilities:

1. classify_query_mode(message) -> "theoretical" | "personal"
   Determines whether the user is asking a general/educational astrology question
   (theoretical) or a personal chart reading (personal). This single bit of
   information drives a fundamentally different LLM prompt instruction, preventing
   the AI from falsely personalizing general questions to the native's chart.

2. synthesize_rag_query(message, topic, detected_houses, detected_concepts, query_mode) -> str
   Translates any raw user message (Hinglish, slang, abbreviations) into a clean,
   canonical English string optimized for classical book retrieval in the vector
   store. Runs in sub-millisecond (pure Python, zero LLM cost).

   Input:  "shani 11th house mein transit ho to kya hoga?"
   Output: "Saturn transit 11th house Gochar effects classical Vedic"

   This ensures EVERY query gets an optimized RAG search string, not just the ones
   that happen to go through Layer 3 (LLM) of the hybrid router.
"""

import re
from typing import List, Optional


# ---------------------------------------------------------------------------
# Hinglish / abbreviated planet name -> English canonical name
# ---------------------------------------------------------------------------

_PLANET_MAP = {
    # Hindi / Sanskrit names
    "shani": "Saturn", "shani dev": "Saturn",
    "guru": "Jupiter", "brihaspati": "Jupiter",
    "mangal": "Mars", "mangaldev": "Mars", "angaraka": "Mars",
    "shukra": "Venus",
    "budh": "Mercury", "budha": "Mercury",
    "surya": "Sun", "ravi": "Sun",
    "chandra": "Moon", "som": "Moon",
    "rahu": "Rahu",
    "ketu": "Ketu",
    # English abbreviations / common misspellings
    "jup": "Jupiter", "sat": "Saturn", "mar": "Mars",
    "ven": "Venus", "mer": "Mercury", "moo": "Moon",
    "sun": "Sun", "moon": "Moon",
    "jupiter": "Jupiter", "saturn": "Saturn", "mars": "Mars",
    "venus": "Venus", "mercury": "Mercury",
}

# Topic -> domain keywords appended to the synthesized query for better book targeting
_TOPIC_BIAS = {
    "career":    "10th house profession career D10 Dasamsa Saturn Sun",
    "marriage":  "7th house spouse marriage Venus Jupiter Navamsa D9",
    "health":    "1st house 6th house health disease lagna Saturn Mars",
    "finance":   "2nd house 11th house wealth Dhan Jupiter Venus gains",
    "education": "5th house education study Mercury Jupiter intellect",
    "abroad":    "12th house 9th house foreign travel Rahu Saturn abroad",
    "remedies":  "remedies gemstone mantra donation 9th house Jupiter",
    "muhurta":   "muhurta auspicious timing panchang tithi nakshatra",
    "children":  "5th house progeny children Jupiter D7 Saptamsa",
    "general":   "birth chart ascendant lagna planets Vedic astrology",
}

# ---------------------------------------------------------------------------
# Patterns that signal a THEORETICAL / general-knowledge query
# ---------------------------------------------------------------------------

_THEORETICAL_PATTERNS = [
    # "what is X", "what does X mean", "what happens when"
    r"\bwhat\s+is\s+(a\s+|an\s+|the\s+)?[a-z]",
    r"\bwhat\s+does\s+.+\s+mean\b",
    r"\bwhat\s+happens\s+when\b",
    r"\bwhat\s+are\s+(the\s+)?effects?\s+of\b",
    # "tell me the effect/significance/meaning of"
    r"\b(tell\s+me\s+(the\s+)?(effect|significance|meaning|result|impact|importance|role)\s+of)\b",
    r"\b(effect|significance|meaning|result|importance|role)\s+of\s+(planet|house|yoga|transit|gochar|nakshatra)\b",
    # "explain X", "describe X"
    r"\bexplain\s+(the\s+)?[a-z]",
    r"\bdescribe\s+(the\s+)?[a-z]",
    # "if [planet] is in [house]" — hypothetical framing
    r"\bif\s+(sun|moon|mars|mercury|jupiter|venus|saturn|rahu|ketu|shani|guru|mangal|shukra|budh|surya|chandra)\s+(is|are|be|transits?|placed?|sits?|moves?)\b",
    r"\bif\s+(someone|a\s+person|a\s+native|anyone)\s+(has|have|is|are)\b",
    # "in general", "generally speaking"
    r"\bin\s+general\b",
    r"\bgenerally\s+speaking\b",
    r"\bclassically\b",
    r"\bin\s+vedic\s+astrology\b",
    # "how does [planet] affect [house]" without possessive "my/mera"
    r"\bhow\s+does\s+(sun|moon|mars|mercury|jupiter|venus|saturn|rahu|ketu|shani|guru|mangal|shukra|budh|surya|chandra)\b",
    # Planet + "in" + house + "house" without "my"
    r"\b(sun|moon|mars|mercury|jupiter|venus|saturn|rahu|ketu)\s+in\s+(the\s+)?(1st|2nd|3rd|4th|5th|6th|7th|8th|9th|10th|11th|12th)\s+house\b",
]

# Patterns that force PERSONAL mode even if theoretical patterns match
_PERSONAL_OVERRIDE_PATTERNS = [
    r"\bmy\b", r"\bmine\b", r"\bi\s+(am|have|will|want|need|see)\b",
    r"\bmera\b", r"\bmeri\b", r"\bmere\b",
    r"\bapna\b", r"\bapni\b", r"\bapne\b",
    r"\bmy\s+chart\b", r"\bmy\s+kundli\b", r"\bmy\s+lagna\b",
    r"\bmujhe\b", r"\bmain\b",
    r"\bwill\s+i\b", r"\bkab\s+hoga\b", r"\bkab\s+hogi\b",
    r"\bwhen\s+will\s+i\b",
]

_THEORETICAL_RE = [re.compile(p, re.IGNORECASE) for p in _THEORETICAL_PATTERNS]
_PERSONAL_OVERRIDE_RE = [re.compile(p, re.IGNORECASE) for p in _PERSONAL_OVERRIDE_PATTERNS]


def classify_query_mode(message: str) -> str:
    """
    Returns 'theoretical' if the user is asking a general astrology question,
    or 'personal' if they are asking about their own chart.

    Logic:
    1. If any personal override pattern matches -> always 'personal'
    2. Else if any theoretical pattern matches -> 'theoretical'
    3. Default -> 'personal' (safe fallback for personal chart readings)
    """
    text = message.strip()

    # Personal override takes highest priority
    for pattern in _PERSONAL_OVERRIDE_RE:
        if pattern.search(text):
            return "personal"

    # Theoretical pattern detection
    for pattern in _THEORETICAL_RE:
        if pattern.search(text):
            return "theoretical"

    return "personal"


# ---------------------------------------------------------------------------
# Query synthesizer helpers
# ---------------------------------------------------------------------------

def _normalize_planets(text: str) -> str:
    """Replace Hinglish/abbreviated planet names with canonical English names."""
    text_lower = text.lower()
    for hinglish, english in _PLANET_MAP.items():
        # Word-boundary replace (avoid replacing "sun" inside "sunday")
        text_lower = re.sub(r"\b" + re.escape(hinglish) + r"\b", english, text_lower)
    return text_lower


def _extract_house_numbers(text: str) -> List[str]:
    """Extract house ordinals like '5th', '11th', '1st'."""
    matches = re.findall(r"\b(1[0-2]|[1-9])(?:st|nd|rd|th)?\s*house\b", text, re.IGNORECASE)
    return [f"{m}th house" for m in matches]


def synthesize_rag_query(
    message: str,
    topic: Optional[str] = None,
    detected_houses: Optional[List[int]] = None,
    detected_concepts: Optional[List[str]] = None,
    query_mode: str = "personal",
) -> str:
    """
    Produce a clean, canonical English search string for the vector store.

    Priority order of query components:
    1. Normalized planet names from the message
    2. House numbers from the message or detected_houses
    3. Key astrological concept terms (transit, yoga, dasha, etc.)
    4. Topic-specific domain bias keywords
    5. Mode-appropriate suffix (classical Vedic / personal chart)

    The output is a single concatenated string with the most signal-dense
    terms first, which is exactly what hybrid search (BM25 + cosine) needs.
    """
    # Step 1: Normalize planet names in the message
    normalized = _normalize_planets(message)

    # Step 2: Extract canonical planet names found in message
    planet_names = []
    canonical_planets = [
        "Sun", "Moon", "Mars", "Mercury", "Jupiter",
        "Venus", "Saturn", "Rahu", "Ketu"
    ]
    for planet in canonical_planets:
        if planet.lower() in normalized.lower():
            planet_names.append(planet)

    # Step 3: Extract house numbers
    house_terms = _extract_house_numbers(normalized)
    if not house_terms and detected_houses:
        house_terms = [f"{h}th house" for h in detected_houses]

    # Step 4: Detect key astrological keywords in the normalized text
    astro_keywords = []
    keyword_map = {
        "transit": ["transit", "gochar", "gochara", "transiting"],
        "yoga": ["yoga", "yog"],
        "dasha": ["dasha", "mahadasha", "antardasha", "dasha period"],
        "retrograde": ["retrograde", "vakri"],
        "conjunction": ["conjunction", "yuti", "conjunct"],
        "aspect": ["aspect", "drishti"],
        "exaltation": ["exaltation", "uchcha", "exalted"],
        "debilitation": ["debilitation", "neecha", "debilitated"],
        "nakshatra": ["nakshatra", "star lord", "sub lord"],
    }
    text_lower = normalized.lower()
    for canonical, variants in keyword_map.items():
        if any(v in text_lower for v in variants):
            astro_keywords.append(canonical)

    # Step 5: Build the synthesized query
    parts = []
    if planet_names:
        parts.extend(planet_names)
    if house_terms:
        parts.extend(house_terms)
    if astro_keywords:
        parts.extend(astro_keywords)
    if detected_concepts:
        parts.extend(detected_concepts[:3])  # cap to avoid over-loading

    # Topic bias
    bias = _TOPIC_BIAS.get(topic or "general", "")
    if bias:
        parts.append(bias)

    # Mode-appropriate suffix for classical book retrieval
    if query_mode == "theoretical":
        parts.append("effects classical Vedic general")
    else:
        parts.append("Vedic astrology")

    # If we extracted nothing useful, fall back to normalized message text
    if not planet_names and not house_terms and not astro_keywords:
        return f"{normalized.strip()} {bias}".strip()

    # Deduplicate while preserving order
    seen = set()
    unique_parts = []
    for part in parts:
        key = part.lower().strip()
        if key not in seen:
            seen.add(key)
            unique_parts.append(part)

    return " ".join(unique_parts)
