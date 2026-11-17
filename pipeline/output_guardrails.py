"""
pipeline/output_guardrails.py
─────────────────────────────
Format guardrails for Idea Lab output, applied before anything reaches the UI.

The Next.js Idea Lab page (FutureX apps/web/app/(main)/idea-lab/page.tsx) renders:
  • the feasibility report only when `analysis` is a JSON object with the report
    keys; anything else is shown as a "Clarifying Question" or "Raw Analysis";
  • report sections, QA answers and advisor replies with a small markdown subset:
    #/##/### headings, "- " / "* " / "1. " list items, "---" separators and
    **bold**. Tables, links, code, HTML and italics show up as raw characters;
  • the reasoning trail and the engagement question as plain text.

Every guard runs deterministic rules first. The report and the two question
types get one LLM repair pass only when the rules still find problems, and fall
back to a rule-only result when that pass is disabled or fails.
"""

from __future__ import annotations

import html
import json
import logging
import re
import time
from typing import Any

from core.config import settings
from core.json_utils import parse_json_from_text
from core.logging import get_logger

logger = get_logger(__name__)


# ── Report contract ────────────────────────────────────────────────────────────

REPORT_KEYS = (
    "chain_of_thought",
    "idea_fit",
    "competitors",
    "opportunity",
    "score",
    "score_rationale",
    "targeting",
    "next_step",
)
REPORT_TEXT_FIELDS = (
    "idea_fit",
    "competitors",
    "opportunity",
    "score_rationale",
    "targeting",
    "next_step",
)
REQUIRED_REPORT_FIELDS = (
    "idea_fit",
    "competitors",
    "opportunity",
    "score",
    "targeting",
    "next_step",
)
REPORT_SECTION_TITLES = {
    "idea_fit": "Idea Fit",
    "competitors": "Competitors",
    "opportunity": "Opportunity",
    "score_rationale": "Score Rationale",
    "targeting": "Targeting",
    "next_step": "Next Step",
}

# Section names LLMs drift to, mapped onto the keys the UI reads.
_KEY_ALIASES = {
    **dict.fromkeys(
        (
            "chain_of_thought",
            "chain_of_thoughts",
            "reasoning",
            "reasoning_steps",
            "reasoning_trail",
            "thought_process",
            "analysis_steps",
        ),
        "chain_of_thought",
    ),
    **dict.fromkeys(
        ("idea_fit", "fit", "problem_solution_fit", "product_market_fit", "idea_market_fit"),
        "idea_fit",
    ),
    **dict.fromkeys(
        (
            "competitors",
            "competitor",
            "competition",
            "competitor_analysis",
            "competitive_analysis",
            "competitive_landscape",
        ),
        "competitors",
    ),
    **dict.fromkeys(
        ("opportunity", "opportunities", "market_opportunity", "market_gap", "market_gaps"),
        "opportunity",
    ),
    **dict.fromkeys(
        ("score", "feasibility_score", "overall_score", "final_score"),
        "score",
    ),
    **dict.fromkeys(
        (
            "score_rationale",
            "rationale",
            "score_reasoning",
            "score_explanation",
            "score_justification",
        ),
        "score_rationale",
    ),
    **dict.fromkeys(
        (
            "targeting",
            "target_customers",
            "target_customer",
            "target_segments",
            "target_market",
            "target_audience",
            "customer_targeting",
            "go_to_market",
            "go_to_market_strategy",
            "gtm",
        ),
        "targeting",
    ),
    **dict.fromkeys(
        (
            "next_step",
            "next_steps",
            "next_step_s",
            "action_items",
            "action_plan",
            "recommended_next_steps",
            "recommendations",
        ),
        "next_step",
    ),
}

MAX_FIELD_CHARS = 6000
MAX_CHAIN_STEPS = 10
MAX_CHAIN_STEP_CHARS = 400
MAX_REPAIR_INPUT_CHARS = 12000
CLARIFYING_MAX_CHARS = 600
ENGAGEMENT_MAX_WORDS = 35
DEFAULT_CLARIFYING_QUESTION = (
    "Who exactly would pay for this first, and what are they using today to solve the problem?"
)

_VALID_SCORE_RE = re.compile(r"^\d{1,3}/100$")


# ── Markdown rules (UI-supported subset) ───────────────────────────────────────

_HEADING_RE = re.compile(r"^(?:(#{2,6})\s*|(#)\s+)(\S.*?)\s*#*$")
_SEPARATOR_RE = re.compile(r"^(?:(?:-\s*){3,}|(?:\*\s*){3,}|(?:_\s*){3,}|={3,}|[—–]{2,})$")
_BULLET_RE = re.compile(r"^(?:[•●▪◦‣∙·–—+]|[-*])\s+(?:\[[ xX]\]\s+)?(.*)$")
_NUMBERED_RE = re.compile(r"^\(?(\d{1,3})[.)]\s+(.*)$")
_TABLE_DIVIDER_RE = re.compile(r"^\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)*\|?$")
_ESCAPED_NEWLINE_RE = re.compile(r"(?<!\\)\\n")

_HTML_BREAK_RE = re.compile(r"<\s*(?:br|/p|/div|/li|/h[1-6]|/tr)\s*/?\s*>", re.IGNORECASE)
_HTML_LIST_ITEM_RE = re.compile(r"<\s*li(?:\s[^>]*)?>", re.IGNORECASE)
_HTML_BOLD_RE = re.compile(r"<\s*/?\s*(?:b|strong)\s*>", re.IGNORECASE)
_HTML_TAG_RE = re.compile(
    r"<\s*/?\s*(?:p|div|span|ul|ol|h[1-6]|em|i|u|a|table|thead|tbody|tr|td|th|code|pre|"
    r"sup|sub|small|section|article|blockquote|hr)(?:\s[^>]*)?/?>",
    re.IGNORECASE,
)


