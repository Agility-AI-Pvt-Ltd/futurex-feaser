from __future__ import annotations

import json
from typing import Any

from core.json_utils import parse_json_from_text


FEASIBILITY_REPORT_KEYS = (
    "chain_of_thought",
    "idea_fit",
    "competitors",
    "opportunity",
    "score",
    "targeting",
    "next_step",
)


def _normalize_chain_of_thought(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _normalize_text_field(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value).strip()


def parse_feasibility_report(raw_text: str) -> dict[str, Any]:
    parsed = parse_json_from_text(raw_text, expected_type=dict)
    report = {
        "chain_of_thought": _normalize_chain_of_thought(parsed.get("chain_of_thought")),
        "idea_fit": _normalize_text_field(parsed.get("idea_fit")),
        "competitors": _normalize_text_field(parsed.get("competitors")),
        "opportunity": _normalize_text_field(parsed.get("opportunity")),
        "score": _normalize_text_field(parsed.get("score")),
        "targeting": _normalize_text_field(parsed.get("targeting")),
        "next_step": _normalize_text_field(parsed.get("next_step")),
    }
    return report


def normalize_feasibility_report_json(raw_text: str) -> str:
    return json.dumps(parse_feasibility_report(raw_text), ensure_ascii=False)


def get_feasibility_report_repair_prompt(raw_text: str) -> str:
    return (
        "You are fixing malformed JSON from a startup feasibility analysis.\n"
        "Convert the content below into ONE strict valid JSON object.\n"
        "Return ONLY JSON with EXACTLY these 7 keys:\n"
        '{\n'
        '  "chain_of_thought": ["..."],\n'
        '  "idea_fit": "",\n'
        '  "competitors": "",\n'
        '  "opportunity": "",\n'
        '  "score": "",\n'
        '  "targeting": "",\n'
        '  "next_step": ""\n'
        '}\n'
        "Rules:\n"
        "- No markdown fences.\n"
        "- No explanation before or after the JSON.\n"
        "- If any field is missing, use an empty string or an empty array.\n"
        "- Preserve the original meaning as closely as possible.\n\n"
        f"Original content:\n{raw_text}"
    )
