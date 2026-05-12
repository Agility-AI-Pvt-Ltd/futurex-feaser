from __future__ import annotations

from core.config import settings
from core.storage_paths import resolve_writable_path


def get_fastembed_cache_dir() -> str:
    return resolve_writable_path(
        settings.fastembed_cache_dir,
        settings.fastembed_fallback_cache_dir,
        label="fastembed",
    )