def _unescape_newlines(text: str) -> str:
    """LLMs sometimes double-escape newlines inside JSON strings."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if "\\n" in text:
        text = _ESCAPED_NEWLINE_RE.sub("\n", text).replace("\\t", " ")
    return text


def _strip_html(text: str) -> str:
    if "<" not in text and "&" not in text:
        return text
    text = _HTML_BREAK_RE.sub("\n", text)
    text = _HTML_LIST_ITEM_RE.sub("\n- ", text)
    text = _HTML_BOLD_RE.sub("**", text)
    text = _HTML_TAG_RE.sub("", text)
    return html.unescape(text)


def _sanitize_inline(text: str) -> str:
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(
        r"\[([^\]]+)\]\((\S+?)\)",
        lambda m: m.group(1) if m.group(1).strip() == m.group(2).strip() else f"{m.group(1)} ({m.group(2)})",
        text,
    )
    text = re.sub(r"`([^`]+)`", r"\1", text).replace("`", "")
    text = re.sub(r"\*\*\*(.+?)\*\*\*", r"**\1**", text)
    text = re.sub(r"(?<![\w_])__(?!\s)(.+?)(?<!\s)__(?![\w_])", r"**\1**", text)
    # Single-asterisk italics are not rendered by the UI; keep the words.
    text = re.sub(r"(?<![*\w])\*(?![\s*])([^*\n]+?)(?<![\s*])\*(?![*\w])", r"\1", text)
    text = re.sub(r"~~(.+?)~~", r"\1", text)
    text = re.sub(r"\\([*_#`\[\]()>~-])", r"\1", text)
    if text.count("**") % 2:
        index = text.rfind("**")
        text = text[:index] + text[index + 2 :]
    return text.strip()


def _split_table_row(row: str) -> list[str]:
    return [cell.strip() for cell in row.strip().strip("|").split("|")]


def _table_to_bullets(rows: list[str]) -> list[str]:
    cells = [_split_table_row(row) for row in rows if not _TABLE_DIVIDER_RE.match(row)]
    if not cells:
        return []
    header, body = cells[0], cells[1:]
    if not body:
        joined = ", ".join(_sanitize_inline(cell) for cell in header if cell)
        return [f"- {joined}"] if joined else []

    bullets = []
    for row in body:
        values = [_sanitize_inline(cell) for cell in row]
        if not any(values):
            continue
        lead = values[0].replace("**", "")
        details = []
        for index, value in enumerate(values[1:], start=1):
            if not value:
                continue
            label = _sanitize_inline(header[index]).replace("**", "") if index < len(header) else ""
            details.append(f"{label}: {value}" if label else value)
        if lead and details:
            bullets.append(f"- **{lead}**: {'; '.join(details)}")
        elif lead:
            bullets.append(f"- **{lead}**")
        else:
            bullets.append(f"- {'; '.join(details)}")
    return bullets


def _sanitize_line(line: str) -> str:
    while line.startswith(">"):
        line = line[1:].lstrip()
    if not line:
        return ""
    if _SEPARATOR_RE.match(line):
        return "---"
    if re.fullmatch(r"#+", line):
        return ""
    heading = _HEADING_RE.match(line)
    if heading:
        level = min(len(heading.group(1) or heading.group(2)), 3)
        body = _sanitize_inline(heading.group(3))
        return f"{'#' * level} {body}" if body else ""
    bullet = _BULLET_RE.match(line)
    if bullet:
        body = _sanitize_inline(bullet.group(1))
        return f"- {body}" if body else ""
    numbered = _NUMBERED_RE.match(line)
    if numbered:
        body = _sanitize_inline(numbered.group(2))
        return f"{numbered.group(1)}. {body}" if body else ""
    return _sanitize_inline(line)


def sanitize_markdown(text: Any) -> str:
    """Rewrite markdown into the subset the Idea Lab UI renders."""
    if text is None:
        return ""
    text = _strip_html(_unescape_newlines(str(text)))

    lines: list[str] = []
    table: list[str] = []
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if line.startswith("|") and line.endswith("|") and len(line) > 1:
            table.append(line)
            continue
        if table:
            lines.extend(_table_to_bullets(table))
            table.clear()
        if line.startswith(("```", "~~~")):
            continue
        lines.append(_sanitize_line(line))
    if table:
        lines.extend(_table_to_bullets(table))

    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def to_plain_text(text: Any) -> str:
    """Flatten markdown to one line of plain text for fields the UI shows verbatim."""
    if text is None:
        return ""
    text = _strip_html(_unescape_newlines(str(text)))
    parts = []
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if (
            not line
            or line.startswith(("```", "~~~"))
            or _SEPARATOR_RE.match(line)
            or _TABLE_DIVIDER_RE.match(line)
        ):
            continue
        line = re.sub(r"^>\s*", "", line)
        line = re.sub(r"^#{1,6}\s*", "", line)
        marker = _BULLET_RE.match(line) or _NUMBERED_RE.match(line)
        if marker:
            line = marker.group(marker.lastindex)
        line = _sanitize_inline(line).replace("**", "").strip("| ").replace(" | ", ", ")
        if line:
            parts.append(line)
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


# ── Report normalisation ───────────────────────────────────────────────────────

def _canonical_key(key: Any) -> str | None:
    snake = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", str(key).strip())
    snake = re.sub(r"[^a-z0-9]+", "_", snake.lower()).strip("_")
    return _KEY_ALIASES.get(snake)


def _humanize_key(key: Any) -> str:
    text = re.sub(r"[_\-]+", " ", str(key)).strip()
    return text[:1].upper() + text[1:]


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, dict)):
        return len(value) == 0
    return False


def _plain_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return "; ".join(
            f"{_humanize_key(k)}: {_plain_value(v)}" for k, v in value.items() if _plain_value(v)
        )
    if isinstance(value, (list, tuple)):
        return ", ".join(part for part in (_plain_value(v) for v in value) if part)
    return str(value).strip()


_NAME_KEYS = ("name", "title", "competitor", "company", "product", "segment", "label")
_STEP_TEXT_KEYS = ("description", "text", "step", "thought", "reasoning", "detail", "content")


def _structured_to_markdown(value: Any) -> str:
    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            if isinstance(item, (dict, list, tuple)) and item:
                nested = _structured_to_markdown(item)
                if nested:
                    parts.append(f"**{_humanize_key(key)}**\n{nested}")
                continue
            text = _plain_value(item)
            if text:
                parts.append(f"- **{_humanize_key(key)}**: {text}")
        return "\n".join(parts)

    lines = []
    for item in value:
        if isinstance(item, dict):
            name_key = next(
                (k for k in item if str(k).lower() in _NAME_KEYS and _plain_value(item[k])),
                None,
            )
            detail = _plain_value({k: v for k, v in item.items() if k != name_key})
            if name_key:
                name = _plain_value(item[name_key]).replace("**", "")
                lines.append(f"- **{name}**: {detail}" if detail else f"- **{name}**")
            elif detail:
                lines.append(f"- {detail}")
        else:
            text = _plain_value(item)
            if text:
                lines.append(f"- {text}")
    return "\n".join(lines)


def _to_markdown_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        stripped = value.strip()
        if stripped[:1] in ("[", "{"):
            try:
                parsed = json.loads(stripped)
            except ValueError:
                parsed = None
            if isinstance(parsed, (dict, list)):
                return _structured_to_markdown(parsed)
        return stripped
    if isinstance(value, (dict, list, tuple)):
        return _structured_to_markdown(value)
    return str(value).strip()


def _strip_leading_title(text: str, field: str) -> str:
    """Drop a heading or "Label:" prefix that repeats the section title the UI already shows."""
    if not text:
        return text
    lines = text.split("\n")
    first = re.sub(r"[#*_:\s]+", " ", lines[0]).strip()
    if _canonical_key(first) == field:
        return "\n".join(lines[1:]).strip()
    prefix = re.match(r"^(?:\*\*)?([A-Za-z][A-Za-z _-]{1,40}?)(?:\*\*)?\s*:\s*(?:\*\*)?\s*", text)
    if prefix and _canonical_key(prefix.group(1)) == field:
        return text[prefix.end() :].strip()
    return text


_SCORE_FRACTION_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:/|out\s+of)\s*(100|10|5)\b(?!\.\d)", re.IGNORECASE)
_SCORE_PERCENT_RE = re.compile(r"^\D{0,30}?(\d+(?:\.\d+)?)\s*%")
_SCORE_LEADING_NUMBER_RE = re.compile(
    r"^\s*(?:(?:overall|final|feasibility)\s+)*(?:score\s*(?:is|of)?\s*[:\-–—]?\s*)?"
    r"(\d+(?:\.\d+)?)\s*(?:points?)?\s*(?=$|[-–—:.,;(])",
    re.IGNORECASE,
)
_SCORE_LABEL_RE = re.compile(
    r"^\s*(?:(?:overall|final|feasibility)\s+)*score\s*(?:is|of)?\s*[:\-–—]?\s*", re.IGNORECASE
)


def normalize_score(value: Any) -> tuple[str, str]:
    """Return ("NN/100", leftover_text). The score is "" when no score can be read."""
    if isinstance(value, bool):
        return "", ""
    if isinstance(value, (int, float)):
        text = str(value)
    else:
        text = value if isinstance(value, str) else _plain_value(value)
        text = _sanitize_inline(_strip_html(_unescape_newlines(text))).replace("**", "")
        text = re.sub(r"\s+", " ", text.replace("#", " ")).strip()
    if not text:
        return "", ""

    number = None
    match = _SCORE_FRACTION_RE.search(text)
    if match:
        number = float(match.group(1)) / float(match.group(2)) * 100
    if number is None:
        match = _SCORE_PERCENT_RE.search(text)
        if match:
            number = float(match.group(1))
    if number is None:
        match = _SCORE_LEADING_NUMBER_RE.match(text)
        if match:
            number = float(match.group(1))
            if "." in match.group(1) and number <= 10:
                number *= 10
    if number is None:
        return "", text

    score = max(0, min(100, round(number)))
    leftover = (text[: match.start(1)] + " " + text[match.end() :]).strip()
    leftover = _SCORE_LABEL_RE.sub("", leftover)
    leftover = re.sub(r"^[\s\-–—:.,;()\[\]]+|[\s\-–—:,;()\[\]]+$", "", leftover)
    leftover = re.sub(r"^rationale\s*[:\-–—]\s*", "", leftover, flags=re.IGNORECASE).strip()
    return f"{score}/100", leftover


_STEP_PREFIX_RE = re.compile(
    r"^\s*(?:(?:[-*•]\s+)|(?:\(?\d{1,2}[.):]\s*)|(?:step\s*\d{1,2}\s*[:.)\-–—]\s*))+",
    re.IGNORECASE,
)


def _normalize_chain_of_thought(value: Any) -> list[str]:
    if _is_empty(value):
        return []
    if isinstance(value, str):
        stripped = value.strip()
        parsed = None
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
            except ValueError:
                parsed = None
        items = parsed if isinstance(parsed, list) else _unescape_newlines(stripped).split("\n")
    elif isinstance(value, dict):
        items = list(value.values())
    elif isinstance(value, (list, tuple)):
        items = list(value)
    else:
        items = [value]

    steps: list[str] = []
    for item in items:
        if isinstance(item, dict):
            lowered = {str(k).lower(): v for k, v in item.items()}
            text = next(
                (lowered[k] for k in _STEP_TEXT_KEYS if isinstance(lowered.get(k), str) and lowered[k].strip()),
                _plain_value(item),
            )
        else:
            text = _plain_value(item)
        text = _STEP_PREFIX_RE.sub("", to_plain_text(text)).strip()
        if text and text not in steps:
            steps.append(text[:MAX_CHAIN_STEP_CHARS])
    return steps[:MAX_CHAIN_STEPS]


def _unwrap_report(data: dict) -> dict:
    """Handle {"report": {...}} style wrappers around the real report object."""
    for _ in range(2):
        if any(_canonical_key(key) for key in data):
            return data
        nested = [value for value in data.values() if isinstance(value, dict)]
        if len(nested) != 1:
            return data
        data = nested[0]
    return data


def normalize_report(data: dict) -> dict[str, Any]:
    """Map any report-like dict onto the exact 8-key shape the UI renders."""
    collected: dict[str, Any] = {}
    for key, value in _unwrap_report(data).items():
        canonical = _canonical_key(key)
        if canonical and (canonical not in collected or _is_empty(collected[canonical])):
            collected[canonical] = value

    report: dict[str, Any] = {key: "" for key in REPORT_KEYS}
    report["chain_of_thought"] = _normalize_chain_of_thought(collected.get("chain_of_thought"))
    for field in REPORT_TEXT_FIELDS:
        text = sanitize_markdown(_to_markdown_text(collected.get(field)))
        report[field] = _strip_leading_title(text, field)[:MAX_FIELD_CHARS].strip()

    score, leftover = normalize_score(collected.get("score"))
    report["score"] = score
    if not report["score_rationale"] and len(leftover.split()) >= 4:
        rationale = sanitize_markdown(leftover)
        report["score_rationale"] = rationale[:1].upper() + rationale[1:]
    return report


def report_issues(report: dict[str, Any] | None) -> list[str]:
    if not report:
        return ["the output is not a feasibility report object"]
    issues = [f"'{field}' is missing or empty" for field in REQUIRED_REPORT_FIELDS if not report.get(field)]
    score = report.get("score")
    if score and not _VALID_SCORE_RE.match(str(score)):
        issues.append("'score' must look like 72/100")
    return issues


_SECTION_LABEL_RE = re.compile(
    r"^(?:#{1,6}\s*)?(?:\d{1,2}[.)]\s+)?(?:\*\*|__)?(?P<label>[A-Za-z][A-Za-z /&_-]{0,40}?)(?:\*\*|__)?\s*"
    r"(?:(?::\s*(?:\*\*|__)?\s*(?P<rest>.*))|$)"
)


def _section_label(line: str) -> tuple[str, str] | None:
    match = _SECTION_LABEL_RE.match(line)
    if not match:
        return None
    field = _canonical_key(match.group("label"))
    if not field:
        return None
    return field, (match.group("rest") or "").strip()


def extract_report_from_markdown(text: str) -> dict[str, str] | None:
    """Recover report sections from a markdown/plain-text answer instead of JSON."""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for raw_line in _unescape_newlines(text).split("\n"):
        line = raw_line.strip()
        label = _section_label(line) if line else None
        if label:
            current, rest = label
            sections.setdefault(current, [])
            if rest:
                sections[current].append(rest)
            continue
        if current:
            sections[current].append(raw_line)

    found = {key: "\n".join(lines).strip() for key, lines in sections.items()}
    found = {key: value for key, value in found.items() if value}
    if sum(1 for key in found if key in REQUIRED_REPORT_FIELDS) < 3:
        return None
    return found


_JSON_STRING_FIELD_RE = re.compile(r'"([A-Za-z_ ]{2,40})"\s*:\s*"((?:[^"\\]|\\.)*)"')


def _salvage_json_fields(text: str) -> dict[str, str] | None:
    """Pull complete string fields out of truncated or otherwise broken JSON."""
    found: dict[str, str] = {}
    for key, raw_value in _JSON_STRING_FIELD_RE.findall(text):
        canonical = _canonical_key(key)
        if not canonical or canonical in found:
            continue
        try:
            found[canonical] = json.loads(f'"{raw_value}"')
        except ValueError:
            found[canonical] = raw_value
    if sum(1 for key in found if key in REQUIRED_REPORT_FIELDS) < 3:
        return None
    return found


def _unwrap_code_fence(text: str) -> str:
    fenced = re.fullmatch(r"```[A-Za-z]*\s*([\s\S]*?)\s*```", text.strip())
    return fenced.group(1).strip() if fenced else text.strip()


def _load_json_document(text: str) -> Any:
    """Parse text only when the whole message is JSON; None otherwise."""
    text = _unwrap_code_fence(text)
    if text[:1] not in ("{", "[", '"'):
        return None
    try:
        # strict=False accepts raw newlines inside strings, which LLMs emit often.
        return json.loads(text, strict=False)
    except ValueError:
        return None


def _rule_based_report(text: str) -> tuple[dict[str, Any] | None, str | None, dict | None]:
    """Return (report, source, the dict it was built from); source is json/salvaged_json/markdown."""
    data = _load_json_document(text)
    if not isinstance(data, dict):
        try:
            data = parse_json_from_text(text, expected_type=dict)
        except ValueError:
            data = None
    if data is not None:
        report = normalize_report(data)
        if any(report[key] for key in REPORT_KEYS):
            return report, "json", data

    for source, extractor in (("salvaged_json", _salvage_json_fields), ("markdown", extract_report_from_markdown)):
        sections = extractor(text)
        if sections:
            return normalize_report(sections), source, sections
    return None, None, None


def _merge_reports(base: dict[str, Any] | None, repaired: dict[str, Any]) -> dict[str, Any]:
    if base is None:
        return repaired
    merged = dict(base)
    for key in REPORT_KEYS:
        if _is_empty(merged.get(key)) and not _is_empty(repaired.get(key)):
            merged[key] = repaired[key]
    return merged


def _fallback_report(text: str) -> dict[str, Any]:
    report: dict[str, Any] = {key: "" for key in REPORT_KEYS}
    report["chain_of_thought"] = []
    report["idea_fit"] = sanitize_markdown(text)[:MAX_FIELD_CHARS] or (
        "The analysis could not be formatted. Please run the analysis again."
    )
    return report


def report_to_markdown(report: dict[str, Any]) -> str:
    parts = []
    if report.get("score"):
        parts.append(f"**Score:** {report['score']}")
    for field in REPORT_TEXT_FIELDS:
        if report.get(field):
            parts.append(f"### {REPORT_SECTION_TITLES[field]}\n{report[field]}")
    return "\n\n".join(parts)


# ── LLM repair ─────────────────────────────────────────────────────────────────

def _extract_llm_content(response: Any) -> str:
    if isinstance(response, str):
        return response
    return getattr(response, "content", "") or ""


def _llm_repair_enabled(llm) -> bool:
    return llm is not None and settings.OUTPUT_GUARDRAIL_LLM_REPAIR_ENABLED


def get_report_format_repair_prompt(raw_text: str, issues: list[str]) -> str:
    return (
        "You are a strict formatter for a startup feasibility report that a web UI renders.\n"
        f"The draft below breaks the required format. Problems found: {'; '.join(issues)}.\n\n"
        "Rewrite it as ONE JSON object with exactly these keys and nothing else:\n"
        "{\n"
        '  "chain_of_thought": ["short reasoning step", "..."],\n'
        '  "idea_fit": "markdown text",\n'
        '  "competitors": "markdown text",\n'
        '  "opportunity": "markdown text",\n'
        '  "score": "NN/100",\n'
        '  "score_rationale": "2-4 sentences",\n'
        '  "targeting": "markdown text",\n'
        '  "next_step": "markdown text"\n'
        "}\n\n"
        "Rules:\n"
        "- Return raw JSON only: no code fences and no text before or after it.\n"
        "- Every value is a string, except chain_of_thought, which is an array of plain-text "
        "strings without numbering.\n"
        '- "score" is only an integer from 0 to 100 followed by "/100", e.g. "68/100".\n'
        '- Markdown inside values may use only "- " bullets, "1. " numbered items, "### " headings '
        "and **bold**. No tables, links, code, HTML or italics.\n"
        "- Keep the draft's facts, competitor names and recommendations. Do not invent new research; "
        "if the draft has nothing for a key, summarise what the rest of the draft implies for it.\n"
        "- If the draft has no score, infer one that matches its own assessment.\n\n"
        f"Draft:\n{raw_text[:MAX_REPAIR_INPUT_CHARS]}"
    )


def _llm_repair_report(text: str, issues: list[str], llm) -> dict[str, Any] | None:
    try:
        content = _extract_llm_content(llm.invoke(get_report_format_repair_prompt(text, issues)))
        data = parse_json_from_text(content, expected_type=dict)
    except Exception as exc:
        logger.warning("guardrail.report.llm_repair_failed error=%s", exc)
        return None
    report = normalize_report(data)
    return report if any(report[key] for key in REPORT_KEYS) else None


def get_question_rewrite_prompt(text: str, issues: list[str], *, kind: str) -> str:
    if kind == "engagement":
        shape = (
            "- Exactly one question, under 30 words, ending with a question mark.\n"
            "- Plain text only: no markdown, bullets, labels, quotes or preamble.\n"
        )
    else:
        shape = (
            "- Exactly one clarifying question ending with a question mark. At most one short "
            "sentence of context may come before it.\n"
            "- No report sections, headings, lists, labels, quotes or preamble.\n"
        )
    return (
        "You fix the format of a question a startup advisor asks a founder.\n"
        f"Problems found: {'; '.join(issues)}.\n\n"
        "Rewrite it so that it follows these rules:\n"
        f"{shape}"
        "- Keep the most important point of the original. Do not add new topics.\n"
        "- Return only the rewritten question.\n\n"
        f"Original:\n{text[:MAX_REPAIR_INPUT_CHARS]}"
    )


# ── Question rules ─────────────────────────────────────────────────────────────

_MESSAGE_KEYS = (
    "question",
    "clarifying_question",
    "engagement_question",
    "follow_up_question",
    "answer",
    "response",
    "reply",
    "message",
    "text",
    "content",
)
_PREAMBLE_RE = re.compile(
    r"^(?:(?:sure|certainly|of course|absolutely|okay|ok|alright)[!,.]+\s*"
    r"|here(?:'s| is| are)\b[^:\n?]{0,80}:\s*"
    r"|(?:\*\*|__)?\s*(?:(?:my|one|a|the)\s+)?(?:critical\s+|clarifying\s+|follow[- ]?up\s+|engagement\s+)*"
    r"question\s*\d*\s*(?:\*\*|__)?\s*[:\-–—]\s*(?:\*\*|__)?\s*"
    r"|q\s*[:.]\s*)",
    re.IGNORECASE,
)
_QUOTE_PAIRS = {'"': '"', "'": "'", "“": "”", "‘": "’"}


def _strip_wrapping_quotes(text: str) -> str:
    while len(text) >= 2 and _QUOTE_PAIRS.get(text[0]) == text[-1]:
        text = text[1:-1].strip()
    return text


def _unwrap_code_fence(text: str) -> str:
    fenced = re.fullmatch(r"```[A-Za-z]*\s*([\s\S]*?)\s*```", text.strip())
    return fenced.group(1).strip() if fenced else text.strip()


def _extract_message_text(raw: Any, *, strip_preamble: bool) -> str:
    """Unwrap JSON, code fences, quotes and chatty preambles around a message."""
    if isinstance(raw, dict):
        value: Any = raw
    else:
        text = _unwrap_code_fence(_extract_llm_content(raw))
        document = _load_json_document(text)
        value = text if document is None else document

    if isinstance(value, dict):
        value = next(
            (value[key] for key in _MESSAGE_KEYS if isinstance(value.get(key), str) and value[key].strip()),
            next((v for v in value.values() if isinstance(v, str) and v.strip()), ""),
        )
    elif isinstance(value, list):
        value = next((v for v in value if isinstance(v, str) and v.strip()), "")
    text = _unescape_newlines(str(value)).strip()

    if strip_preamble:
        for _ in range(3):
            stripped = _PREAMBLE_RE.sub("", text, count=1).strip()
            if stripped == text:
                break
            text = stripped
        text = _strip_wrapping_quotes(text)
        text = text[:1].upper() + text[1:]
    return text


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=\S)")


def question_issues(text: str, *, max_chars: int | None = None, max_words: int | None = None) -> list[str]:
    if not text.strip():
        return ["the question is empty"]
    issues = []
    question_count = len(re.findall(r"\?+", text))
    if question_count == 0:
        issues.append("it does not ask a question")
    elif question_count > 1:
        issues.append(f"it asks {question_count} questions instead of one")
    if re.search(r"^\s*(?:#{1,6}\s|---\s*$)", text, re.MULTILINE):
        issues.append("it contains report headings or sections")
    if max_chars and len(text) > max_chars:
        issues.append(f"it is longer than {max_chars} characters")
    if max_words and len(text.split()) > max_words:
        issues.append(f"it is longer than {max_words} words")
    return issues


def _truncate_at_sentence(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    boundary = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    if boundary > max_chars // 3:
        return cut[: boundary + 1].strip()
    return cut.rsplit(" ", 1)[0].rstrip(",;:") + "…"


def _rule_fix_question(text: str, *, keep_context: bool, max_chars: int) -> str:
    """Keep the first question (plus one lead-in sentence when allowed)."""
    without_headings = re.sub(r"^\s*#{1,6}\s.*$", "", text, flags=re.MULTILINE)
    sentences = _SENTENCE_SPLIT_RE.split(to_plain_text(without_headings))
    for index, sentence in enumerate(sentences):
        if sentence.rstrip().endswith("?"):
            lead = sentences[index - 1] if keep_context and index > 0 else ""
            if len(lead.split()) < 4:
                lead = ""
            return _truncate_at_sentence(f"{lead} {sentence}".strip(), max_chars)
    return _truncate_at_sentence(text, max_chars)


def _is_json_value(text: str) -> bool:
    try:
        json.loads(text)
    except ValueError:
        return False
    return True




def _guard_question(text: str, llm, *, kind: str) -> tuple[str, dict[str, Any]]:
    engagement = kind == "engagement"
    max_chars = 280 if engagement else CLARIFYING_MAX_CHARS
    max_words = ENGAGEMENT_MAX_WORDS if engagement else None
    clean = to_plain_text if engagement else sanitize_markdown

    question = clean(_extract_message_text(text, strip_preamble=True))
    issues = question_issues(question, max_chars=max_chars, max_words=max_words)
    repaired_by = "rules"
    llm_calls = 0

    if issues and question and _llm_repair_enabled(llm):
        llm_calls = 1
        try:
            rewritten = _extract_llm_content(llm.invoke(get_question_rewrite_prompt(question, issues, kind=kind)))
            candidate = clean(_extract_message_text(rewritten, strip_preamble=True))
        except Exception as exc:
            logger.warning("guardrail.%s_question.llm_rewrite_failed error=%s", kind, exc)
            candidate = ""
        if candidate and not question_issues(candidate, max_chars=max_chars, max_words=max_words):
            question, repaired_by = candidate, "llm"

    if repaired_by == "rules" and issues and question:
        question = _rule_fix_question(question, keep_context=not engagement, max_chars=max_chars)

    return question, {
        "issues": issues,
        "repaired_by": repaired_by,
        "llm_calls": llm_calls,
        "remaining": question_issues(question, max_chars=max_chars, max_words=max_words),
    }


# ── Run logging ────────────────────────────────────────────────────────────────
# One line per guard run, so container logs show every output was checked even
# when nothing needed fixing. Lines carry codes and sizes only, never user text.

_FORMAT_FINDINGS = (
    ("code_fence", re.compile(r"^\s*(?:```|~~~)", re.MULTILINE)),
    ("table", re.compile(r"^\s*\|.*\|\s*$", re.MULTILINE)),
    ("deep_heading", re.compile(r"^\s*#{4,6}", re.MULTILINE)),
    ("html", re.compile(r"<\s*/?\s*(?:br|p|div|span|ul|ol|li|b|strong|em|i|u|a|h[1-6]|table|tr|td|th)\b[^>]*>", re.IGNORECASE)),
    ("link", re.compile(r"\[[^\]]+\]\([^)\s]+\)")),
    ("inline_code", re.compile(r"`[^`\n]+`")),
    ("italic", re.compile(r"(?<![*\w])\*(?![\s*])[^*\n]+?(?<![\s*])\*(?![*\w])")),
    ("escaped_newline", _ESCAPED_NEWLINE_RE),
)
_WARNING_STATUSES = {"fallback", "incomplete", "default_used", "left_unchanged"}


def _raw_text(raw: Any) -> str:
    if isinstance(raw, str):
        return raw
    if isinstance(raw, (dict, list)):
        return json.dumps(raw, ensure_ascii=False)
    return _extract_llm_content(raw) or ""


def _string_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _string_values(item)]
    if isinstance(value, (list, tuple)):
        return [text for item in value for text in _string_values(item)]
    return []


def _format_findings(text: str) -> list[str]:
    return [name for name, pattern in _FORMAT_FINDINGS if pattern.search(text)]


def _message_findings(text: str, *, question: bool = False) -> list[str]:
    """What was wrong with a message before the rules cleaned it up."""
    findings = []
    inner = _unwrap_code_fence(text)
    if inner != text.strip():
        findings.append("code_fence")
    document = _load_json_document(inner)
    if isinstance(document, (dict, list)):
        findings.append("json_wrapped")
        inner = "\n".join(_string_values(document))
    elif isinstance(document, str):
        findings.append("quoted")
        inner = document
    if question:
        if _PREAMBLE_RE.match(inner.strip()):
            findings.append("preamble")
        if "quoted" not in findings and _strip_wrapping_quotes(inner.strip()) != inner.strip():
            findings.append("quoted")
    findings.extend(name for name in _format_findings(inner) if name not in findings)
    return findings


def _report_findings(text: str, source: str | None, data: dict | None, report: dict | None) -> list[str]:
    findings = []
    if _unwrap_code_fence(text) != text.strip():
        findings.append("code_fence")
    if source == "salvaged_json":
        findings.append("truncated_json")
    elif source == "markdown":
        findings.append("markdown_not_json")
    if data is not None:
        fields = _unwrap_report(data)
        if fields is not data:
            findings.append("wrapped_report")
        if source == "json" and any(key not in REPORT_KEYS for key in fields):
            findings.append("renamed_or_extra_keys")
        if any(
            isinstance(value, (dict, list, tuple))
            for key, value in fields.items()
            if _canonical_key(key) != "chain_of_thought"
        ):
            findings.append("structured_values")
        raw_score = next((value for key, value in fields.items() if _canonical_key(key) == "score"), None)
        if report and not _is_empty(raw_score) and str(raw_score).strip() != report["score"]:
            findings.append("score_normalized")
        text = "\n".join(_string_values(fields))
    findings.extend(name for name in _format_findings(text) if name not in findings)
    return findings


def _run_status(*, changed: bool, issues: list[str], remaining: list[str], repaired_by: str) -> str:
    if repaired_by in ("fallback", "default"):
        return "fallback" if repaired_by == "fallback" else "default_used"
    if remaining:
        return "incomplete"
    if repaired_by == "llm":
        return "llm_repaired"
    if changed or issues:
        return "rules_fixed"
    return "ok"


def _log_guard_run(
    guard: str,
    *,
    status: str,
    started: float,
    conversation_id: str | None,
    chars_in: int,
    chars_out: int,
    findings: list[str] | None = None,
    issues: list[str] | None = None,
    remaining: list[str] | None = None,
    llm_calls: int = 0,
    **extra: Any,
) -> None:
    fields = {
        "status": status,
        "conversation_id": conversation_id or "-",
        "fixes": list(findings or []),
        "issues": list(issues or []),
        "remaining": list(remaining or []),
        "llm_calls": llm_calls,
        "chars_in": chars_in,
        "chars_out": chars_out,
        **extra,
        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
    }
    message = f"guardrail.{guard} " + " ".join(
        f"{key}={json.dumps(value) if isinstance(value, list) else value}" for key, value in fields.items()
    )
    level = logging.WARNING if status in _WARNING_STATUSES else logging.INFO
    logger.log(level, message, extra={"event": f"guardrail.{guard}", "guard": guard, **fields})


# ── Public guards ──────────────────────────────────────────────────────────────

def guard_feasibility_report(raw: Any, llm=None, *, conversation_id: str | None = None) -> str:
    """Return the report as the exact JSON object the UI renders."""
    started = time.perf_counter()
    text = _raw_text(raw)

    report, source, data = _rule_based_report(text)
    findings = _report_findings(text, source, data, report)
    issues = report_issues(report)
    repaired_by = "rules"
    llm_calls = 0

    if issues and text.strip() and _llm_repair_enabled(llm):
        llm_calls = 1
        repaired = _llm_repair_report(text, issues, llm)
        if repaired:
            report = _merge_reports(report, repaired)
            repaired_by = "llm"

    if report is None:
        report = _fallback_report(text)
        repaired_by = "fallback"

    output = json.dumps(report, ensure_ascii=False)
    remaining = report_issues(report)
    _log_guard_run(
        "report",
        status=_run_status(changed=bool(findings), issues=issues, remaining=remaining, repaired_by=repaired_by),
        started=started,
        conversation_id=conversation_id,
        chars_in=len(text),
        chars_out=len(output),
        findings=findings,
        issues=issues,
        remaining=remaining,
        llm_calls=llm_calls,
        source=source or "none",
    )
    return output


def _guard_and_log_question(raw: Any, llm, *, kind: str, conversation_id: str | None) -> tuple[str, dict]:
    started = time.perf_counter()
    text = _raw_text(raw)
    question, meta = _guard_question(text, llm, kind=kind)
    if kind == "clarifying" and (not question or _is_json_value(question)):
        question = DEFAULT_CLARIFYING_QUESTION
        meta["repaired_by"] = "default"
    _log_guard_run(
        f"{kind}_question",
        status=_run_status(
            changed=question != text.strip(),
            issues=meta["issues"],
            remaining=meta["remaining"] if meta["repaired_by"] != "default" else [],
            repaired_by=meta["repaired_by"],
        ),
        started=started,
        conversation_id=conversation_id,
        chars_in=len(text),
        chars_out=len(question),
        findings=_message_findings(text, question=True),
        issues=meta["issues"],
        remaining=meta["remaining"],
        llm_calls=meta["llm_calls"],
    )
    return question, meta


def guard_clarifying_question(raw: Any, llm=None, *, conversation_id: str | None = None) -> str:
    """One clarifying question that the UI never mistakes for a report."""
    return _guard_and_log_question(raw, llm, kind="clarifying", conversation_id=conversation_id)[0]


def guard_engagement_question(raw: Any, llm=None, *, conversation_id: str | None = None) -> str:
    """One short plain-text question, or "" when nothing usable is left."""
    return _guard_and_log_question(raw, llm, kind="engagement", conversation_id=conversation_id)[0]


def _clean_markdown_answer(text: str) -> str:
    document = _load_json_document(text)
    if isinstance(document, dict):
        report = normalize_report(document)
        if sum(1 for field in REQUIRED_REPORT_FIELDS if report[field]) >= 3:
            return report_to_markdown(report)
        message = _extract_message_text(document, strip_preamble=False)
        return sanitize_markdown(message or _structured_to_markdown(document))
    if isinstance(document, list):
        return sanitize_markdown(_structured_to_markdown(document))
    return sanitize_markdown(_extract_message_text(text, strip_preamble=False))


def guard_markdown_answer(raw: Any, *, kind: str = "markdown_answer", conversation_id: str | None = None) -> str:
    """QA answers and advisor replies, rewritten into the UI's markdown subset."""
    started = time.perf_counter()
    text = _raw_text(raw)
    answer = _clean_markdown_answer(text)
    _log_guard_run(
        kind,
        status="rules_fixed" if answer != text.strip() else "ok",
        started=started,
        conversation_id=conversation_id,
        chars_in=len(text),
        chars_out=len(answer),
        findings=_message_findings(text),
    )
    return answer


