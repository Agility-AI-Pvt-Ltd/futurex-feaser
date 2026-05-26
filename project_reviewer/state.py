from __future__ import annotations

from typing import Any, NotRequired, TypedDict


class ReviewState(TypedDict):
    submission_id: int
    source_type: str
    author_id: NotRequired[str | None]
    github_url: NotRequired[str | None]
    archive_path: NotRequired[str | None]
    selected_repo: NotRequired[str | None]
    repository_path: NotRequired[str | None]
    storage_backend: NotRequired[str | None]
    storage_bucket: NotRequired[str | None]
    storage_object_path: NotRequired[str | None]
    inventory: NotRequired[dict[str, Any]]
    static_analysis: NotRequired[dict[str, Any]]
    context: NotRequired[str]
    llm_analysis: NotRequired[dict[str, Any]]
    verdict: NotRequired[dict[str, Any]]
    graph_trace: NotRequired[list[dict[str, Any]]]
    errors: NotRequired[list[str]]
