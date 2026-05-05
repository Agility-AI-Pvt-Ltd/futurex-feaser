from __future__ import annotations

import os
from contextlib import nullcontext
from functools import lru_cache
from typing import Any

from core.config import settings

try:
    from langsmith import Client, traceable, tracing_context
except ImportError:  # pragma: no cover - fallback only when dependency missing
    Client = None
    traceable = None
    tracing_context = None


def langsmith_enabled() -> bool:
    return bool(settings.LANGSMITH_TRACING and settings.LANGSMITH_API_KEY)


def configure_langsmith() -> None:
    if not langsmith_enabled():
        return

    os.environ.setdefault("LANGSMITH_TRACING", "true")
    os.environ.setdefault("LANGSMITH_TRACING_V2", "true")
    os.environ.setdefault("LANGSMITH_ENDPOINT", settings.LANGSMITH_ENDPOINT)
    os.environ.setdefault("LANGSMITH_API_KEY", settings.LANGSMITH_API_KEY)
    os.environ.setdefault("LANGSMITH_PROJECT", settings.LANGSMITH_PROJECT)


@lru_cache(maxsize=1)
def get_langsmith_client():
    if not langsmith_enabled() or Client is None:
        return None
    return Client(
        api_key=settings.LANGSMITH_API_KEY,
        api_url=settings.LANGSMITH_ENDPOINT,
    )


def ls_traceable(*, run_type: str = "chain", name: str | None = None, tags: list[str] | None = None):
    def decorator(func):
        if traceable is None:
            return func
        return traceable(
            run_type=run_type,
            name=name,
            project_name=settings.LANGSMITH_PROJECT,
            client=get_langsmith_client(),
            enabled=langsmith_enabled(),
            tags=tags,
        )(func)

    return decorator


def ls_tracing_context(*, metadata: dict[str, Any] | None = None, tags: list[str] | None = None):
    if tracing_context is None:
        return nullcontext()

    return tracing_context(
        project_name=settings.LANGSMITH_PROJECT,
        client=get_langsmith_client(),
        enabled=langsmith_enabled(),
        metadata=metadata,
        tags=tags,
    )
