"""
Childbirth (Santan Yoga) analysis — 5th house, 5th lord, Jupiter (child
significator), Dasha timing, and joint-couple timing overlap.

Every verdict here now carries an explicit reasoning chain (sign dignity,
lordship, house placement, retrograde status) rather than a blanket
strong/weak label — this is what makes the output auditable back to the
raw Kundli data instead of reading like an opaque AI guess.
"""
from datetime import datetime
from typing import Dict, Any, List, Optional
from app.services.kundli_service import get_house_lord, SIGN_LORDS
from app.services.topic_service import (
    get_house_for_sign, get_sign_for_house,
    KENDRA_TRIKONA_HOUSES, DUSTHANA_HOUSES,
    NATURAL_BENEFICS, NATURAL_MALEFICS,
)
from app.services.yoga_service import EXALTATION, DEBILITATION, OWN_SIGNS

FIFTH_HOUSE = 5
CHILD_SIGNIFICATOR = "Jupiter"  # Putra Karaka in classical Vedic astrology

DIGNITY_SCORES = {
    "exalted": 2,
    "own_sign": 1,
    "neutral": 0,
    "debilitated": -2,
}

DIGNITY_LABELS = {
    "exalted": "Exalted",
    "own_sign": "Own sign",
    "neutral": "Neutral (no special dignity)",
    "debilitated": "Debilitated",
}


def _find_planet(planets: List[dict], name: str) -> Optional[dict]:
    return next((p for p in planets if p.get("name") == name), None)


# ------------------------------------------------------------------
# SIGN DIGNITY — exaltation / own-sign / debilitation, the piece the
# previous version skipped entirely. Reuses the same fixed classical
# tables already used by yoga_service.py, so a planet's dignity is
# assessed consistently everywhere in the app.
# ------------------------------------------------------------------
def get_sign_dignity(planet_name: str, sign: str) -> str:
    if EXALTATION.get(planet_name) == sign:
        return "exalted"
    if sign in OWN_SIGNS.get(planet_name, []):
        return "own_sign"
    if DEBILITATION.get(planet_name) == sign:
        return "debilitated"
    return "neutral"


def get_lordships(planet_name: str, ascendant_sign: str) -> List[int]:
    """Which house number(s) this planet rules from this ascendant —
    a planet can own 1 or 2 signs, so up to 2 house numbers."""
    houses = []
    for sign, lord in SIGN_LORDS.items():
        if lord == planet_name:
            h = get_house_for_sign(sign, ascendant_sign)
            if h:
                houses.append(h)
    return sorted(houses)


def assess_planet_strength(planet_name: str, sign: str, house: Optional[int], retro: bool) -> Dict[str, Any]:
    """Builds an explicit, auditable strength assessment for one planet
    placement — sign dignity + house category + retrograde status, each
    surfaced separately, with a combined score and a plain-language
    'assessment' string that names WHY, not just strong/weak."""
    dignity = get_sign_dignity(planet_name, sign)
    dignity_score = DIGNITY_SCORES[dignity]

    house_category = None
    house_score = 0
    if house:
        if house in DUSTHANA_HOUSES:
            house_category = "dusthana"
            house_score = -1
        elif house in KENDRA_TRIKONA_HOUSES:
            house_category = "kendra_trikona"
            house_score = 1
        else:
            house_category = "neutral_house"
            house_score = 0

    retro_penalty = 0
    # Retrograde is not automatically bad in classical practice — an
    # exalted or own-sign planet retrograde is still considered strong
    # (some traditions treat retrograde exaltation as even stronger).
    # It only counts against a placement that has no dignity to fall
    # back on.
    if retro and dignity in ("neutral", "debilitated"):
        retro_penalty = -1

    combined = dignity_score + house_score + retro_penalty

    reasons = [f"{DIGNITY_LABELS[dignity]} in {sign}"]
    if house_category == "kendra_trikona":
        reasons.append(f"placed in a Kendra/Trikona house ({house})")
    elif house_category == "dusthana":
        reasons.append(f"placed in a Dusthana house ({house})")
    if retro:
        if retro_penalty:
            reasons.append("retrograde, with no dignity to offset it")
        else:
            reasons.append("retrograde (does not weaken an exalted/own-sign placement)")

    if combined >= 2:
        verdict = "Strong"
    elif combined >= 1:
        verdict = "Favorable"
    elif combined <= -2:
        verdict = "Weak"
    elif combined <= -1:
        verdict = "Challenged"
    else:
        verdict = "Mixed / Moderate"

    return {
        "planet": planet_name,
        "sign": sign,
        "house": house,
        "retro": retro,
        "dignity": dignity,
        "dignity_label": DIGNITY_LABELS[dignity],
        "house_category": house_category,
        "combined_score": combined,
        "verdict": verdict,
        "reason": f"{verdict} — " + ", ".join(reasons) + "." if reasons else verdict,
    }


