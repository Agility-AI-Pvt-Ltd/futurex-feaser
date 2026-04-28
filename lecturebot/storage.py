from __future__ import annotations

import posixpath
import re
import uuid
from pathlib import Path

from core.config import settings
from core.logging import get_logger


logger = get_logger(__name__)
LOCAL_STORAGE_BUCKET_NAME = "local"


def slugify_path_segment(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip().lower())
    cleaned = cleaned.strip("-.")
    return cleaned or "default"


def ensure_storage_root() -> Path:
    storage_root = Path(settings.lecture_transcript_storage_path)
    storage_root.mkdir(parents=True, exist_ok=True)
    return storage_root


def build_transcript_object_path(session_name: str, file_name: str) -> str:
    safe_session = slugify_path_segment(session_name)
    original_name = Path(file_name).name
    safe_name = slugify_path_segment(Path(original_name).stem)
    suffix = Path(original_name).suffix.lower()
    unique_name = f"{safe_name}-{uuid.uuid4().hex}{suffix}"
    return posixpath.join(safe_session, unique_name)


def resolve_transcript_file_path(object_path: str) -> Path:
    storage_root = ensure_storage_root().resolve()
    target_path = (storage_root / object_path).resolve()
    try:
        target_path.relative_to(storage_root)
    except ValueError as exc:
        raise ValueError(f"Invalid transcript object path: {object_path}") from exc
    return target_path


def upload_transcript_bytes(
    *,
    session_name: str,
    file_name: str,
    file_bytes: bytes,
    content_type: str | None = None,
) -> tuple[str, str]:
    del content_type

    object_path = build_transcript_object_path(session_name, file_name)
    target_path = resolve_transcript_file_path(object_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(
        "storage.upload.start root=%s object_path=%s bytes=%s",
        settings.lecture_transcript_storage_path,
        object_path,
        len(file_bytes),
    )
    target_path.write_bytes(file_bytes)
    logger.info(
        "storage.upload.end root=%s object_path=%s",
        settings.lecture_transcript_storage_path,
        object_path,
    )
    return LOCAL_STORAGE_BUCKET_NAME, object_path


def download_transcript_text(bucket_name: str, object_path: str) -> str:
    logger.info(
        "storage.download.start bucket=%s object_path=%s",
        bucket_name,
        object_path,
    )
    file_path = resolve_transcript_file_path(object_path)
    if not file_path.is_file():
        raise ValueError(f"Transcript file not found: {object_path}")
    text = file_path.read_text(encoding="utf-8")
    logger.info(
        "storage.download.end bucket=%s object_path=%s chars=%s",
        bucket_name,
        object_path,
        len(text),
    )
    return text
