from pydantic import BaseModel
from typing import List, Optional

class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str

class ChatResponse(BaseModel):
    session_id: str
    message: str
    dob: Optional[str] = None
    birth_time: Optional[str] = None
    birth_place: Optional[str] = None
    language: str

class SessionInfoResponse(BaseModel):
    session_id: str
    dob: Optional[str] = None
    birth_time: Optional[str] = None
    birth_place: Optional[str] = None
    name: Optional[str] = None
    relation: Optional[str] = "Self"
    gender: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    language: str
    updated_at: str

class MessageResponse(BaseModel):
    role: str
    content: str
    timestamp: str

class HistoryResponse(BaseModel):
    session_id: str
    messages: List[MessageResponse]

class IngestResponse(BaseModel):
    status: str
    processed_files: List[str]
    chunks_count: int

class StatusResponse(BaseModel):
    status: str
    indexing_completed: bool
    total_chunks: int