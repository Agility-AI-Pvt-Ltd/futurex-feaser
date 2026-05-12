from __future__ import annotations

from typing import Any

from core.config import settings
from core.storage_paths import resolve_writable_path

_clients_by_path: dict[str, Any] = {}


def _resolve_writable_qdrant_path(path: str) -> str:
    return resolve_writable_path(
        path,
        settings.qdrant_fallback_path,
        label="qdrant",
    )


def get_local_qdrant_client(path: str | None = None) -> Any:
    qdrant_path = _resolve_writable_qdrant_path(path or settings.qdrant_path)
    if qdrant_path not in _clients_by_path:
        from qdrant_client import QdrantClient

        _clients_by_path[qdrant_path] = QdrantClient(path=qdrant_path)
    return _clients_by_path[qdrant_path]


def close_qdrant_clients() -> None:
    for client in _clients_by_path.values():
        try:
            client.close()
        except Exception:
            pass
    _clients_by_path.clear()
