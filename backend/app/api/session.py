import json
from datetime import date
from fastapi import APIRouter, HTTPException
from app.models.schemas import SessionInfoResponse
from app.memory.database import db
from app.services.geocoding_service import geocoding_service
from app.services.dashboard_service import get_lucky_color, generate_daily_prediction, generate_weekly_guidance
from app.services.transit_service import transit_service
from app.utils.logger import logger

router = APIRouter(prefix="/session", tags=["Session"])


@router.get("/profiles/all")
async def get_all_profiles():
    """Returns all profiles saved in database so frontend can restore and sync charts."""
    try:
        profiles = db.get_all_valid_profiles()
        return {"profiles": profiles}
    except Exception as e:
        logger.error(f"Error fetching all profiles: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/transits/live")
async def get_live_transits():
    """Returns real-time sky planetary positions and multi-profile transit overlays."""
    try:
        current_transits = transit_service.get_current_transits()
        profiles = db.get_all_valid_profiles()
        
        multi_overlays = []
        for p in profiles:
            sid = p.get("session_id")
            s = db.get_or_create_session(sid)
            overlay = transit_service.calculate_gochar_overlay(s, current_transits)
            if overlay.get("available"):
                multi_overlays.append(overlay)

        return {
            "date": current_transits.get("date"),
            "sky_planets": current_transits.get("planets", []),
            "overlays": multi_overlays
        }
    except Exception as e:
        logger.error(f"Error fetching live transits: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}/transits")
async def get_session_transits(session_id: str):
    """Returns real-time Gochar transit overlay for a specific session/chart."""
    try:
        session = db.get_or_create_session(session_id)
        current_transits = transit_service.get_current_transits()
        overlay = transit_service.calculate_gochar_overlay(session, current_transits)
        return overlay
    except Exception as e:
        logger.error(f"Error calculating session transits: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}", response_model=SessionInfoResponse)
async def get_session_info(session_id: str):
    try:
        session = db.get_or_create_session(session_id)
        return SessionInfoResponse(
            session_id=session["session_id"], dob=session.get("dob"),
            birth_time=session.get("birth_time"), birth_place=session.get("birth_place"),
            gender=session.get("gender"), name=session.get("name"), relation=session.get("relation", "Self"),
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
        if not raw and session.get("dob") and session.get("birth_place"):
            from app.services.chat_service import chat_service
            chat_service._fetch_and_cache_kundli(session_id, session)
            session = db.get_or_create_session(session_id)
            raw = session.get("kundli_raw")
        if not raw:
            return {"available": False, "planets": [], "ascendant_sign": None}
        parsed = json.loads(raw)
        return {"available": True, "planets": parsed.get("planets", []), "ascendant_sign": parsed.get("ascendant_sign")}
    except Exception as e:
        logger.error(f"Error fetching kundli chart: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}/reasoning-trace")
async def get_reasoning_trace(session_id: str):
    """Powers the 'How I Reached This' panel — returns the cached step-by-step
    reasoning trace from the most recent astrology response."""
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
    """Force a fresh Kundli fetch — used right after editing birth details."""
    from app.services.chat_service import chat_service
    try:
        session = db.get_or_create_session(session_id)
        kundli_str = chat_service._fetch_and_cache_kundli(session_id, session)
        return {"success": kundli_str != "No chart data available."}
    except Exception as e:
        logger.error(f"Error recalculating kundli: {e}")
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
            gender=updated.get("gender"), name=updated.get("name"), relation=updated.get("relation", "Self"),
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