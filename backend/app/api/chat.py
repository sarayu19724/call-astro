import uuid
import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from app.models.schemas import ChatRequest, ChatResponse, HistoryResponse, MessageResponse
from app.services.chat_service import chat_service
from app.memory.database import db
from app.utils.logger import logger

router = APIRouter(prefix="/chat", tags=["Chat"])

@router.post("", response_model=ChatResponse)
async def post_chat_message(payload: ChatRequest):
    """Send a message to the astrologer chatbot, updating session memory and obtaining predictions.
    Non-streaming — kept for compatibility. Use /chat/stream for the streaming version."""
    session_id = payload.session_id
    if not session_id or session_id.strip() == "":
        session_id = str(uuid.uuid4())
        logger.info(f"Generating new session_id: {session_id}")

    try:
        result = chat_service.process_chat_message(session_id, payload.message)
        return ChatResponse(
            session_id=result["session_id"],
            message=result["message"],
            dob=result.get("dob"),
            birth_time=result.get("birth_time"),
            birth_place=result.get("birth_place"),
            language=result["language"]
        )
    except Exception as e:
        logger.error(f"Error processing chat message: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/stream")
async def post_chat_message_stream(payload: ChatRequest):
    """Streaming version of /chat — sends the astrologer's reply as Server-Sent
    Events, one token at a time, instead of waiting for the full response."""
    session_id = payload.session_id
    if not session_id or session_id.strip() == "":
        session_id = str(uuid.uuid4())
        logger.info(f"Generating new session_id: {session_id}")

    def event_generator():
        try:
            for event in chat_service.process_chat_message_stream(session_id, payload.message):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            logger.error(f"Stream generator error: {e}")
            error_event = {
                "type": "done", "session_id": session_id,
                "message": "Kripya dobara koshish karein.",
                "dob": None, "birth_time": None, "birth_place": None, "language": "Hinglish"
            }
            yield f"data: {json.dumps(error_event)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.get("/history/{session_id}", response_model=HistoryResponse)
async def get_chat_history(session_id: str):
    """Retrieve all logged chat history for a session."""
    try:
        messages = db.get_history(session_id, limit=50)
        formatted_messages = [
            MessageResponse(
                role=msg["role"],
                content=msg["content"],
                timestamp=msg["timestamp"]
            )
            for msg in messages
        ]
        return HistoryResponse(
            session_id=session_id,
            messages=formatted_messages
        )
    except Exception as e:
        logger.error(f"Error retrieving chat history: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/history/{session_id}")
async def clear_chat_history(session_id: str):
    """Clear chat history for a session."""
    try:
        db.clear_history(session_id)
        return {"status": "success", "message": "Chat history cleared"}
    except Exception as e:
        logger.error(f"Error clearing chat history: {e}")
        raise HTTPException(status_code=500, detail=str(e))