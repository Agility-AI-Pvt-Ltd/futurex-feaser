from __future__ import annotations

from typing import Any

from core.config import settings
from core.storage_paths import resolve_writable_path

_clients_by_path: dict[str, Any] = {}


class QdrantDisabledError(RuntimeError):
    pass


def _resolve_writable_qdrant_path(path: str) -> str:
    return resolve_writable_path(
        path,
        settings.qdrant_fallback_path,
        label="qdrant",
    )


def get_local_qdrant_client(path: str | None = None) -> Any:
    if not settings.qdrant_enabled:
        raise QdrantDisabledError("Qdrant is disabled because QDRANT_BACKEND=none.")

    if settings.qdrant_backend == "remote":
        key = "remote"
        if key not in _clients_by_path:
            endpoint_url = settings.QDRANT_URL.strip() or settings.QDRANT_CLOUD_URL.strip()
            if not endpoint_url:
                raise RuntimeError(
                    "QDRANT_URL or QDRANT_CLOUD_URL is required when QDRANT_BACKEND=remote."
                )
            api_key = settings.QDRANT_API_KEY.strip() or settings.QDRANT_CLOUD_API_KEY.strip() or None

            from qdrant_client import QdrantClient

            _clients_by_path[key] = QdrantClient(
                url=endpoint_url,
                api_key=api_key,
            )
        return _clients_by_path[key]

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
