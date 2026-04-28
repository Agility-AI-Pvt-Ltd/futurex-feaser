from __future__ import annotations

from typing import List, NotRequired, TypedDict


class ChatPipelineState(TypedDict):
    question: str
    history: List[dict]
    trace_id: NotRequired[str]
    memory_summary: NotRequired[str]
    conversation_relation: NotRequired[str]
    relation_confidence: NotRequired[str]
    relation_reason: NotRequired[str]
    resolved_question: NotRequired[str]
    history_context_used: NotRequired[str]
    transcript_id: NotRequired[int]
    transcript_source: NotRequired[str]
    transcript_session_name: NotRequired[str]
    transcript_object_path: NotRequired[str]
    retrieval_query: NotRequired[str]
    context_chunks: NotRequired[List[dict]]
    context_text: NotRequired[str]
    sources: NotRequired[List[str]]
    answer: NotRequired[str]
    updated_memory_summary: NotRequired[str]
