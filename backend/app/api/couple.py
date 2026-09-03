import json
import uuid
import threading
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.memory.couple_database import couple_db
from app.services.couple_service import fetch_partner_chart_bundle
from app.services.childbirth_service import build_partner_childbirth_report, build_joint_childbirth_analysis
from app.services.llm_service import llm_service
from app.utils.logger import logger

router = APIRouter(prefix="/couple", tags=["CoupleTest"])


class PartnerProfile(BaseModel):
    name: str
    dob: str
    birth_time: str
    birth_place: str


class CoupleChatRequest(BaseModel):
    message: str
    language: Optional[str] = "Hinglish"


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


@router.get("/{couple_id}/status")
async def get_couple_status(couple_id: str):
    session = couple_db.get_or_create(couple_id)

    def _partner_view(prefix: str):
        data = _safe_load(session.get(f"{prefix}_data"))
        chart = data.get("chart") if data else None
        return {
            "status": session.get(f"{prefix}_status") or "idle",
            "error": session.get(f"{prefix}_error"),
            "name": session.get(f"{prefix}_name"),
            "dob": session.get(f"{prefix}_dob"),
            "birth_time": session.get(f"{prefix}_time"),
            "birth_place": session.get(f"{prefix}_place"),
            "planets": chart.get("planets") if chart else None,
            "ascendant_sign": chart.get("ascendant_sign") if chart else None,
            "current_dasha": (data.get("dasha_info") if data else None),
        }

    return {
        "couple_id": couple_id,
        "partner1": _partner_view("partner1"),
        "partner2": _partner_view("partner2"),
        "both_ready": session.get("partner1_status") == "ready" and session.get("partner2_status") == "ready",
    }


@router.get("/{couple_id}/childbirth")
async def get_childbirth_analysis(couple_id: str):
    session = couple_db.get_or_create(couple_id)

    if session.get("partner1_status") != "ready" or session.get("partner2_status") != "ready":
        return {"available": False, "reason": "Both partners' charts must be ready first."}

    cached = _safe_load(session.get("childbirth_analysis"))
    if cached:
        return {"available": True, **cached}

    data1 = _safe_load(session.get("partner1_data"))
    data2 = _safe_load(session.get("partner2_data"))
    if not data1 or not data2:
        return {"available": False, "reason": "Chart data missing — please re-run the couple test."}

    report1 = build_partner_childbirth_report(
        data1["chart"]["planets"], data1["chart"]["ascendant_sign"],
        data1.get("dasha_info"), data1.get("upcoming_periods"),
    )
    report2 = build_partner_childbirth_report(
        data2["chart"]["planets"], data2["chart"]["ascendant_sign"],
        data2.get("dasha_info"), data2.get("upcoming_periods"),
    )
    joint = build_joint_childbirth_analysis(report1, report2)

    result = {
        "partner1_name": session.get("partner1_name"),
        "partner2_name": session.get("partner2_name"),
        "partner1_report": report1,
        "partner2_report": report2,
        "joint": joint,
        "computed_at": datetime.utcnow().isoformat(),
    }

    couple_db.update(couple_id, {"childbirth_analysis": json.dumps(result, default=str, ensure_ascii=False)})
    return {"available": True, **result}


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

Conversation so far:
{history}

Couple's question:
"{question}"

Write the answer now:
"""


def _format_partner_facts(name: str, report: dict) -> str:
    facts = report["facts"]
    lines = [
        f"5th House sign: {facts.get('sign')}",
        f"5th House lord: {facts.get('lord')}",
    ]
    lp = facts.get("lord_placement")
    if lp:
        lines.append(f"5th lord placed in {lp.get('sign')} (house {lp.get('house')}){' (retrograde)' if lp.get('retro') else ''}")
    sig = facts.get("significator")
    if sig:
        lines.append(f"Jupiter (child significator) in {sig.get('sign')} (house {sig.get('house')}){' (retrograde)' if sig.get('retro') else ''}")
    if facts.get("occupants"):
        lines.append("Planets in 5th house: " + ", ".join(o["name"] for o in facts["occupants"]))
    if report.get("current_dasha"):
        lines.append(f"Current Dasha: {report['current_dasha']}")
    lines.append(f"Overall verdict: {report.get('verdict')}")
    return "\n".join(lines)


def _format_joint_facts(joint: dict) -> str:
    lines = [f"Joint verdict: {joint.get('joint_verdict')}"]
    if joint.get("common_factors"):
        lines.append("Common supporting factors: " + "; ".join(joint["common_factors"]))
    if joint.get("conflicting_factors"):
        lines.append("Conflicting factors: " + "; ".join(joint["conflicting_factors"]))
    if joint.get("overlapping_windows"):
        w = joint["overlapping_windows"][0]
        lines.append(f"Most likely overlapping window: {w['start']} to {w['end']}")
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

    history = _safe_load(session.get("chat_history")) or []
    history_text = "\n".join(f"{h['role']}: {h['content']}" for h in history[-6:])

    prompt = COUPLE_CHAT_PROMPT.format(
        language=payload.language or "Hinglish",
        partner1_name=childbirth["partner1_name"] or "Partner 1",
        partner2_name=childbirth["partner2_name"] or "Partner 2",
        partner1_facts=_format_partner_facts(childbirth["partner1_name"], childbirth["partner1_report"]),
        partner2_facts=_format_partner_facts(childbirth["partner2_name"], childbirth["partner2_report"]),
        joint_facts=_format_joint_facts(childbirth["joint"]),
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

    return {"message": response_text}


@router.get("/{couple_id}/chat/history")
async def get_couple_chat_history(couple_id: str):
    session = couple_db.get_or_create(couple_id)
    history = _safe_load(session.get("chat_history")) or []
    return {"messages": history}


@router.delete("/{couple_id}")
async def delete_couple_session(couple_id: str):
    couple_db.delete(couple_id)
    return {"status": "success"}