from __future__ import annotations

import uuid
from typing import List

from core.config import settings
from core.logging import get_logger, truncate_for_log
from lecturebot.graph import chat_app


logger = get_logger(__name__)
FALLBACK_ANSWER = (
    "I could not complete the answer right now because the AI pipeline is temporarily "
    "unavailable. Please try again in a moment."
)


def run_chat_pipeline(
    question: str,
    history: List[dict],
    memory_summary: str = "",
    transcript_id: int | None = None,
    transcript_source: str = "",
    transcript_session_name: str = "",
    transcript_object_path: str = "",
) -> tuple[str, List[str], str]:
    trace_id = str(uuid.uuid4())
    try:
        result = chat_app.invoke(
            {
                "question": question,
                "history": history,
                "memory_summary": memory_summary,
                "transcript_id": transcript_id,
                "transcript_source": transcript_source,
                "transcript_session_name": transcript_session_name,
                "transcript_object_path": transcript_object_path,
                "trace_id": trace_id,
            }
        )
    except Exception:
        logger.exception("lecture_chat_pipeline.error trace_id=%s", trace_id)
        result = {
            "answer": FALLBACK_ANSWER,
            "sources": [],
            "updated_memory_summary": memory_summary,
        }

    logger.info(
        "lecture_chat_pipeline.end trace_id=%s answer=%s",
        trace_id,
        truncate_for_log(result.get("answer", ""), settings.LECTURE_LOG_PROMPT_CHARS),
    )
    return (
        result.get("answer", ""),
        result.get("sources", []),
        result.get("updated_memory_summary", memory_summary),
    )