def build_fifth_house_facts(planets: List[dict], ascendant_sign: str) -> Dict[str, Any]:
    sign = get_sign_for_house(FIFTH_HOUSE, ascendant_sign)
    lord = get_house_lord(FIFTH_HOUSE, ascendant_sign)

    occupants = []
    for p in planets:
        p_sign = p.get("sign_name", "")
        house = get_house_for_sign(p_sign, ascendant_sign)
        if house == FIFTH_HOUSE:
            occupants.append({
                "name": p.get("name"),
                "retro": str(p.get("isRetro", "")).lower() == "true",
            })

    lord_assessment = None
    if lord:
        match = _find_planet(planets, lord)
        if match:
            l_sign = match.get("sign_name", "")
            l_house = get_house_for_sign(l_sign, ascendant_sign)
            l_retro = str(match.get("isRetro", "")).lower() == "true"
            lord_assessment = assess_planet_strength(lord, l_sign, l_house, l_retro)
            lord_assessment["lordships"] = get_lordships(lord, ascendant_sign)

    significator_assessment = None
    sig_match = _find_planet(planets, CHILD_SIGNIFICATOR)
    if sig_match:
        s_sign = sig_match.get("sign_name", "")
        s_house = get_house_for_sign(s_sign, ascendant_sign)
        s_retro = str(sig_match.get("isRetro", "")).lower() == "true"
        significator_assessment = assess_planet_strength(CHILD_SIGNIFICATOR, s_sign, s_house, s_retro)

    benefic_occupants = [o["name"] for o in occupants if o["name"] in NATURAL_BENEFICS]
    malefic_occupants = [o["name"] for o in occupants if o["name"] in NATURAL_MALEFICS]

    return {
        "house_number": FIFTH_HOUSE,
        "sign": sign,
        "lord": lord,
        "occupants": occupants,
        "lord_assessment": lord_assessment,
        "significator_assessment": significator_assessment,
        "benefic_occupants": benefic_occupants,
        "malefic_occupants": malefic_occupants,
    }


def score_fifth_house_strength(facts: Dict[str, Any]) -> int:
    """Rolls the two explicit assessments (5th lord, Jupiter) into a single
    -1/0/+1 chart-level signal, now driven by their real combined_score
    rather than a crude 'is it in a good house category' check."""
    scores = []

    lp = facts.get("lord_assessment")
    if lp:
        scores.append(lp["combined_score"])

    sig = facts.get("significator_assessment")
    if sig:
        scores.append(sig["combined_score"])

    if facts.get("benefic_occupants"):
        scores.append(1)
    if facts.get("malefic_occupants") and not facts.get("benefic_occupants"):
        scores.append(-1)

    if not scores:
        return 0
    total = sum(scores)
    return (total > 0) - (total < 0)


def score_dasha_for_children(dasha_info: Optional[dict], fifth_lord: Optional[str]) -> int:
    if not dasha_info:
        return 0
    maha = dasha_info.get("current_mahadasha", {}) or {}
    antar = dasha_info.get("current_antardasha", {}) or {}
    relevant = {CHILD_SIGNIFICATOR}
    if fifth_lord:
        relevant.add(fifth_lord)

    score = 0.0
    for period_lord in (maha.get("lord"), antar.get("lord")):
        if not period_lord:
            continue
        if period_lord in relevant:
            score += 1
        elif period_lord in NATURAL_MALEFICS:
            score -= 0.5
    return (score > 0) - (score < 0)


def build_verdict(chart_score: int, dasha_score: int) -> str:
    if chart_score > 0 and dasha_score > 0:
        return "favorable"
    if chart_score < 0 and dasha_score < 0:
        return "challenging"
    if chart_score == 0 and dasha_score == 0:
        return "neutral"
    return "mixed"


def rank_favorable_child_periods(upcoming_periods: List[dict], fifth_lord: Optional[str], top_n: int = 5) -> List[dict]:
    significators = {CHILD_SIGNIFICATOR}
    if fifth_lord:
        significators.add(fifth_lord)

    scored = []
    for period in upcoming_periods:
        score = 0
        if period.get("mahadasha") in significators:
            score += 2
        if period.get("antardasha") in significators:
            score += 1
        if score > 0:
            scored.append({**period, "favorability_score": score})

    scored.sort(key=lambda p: p["favorability_score"], reverse=True)
    return scored[:top_n]


def build_partner_childbirth_report(planets: List[dict], ascendant_sign: str,
                                      dasha_info: Optional[dict],
                                      upcoming_periods: Optional[List[dict]] = None) -> Dict[str, Any]:
    facts = build_fifth_house_facts(planets, ascendant_sign)
    chart_score = score_fifth_house_strength(facts)
    dasha_score = score_dasha_for_children(dasha_info, facts.get("lord"))
    verdict = build_verdict(chart_score, dasha_score)

    favorable_periods = []
    if upcoming_periods:
        favorable_periods = rank_favorable_child_periods(upcoming_periods, facts.get("lord"))

    current_dasha_str = None
    if dasha_info:
        maha = dasha_info.get("current_mahadasha", {}) or {}
        antar = dasha_info.get("current_antardasha", {}) or {}
        if maha.get("lord"):
            current_dasha_str = f"{maha['lord']} Mahadasha"
            if antar.get("lord"):
                current_dasha_str += f" – {antar['lord']} Antardasha"

    return {
        "facts": facts,
        "chart_score": chart_score,
        "dasha_score": dasha_score,
        "verdict": verdict,
        "current_dasha": current_dasha_str,
        "favorable_periods": favorable_periods,
    }


