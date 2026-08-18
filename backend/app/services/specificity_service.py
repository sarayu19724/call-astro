"""
Chart-specificity scoring.

Detects whether an LLM response is actually grounded
in the user's Kundli rather than being generic astrology advice.
"""

import re
from typing import Optional, Dict


CHART_ENTITY_PATTERNS = [
    r"\b(sun|moon|mars|mercury|jupiter|venus|saturn|rahu|ketu)\b",

    r"\b([1-9]|1[0-2])(?:st|nd|rd|th)\s+house\b",

    r"\b(aries|taurus|gemini|cancer|leo|virgo|libra|"
    r"scorpio|sagittarius|capricorn|aquarius|pisces)\b",

    r"\b(mahadasha|antardasha|pratyantardasha|dasha)\b",

    r"\bd(1|7|9|10|24)\b",

    r"\b(ascendant|lagna|rashi)\b",

    r"\b(yoga|exalted|debilitated|retrograde|conjunct)\b",
]


GENERIC_FILLER_PATTERNS = [
    r"\bwork hard\b",
    r"\bstay positive\b",
    r"\bbe patient\b",
    r"\btrust (the|your) (process|journey)\b",
    r"\bgood things (will|are) come\b",
    r"\bkeep faith\b",
    r"\bpositive mindset\b",
    r"\beverything happens for a reason\b",
]


LOW_SPECIFICITY_THRESHOLD = 0.08


def compute_chart_specificity(response_text: str) -> Dict:
    """
    Measure how much of the response is anchored
    to concrete astrology/chart entities.

    Returns:
        entity_count
        word_count
        specificity_ratio
        filler_count
        is_generic
    """

    if not response_text:
        return {
            "entity_count": 0,
            "word_count": 0,
            "specificity_ratio": 0.0,
            "filler_count": 0,
            "is_generic": True,
        }

    text = response_text.lower()

    words = text.split()
    word_count = len(words) or 1

    entity_matches = 0

    for pattern in CHART_ENTITY_PATTERNS:
        entity_matches += len(re.findall(pattern, text))

    filler_matches = 0

    for pattern in GENERIC_FILLER_PATTERNS:
        filler_matches += len(re.findall(pattern, text))

    specificity_ratio = entity_matches / word_count

    is_generic = (
        specificity_ratio < LOW_SPECIFICITY_THRESHOLD
        and filler_matches > 0
    )

    return {
        "entity_count": entity_matches,
        "word_count": word_count,
        "specificity_ratio": round(specificity_ratio, 3),
        "filler_count": filler_matches,
        "is_generic": is_generic,
    }


def build_specificity_correction(
    score: Dict
) -> Optional[str]:
    """
    Build a correction prompt when the generated
    response is too generic.
    """

    if not score.get("is_generic"):
        return None

    return (
        f"The response was too generic "
        f"(chart-specificity ratio "
        f"{score['specificity_ratio']:.1%} — "
        f"only {score['entity_count']} chart-specific "
        f"references across {score['word_count']} words). "

        f"Rewrite it to reference at least 2-3 "
        f"SPECIFIC chart facts "
        f"(a named planet, house, sign, or Dasha period) "
        f"instead of generic encouragement or vague "
        f"astrology language."
    )