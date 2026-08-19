"""
Claim Validator 2.0 — verifies specific factual claims in the generated
response against the REAL chart/Dasha data actually fed to the LLM, not
just plausible-sounding text. Two independent checks:

1. Year/timeframe claims — must match the real Dasha timeline (existing).
2. Chart-fact claims — planet-in-sign and planet-in-house statements must
   match the actual computed chart. This catches the more dangerous
   hallucination: the LLM confidently stating a WRONG planet placement,
   not just a wrong date.
"""
import re
from typing import List, Optional, Dict

ABSOLUTE_CLAIM_PATTERNS = [
    r"\bwill definitely\b", r"\byou will surely\b", r"\bguaranteed\b",
    r"\b100%\b", r"\bcertainly will\b",
    r"\bpakka\b.*\bhoga\b", r"\bzaroor\b.*\bhoga\b",
]

YEAR_PATTERN = re.compile(r"\b(20\d{2})\b")

PLANET_NAMES = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"]
ZODIAC_SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"
]

# Matches phrases like "Mercury is in Virgo", "Mercury in Virgo", "Saturn placed in Libra"
PLANET_SIGN_PATTERN = re.compile(
    r"\b(" + "|".join(PLANET_NAMES) + r")\b[^.]{0,25}?\b(" + "|".join(ZODIAC_SIGNS) + r")\b",
    re.IGNORECASE
)

# Matches phrases like "Mercury in the 1st house", "10th house lord Mercury"
PLANET_HOUSE_PATTERN = re.compile(
    r"\b(" + "|".join(PLANET_NAMES) + r")\b[^.]{0,20}?\b(1[0-2]|[1-9])(?:st|nd|rd|th)\s+house\b",
    re.IGNORECASE
)


def _extract_years_from_timeline(dasha_timeline: str) -> List[int]:
    if not dasha_timeline:
        return []
    return [int(y) for y in YEAR_PATTERN.findall(dasha_timeline)]


def _get_house_for_sign(sign_name: str, ascendant_sign: str) -> Optional[int]:
    try:
        asc_idx = ZODIAC_SIGNS.index(ascendant_sign)
        sign_idx = ZODIAC_SIGNS.index(sign_name)
        return ((sign_idx - asc_idx) % 12) + 1
    except ValueError:
        return None


def _verify_planet_sign_claims(text: str, planets: List[dict]) -> List[str]:
    """Checks every 'Planet in Sign' claim in the response against the
    real chart. Returns a failure message for each mismatch."""
    failures = []
    if not planets:
        return failures

    actual_signs = {p.get("name"): p.get("sign_name") for p in planets if p.get("name")}

    for match in PLANET_SIGN_PATTERN.finditer(text):
        claimed_planet = match.group(1).strip().capitalize()
        claimed_sign = match.group(2).strip().capitalize()

        actual_sign = actual_signs.get(claimed_planet)
        if actual_sign and actual_sign.lower() != claimed_sign.lower():
            failures.append(
                f"The response states '{claimed_planet} is in {claimed_sign}', but the actual "
                f"chart data shows {claimed_planet} is in {actual_sign}. Correct this specific "
                f"placement — do not guess planet positions, use only the chart data provided."
            )

    return failures


def _verify_planet_house_claims(text: str, planets: List[dict], ascendant_sign: Optional[str]) -> List[str]:
    """Checks every 'Planet in Nth house' claim against the real chart."""
    failures = []
    if not planets or not ascendant_sign:
        return failures

    for match in PLANET_HOUSE_PATTERN.finditer(text):
        claimed_planet = match.group(1).strip().capitalize()
        claimed_house = int(match.group(2))

        planet_match = next((p for p in planets if p.get("name") == claimed_planet), None)
        if not planet_match:
            continue

        actual_house = _get_house_for_sign(planet_match.get("sign_name", ""), ascendant_sign)
        if actual_house and actual_house != claimed_house:
            failures.append(
                f"The response states '{claimed_planet} is in the {claimed_house}th house', but "
                f"based on the actual chart, {claimed_planet} is in the {actual_house}th house. "
                f"Correct this — do not state a house placement that doesn't match the chart data provided."
            )

    return failures


