from __future__ import annotations

import ast
import json
import re
from typing import Any


_SMART_QUOTES_TRANSLATION = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
    }
)


def _find_balanced_json_substring(text: str, start: int) -> str | None:
    opening = text[start]
    closing = "}" if opening == "{" else "]"
    depth = 0
    in_string = False
    string_quote = ""
    escape = False

    for index in range(start, len(text)):
        char = text[index]

        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == string_quote:
                in_string = False
            continue

        if char in {'"', "'"}:
            in_string = True
            string_quote = char
            continue

        if char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return text[start : index + 1]

    return None


def _iter_json_candidates(raw_text: str):
    text = (raw_text or "").strip()
    if not text:
        return

    fence_matches = re.finditer(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    for match in fence_matches:
        candidate = match.group(1).strip()
        if candidate:
            yield candidate

    for index, char in enumerate(text):
        if char not in "{[":
            continue
        candidate = _find_balanced_json_substring(text, index)
        if candidate:
            yield candidate.strip()

    yield text


def _cleanup_json_candidate(candidate: str) -> str:
    cleaned = (candidate or "").strip()
    cleaned = cleaned.lstrip("\ufeff").translate(_SMART_QUOTES_TRANSLATION)
    cleaned = re.sub(r",(\s*[}\]])", r"\1", cleaned)
    cleaned = re.sub(
        r'([{,]\s*)([A-Za-z_][A-Za-z0-9_\- ]*)(\s*:)',
        lambda match: f'{match.group(1)}"{match.group(2).strip()}"{match.group(3)}',
        cleaned,
    )
    return cleaned


def _to_python_literal(candidate: str) -> str:
    pythonish = candidate
    pythonish = re.sub(r"\btrue\b", "True", pythonish, flags=re.IGNORECASE)
    pythonish = re.sub(r"\bfalse\b", "False", pythonish, flags=re.IGNORECASE)
    pythonish = re.sub(r"\bnull\b", "None", pythonish, flags=re.IGNORECASE)
    return pythonish


def extract_json_payload(raw_text: str) -> str:
    text = (raw_text or "").strip()
    if not text:
        raise ValueError("Empty LLM response")

    for candidate in _iter_json_candidates(text):
        candidate = candidate.strip()
        if candidate.startswith(("{", "[")) and candidate.endswith(("}", "]")):
            return candidate

    raise ValueError("No JSON payload found in LLM response")


def parse_json_from_text(raw_text: str, *, expected_type: type | tuple[type, ...] | None = None) -> Any:
    text = (raw_text or "").strip()
    if not text:
        raise ValueError("Empty LLM response")

    seen_candidates: set[str] = set()
    parse_errors: list[str] = []

    for candidate in _iter_json_candidates(text):
        for attempt in (candidate.strip(), _cleanup_json_candidate(candidate)):
            if not attempt or attempt in seen_candidates:
                continue
            seen_candidates.add(attempt)

            try:
                value = json.loads(attempt)
            except Exception as exc:
                parse_errors.append(str(exc))
            else:
                if expected_type is not None and not isinstance(value, expected_type):
                    parse_errors.append(f"Parsed JSON had unexpected type: {type(value).__name__}")
                else:
                    return value

            try:
                value = ast.literal_eval(_to_python_literal(attempt))
            except Exception as exc:
                parse_errors.append(str(exc))
            else:
                if expected_type is not None and not isinstance(value, expected_type):
                    parse_errors.append(f"Parsed literal had unexpected type: {type(value).__name__}")
                else:
                    return value

    raise ValueError(
        "Could not parse JSON from LLM response"
        + (f": {parse_errors[-1]}" if parse_errors else "")
    )
