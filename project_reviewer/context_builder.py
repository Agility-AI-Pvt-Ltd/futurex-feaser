from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.config import settings
from project_reviewer.analyzers import is_text_file, read_text_limited


def build_llm_context(repository_path: str, inventory: dict[str, Any], static_analysis: dict[str, Any]) -> str:
    root = Path(repository_path).resolve()
    max_chars = max(10_000, settings.PROJECT_REVIEWER_MAX_CONTEXT_CHARS)

    sections: list[str] = [
        "# Repository Inventory",
        json.dumps(_compact_inventory(inventory), indent=2, default=str),
        "# Static Analysis Signals",
        json.dumps(_compact_static_analysis(static_analysis), indent=2, default=str),
        "# Representative Files",
    ]
    current_size = sum(len(section) for section in sections)

    for relative_path in _select_context_files(inventory):
        path = root / relative_path
        if not path.is_file() or not is_text_file(path):
            continue
        content = read_text_limited(path, max_bytes=min(settings.PROJECT_REVIEWER_MAX_FILE_BYTES, 60_000))
        if not content.strip():
            continue
        block = f"\n## {relative_path}\n```text\n{content[:12_000]}\n```\n"
        if current_size + len(block) > max_chars:
            sections.append("\n# Context Truncation\nAdditional files were omitted to stay inside the review context budget.")
            break
        sections.append(block)
        current_size += len(block)

    return "\n".join(sections)


def _compact_inventory(inventory: dict[str, Any]) -> dict[str, Any]:
    return {
        "file_count": inventory.get("file_count"),
        "total_bytes": inventory.get("total_bytes"),
        "primary_language": inventory.get("primary_language"),
        "language_counts": inventory.get("language_counts", {}),
        "key_files": inventory.get("key_files", [])[:40],
        "truncated": inventory.get("truncated", False),
        "sample_files": [
            item
            for item in inventory.get("files", [])[:120]
            if item.get("language") != "other"
        ],
    }


def _compact_static_analysis(static_analysis: dict[str, Any]) -> dict[str, Any]:
    python_metrics = static_analysis.get("python_metrics", {})
    return {
        "summary": static_analysis.get("summary", {}),
        "risk_flags": static_analysis.get("risk_flags", []),
        "feature_signals": static_analysis.get("feature_signals", {}),
        "security_signals": static_analysis.get("security_signals", {}),
        "test_signals": static_analysis.get("test_signals", {}),
        "architecture_signals": static_analysis.get("architecture_signals", {}),
        "git_signals": static_analysis.get("git_signals", {}),
        "spelling_signals": static_analysis.get("spelling_signals", {}),
        "python_totals": python_metrics.get("totals", {}),
        "worst_complexity": python_metrics.get("worst_complexity", [])[:10],
    }


def _select_context_files(inventory: dict[str, Any]) -> list[str]:
    files = inventory.get("files", [])
    key_files = list(inventory.get("key_files", []))
    important_dirs = ("api/", "app/", "src/", "server/", "backend/", "frontend/", "core/", "models/", "services/", "routes/")

    selected: list[str] = []
    for path in key_files:
        _append_unique(selected, path)

    for item in files:
        path = item.get("path", "")
        if path.startswith(important_dirs):
            _append_unique(selected, path)
        if len(selected) >= 45:
            break

    for item in files:
        path = item.get("path", "")
        if item.get("language") in {"python", "typescript", "javascript", "java", "go", "rust"}:
            _append_unique(selected, path)
        if len(selected) >= 65:
            break

    return selected


def _append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)
