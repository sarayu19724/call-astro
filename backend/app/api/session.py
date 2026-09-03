import json
import threading
from datetime import date, datetime
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from app.models.schemas import SessionInfoResponse
from app.memory.database import db
from app.services.geocoding_service import geocoding_service
from app.services.dashboard_service import get_lucky_color, generate_daily_prediction, generate_weekly_guidance
from app.utils.logger import logger

router = APIRouter(prefix="/session", tags=["Session"])

# How long a "pending" status is trusted before we allow a new fetch to
# start anyway (guards against a crashed background thread leaving the
# session stuck in "pending" forever).
PENDING_STALE_AFTER_SECONDS = 240


@router.get("/{session_id}", response_model=SessionInfoResponse)
async def get_session_info(session_id: str):
    try:
        session = db.get_or_create_session(session_id)
        return SessionInfoResponse(
            session_id=session["session_id"], dob=session.get("dob"),
            birth_time=session.get("birth_time"), birth_place=session.get("birth_place"),
            gender=session.get("gender"), name=session.get("name"),
            latitude=session.get("latitude"), longitude=session.get("longitude"),
            language=session.get("language", "Hinglish"), updated_at=session.get("updated_at")
        )
    except Exception as e:
        logger.error(f"Error fetching session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}/kundli-chart")
async def get_kundli_chart(session_id: str):
    try:
        session = db.get_or_create_session(session_id)
        raw = session.get("kundli_raw")
        if not raw:
            return {"available": False, "planets": [], "ascendant_sign": None}
        parsed = json.loads(raw)
        return {"available": True, "planets": parsed.get("planets", []), "ascendant_sign": parsed.get("ascendant_sign")}
    except Exception as e:
        logger.error(f"Error fetching kundli chart: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}/kundli-status")
async def get_kundli_status(session_id: str):
    """Polled by the frontend instead of hammering /kundli-chart repeatedly.
    Distinguishes 'still working' from 'actually failed' with a real reason,
    instead of the frontend guessing after a fixed timeout."""
    try:
        session = db.get_or_create_session(session_id)
        status = session.get("kundli_fetch_status") or "idle"
        started_at = session.get("kundli_fetch_started_at")

        # Self-heal: if a previous background thread died without updating
        # status (server restart, unhandled crash), don't leave the user
        # stuck on "pending" forever.
        if status == "pending" and started_at:
            try:
                started = datetime.fromisoformat(started_at)
                elapsed = (datetime.utcnow() - started).total_seconds()
                if elapsed > PENDING_STALE_AFTER_SECONDS:
                    db.update_session(session_id, {
                        "kundli_fetch_status": "failed",
                        "kundli_fetch_error": "Chart calculation took too long and was abandoned. Please retry.",
                    })
                    status = "failed"
            except ValueError:
                pass

        return {
            "status": status,
            "error": session.get("kundli_fetch_error"),
            "has_chart": bool(session.get("kundli_raw")),
        }
    except Exception as e:
        logger.error(f"Error fetching kundli status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}/reasoning-trace")
async def get_reasoning_trace(session_id: str):
    try:
        session = db.get_or_create_session(session_id)
        raw = session.get("last_reasoning_trace")
        if not raw:
            return {"available": False, "steps": []}
        steps = json.loads(raw)
        if not steps:
            return {"available": False, "steps": []}
        return {"available": True, "steps": steps}
    except Exception as e:
        logger.error(f"Error fetching reasoning trace: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}/dashboard")
