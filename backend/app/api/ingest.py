from fastapi import APIRouter, HTTPException
from app.models.schemas import StatusResponse
from app.rag.vector_store import vector_store
from app.utils.logger import logger

router = APIRouter(prefix="/ingest", tags=["Ingestion"])

@router.get("/status", response_model=StatusResponse)
async def check_ingest_status():
    """Check the current status of knowledge base indexing. Automatic indexing happens on server startup."""
    try:
        # Check if chunks are loaded in vector memory
        total_chunks = len(vector_store.chunks)
        indexing_completed = total_chunks > 0
        
        return StatusResponse(
            status="success",
            indexing_completed=indexing_completed,
            total_chunks=total_chunks
        )
    except Exception as e:
        logger.error(f"Failed to fetch status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
