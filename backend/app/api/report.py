import os
import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from app.memory.database import db
from app.services.kundli_report_service import (
    start_report_generation_async, REPORT_STEPS, _initial_report_progress
)
from app.utils.logger import logger

router = APIRouter(prefix="/session", tags=["KundliReport"])


@router.post("/{session_id}/kundli-report/generate")
async def start_kundli_report(session_id: str, language: str = "Hinglish"):
    session = db.get_or_create_session(session_id)

    if not session.get("kundli_raw"):
        raise HTTPException(
            status_code=400,
            detail="Your chart isn't ready yet. Please wait for Kundli calculation to finish first."
        )

    if session.get("report_status") == "generating":
        # Already running — don't spawn a second thread, just let the
        # frontend keep polling the existing job.
        return {"status": "generating"}

    db.update_session(session_id, {
        "report_status": "pending",
        "report_error": None,
        "report_progress": json.dumps(_initial_report_progress()),
        "report_file_path": None,
    })

    start_report_generation_async(session_id, language)
    logger.info(f"[KundliReport] generation triggered for session {session_id} ({language})")
    return {"status": "pending"}


@router.get("/{session_id}/kundli-report/status")
async def get_kundli_report_status(session_id: str):
    session = db.get_or_create_session(session_id)
    status = session.get("report_status") or "idle"

    progress_raw = session.get("report_progress")
    try:
        progress = json.loads(progress_raw) if progress_raw else []
    except Exception:
        progress = []

    return {
        "status": status,
        "progress": progress,
        "error": session.get("report_error"),
        "ready": status == "ready" and bool(session.get("report_file_path")) and os.path.exists(session.get("report_file_path") or ""),
    }


@router.get("/{session_id}/kundli-report/download")
async def download_kundli_report(session_id: str, language: str = "Hinglish"):
    session = db.get_or_create_session(session_id)

    if session.get("report_status") != "ready":
        raise HTTPException(status_code=409, detail="Report is not ready yet.")

    path = session.get("report_file_path")
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Report file not found. Please regenerate.")

    name = (session.get("name") or "Kundli").replace(" ", "_")
    filename = f"{name}_Kundli_{language}.pdf"
    return FileResponse(path, media_type="application/pdf", filename=filename)