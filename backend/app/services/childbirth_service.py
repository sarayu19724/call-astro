from datetime import datetime
from typing import Dict, Any, List, Optional
from app.services.kundli_service import get_house_lord
from app.services.topic_service import (
    get_house_for_sign, get_sign_for_house,
    KENDRA_TRIKONA_HOUSES, DUSTHANA_HOUSES,
    NATURAL_BENEFICS, NATURAL_MALEFICS,
)

FIFTH_HOUSE = 5
CHILD_SIGNIFICATOR = "Jupiter"  # Putra Karaka in classical Vedic astrology


def _find_planet(planets: List[dict], name: str) -> Optional[dict]:
    return next((p for p in planets if p.get("name") == name), None)


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

    lord_placement = None
    if lord:
        match = _find_planet(planets, lord)
        if match:
            l_sign = match.get("sign_name", "")
            l_house = get_house_for_sign(l_sign, ascendant_sign)
            lord_placement = {
                "planet": lord, "sign": l_sign, "house": l_house,
                "retro": str(match.get("isRetro", "")).lower() == "true",
                "in_kendra_trikona": l_house in KENDRA_TRIKONA_HOUSES if l_house else False,
                "in_dusthana": l_house in DUSTHANA_HOUSES if l_house else False,
            }

    significator = None
    sig_match = _find_planet(planets, CHILD_SIGNIFICATOR)
    if sig_match:
        s_sign = sig_match.get("sign_name", "")
        s_house = get_house_for_sign(s_sign, ascendant_sign)
        significator = {
            "planet": CHILD_SIGNIFICATOR, "sign": s_sign, "house": s_house,
            "retro": str(sig_match.get("isRetro", "")).lower() == "true",
            "in_kendra_trikona": s_house in KENDRA_TRIKONA_HOUSES if s_house else False,
            "in_dusthana": s_house in DUSTHANA_HOUSES if s_house else False,
        }

    benefic_occupants = [o["name"] for o in occupants if o["name"] in NATURAL_BENEFICS]
    malefic_occupants = [o["name"] for o in occupants if o["name"] in NATURAL_MALEFICS]

    return {
        "house_number": FIFTH_HOUSE,
        "sign": sign,
        "lord": lord,
        "occupants": occupants,
        "lord_placement": lord_placement,
        "significator": significator,
        "benefic_occupants": benefic_occupants,
        "malefic_occupants": malefic_occupants,
    }


def score_fifth_house_strength(facts: Dict[str, Any]) -> int:
    """+1/-1/0, mirroring topic_service's chart-signal scoring style."""
    score = 0
    checked = 0

    lp = facts.get("lord_placement")
    if lp and lp.get("house"):
        checked += 1
        if lp.get("in_dusthana") or lp.get("retro"):
            score -= 1
        elif lp.get("in_kendra_trikona"):
            score += 1

    sig = facts.get("significator")
    if sig and sig.get("house"):
        checked += 1
        if sig.get("in_dusthana") or sig.get("retro"):
            score -= 1
        elif sig.get("in_kendra_trikona"):
            score += 1

    if facts.get("benefic_occupants"):
        checked += 1
        score += 1
    if facts.get("malefic_occupants") and not facts.get("benefic_occupants"):
        checked += 1
        score -= 1

    if checked == 0:
        return 0
    return (score > 0) - (score < 0)


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

    sig_a = report_a["facts"].get("significator") or {}
    sig_b = report_b["facts"].get("significator") or {}
    if sig_a.get("in_kendra_trikona") and sig_b.get("in_kendra_trikona"):
        common_factors.append("Both charts show Jupiter (child significator) well placed.")
    elif sig_a.get("in_dusthana") or sig_b.get("in_dusthana"):
        conflicting_factors.append("Jupiter is weakly placed in at least one partner's chart.")

    lp_a = report_a["facts"].get("lord_placement") or {}
    lp_b = report_b["facts"].get("lord_placement") or {}
    if lp_a.get("in_kendra_trikona") and lp_b.get("in_kendra_trikona"):
        common_factors.append("Both 5th house lords are strongly placed.")
    if bool(lp_a.get("in_dusthana")) != bool(lp_b.get("in_dusthana")):
        conflicting_factors.append("The two charts' 5th lords differ in strength — one supportive, one weaker.")

    if not common_factors and not conflicting_factors:
        common_factors.append("No strongly differentiating factor found — both charts show a broadly comparable baseline.")

    return {
        "joint_verdict": joint_verdict,
        "overlapping_windows": overlaps,
        "common_factors": common_factors,
        "conflicting_factors": conflicting_factors,
    }