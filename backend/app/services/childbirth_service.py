"""
Childbirth (Santan Yoga) analysis — 5th house, 5th lord, Jupiter (child
significator), Dasha timing, and joint-couple timing overlap.

ARCHITECTURE NOTE (fixes the "wrong current Dasha" + "past period shown as
future" bugs): this module now cleanly separates two kinds of data:

  STATIC facts  — 5th house sign/lord, Jupiter placement, dignity scores.
                  These never change once the chart is calculated, so they
                  ARE safe to cache indefinitely.

  TIMING facts  — "current Dasha right now", "favorable periods in the
                  next N years". These are recomputed FRESH, from the raw
                  cached dasha_tree, every single time they're requested —
                  using the real wall-clock "now" at request time. Nothing
                  Dasha-related is ever cached as a fixed snapshot, because
                  a snapshot is correct only at the instant it was taken.
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
from app.services.dasha_api_service import dasha_api_service

FIFTH_HOUSE = 5
CHILD_SIGNIFICATOR = "Jupiter"  # Putra Karaka in classical Vedic astrology
FUTURE_WINDOW_YEARS = 7  # hard boundary for "future eligible periods"

DIGNITY_SCORES = {"exalted": 2, "own_sign": 1, "neutral": 0, "debilitated": -2}
DIGNITY_LABELS = {
    "exalted": "Exalted", "own_sign": "Own sign",
    "neutral": "Neutral (no special dignity)", "debilitated": "Debilitated",
}


def _find_planet(planets: List[dict], name: str) -> Optional[dict]:
    return next((p for p in planets if p.get("name") == name), None)


def get_sign_dignity(planet_name: str, sign: str) -> str:
    if EXALTATION.get(planet_name) == sign:
        return "exalted"
    if sign in OWN_SIGNS.get(planet_name, []):
        return "own_sign"
    if DEBILITATION.get(planet_name) == sign:
        return "debilitated"
    return "neutral"


def get_lordships(planet_name: str, ascendant_sign: str) -> List[int]:
    houses = []
    for sign, lord in SIGN_LORDS.items():
        if lord == planet_name:
            h = get_house_for_sign(sign, ascendant_sign)
            if h:
                houses.append(h)
    return sorted(houses)


def assess_planet_strength(planet_name: str, sign: str, house: Optional[int], retro: bool) -> Dict[str, Any]:
    dignity = get_sign_dignity(planet_name, sign)
    dignity_score = DIGNITY_SCORES[dignity]

    house_category = None
    house_score = 0
    if house:
        if house in DUSTHANA_HOUSES:
            house_category, house_score = "dusthana", -1
        elif house in KENDRA_TRIKONA_HOUSES:
            house_category, house_score = "kendra_trikona", 1
        else:
            house_category, house_score = "neutral_house", 0

    retro_penalty = -1 if (retro and dignity in ("neutral", "debilitated")) else 0
    combined = dignity_score + house_score + retro_penalty

    reasons = [f"{DIGNITY_LABELS[dignity]} in {sign}"]
    if house_category == "kendra_trikona":
        reasons.append(f"placed in a Kendra/Trikona house ({house})")
    elif house_category == "dusthana":
        reasons.append(f"placed in a Dusthana house ({house})")
    if retro:
        reasons.append("retrograde, with no dignity to offset it" if retro_penalty
                        else "retrograde (does not weaken an exalted/own-sign placement)")

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
        "planet": planet_name, "sign": sign, "house": house, "retro": retro,
        "dignity": dignity, "dignity_label": DIGNITY_LABELS[dignity],
        "house_category": house_category, "combined_score": combined, "verdict": verdict,
        "reason": f"{verdict} — " + ", ".join(reasons) + ".",
    }


def build_fifth_house_facts(planets: List[dict], ascendant_sign: str) -> Dict[str, Any]:
    sign = get_sign_for_house(FIFTH_HOUSE, ascendant_sign)
    lord = get_house_lord(FIFTH_HOUSE, ascendant_sign)

    occupants = []
    for p in planets:
        house = get_house_for_sign(p.get("sign_name", ""), ascendant_sign)
        if house == FIFTH_HOUSE:
            occupants.append({"name": p.get("name"), "retro": str(p.get("isRetro", "")).lower() == "true"})

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
        "house_number": FIFTH_HOUSE, "sign": sign, "lord": lord, "occupants": occupants,
        "lord_assessment": lord_assessment, "significator_assessment": significator_assessment,
        "benefic_occupants": benefic_occupants, "malefic_occupants": malefic_occupants,
    }


def score_fifth_house_strength(facts: Dict[str, Any]) -> int:
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


def score_dasha_for_children(current_period: Optional[dict], fifth_lord: Optional[str]) -> int:
    """current_period is the dict shape returned by
    dasha_api_service.find_current_period (recomputed fresh, never cached)."""
    if not current_period:
        return 0
    maha = current_period.get("current_mahadasha", {}) or {}
    antar = current_period.get("current_antardasha", {}) or {}
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


def rank_favorable_child_periods(periods: List[dict], fifth_lord: Optional[str], top_n: int = 5) -> List[dict]:
    significators = {CHILD_SIGNIFICATOR}
    if fifth_lord:
        significators.add(fifth_lord)
    scored = []
    for period in periods:
        score = 0
        if period.get("mahadasha") in significators:
            score += 2
        if period.get("antardasha") in significators:
            score += 1
        if score > 0:
            scored.append({**period, "favorability_score": score})
    scored.sort(key=lambda p: p["favorability_score"], reverse=True)
    return scored[:top_n]


def _parse_period_date(d: Optional[str]) -> Optional[datetime]:
    if not d:
        return None
    try:
        return datetime.strptime(d, "%d/%m/%Y %H:%M:%S")
    except Exception:
        try:
            return datetime.strptime(d.split(" ")[0], "%d/%m/%Y")
        except Exception:
            return None


# ------------------------------------------------------------------
# FIX 1 + FIX 2 — fresh "current period" + hard-boundary future window.
# This is the ONLY place "now" is decided for Dasha purposes, called
# fresh on every request. It never trusts a snapshot computed earlier.
# ------------------------------------------------------------------
def compute_partner_timing(dasha_tree: Optional[List[dict]], fifth_lord: Optional[str],
                            now: Optional[datetime] = None, years_ahead: int = FUTURE_WINDOW_YEARS) -> Dict[str, Any]:
    now = now or datetime.now()

    if not dasha_tree:
        return {
            "current_dasha_str": None, "current_period": None, "dasha_score": 0,
            "favorable_future_periods": [], "window_start": now.strftime("%d %b %Y"),
            "window_end": now.replace(year=now.year + years_ahead).strftime("%d %b %Y"),
        }

    # Recomputed fresh using the REAL current time — this is FIX 1.
    current_period = dasha_api_service.find_current_period(dasha_tree)

    current_dasha_str = None
    if current_period:
        maha = current_period.get("current_mahadasha", {}) or {}
        antar = current_period.get("current_antardasha", {}) or {}
        if maha.get("lord"):
            current_dasha_str = f"{maha['lord']} Mahadasha"
            if antar.get("lord"):
                current_dasha_str += f" – {antar['lord']} Antardasha"

    dasha_score = score_dasha_for_children(current_period, fifth_lord)

    # FIX 2 — a period is a "future candidate" ONLY if it starts strictly
    # after "now". A period already in progress belongs in current_period
    # above, never in this list, so the two can never be conflated again.
    all_periods = dasha_api_service.flatten_periods(dasha_tree, level="antardasha")
    cutoff = now.replace(year=now.year + years_ahead)

    future_periods = []
    for period in all_periods:
        start = _parse_period_date(period.get("start"))
        end = _parse_period_date(period.get("end"))
        if not start or not end:
            continue
        if start > now and start <= cutoff:
            future_periods.append(period)

    favorable_future_periods = rank_favorable_child_periods(future_periods, fifth_lord)

    return {
        "current_dasha_str": current_dasha_str,
        "current_period": current_period,
        "dasha_score": dasha_score,
        "favorable_future_periods": favorable_future_periods,
        "window_start": now.strftime("%d %b %Y"),
        "window_end": cutoff.strftime("%d %b %Y"),
    }


def build_partner_childbirth_static(planets: List[dict], ascendant_sign: str) -> Dict[str, Any]:
    """The part that's safe to cache — never depends on 'now'."""
    facts = build_fifth_house_facts(planets, ascendant_sign)
    chart_score = score_fifth_house_strength(facts)
    return {"facts": facts, "chart_score": chart_score}


