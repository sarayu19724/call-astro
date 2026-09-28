"""Prediction-journal API routes.

There are intentionally NO manual memory-edit routes. User memory is created
and updated automatically by the LLM during normal chat. The journal keeps the
original prediction immutable and exposes only reading + outcome recording.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.memory.database import db
from app.services.memory_journal_service import memory_journal_service

router = APIRouter(prefix="/api/prediction-journal", tags=["Prediction Journal"])


class OutcomeRequest(BaseModel):
    outcome: str = Field(..., min_length=1, max_length=2000)
    note: Optional[str] = Field(default=None, max_length=2000)


@router.get("/{session_id}")
def list_predictions(session_id: str):
    session = db.get_or_create_session(session_id)
    return {
        "session_id": session_id,
        "predictions": memory_journal_service.list_predictions(session),
    }


@router.get("/{session_id}/{prediction_id}")
def get_prediction(session_id: str, prediction_id: str):
    session = db.get_or_create_session(session_id)
    prediction = memory_journal_service.get_prediction(session, prediction_id)
    if not prediction:
        raise HTTPException(status_code=404, detail="Prediction not found")
    return prediction


@router.post("/{session_id}/{prediction_id}/outcome")
def record_prediction_outcome(session_id: str, prediction_id: str, body: OutcomeRequest):
    session = db.get_or_create_session(session_id)
    prediction = memory_journal_service.record_outcome(
        session_id=session_id,
        session=session,
        prediction_id=prediction_id,
        outcome=body.outcome,
        note=body.note,
    )
    if not prediction:
        raise HTTPException(status_code=404, detail="Prediction not found")
    return prediction
