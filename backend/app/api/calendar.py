from fastapi import APIRouter, HTTPException, Query

from app.services.calendar_service import (
    get_month_events,
    get_day_detail,
    get_month_summary,
    explain_day,
)

from app.utils.logger import logger


router = APIRouter(
    prefix="/session",
    tags=["AstrologyCalendar"],
)


# =========================================================
# DAY DETAIL
# IMPORTANT:
# Keep this route BEFORE /{year}/{month}
# =========================================================
@router.get("/{session_id}/calendar/day/{date_str}")
async def calendar_day(
    session_id: str,
    date_str: str,
    explain: bool = Query(False),
):
    try:
        if explain:
            return explain_day(session_id, date_str)

        return get_day_detail(session_id, date_str)

    except Exception as e:
        logger.error(
            f"Error building calendar day detail "
            f"for {session_id}, {date_str}: {e}"
        )
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


# =========================================================
# MONTH SUMMARY
# =========================================================
@router.get("/{session_id}/calendar/{year}/{month}/summary")
async def calendar_month_summary(
    session_id: str,
    year: int,
    month: int,
):
    if month < 1 or month > 12:
        raise HTTPException(
            status_code=400,
            detail="month must be between 1 and 12",
        )

    try:
        return get_month_summary(
            session_id,
            year,
            month,
        )

    except Exception as e:
        logger.error(
            f"Error building calendar month summary "
            f"for {session_id}, {year}-{month}: {e}"
        )
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


# =========================================================
# MONTH
# =========================================================
@router.get("/{session_id}/calendar/{year}/{month}")
async def calendar_month(
    session_id: str,
    year: int,
    month: int,
):
    if month < 1 or month > 12:
        raise HTTPException(
            status_code=400,
            detail="month must be between 1 and 12",
        )

    try:
        return get_month_events(
            session_id,
            year,
            month,
        )

    except Exception as e:
        logger.error(
            f"Error building calendar month view "
            f"for {session_id}, {year}-{month}: {e}"
        )
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )