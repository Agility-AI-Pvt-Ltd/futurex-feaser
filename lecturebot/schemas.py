from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class MessageOut(BaseModel):
    id: int
    session_id: str
    role: str
    content: str
    timestamp: datetime

    class Config:
        from_attributes = True


class ChatSessionOut(BaseModel):
    id: int
    session_id: str
    created_at: datetime
    is_mentor_requested: bool
    memory_summary: Optional[str] = ""
    messages: List[MessageOut] = Field(default_factory=list)

    class Config:
        from_attributes = True


class ChatRequest(BaseModel):
    session_id: str
    message: str
    transcript_id: Optional[int] = None


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    sources: Optional[List[str]] = Field(default_factory=list)


class TranscriptMetadataOut(BaseModel):
    id: int
    transcript_id: int
    course_name: str = ""
    instructor_name: str = ""
    session_date: str = ""
    description: str = ""
    tags: str = ""
    storage_path: str
    qdrant_collection_name: str
    created_at: datetime

    class Config:
        from_attributes = True


class TranscriptUpdate(BaseModel):
    session_name: Optional[str] = None
    source_name: Optional[str] = None
    course_name: Optional[str] = None
    instructor_name: Optional[str] = None
    session_date: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[str] = None

class TranscriptAssetOut(BaseModel):
    id: int
    session_id: Optional[str] = None
    session_name: str
    source_name: str
    file_name: str
    file_type: str
    bucket_name: str
    object_path: str
    chunks_indexed: int
    created_at: datetime
    metadata_entry: Optional[TranscriptMetadataOut] = None

    class Config:
        from_attributes = True


class UploadResponse(BaseModel):
    message: str
    chunks_indexed: int
    session_name: str
    source_name: str
    bucket_name: str
    object_path: str
    metadata_entry: TranscriptMetadataOut


class TranscriptReprocessResponse(BaseModel):
    message: str
    transcript_id: int
    chunks_indexed: int