def attach_timing(static_report: Dict[str, Any], dasha_tree: Optional[List[dict]],
                   now: Optional[datetime] = None) -> Dict[str, Any]:
    """Combines a cached static report with FRESHLY computed timing.
    Call this on every request — never cache its output."""
    facts = static_report["facts"]
    chart_score = static_report["chart_score"]
    timing = compute_partner_timing(dasha_tree, facts.get("lord"), now=now)
    verdict = build_verdict(chart_score, timing["dasha_score"])

    return {
        "facts": facts,
        "chart_score": chart_score,
        "dasha_score": timing["dasha_score"],
        "verdict": verdict,
        "current_dasha": timing["current_dasha_str"],
        "current_period": timing["current_period"],
        "favorable_periods": timing["favorable_future_periods"],
        "window_start": timing["window_start"],
        "window_end": timing["window_end"],
    }


# Kept for any external caller wanting one-shot static+timing together.
def build_partner_childbirth_report(planets: List[dict], ascendant_sign: str,
                                     dasha_tree: Optional[List[dict]] = None,
                                     now: Optional[datetime] = None) -> Dict[str, Any]:
    static_report = build_partner_childbirth_static(planets, ascendant_sign)
    return attach_timing(static_report, dasha_tree, now=now)


def find_overlapping_windows(periods_a: List[dict], periods_b: List[dict]) -> List[Dict[str, Any]]:
    overlaps = []
    for pa in periods_a:
        a_start, a_end = _parse_period_date(pa.get("start")), _parse_period_date(pa.get("end"))
        if not a_start or not a_end:
            continue
        for pb in periods_b:
            b_start, b_end = _parse_period_date(pb.get("start")), _parse_period_date(pb.get("end"))
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


