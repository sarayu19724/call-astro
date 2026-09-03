import json
import uuid
import threading
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.memory.couple_database import couple_db
from app.services.couple_service import fetch_partner_chart_bundle
from app.services.childbirth_service import (
    build_partner_childbirth_static, attach_timing, build_joint_childbirth_analysis,
)
from app.services.dasha_api_service import dasha_api_service
from app.services.llm_service import llm_service
from app.utils.logger import logger

router = APIRouter(prefix="/couple", tags=["CoupleTest"])

CHILDBIRTH_STATIC_VERSION = 2  # bump if build_partner_childbirth_static's shape changes


class PartnerProfile(BaseModel):
    name: str
    dob: str
    birth_time: str
    birth_place: str


class CoupleChatRequest(BaseModel):
    message: str
    language: Optional[str] = "Hinglish"


class KnownOutcomeRequest(BaseModel):
    outcome: str


def _safe_load(raw: Optional[str]):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


@router.post("")
async def create_couple_session():
    couple_id = "couple_" + uuid.uuid4().hex[:12]
    couple_db.get_or_create(couple_id)
    return {"couple_id": couple_id}


def _run_partner_fetch(couple_id: str, which: int, profile: PartnerProfile):
    prefix = f"partner{which}"
    try:
        bundle = fetch_partner_chart_bundle(profile.name, profile.dob, profile.birth_time, profile.birth_place)
        couple_db.update(couple_id, {
            f"{prefix}_status": "ready",
            f"{prefix}_data": json.dumps(bundle, default=str, ensure_ascii=False),
            f"{prefix}_error": None,
        })
        logger.info(f"[Couple] {prefix} chart ready for {couple_id}")
    except Exception as e:
        logger.error(f"[Couple] {prefix} fetch failed for {couple_id}: {e}")
        couple_db.update(couple_id, {f"{prefix}_status": "failed", f"{prefix}_error": str(e)})


@router.post("/{couple_id}/partner/{which}")
async def set_partner(couple_id: str, which: int, profile: PartnerProfile):
    if which not in (1, 2):
        raise HTTPException(status_code=400, detail="which must be 1 or 2")
    prefix = f"partner{which}"

    couple_db.update(couple_id, {
        f"{prefix}_name": profile.name, f"{prefix}_dob": profile.dob,
        f"{prefix}_time": profile.birth_time, f"{prefix}_place": profile.birth_place,
        f"{prefix}_status": "pending", f"{prefix}_error": None, f"{prefix}_data": None,
        "childbirth_analysis": None,
    })

    thread = threading.Thread(target=_run_partner_fetch, args=(couple_id, which, profile), daemon=True)
    thread.start()
    return {"status": "pending"}


@router.post("/{couple_id}/known-outcome")
async def set_known_outcome(couple_id: str, payload: KnownOutcomeRequest):
    couple_db.update(couple_id, {"known_outcome": payload.outcome.strip() or None})
    return {"status": "success"}


@router.get("/{couple_id}/status")
async def get_couple_status(couple_id: str):
    session = couple_db.get_or_create(couple_id)

    def _partner_view(prefix: str):
        data = _safe_load(session.get(f"{prefix}_data"))
        chart = data.get("chart") if data else None
        dasha_tree = data.get("dasha_tree") if data else None
        # FIX 1 — always recomputed fresh from the cached raw tree, using
        # the real current time. Never served from a stored snapshot.
        fresh_current = dasha_api_service.find_current_period(dasha_tree) if dasha_tree else None
        return {
            "status": session.get(f"{prefix}_status") or "idle",
            "error": session.get(f"{prefix}_error"),
            "name": session.get(f"{prefix}_name"),
            "dob": session.get(f"{prefix}_dob"),
            "birth_time": session.get(f"{prefix}_time"),
            "birth_place": session.get(f"{prefix}_place"),
            "planets": chart.get("planets") if chart else None,
            "ascendant_sign": chart.get("ascendant_sign") if chart else None,
            "current_dasha": fresh_current,
        }

    return {
        "couple_id": couple_id,
        "partner1": _partner_view("partner1"),
        "partner2": _partner_view("partner2"),
        "both_ready": session.get("partner1_status") == "ready" and session.get("partner2_status") == "ready",
        "known_outcome": session.get("known_outcome"),
    }


