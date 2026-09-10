from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from app.services.calendar_service import (
    get_month_events,
    get_day_detail,
    get_month_summary,
    explain_day,
)
from app.services.geocoding_service import geocoding_service
from app.utils.logger import logger

router = APIRouter(prefix="/session", tags=["AstrologyCalendar"])


def _coords(latitude: Optional[float], longitude: Optional[float]):

    if latitude is None or longitude is None:
        return None, None
    return latitude, longitude


@router.get("/{session_id}/calendar/geocode")
async def calendar_geocode_location(
    session_id: str,
    place: str = Query(..., min_length=2, description="Free-text place name to geocode"),
):
    try:
        cleaned = place.strip()
        coords = geocoding_service.geocode(cleaned)
        if not coords:
            raise HTTPException(status_code=404, detail=f"Could not find a location matching '{cleaned}'.")
        lat, lon = coords
        return {"latitude": lat, "longitude": lon, "query": cleaned}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error geocoding calendar location for {session_id}, place='{place}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}/calendar/day/{date_str}")
async def calendar_day(
    session_id: str,
    date_str: str,
    explain: bool = Query(False),
    latitude: Optional[float] = Query(None),
    longitude: Optional[float] = Query(None),
):
    try:
        lat, lon = _coords(latitude, longitude)
        if explain:
            return explain_day(session_id, date_str, lat, lon)
        return get_day_detail(session_id, date_str, lat, lon)
    except Exception as e:
        logger.error(f"Error building calendar day detail for {session_id}, {date_str}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}/calendar/{year}/{month}/summary")
async def calendar_month_summary(
    session_id: str,
    year: int,
    month: int,
    latitude: Optional[float] = Query(None),
    longitude: Optional[float] = Query(None),
):
    if month < 1 or month > 12:
        raise HTTPException(status_code=400, detail="month must be between 1 and 12")
    try:
        lat, lon = _coords(latitude, longitude)
        return get_month_summary(session_id, year, month, lat, lon)
    except Exception as e:
        logger.error(f"Error building calendar month summary for {session_id}, {year}-{month}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}/calendar/{year}/{month}")
async def calendar_month(
    session_id: str,
    year: int,
    month: int,
    latitude: Optional[float] = Query(None),
    longitude: Optional[float] = Query(None),
):
    if month < 1 or month > 12:
        raise HTTPException(status_code=400, detail="month must be between 1 and 12")
    try:
        lat, lon = _coords(latitude, longitude)
        return get_month_events(session_id, year, month, lat, lon)
    except Exception as e:
        logger.error(f"Error building calendar month view for {session_id}, {year}-{month}: {e}")
        raise HTTPException(status_code=500, detail=str(e))