"""
Intent + time-horizon classifier — deterministic, keyword-based (no LLM call).
Also includes chart-fact detection, life-area detection, weekly-guidance detection,
and the top-level query router.
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

LIFE_AREA_PATTERNS = {
    "career": [
        r"\bjob\b", r"\bcareer\b", r"\bemployment\b", r"\bprofession\b",
        r"\bpromotion\b", r"\bsalary\b", r"\binterview\b", r"\bplacement\b",
        r"\binternship\b", r"\bgetting hired\b", r"\bget hired\b",
        r"\bnaukri\b", r"\bjob milegi\b", r"\bcareer growth\b",
    ],
    "marriage": [
        r"\bmarriage\b", r"\bmarry\b", r"\bmarried\b", r"\bshaadi\b",
        r"\bvivah\b", r"\bspouse\b", r"\bhusband\b", r"\bwife\b",
    ],
    "education": [
        r"\bstudy\b", r"\beducation\b", r"\bexam\b", r"\bcollege\b",
        r"\buniversity\b", r"\bdegree\b", r"\bresult\b",
    ],
    "finance": [
        r"\bmoney\b", r"\bfinance\b", r"\bfinancial\b", r"\bincome\b",
        r"\bwealth\b", r"\bbusiness\b", r"\bprofit\b",
    ],
    "health": [
        r"\bhealth\b", r"\bhealthcare\b", r"\billness\b", r"\bdisease\b",
        r"\bwellness\b",
    ],
}

WEEKLY_GUIDANCE_PATTERNS = [
    r"\bthis week\b", r"\bweekly guidance\b", r"\bweek ahead\b",
    r"\bhow will my week be\b", r"\bhow is my week\b",
    r"\bthis week's guidance\b", r"\bwhat should i focus on this week\b",
    r"\biss hafte\b", r"\bis hafte\b",
]


def classify_intent(message: str) -> str:
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


def detect_life_area(message: str) -> Optional[str]:
    text = message.lower()
    for life_area, patterns in LIFE_AREA_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text):
                return life_area
    return None


def is_weekly_guidance_request(message: str) -> bool:
    text = message.lower().strip()
    return any(re.search(pattern, text) for pattern in WEEKLY_GUIDANCE_PATTERNS)


def is_followup(message: str, history_text: str) -> bool:
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
        "about WHEN using the Dasha timeline provided. Answer the user's "
        "actual life-area question, not generic weekly guidance."
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
        "remedies tied to the specific weak/afflicted factor in their chart. "
        "Do not list many remedies."
    ),
    "general": (
        "Give a natural, integrated prediction focused on the user's actual "
        "question and identified life area. Do not default to weekly guidance."
    ),
}


def get_response_contract(intent: str) -> str:
    return RESPONSE_CONTRACTS.get(intent, RESPONSE_CONTRACTS["general"])

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
    text = message.lower()
    for fact_type, patterns in CHART_FACT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text):
                return fact_type
    return None

KNOWLEDGE_ONLY_PATTERNS = [
    r"\bwhat does .* mean\b", r"\bwhat is .* in vedic astrology\b",
    r"\bkya matlab hai\b", r"\bwhat does .* signify\b",
    r"\bwhat is the significance of\b", r"\bexplain .* yoga\b",
    r"\bwhat is .*(dasha|yoga|nakshatra|graha)\b",
]


def route_query(message: str, history_text: str = "") -> str:
    if is_weekly_guidance_request(message):
        return "weekly_guidance"
    if is_chart_fact_question(message):
        return "chart_fact"
    intent = classify_intent(message)
    if intent == "timing":
        return "timing"
    if intent in ("explanation", "strength_check"):
        return "analysis"
    text = message.lower()
    if any(re.search(pattern, text) for pattern in KNOWLEDGE_ONLY_PATTERNS):
        return "knowledge"
    return "analysis"
