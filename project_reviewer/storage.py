from __future__ import annotations

import io
import posixpath
import re
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class StoredArtifact:
    backend: str
    bucket_name: str | None
    object_path: str
    local_path: str | None
    total_bytes: int


def slugify_segment(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", (value or "").strip().lower())
    cleaned = cleaned.strip("-.")
    return cleaned or "submission"


def ensure_storage_root() -> Path:
    root = Path(settings.project_reviewer_storage_path)
    root.mkdir(parents=True, exist_ok=True)
    return root


def ensure_workdir_root() -> Path:
    root = Path(settings.project_reviewer_workdir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _build_object_path(submission_id: int, name: str) -> str:
    safe_name = slugify_segment(Path(name).name)
    return posixpath.join(str(submission_id), f"{uuid.uuid4().hex}-{safe_name}")


def resolve_local_artifact_path(object_path: str) -> Path:
    root = ensure_storage_root().resolve()
    target = (root / object_path).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Invalid project reviewer object path: {object_path}") from exc
    return target


def store_bytes(*, submission_id: int, file_name: str, content: bytes) -> StoredArtifact:
    backend = (settings.PROJECT_REVIEWER_STORAGE_BACKEND or "local").strip().lower()
    object_path = _build_object_path(submission_id, file_name)

    if backend == "gcs" and settings.PROJECT_REVIEWER_GCS_BUCKET_NAME:
        return _store_gcs_bytes(object_path=object_path, content=content)

    target = resolve_local_artifact_path(object_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return StoredArtifact(
        backend="local",
        bucket_name=None,
        object_path=object_path,
        local_path=str(target),
        total_bytes=len(content),
    )


def store_directory_snapshot(*, submission_id: int, directory: Path, file_name: str = "source.zip") -> StoredArtifact:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        root = directory.resolve()
        for path in sorted(root.rglob("*")):
            if path.is_dir() or ".git" in path.parts:
                continue
            try:
                relative_path = path.resolve().relative_to(root)
            except ValueError:
                continue
            archive.write(path, relative_path.as_posix())
    return store_bytes(submission_id=submission_id, file_name=file_name, content=buffer.getvalue())


def _store_gcs_bytes(*, object_path: str, content: bytes) -> StoredArtifact:
    try:
        from google.cloud import storage as gcs_storage
    except ImportError as exc:
        raise RuntimeError(
            "PROJECT_REVIEWER_STORAGE_BACKEND=gcs requires google-cloud-storage."
        ) from exc

    bucket_name = settings.PROJECT_REVIEWER_GCS_BUCKET_NAME
    prefix = settings.PROJECT_REVIEWER_GCS_PREFIX.strip("/")
    gcs_object_path = posixpath.join(prefix, object_path) if prefix else object_path

    client = gcs_storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(gcs_object_path)
    blob.upload_from_string(content, content_type="application/zip")

    logger.info(
        "project_reviewer.storage.gcs_upload bucket=%s object_path=%s bytes=%s",
        bucket_name,
        gcs_object_path,
        len(content),
    )
    return StoredArtifact(
        backend="gcs",
        bucket_name=bucket_name,
        object_path=gcs_object_path,
        local_path=None,
        total_bytes=len(content),
    )
