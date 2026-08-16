"""
Post-generation claim validator — a step up from the basic mention-check in
quality_checker.py. Specifically validates DATE/TIMEFRAME claims against the
real Dasha timeline (the most dangerous hallucination category: a model
stating a confident year/period that doesn't match any real period fed to
it), and flags absolute/deterministic language that shouldn't appear given
your evidence-voting confidence level.
"""
import re
from typing import List, Optional, Dict

# Deterministic/absolute claim language — dangerous when evidence is mixed
# or confidence is not high, per your "avoid fear-based/deterministic
# wording" principle.
ABSOLUTE_CLAIM_PATTERNS = [
    r"\bwill definitely\b", r"\byou will surely\b", r"\bguaranteed\b",
    r"\b100%\b", r"\bcertainly will\b", \
    r"\bpakka\b.*\bhoga\b", r"\bzaroor\b.*\bhoga\b",
]

YEAR_PATTERN = re.compile(r"\b(20\d{2})\b")


def _extract_years_from_timeline(dasha_timeline: str) -> List[int]:
    """Pull every year mentioned in the real dasha timeline text — these are
    the ONLY years a response is allowed to confidently cite."""
    if not dasha_timeline:
        return []
    return [int(y) for y in YEAR_PATTERN.findall(dasha_timeline)]


def validate_claims(
    response_text: str,
    dasha_timeline: str = "",
    evidence_vote: Optional[Dict] = None,
) -> List[str]:
    """Returns a list of specific validation failures. Distinct from
    check_response_quality (quality_checker.py) — this focuses specifically
    on date/timeframe accuracy and confidence-language mismatches, the two
    failure modes with the highest real-world trust cost."""
    failures = []
    text = response_text.strip()
    if not text:
        return failures

    # 1. Year claims must be grounded in the real timeline, if one exists
    mentioned_years = [int(y) for y in YEAR_PATTERN.findall(text)]
    if mentioned_years and dasha_timeline:
        valid_years = set(_extract_years_from_timeline(dasha_timeline))
        for year in mentioned_years:
            if valid_years and year not in valid_years:
                # allow +/-1 year slack for period boundaries/rounding
                if not any(abs(year - vy) <= 1 for vy in valid_years):
                    failures.append(
                        f"The response states the year {year}, but this does not "
                        f"match any period in the actual Dasha timeline provided. "
                        f"Only cite years/periods that appear in the timeline data — "
                        f"if unsure of an exact year, describe the period by Dasha "
                        f"lord name instead of a specific year."
                    )
    elif mentioned_years and not dasha_timeline:
        failures.append(
            f"The response states a specific year ({mentioned_years[0]}) but no "
            f"real Dasha timeline data was available. Do not invent a specific "
            f"year without timeline evidence — speak in terms of Dasha periods "
            f"instead, or acknowledge timing is not precisely calculable here."
        )

    # 2. Absolute/deterministic language check against evidence confidence
    has_absolute = any(re.search(p, text, re.IGNORECASE) for p in ABSOLUTE_CLAIM_PATTERNS)
    if has_absolute:
        confidence = evidence_vote.get("confidence_pct", 50) if evidence_vote else 50
        verdict = evidence_vote.get("verdict") if evidence_vote else None
        if confidence < 70 or verdict == "mixed":
            failures.append(
                f"The response uses absolute/guaranteed language (e.g. 'will "
                f"definitely', 'guaranteed', '100%'), but the evidence confidence "
                f"is only {confidence}% ({verdict or 'uncertain'}). Remove absolute "
                f"claims — astrology should never be stated as a certainty, "
                f"especially when evidence is mixed or moderate."
            )

    return failures


def build_claim_correction_instructions(failures: List[str]) -> str:
    if not failures:
        return ""
    lines = ["IMPORTANT — the following claims in your previous answer are unsupported, correct them:"]
    for i, f in enumerate(failures, 1):
        lines.append(f"{i}. {f}")
    return "\n".join(lines)