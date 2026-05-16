from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from core.config import settings
from core.llm_factory import get_llm
from core.logging import get_logger, truncate_for_log
from lecturebot.prompts import (
    get_transcript_chunk_summary_messages,
    get_transcript_summary_merge_messages,
)
from lecturebot.storage import download_transcript_text
from lecturebot.transcript_converter import clean_transcript_text, convert_transcript_to_text
from models import LectureTranscriptAsset, LectureTranscriptMetadata


logger = get_logger(__name__)


@dataclass(frozen=True)
class TranscriptSummaryResult:
    answer: str
    sources: list[str]
    cache_hit: bool


def _chunk_text(text: str, max_chars: int) -> list[str]:
    max_chars = max(2000, max_chars)
    paragraphs = [paragraph.strip() for paragraph in text.splitlines() if paragraph.strip()]
    if not paragraphs:
        return []

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current:
                chunks.append("\n".join(current))
                current = []
                current_len = 0
            for start in range(0, len(paragraph), max_chars):
                chunks.append(paragraph[start : start + max_chars])
            continue

        projected_len = current_len + len(paragraph) + 1
        if current and projected_len > max_chars:
            chunks.append("\n".join(current))
            current = [paragraph]
            current_len = len(paragraph)
        else:
            current.append(paragraph)
            current_len = projected_len

    if current:
        chunks.append("\n".join(current))

    return chunks


def _ensure_metadata(db: Session, transcript: LectureTranscriptAsset) -> LectureTranscriptMetadata:
    if transcript.metadata_entry:
        return transcript.metadata_entry

    metadata = LectureTranscriptMetadata(
        transcript_id=transcript.id,
        storage_path=transcript.object_path,
        qdrant_collection_name=settings.LECTURE_QDRANT_COLLECTION_NAME,
    )
    db.add(metadata)
    db.flush()
    return metadata


def _normalize_transcript_text(transcript: LectureTranscriptAsset, raw_text: str) -> str:
    if transcript.file_type == "vtt":
        return convert_transcript_to_text(transcript.file_name, raw_text)
    return clean_transcript_text(raw_text)


def get_transcript_text_from_db(
    db: Session,
    transcript: LectureTranscriptAsset,
) -> str:
    """Return full transcript text from DB, backfilling from storage for legacy rows."""
    metadata = _ensure_metadata(db, transcript)
    if metadata.transcript_text and metadata.transcript_text.strip():
        return metadata.transcript_text.strip()

    raw_text = download_transcript_text(transcript.bucket_name, transcript.object_path)
    transcript_text = _normalize_transcript_text(transcript, raw_text).strip()
    metadata.transcript_text = transcript_text
    db.flush()
    logger.info(
        "lecture_transcript_text.backfilled transcript_id=%s chars=%s",
        transcript.id,
        len(transcript_text),
    )
    return transcript_text


def _invoke_summary_llm(messages: Iterable) -> str:
    llm = get_llm(model=settings.LECTURE_OPENAI_MODEL_NAME, temperature=0.0)
    response = llm.invoke(list(messages))
    return (response.content or "").strip()


def generate_transcript_summary(
    *,
    transcript_name: str,
    transcript_text: str,
) -> str:
    chunks = _chunk_text(
        transcript_text,
        settings.LECTURE_TRANSCRIPT_SUMMARY_CHUNK_CHARS,
    )
    if not chunks:
        return ""

    chunk_summaries: list[str] = []
    total_chunks = len(chunks)
    for index, chunk in enumerate(chunks, start=1):
        summary = _invoke_summary_llm(
            get_transcript_chunk_summary_messages(
                transcript_name=transcript_name,
                chunk_text=chunk,
                chunk_number=index,
                total_chunks=total_chunks,
            )
        )
        if summary:
            chunk_summaries.append(summary)

    if not chunk_summaries:
        return ""

    if len(chunk_summaries) == 1:
        final_summary = chunk_summaries[0]
    else:
        final_summary = _invoke_summary_llm(
            get_transcript_summary_merge_messages(
                transcript_name=transcript_name,
                chunk_summaries=chunk_summaries,
                max_chars=settings.LECTURE_TRANSCRIPT_SUMMARY_MAX_CHARS,
            )
        )

    return final_summary.strip()[: settings.LECTURE_TRANSCRIPT_SUMMARY_MAX_CHARS]


def get_or_create_transcript_summary(
    *,
    transcript_id: int | None,
    trace_id: str = "unknown",
) -> TranscriptSummaryResult:
    if transcript_id is None:
        return TranscriptSummaryResult(
            answer="Please select or upload a transcript first, then ask for a summary.",
            sources=[],
            cache_hit=False,
        )

    from core.database import SessionLocal

    db = SessionLocal()
    try:
        transcript = db.query(LectureTranscriptAsset).filter_by(id=transcript_id).first()
        if not transcript:
            return TranscriptSummaryResult(
                answer="I could not find the selected transcript.",
                sources=[],
                cache_hit=False,
            )

        metadata = _ensure_metadata(db, transcript)
        if metadata.transcript_summary and metadata.transcript_summary.strip():
            logger.info(
                "lecture_transcript_summary.cache_hit trace_id=%s transcript_id=%s",
                trace_id,
                transcript_id,
            )
            return TranscriptSummaryResult(
                answer=metadata.transcript_summary.strip(),
                sources=[f"cached-summary:{transcript.source_name}"],
                cache_hit=True,
            )

        transcript_source = transcript.source_name
        transcript_text = get_transcript_text_from_db(db, transcript)
        db.commit()
        if not transcript_text:
            return TranscriptSummaryResult(
                answer="The transcript appears to be empty, so I cannot summarize it.",
                sources=[transcript_source],
                cache_hit=False,
            )

        summary = generate_transcript_summary(
            transcript_name=transcript_source,
            transcript_text=transcript_text,
        )
        if not summary:
            return TranscriptSummaryResult(
                answer="I could not generate a transcript summary right now. Please try again in a moment.",
                sources=[transcript_source],
                cache_hit=False,
            )

        metadata.transcript_text = transcript_text
        metadata.transcript_summary = summary
        metadata.summary_generated_at = datetime.datetime.utcnow()
        db.commit()

        logger.info(
            "lecture_transcript_summary.generated trace_id=%s transcript_id=%s chars=%s summary=%s",
            trace_id,
            transcript_id,
            len(summary),
            truncate_for_log(summary, settings.LECTURE_LOG_RAG_CHUNK_CHARS),
        )
        return TranscriptSummaryResult(
            answer=summary,
            sources=[f"full-transcript:{transcript_source}"],
            cache_hit=False,
        )
    except SQLAlchemyError:
        db.rollback()
        logger.exception(
            "lecture_transcript_summary.db_error trace_id=%s transcript_id=%s",
            trace_id,
            transcript_id,
        )
        return TranscriptSummaryResult(
            answer="I could not load the transcript summary from the database right now.",
            sources=[],
            cache_hit=False,
        )
    except Exception:
        db.rollback()
        logger.exception(
            "lecture_transcript_summary.error trace_id=%s transcript_id=%s",
            trace_id,
            transcript_id,
        )
        return TranscriptSummaryResult(
            answer="I could not generate a transcript summary right now. Please try again in a moment.",
            sources=[],
            cache_hit=False,
        )
    finally:
        db.close()