@router.get("/{couple_id}/childbirth")
async def get_childbirth_analysis(couple_id: str):
    session = couple_db.get_or_create(couple_id)

    if session.get("partner1_status") != "ready" or session.get("partner2_status") != "ready":
        return {"available": False, "reason": "Both partners' charts must be ready first."}

    data1 = _safe_load(session.get("partner1_data"))
    data2 = _safe_load(session.get("partner2_data"))
    if not data1 or not data2:
        return {"available": False, "reason": "Chart data missing — please re-run the couple test."}

    # Only the STATIC part (chart facts, never time-sensitive) is cached.
    cached = _safe_load(session.get("childbirth_analysis"))
    if cached and cached.get("_static_version") == CHILDBIRTH_STATIC_VERSION:
        static1, static2 = cached["partner1_static"], cached["partner2_static"]
    else:
        static1 = build_partner_childbirth_static(data1["chart"]["planets"], data1["chart"]["ascendant_sign"])
        static2 = build_partner_childbirth_static(data2["chart"]["planets"], data2["chart"]["ascendant_sign"])
        couple_db.update(couple_id, {"childbirth_analysis": json.dumps({
            "_static_version": CHILDBIRTH_STATIC_VERSION,
            "partner1_static": static1, "partner2_static": static2,
        }, default=str, ensure_ascii=False)})

    # FIX 1 + FIX 2 — timing is ALWAYS recomputed fresh, every request,
    # using the real current time and the hard 7-year future boundary.
    now = datetime.now()
    report1 = attach_timing(static1, data1.get("dasha_tree"), now=now)
    report2 = attach_timing(static2, data2.get("dasha_tree"), now=now)

    name1 = session.get("partner1_name") or "Partner 1"
    name2 = session.get("partner2_name") or "Partner 2"
    joint = build_joint_childbirth_analysis(report1, report2, partner_a_name=name1, partner_b_name=name2)

    result = {
        "partner1_name": name1,
        "partner2_name": name2,
        "partner1_report": report1,
        "partner2_report": report2,
        "joint": joint,
        "window_start": report1.get("window_start"),
        "window_end": report1.get("window_end"),
        "computed_at": now.isoformat(),
    }
    return {"available": True, "known_outcome": session.get("known_outcome"), **result}


# ------------------------------------------------------------------
# FIX 3 — scope detection: an individual-partner question must NEVER
# pull in the other partner's facts or the joint analysis.
# ------------------------------------------------------------------
def _detect_chat_scope(message: str, name1: str, name2: str) -> str:
    text = f" {message.lower()} "
    n1 = (name1 or "").strip().lower()
    n2 = (name2 or "").strip().lower()
    mentions1 = bool(n1) and n1 in text
    mentions2 = bool(n2) and n2 in text
    if mentions1 and not mentions2:
        return "partner1"
    if mentions2 and not mentions1:
        return "partner2"
    return "joint"


COUPLE_CHAT_PROMPT = """You are an experienced, warm Indian Vedic Astrologer, answering a MARRIED COUPLE
together about their question, using BOTH of their birth charts and a pre-computed childbirth analysis.

Respond STRICTLY in {language} (Hindi: Devanagari; Hinglish: Latin-script conversational; English: warm English).
Length: 3-5 sentences, under 100 words. Plain prose, no bullet points, no headers.
Speak with grounded confidence directly from the facts given below — never mention books, RAG, retrieval,
or any technical process. Address both partners by name where natural.

{partner1_name}'s 5th-house / children facts:
{partner1_facts}

{partner2_name}'s 5th-house / children facts:
{partner2_facts}

Joint analysis (already computed — use this, don't recompute):
{joint_facts}

{known_outcome_block}

Conversation so far:
{history}

Couple's question:
"{question}"

Write the answer now:
"""

INDIVIDUAL_CHAT_PROMPT = """You are an experienced, warm Indian Vedic Astrologer. The question below is about
{partner_name}'s OWN chart specifically. Answer using ONLY {partner_name}'s facts below — do NOT mention the
other partner's chart, planets, houses, or Dasha, and do NOT reference any "joint" or "combined" analysis.
This answer is scoped to {partner_name} alone.

Respond STRICTLY in {language} (Hindi: Devanagari; Hinglish: Latin-script conversational; English: warm English).
Length: 3-5 sentences, under 90 words. Plain prose, no bullet points, no headers.
Speak with grounded confidence directly from the facts given below — never mention books, RAG, retrieval,
or any technical process.

{partner_name}'s 5th-house / children facts:
{partner_facts}

{partner_name}'s current Dasha (as of today):
{current_dasha}

{partner_name}'s upcoming favorable periods (window: {window_start} to {window_end}):
{future_periods}

{known_outcome_block}

Conversation so far:
{history}

Question:
"{question}"

Write the answer now — about {partner_name} only:
"""

KNOWN_OUTCOME_WITH_DATA = """OBSERVED REAL-WORLD OUTCOME FOR THIS CASE (treat this as established fact, not
something to infer from the chart): {outcome}
Use this as ground truth. Your job is to explain HOW the chart and Dasha support or contextualize this known
outcome — never contradict it, and never claim to independently "detect" whether a child has arrived when
this fact already tells you."""

KNOWN_OUTCOME_ABSENT = """No observed real-world outcome has been provided for this case. Do NOT claim to know
or infer whether a child has or hasn't already arrived — astrology alone cannot reliably establish that.
Speak only about favorable/challenging timing and periods, and avoid declarative statements about what has
already happened in real life."""