def validate_claims(
    response_text: str,
    dasha_timeline: str = "",
    evidence_vote: Optional[Dict] = None,
    planets: Optional[List[dict]] = None,
    ascendant_sign: Optional[str] = None,
) -> List[str]:
    """Returns a list of specific validation failures across THREE checks:
    1. Year/timeframe claims vs. real Dasha timeline
    2. Absolute/deterministic language vs. evidence confidence
    3. Planet-sign / planet-house claims vs. the real computed chart (NEW)
    """
    failures = []
    text = response_text.strip()
    if not text:
        return failures

    # --- Check 1: Year claims ---
    mentioned_years = [int(y) for y in YEAR_PATTERN.findall(text)]
    if mentioned_years and dasha_timeline:
        valid_years = set(_extract_years_from_timeline(dasha_timeline))
        for year in mentioned_years:
            if valid_years and year not in valid_years:
                if not any(abs(year - vy) <= 1 for vy in valid_years):
                    failures.append(
                        f"The response states the year {year}, but this does not match any "
                        f"period in the actual Dasha timeline provided. Only cite years/periods "
                        f"that appear in the timeline data — if unsure of an exact year, describe "
                        f"the period by Dasha lord name instead of a specific year."
                    )
    elif mentioned_years and not dasha_timeline:
        failures.append(
            f"The response states a specific year ({mentioned_years[0]}) but no real Dasha "
            f"timeline data was available. Do not invent a specific year without timeline "
            f"evidence — speak in terms of Dasha periods instead."
        )

    # --- Check 2: Absolute language vs confidence ---
    has_absolute = any(re.search(p, text, re.IGNORECASE) for p in ABSOLUTE_CLAIM_PATTERNS)
    if has_absolute:
        confidence = evidence_vote.get("confidence_pct", 50) if evidence_vote else 50
        verdict = evidence_vote.get("verdict") if evidence_vote else None
        if confidence < 70 or verdict == "mixed":
            failures.append(
                f"The response uses absolute/guaranteed language (e.g. 'will definitely', "
                f"'guaranteed', '100%'), but the evidence confidence is only {confidence}% "
                f"({verdict or 'uncertain'}). Remove absolute claims — astrology should never "
                f"be stated as a certainty, especially when evidence is mixed or moderate."
            )

    # --- Check 3 (NEW): Chart-fact verification ---
    if planets:
        failures.extend(_verify_planet_sign_claims(text, planets))
        if ascendant_sign:
            failures.extend(_verify_planet_house_claims(text, planets, ascendant_sign))

    return failures


def build_claim_correction_instructions(failures: List[str]) -> str:
    if not failures:
        return ""
    lines = ["IMPORTANT — the following claims in your previous answer are unsupported or incorrect, fix them:"]
    for i, f in enumerate(failures, 1):
        lines.append(f"{i}. {f}")
    return "\n".join(lines)

def build_streamed_correction_note(failures: List[str], language: str = "Hinglish") -> str:
    """For STREAMED responses where regeneration isn't possible — appends a
    brief, honest correction note after the fact rather than leaving a
    detected factual error uncorrected in the user's view. Only used when
    validate_claims() finds a real chart-fact mismatch."""
    if not failures:
        return ""

    labels = {
        "English": "\n\n📝 Correction: ",
        "Hindi": "\n\n📝 सुधार: ",
        "Hinglish": "\n\n📝 Correction: ",
    }
    prefix = labels.get(language, labels["Hinglish"])

    # Only surface the corrected FACT, not the full internal validator
    # message (which is written as an LLM instruction, not user-facing text)
    correction_lines = []
    for f in failures:
        # Extract just the "actual chart shows X" portion when present
        if "the actual chart" in f.lower() or "actual chart data shows" in f.lower():
            correction_lines.append(f.split(".")[0] + ".")

    if not correction_lines:
        return ""

    return prefix + " ".join(correction_lines)