def find_overlapping_windows(periods_a: List[dict], periods_b: List[dict]) -> List[Dict[str, Any]]:
    """Finds calendar overlap between two partners' favorable-period lists."""

    def _parse(d):
        if not d:
            return None
        try:
            return datetime.strptime(d.split(" ")[0], "%d/%m/%Y")
        except Exception:
            return None

    overlaps = []
    for pa in periods_a:
        a_start, a_end = _parse(pa.get("start")), _parse(pa.get("end"))
        if not a_start or not a_end:
            continue
        for pb in periods_b:
            b_start, b_end = _parse(pb.get("start")), _parse(pb.get("end"))
            if not b_start or not b_end:
                continue
            latest_start = max(a_start, b_start)
            earliest_end = min(a_end, b_end)
            if latest_start <= earliest_end:
                overlaps.append({
                    "start": latest_start.strftime("%d/%m/%Y"),
                    "end": earliest_end.strftime("%d/%m/%Y"),
                    "partner_a_period": f"{pa.get('mahadasha')}/{pa.get('antardasha')}",
                    "partner_b_period": f"{pb.get('mahadasha')}/{pb.get('antardasha')}",
                })

    overlaps.sort(key=lambda w: datetime.strptime(w["start"], "%d/%m/%Y"))
    return overlaps


def build_joint_childbirth_analysis(report_a: Dict[str, Any], report_b: Dict[str, Any]) -> Dict[str, Any]:
    """Now builds common/conflicting factors from the real per-planet
    assessments (verdict + reason) instead of a binary in_kendra_trikona /
    in_dusthana check — so a claim like 'Jupiter is weak' can no longer be
    made for a chart where Jupiter is actually exalted or in its own sign."""
    overlaps = find_overlapping_windows(
        report_a.get("favorable_periods", []),
        report_b.get("favorable_periods", []),
    )

    verdict_a = report_a["verdict"]
    verdict_b = report_b["verdict"]

    if verdict_a == "favorable" and verdict_b == "favorable":
        joint_verdict = "favorable"
    elif verdict_a == "challenging" and verdict_b == "challenging":
        joint_verdict = "challenging"
    else:
        joint_verdict = "mixed"

    common_factors = []
    conflicting_factors = []

    sig_a = report_a["facts"].get("significator_assessment") or {}
    sig_b = report_b["facts"].get("significator_assessment") or {}

    STRONG_VERDICTS = {"Strong", "Favorable"}
    WEAK_VERDICTS = {"Weak", "Challenged"}

    if sig_a.get("verdict") in STRONG_VERDICTS and sig_b.get("verdict") in STRONG_VERDICTS:
        common_factors.append(
            f"Jupiter (child significator) is well placed for both — "
            f"{sig_a.get('reason', '')} for partner A, {sig_b.get('reason', '')} for partner B."
        )
    else:
        if sig_a.get("verdict") in WEAK_VERDICTS:
            conflicting_factors.append(f"Partner A's Jupiter: {sig_a.get('reason', 'placement not favorable')}")
        if sig_b.get("verdict") in WEAK_VERDICTS:
            conflicting_factors.append(f"Partner B's Jupiter: {sig_b.get('reason', 'placement not favorable')}")
        if sig_a.get("verdict") not in WEAK_VERDICTS and sig_b.get("verdict") not in WEAK_VERDICTS \
                and not (sig_a.get("verdict") in STRONG_VERDICTS and sig_b.get("verdict") in STRONG_VERDICTS):
            common_factors.append(
                f"Jupiter is moderate in both charts — "
                f"{sig_a.get('reason', 'no strong signal')} for partner A, "
                f"{sig_b.get('reason', 'no strong signal')} for partner B."
            )

    lp_a = report_a["facts"].get("lord_assessment") or {}
    lp_b = report_b["facts"].get("lord_assessment") or {}

    if lp_a.get("verdict") in STRONG_VERDICTS and lp_b.get("verdict") in STRONG_VERDICTS:
        common_factors.append(
            f"Both 5th house lords are favorably placed — "
            f"{lp_a.get('reason', '')} for partner A, {lp_b.get('reason', '')} for partner B."
        )
    elif (lp_a.get("verdict") in STRONG_VERDICTS) != (lp_b.get("verdict") in STRONG_VERDICTS):
        conflicting_factors.append(
            "The two charts' 5th lords differ in strength — "
            f"partner A: {lp_a.get('reason', 'not assessed')}; partner B: {lp_b.get('reason', 'not assessed')}."
        )

    if not common_factors and not conflicting_factors:
        common_factors.append("No strongly differentiating factor found — both charts show a broadly comparable baseline.")

    return {
        "joint_verdict": joint_verdict,
        "overlapping_windows": overlaps,
        "common_factors": common_factors,
        "conflicting_factors": conflicting_factors,
    }