def guard_qa_history(items: list | None, *, conversation_id: str | None = None) -> list:
    """Clean stored QA answers on read; logs one summary line instead of one per answer."""
    started = time.perf_counter()
    cleaned, changed, findings = [], 0, []
    for item in items or []:
        if isinstance(item, dict) and isinstance(item.get("a"), str) and item["a"]:
            answer = _clean_markdown_answer(item["a"])
            if answer != item["a"].strip():
                changed += 1
                findings.extend(name for name in _message_findings(item["a"]) if name not in findings)
            item = {**item, "a": answer}
        cleaned.append(item)
    _log_guard_run(
        "qa_history",
        status="rules_fixed" if changed else "ok",
        started=started,
        conversation_id=conversation_id,
        chars_in=sum(len(str(item.get("a", ""))) for item in items or [] if isinstance(item, dict)),
        chars_out=sum(len(str(item.get("a", ""))) for item in cleaned if isinstance(item, dict)),
        findings=findings,
        items=len(cleaned),
        changed=changed,
    )
    return cleaned


def guard_stored_analysis(
    analysis: str | None,
    *,
    is_first_turn: bool,
    conversation_id: str | None = None,
) -> str | None:
    """Rule-only pass (no LLM calls) for analysis read back from the database."""
    if not analysis or not analysis.strip():
        return analysis
    started = time.perf_counter()
    report, source, data = _rule_based_report(analysis)
    if report is None and is_first_turn:
        return guard_clarifying_question(analysis, conversation_id=conversation_id)

    output = json.dumps(report, ensure_ascii=False) if report is not None else analysis
    findings = _report_findings(analysis, source, data, report) if report is not None else []
    if report is None:
        status = "left_unchanged"
    else:
        status = "rules_fixed" if output != analysis.strip() else "ok"
    _log_guard_run(
        "stored_analysis",
        status=status,
        started=started,
        conversation_id=conversation_id,
        chars_in=len(analysis),
        chars_out=len(output),
        findings=findings,
        remaining=report_issues(report) if report is not None else [],
        source=source or "none",
    )
    return output