async def get_dashboard(session_id: str):
    try:
        session = db.get_or_create_session(session_id)
        today_str = date.today().isoformat()

        if session.get("dashboard_date") == today_str and session.get("dashboard_prediction"):
            return {
                "available": True,
                "prediction": session.get("dashboard_prediction"),
                "lucky_color": session.get("dashboard_lucky_color"),
            }

        kundli_summary = session.get("kundli_data")
        kundli_raw = session.get("kundli_raw")
        if not kundli_summary:
            return {"available": False, "prediction": None, "lucky_color": None}

        moon_sign = None
        if kundli_raw:
            parsed = json.loads(kundli_raw)
            for p in parsed.get("planets", []):
                if p.get("name") == "Moon":
                    moon_sign = p.get("sign_name")
                    break

        lucky_color = get_lucky_color(moon_sign)
        prediction = generate_daily_prediction(kundli_summary, session.get("language", "Hinglish"))

        if prediction is None:
            logger.warning(f"Dashboard prediction generation failed for session {session_id} — not caching")
            return {
                "available": True,
                "prediction": "Aaj ka din shant man se guzariye. 🌟",
                "lucky_color": lucky_color,
            }

        db.update_session(session_id, {
            "dashboard_prediction": prediction,
            "dashboard_lucky_color": lucky_color,
            "dashboard_date": today_str,
        })
        return {"available": True, "prediction": prediction, "lucky_color": lucky_color}
    except Exception as e:
        logger.error(f"Error generating dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}/weekly-guidance")
async def get_weekly_guidance(session_id: str):
    try:
        session = db.get_or_create_session(session_id)
        today = date.today()
        week_id = today.strftime("%Y-W%W")

        if session.get("weekly_week_start") == week_id and session.get("weekly_guidance"):
            return {"available": True, "guidance": session.get("weekly_guidance")}

        kundli_summary = session.get("kundli_data")
        if not kundli_summary:
            return {"available": False, "guidance": None}

        dasha_summary = ""
        cached_dasha = session.get("kundli_dasha")
        if cached_dasha:
            dasha_data = json.loads(cached_dasha)
            maha = dasha_data.get("current_mahadasha", {})
            antar = dasha_data.get("current_antardasha", {})
            if maha:
                dasha_summary = f"Mahadasha: {maha.get('lord')}"
                if antar:
                    dasha_summary += f", Antardasha: {antar.get('lord')}"

        guidance = generate_weekly_guidance(kundli_summary, dasha_summary, session.get("language", "Hinglish"), session.get("name", "Client"))

        if guidance is None:
            logger.warning(f"Weekly guidance generation failed for session {session_id} — not caching")
            return {"available": True, "guidance": "Yeh hafta dhairya aur focus ke saath guzariye. 🌟"}

        db.update_session(session_id, {"weekly_guidance": guidance, "weekly_week_start": week_id})
        return {"available": True, "guidance": guidance}
    except Exception as e:
        logger.error(f"Error generating weekly guidance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{session_id}/recalculate-kundli")
async def recalculate_kundli(session_id: str):
    """Fire-and-forget was the bug: this used to block the HTTP request for
    up to several minutes (Kundli lambda retries + Dasha lambda retries),
    while the frontend gave up polling after ~49s and had no way to tell
    'still working' from 'actually broken'. Now this kicks off a background
    thread immediately, returns right away, and the frontend polls
    /kundli-status for the real outcome. A lock via kundli_fetch_status
    prevents overlapping fetches when the user mashes Retry."""
    from app.services.chat_service import chat_service

    try:
        session = db.get_or_create_session(session_id)
        status = session.get("kundli_fetch_status")
        started_at = session.get("kundli_fetch_started_at")

        if status == "pending" and started_at:
            try:
                started = datetime.fromisoformat(started_at)
                elapsed = (datetime.utcnow() - started).total_seconds()
                if elapsed < PENDING_STALE_AFTER_SECONDS:
                    return {"status": "pending", "message": "Chart calculation already in progress."}
            except ValueError:
                pass

        db.update_session(session_id, {
            "kundli_fetch_status": "pending",
            "kundli_fetch_error": None,
            "kundli_fetch_started_at": datetime.utcnow().isoformat(),
        })

        def _run_fetch():
            try:
                fresh_session = db.get_or_create_session(session_id)
                kundli_str = chat_service._fetch_and_cache_kundli(session_id, fresh_session)
                if kundli_str and kundli_str != "No chart data available.":
                    db.update_session(session_id, {"kundli_fetch_status": "ready", "kundli_fetch_error": None})
                    logger.info(f"[KundliFetch] background fetch succeeded for {session_id}")
                else:
                    db.update_session(session_id, {
                        "kundli_fetch_status": "failed",
                        "kundli_fetch_error": "Could not calculate the chart — please check your birth place, "
                                               "date and time are correct and try again.",
                    })
                    logger.warning(f"[KundliFetch] background fetch returned no data for {session_id}")
            except Exception as e:
                logger.error(f"[KundliFetch] background fetch crashed for {session_id}: {e}")
                db.update_session(session_id, {
                    "kundli_fetch_status": "failed",
                    "kundli_fetch_error": f"Chart calculation failed: {str(e)[:200]}",
                })

        threading.Thread(target=_run_fetch, daemon=True).start()
        return {"status": "pending", "message": "Chart calculation started."}
    except Exception as e:
        logger.error(f"Error triggering kundli recalculation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}/kundli-report")
