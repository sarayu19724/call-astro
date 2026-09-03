from fastapi import APIRouter, HTTPException
from app.services.house_insight_service import generate_house_insight
from app.utils.logger import logger

router = APIRouter(prefix="/session", tags=["HouseInsight"])


@router.get("/{session_id}/house-insight/{house_number}")
async def get_house_insight(session_id: str, house_number: int):
    try:
        return generate_house_insight(session_id, house_number)
    except Exception as e:
        logger.error(f"Error generating house insight: {e}")
        raise HTTPException(status_code=500, detail=str(e))