def _format_partner_facts(name: str, report: dict) -> str:
    facts = report["facts"]
    lines = [f"5th House sign: {facts.get('sign')}", f"5th House lord: {facts.get('lord')}"]
    lp = facts.get("lord_assessment")
    if lp:
        lordships = lp.get("lordships") or []
        lordship_str = f" (rules house{'s' if len(lordships) > 1 else ''} {', '.join(str(h) for h in lordships)})" if lordships else ""
        lines.append(f"5th lord {lp['planet']}{lordship_str}: {lp['reason']}")
    sig = facts.get("significator_assessment")
    if sig:
        lines.append(f"Jupiter (child significator): {sig['reason']}")
    if facts.get("occupants"):
        lines.append("Planets in 5th house: " + ", ".join(o["name"] for o in facts["occupants"]))
    if report.get("current_dasha"):
        lines.append(f"Current Dasha: {report['current_dasha']}")
    lines.append(f"Overall verdict: {report.get('verdict')}")
    return "\n".join(lines)


def _format_future_periods(report: dict) -> str:
    periods = report.get("favorable_periods") or []
    if not periods:
        return "No specific standout favorable period identified in the coming years — timing is broadly neutral for this."
    lines = []
    for p in periods[:3]:
        start = (p.get("start") or "").split(" ")[0]
        end = (p.get("end") or "").split(" ")[0]
        lines.append(f"- {p.get('mahadasha')}/{p.get('antardasha')}: {start} – {end}")
    return "\n".join(lines)


def _format_joint_facts(joint: dict) -> str:
    lines = [f"Joint verdict: {joint.get('joint_verdict')}"]
    if joint.get("common_factors"):
        lines.append("Common supporting factors: " + "; ".join(joint["common_factors"]))
    if joint.get("conflicting_factors"):
        lines.append("Conflicting factors: " + "; ".join(joint["conflicting_factors"]))
    if joint.get("window_evidence"):
        lines.append("\nFull evidence chain for the most likely joint window:\n" + joint["window_evidence"])
    else:
        lines.append("No clear overlapping favorable Dasha window was found in the computed timeframe.")
    return "\n".join(lines)


@router.post("/{couple_id}/chat")
async def couple_chat(couple_id: str, payload: CoupleChatRequest):
    session = couple_db.get_or_create(couple_id)
    if session.get("partner1_status") != "ready" or session.get("partner2_status") != "ready":
        raise HTTPException(status_code=400, detail="Both partners' charts must be ready before chatting.")

    childbirth = await get_childbirth_analysis(couple_id)
    if not childbirth.get("available"):
        raise HTTPException(status_code=400, detail=childbirth.get("reason", "Childbirth analysis unavailable."))

    known_outcome = session.get("known_outcome")
    known_outcome_block = KNOWN_OUTCOME_WITH_DATA.format(outcome=known_outcome) if known_outcome else KNOWN_OUTCOME_ABSENT

    history = _safe_load(session.get("chat_history")) or []
    history_text = "\n".join(f"{h['role']}: {h['content']}" for h in history[-6:])

    name1, name2 = childbirth["partner1_name"], childbirth["partner2_name"]
    scope = _detect_chat_scope(payload.message, name1, name2)
    logger.info(f"[CoupleChat] scope detected: {scope}")

    if scope in ("partner1", "partner2"):
        name = name1 if scope == "partner1" else name2
        report = childbirth["partner1_report"] if scope == "partner1" else childbirth["partner2_report"]
        prompt = INDIVIDUAL_CHAT_PROMPT.format(
            language=payload.language or "Hinglish",
            partner_name=name,
            partner_facts=_format_partner_facts(name, report),
            current_dasha=report.get("current_dasha") or "Not available",
            window_start=childbirth.get("window_start", ""),
            window_end=childbirth.get("window_end", ""),
            future_periods=_format_future_periods(report),
            known_outcome_block=known_outcome_block,
            history=history_text or "None",
            question=payload.message,
        )
    else:
        prompt = COUPLE_CHAT_PROMPT.format(
            language=payload.language or "Hinglish",
            partner1_name=name1, partner2_name=name2,
            partner1_facts=_format_partner_facts(name1, childbirth["partner1_report"]),
            partner2_facts=_format_partner_facts(name2, childbirth["partner2_report"]),
            joint_facts=_format_joint_facts(childbirth["joint"]),
            known_outcome_block=known_outcome_block,
            history=history_text or "None",
            question=payload.message,
        )

    try:
        response_text = llm_service.generate(prompt=prompt, temperature=0.6).strip()
    except Exception as e:
        logger.error(f"[CoupleChat] generation failed: {e}")
        response_text = "Kripya dobara koshish karein."

    history.append({"role": "Couple", "content": payload.message})
    history.append({"role": "Astrologer", "content": response_text})
    couple_db.update(couple_id, {"chat_history": json.dumps(history, ensure_ascii=False)})

    return {"message": response_text, "scope": scope}


@router.get("/{couple_id}/chat/history")
async def get_couple_chat_history(couple_id: str):
    session = couple_db.get_or_create(couple_id)
    history = _safe_load(session.get("chat_history")) or []
    return {"messages": history}


@router.delete("/{couple_id}")
async def delete_couple_session(couple_id: str):
    couple_db.delete(couple_id)
    return {"status": "success"}