async def download_kundli_report(session_id: str, language: str = None):
    """Generates the 3-page professional PDF Kundli report on demand."""
    from app.services.kundli_report_service import generate_kundli_report_pdf

    try:
        session = db.get_or_create_session(session_id)
        if not session.get("kundli_raw"):
            raise HTTPException(status_code=400, detail="Chart not ready yet — please wait for the chart to finish calculating.")

        report_language = language or session.get("language", "Hinglish")
        pdf_bytes = generate_kundli_report_pdf(session_id, report_language)

        safe_name = (session.get("name") or "Kundli").strip().replace(" ", "_")
        filename = f"{safe_name}_Kundli_{report_language}.pdf"

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating kundli report: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{session_id}", response_model=SessionInfoResponse)
async def update_session_info(session_id: str, profile_update: dict):
    try:
        birth_fields_changed = any(k in profile_update for k in ("dob", "birth_time", "birth_place"))

        if profile_update.get("birth_place"):
            coords = geocoding_service.geocode(profile_update["birth_place"])
            if coords:
                profile_update["latitude"], profile_update["longitude"] = coords
            else:
                logger.warning(f"Could not geocode birth_place: {profile_update['birth_place']}")

        language_changed = "language" in profile_update

        if birth_fields_changed:
            profile_update["kundli_data"] = None
            profile_update["kundli_raw"] = None
            profile_update["kundli_dasha"] = None
            profile_update["kundli_full_raw"] = None
            profile_update["dashboard_prediction"] = None
            profile_update["dashboard_date"] = None
            profile_update["weekly_guidance"] = None
            profile_update["weekly_week_start"] = None
            profile_update["topic_memory"] = None
            profile_update["last_reasoning_trace"] = None
            profile_update["kundli_fetch_status"] = "idle"
            profile_update["kundli_fetch_error"] = None
            logger.info(f"Birth details changed for {session_id} — cleared all cached derived data")
        elif language_changed:
            profile_update["dashboard_prediction"] = None
            profile_update["dashboard_date"] = None
            profile_update["weekly_guidance"] = None
            profile_update["weekly_week_start"] = None
            profile_update["last_reasoning_trace"] = None
            logger.info(f"Language changed for {session_id} — cleared dashboard and guidance cache")

        updated = db.update_session(session_id, profile_update)

        if birth_fields_changed:
            db.add_message(session_id, "system", "📝 Birth details updated — your chart has been recalculated.")

        return SessionInfoResponse(
            session_id=updated["session_id"], dob=updated.get("dob"),
            birth_time=updated.get("birth_time"), birth_place=updated.get("birth_place"),
            gender=updated.get("gender"), name=updated.get("name"),
            latitude=updated.get("latitude"), longitude=updated.get("longitude"),
            language=updated.get("language", "Hinglish"), updated_at=updated.get("updated_at")
        )
    except Exception as e:
        logger.error(f"Error updating session info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{session_id}")
async def clear_session(session_id: str):
    try:
        with db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            cursor.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            conn.commit()
        return {"status": "success", "message": f"Session {session_id} has been cleared."}
    except Exception as e:
        logger.error(f"Error clearing session: {e}")
        raise HTTPException(status_code=500, detail=str(e))