"""
Intent + time-horizon classifier — deterministic, keyword-based (no LLM call).
Also includes chart-fact detection and the top-level query router.
"""
import re
from typing import Optional, Dict

INTENT_PATTERNS = {
    "timing": [
        r"\bwhen\b", r"\bkab\b", r"\bkis (saal|year|mahine|month)\b",
        r"\bhow soon\b", r"\btime.*(marriage|job|career)\b",
    ],
    "simple_fact": [
        r"\bwhat is my\b", r"\bmera .* kya hai\b", r"\bwhich sign\b",
        r"\bmoon sign\b", r"\bascendant\b", r"\blagna kya\b",
    ],
    "explanation": [
        r"\bwhy\b", r"\bkyu\b", r"\bkyun\b", r"\breason\b", r"\bkaran\b",
    ],
    "strength_check": [
        r"\bis my .* strong\b", r"\bstrength\b", r"\bkitna strong\b",
        r"\bweak\b", r"\bkamzor\b",
    ],
    "remedy": [
        r"\bremedy\b", r"\bupay\b", r"\bgemstone\b", r"\bratna\b",
        r"\bwhat should i do\b", r"\bkya karu\b",
    ],
}

TIME_HORIZON_PATTERNS = [
    (r"\bnext (\d+)\s*(month|year)", "explicit"),
    (r"\bthis year\b|\bis saal\b", "current_year"),
    (r"\bnext year\b|\bagle saal\b", "next_year"),
    (r"\blifetime\b|\bever\b|\bkabhi\b", "lifetime"),
    (r"\bright now\b|\babhi\b|\bcurrently\b", "current"),
]

STYLE_PATTERNS = {
    "short": [r"\bshort\b", r"\bquick\b", r"\bjaldi\b", r"\bek line\b"],
    "detailed": [r"\bdetail\b", r"\bexplain properly\b", r"\bvistaar\b", r"\bpuri baat\b"],
}


def classify_intent(message: str) -> str:
    # Returns timing, simple_fact, explanation, strength_check, remedy, or general
    text = message.lower()
    for intent, patterns in INTENT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text):
                return intent
    return "general"


def extract_time_horizon(message: str) -> Optional[str]:
    text = message.lower()
    for pattern, label in TIME_HORIZON_PATTERNS:
        if re.search(pattern, text):
            return label
    return None


def detect_requested_style(message: str) -> Optional[str]:
    text = message.lower()
    for style, patterns in STYLE_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text):
                return style
    return None


def is_followup(message: str, history_text: str) -> bool:
    # Short message + existing history + followup markers suggests a followup
    if not history_text:
        return False
    word_count = len(message.split())
    followup_markers = ["what about", "aur", "uske baad", "then", "also", "and"]
    has_marker = any(m in message.lower() for m in followup_markers)
    return word_count <= 8 or has_marker


RESPONSE_CONTRACTS: Dict[str, str] = {
    "simple_fact": (
        "This is a SIMPLE FACT question. Answer directly in 1 sentence "
        "(the fact itself), then ONE short sentence on what it means. "
        "Do not bring in Dasha, timing, or unrelated chart factors."
    ),
    "timing": (
        "This is a TIMING question. Structure your answer as: (1) the most "
        "relevant upcoming or current period, (2) why that period is "
        "relevant (which planet/house), (3) one practical note. Be specific "
        "about WHEN using the Dasha timeline provided — do not give a vague "
        "'in the future' answer if real period data is available."
    ),
    "explanation": (
        "This is a WHY question. Lead with the main chart factor causing "
        "the situation, then a secondary supporting factor if one exists. "
        "Avoid vague causes — name the specific planet/house responsible."
    ),
    "strength_check": (
        "This is a STRENGTH question. State the strength directly (strong / "
        "moderate / weak / mixed), THEN give the specific factors behind "
        "that verdict. Do not hedge the verdict itself."
    ),
    "remedy": (
        "This is a REMEDY question. Suggest ONE, at most TWO, low-risk "
        "remedies (gemstone, simple practice) tied to the specific weak/"
        "afflicted factor in their chart. Do not list many remedies."
    ),
    "general": (
        "Give a natural, integrated prediction weaving chart placement and "
        "timing together, as per your normal style."
    ),
}


def get_response_contract(intent: str) -> str:
    return RESPONSE_CONTRACTS.get(intent, RESPONSE_CONTRACTS["general"])


# ------------------------------------------------------------------
# Chart-fact detection — questions answerable directly from Kundli data
# ------------------------------------------------------------------
CHART_FACT_PATTERNS = {
    "ascendant": [r"\bmy ascendant\b", r"\bmera lagna\b", r"\blagna kya\b", r"\brising sign\b"],
    "moon_sign": [r"\bmy moon sign\b", r"\bmera (chandra )?rashi\b", r"\bmoon sign kya\b"],
    "sun_sign": [r"\bmy sun sign\b", r"\bmera surya rashi\b"],
    "planet_position": [
        r"\bwhere is (my )?(sun|moon|mars|mercury|jupiter|venus|saturn|rahu|ketu)\b",
        r"\b(sun|moon|mars|mercury|jupiter|venus|saturn|rahu|ketu) (kis|which) (sign|rashi|house)\b",
        r"\bmera (sun|moon|mars|mercury|jupiter|venus|saturn|rahu|ketu) kahan\b",
    ],
    "current_dasha": [r"\bmy current dasha\b", r"\bmeri current dasha\b", r"\bwhich dasha am i in\b", r"\babhi kaunsi dasha\b"],
    "birth_details": [r"\bmy (dob|date of birth|birth time|birth place)\b", r"\bmera janm\b"],
}


def is_chart_fact_question(message: str) -> Optional[str]:
    # Returns fact type if answerable directly from Kundli data, else None
    text = message.lower()
    for fact_type, patterns in CHART_FACT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text):
                return fact_type
    return None


# ------------------------------------------------------------------
# Query Router — top-level decision for RAG/Kundli/topic-bundle usage
# ------------------------------------------------------------------
KNOWLEDGE_ONLY_PATTERNS = [
    r"\bwhat does .* mean\b", r"\bwhat is .* in vedic astrology\b",
    r"\bkya matlab hai\b", r"\bwhat does .* signify\b",
    r"\bwhat is the significance of\b", r"\bexplain .* yoga\b",
    r"\bwhat is .*(dasha|yoga|nakshatra|graha)\b",
]


def route_query(message: str, history_text: str = "") -> str:
    # Returns one of: chart_fact, knowledge, timing, analysis
    if is_chart_fact_question(message):
        return "chart_fact"

    intent = classify_intent(message)
    if intent == "timing":
        return "timing"
    if intent in ("explanation", "strength_check"):
        return "analysis"

    text = message.lower()
    if any(re.search(p, text) for p in KNOWLEDGE_ONLY_PATTERNS):
        return "knowledge"

    return "analysis"