# ------------------------------------------------------------------
# FIX 4 — full evidence chain for the top overlapping window, instead
# of just asserting a date range.
# ------------------------------------------------------------------
def format_window_evidence(name_a: str, report_a: Dict[str, Any], name_b: str,
                            report_b: Dict[str, Any], window: Dict[str, Any]) -> str:
    def _facts_block(name, facts):
        lines = [
            f"{name.upper()}",
            f"  5th house sign: {facts.get('sign') or 'unknown'}",
            f"  5th house lord: {facts.get('lord') or 'unknown'}",
        ]
        lp = facts.get("lord_assessment")
        if lp:
            lines.append(f"  5th lord strength: {lp.get('reason')}")
        sig = facts.get("significator_assessment")
        if sig:
            lines.append(f"  Jupiter (child significator): {sig.get('reason')}")
        return "\n".join(lines)

    lines = [
        f"{name_a.upper()} — supporting Dasha: {window['partner_a_period']}",
        _facts_block(name_a, report_a["facts"]),
        "",
        f"{name_b.upper()} — supporting Dasha: {window['partner_b_period']}",
        _facts_block(name_b, report_b["facts"]),
        "",
        f"OVERLAP WINDOW: {window['start']} – {window['end']}",
    ]
    return "\n".join(lines)


def build_joint_childbirth_analysis(report_a: Dict[str, Any], report_b: Dict[str, Any],
                                     partner_a_name: str = "Partner A",
                                     partner_b_name: str = "Partner B") -> Dict[str, Any]:
    overlaps = find_overlapping_windows(
        report_a.get("favorable_periods", []), report_b.get("favorable_periods", []),
    )

    verdict_a, verdict_b = report_a["verdict"], report_b["verdict"]
    if verdict_a == "favorable" and verdict_b == "favorable":
        joint_verdict = "favorable"
    elif verdict_a == "challenging" and verdict_b == "challenging":
        joint_verdict = "challenging"
    else:
        joint_verdict = "mixed"

    common_factors, conflicting_factors = [], []
    sig_a = report_a["facts"].get("significator_assessment") or {}
    sig_b = report_b["facts"].get("significator_assessment") or {}
    STRONG = {"Strong", "Favorable"}
    WEAK = {"Weak", "Challenged"}

    if sig_a.get("verdict") in STRONG and sig_b.get("verdict") in STRONG:
        common_factors.append(
            f"Jupiter (child significator) is well placed for both — "
            f"{sig_a.get('reason', '')} for {partner_a_name}, {sig_b.get('reason', '')} for {partner_b_name}."
        )
    else:
        if sig_a.get("verdict") in WEAK:
            conflicting_factors.append(f"{partner_a_name}'s Jupiter: {sig_a.get('reason', 'placement not favorable')}")
        if sig_b.get("verdict") in WEAK:
            conflicting_factors.append(f"{partner_b_name}'s Jupiter: {sig_b.get('reason', 'placement not favorable')}")

    lp_a = report_a["facts"].get("lord_assessment") or {}
    lp_b = report_b["facts"].get("lord_assessment") or {}
    if lp_a.get("verdict") in STRONG and lp_b.get("verdict") in STRONG:
        common_factors.append(
            f"Both 5th house lords are favorably placed — "
            f"{lp_a.get('reason', '')} for {partner_a_name}, {lp_b.get('reason', '')} for {partner_b_name}."
        )
    elif (lp_a.get("verdict") in STRONG) != (lp_b.get("verdict") in STRONG):
        conflicting_factors.append(
            f"The two charts' 5th lords differ in strength — "
            f"{partner_a_name}: {lp_a.get('reason', 'not assessed')}; {partner_b_name}: {lp_b.get('reason', 'not assessed')}."
        )

    if not common_factors and not conflicting_factors:
        common_factors.append("No strongly differentiating factor found — both charts show a broadly comparable baseline.")

    window_evidence = None
    if overlaps:
        window_evidence = format_window_evidence(partner_a_name, report_a, partner_b_name, report_b, overlaps[0])

    return {
        "joint_verdict": joint_verdict,
        "overlapping_windows": overlaps,
        "common_factors": common_factors,
        "conflicting_factors": conflicting_factors,
        "window_evidence": window_evidence,
    }