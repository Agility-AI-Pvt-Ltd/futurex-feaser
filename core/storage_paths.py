from __future__ import annotations

import logging
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)
_resolved_paths: dict[tuple[str, str, str], str] = {}


def assert_writable_directory(path: str) -> None:
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)

    probe_path = directory / f".write-test-{uuid.uuid4().hex}"
    probe_path.write_text("ok", encoding="utf-8")
    probe_path.unlink(missing_ok=True)


def resolve_writable_path(path: str, fallback_path: str, *, label: str) -> str:
    cache_key = (label, path, fallback_path)
    if cache_key in _resolved_paths:
        return _resolved_paths[cache_key]

    try:
        assert_writable_directory(path)
        _resolved_paths[cache_key] = path
        return path
    except OSError as exc:
        if path == fallback_path:
            raise

        logger.warning(
            "%s.path_not_writable path=%s fallback_path=%s error=%s",
            label,
            path,
            fallback_path,
            exc,
        )
        assert_writable_directory(fallback_path)
        _resolved_paths[cache_key] = fallback_path
        return fallback_path
