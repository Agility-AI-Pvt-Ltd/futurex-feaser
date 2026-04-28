from __future__ import annotations

import re
from pathlib import Path


TIMESTAMP_RE = re.compile(
    r"^(?:\d{2}:)?\d{2}:\d{2}\.\d{3}\s+-->\s+(?:\d{2}:)?\d{2}:\d{2}\.\d{3}"
)
TAG_RE = re.compile(r"<[^>]+>")
VOICE_RE = re.compile(r"^<v\s+[^>]+>", re.IGNORECASE)
PROGRESS_RE = re.compile(r"^(?:batches|ches):\s*\d+%.*$", re.IGNORECASE)
SPEAKER_RE = re.compile(r"^([A-Z][A-Z\s.'-]{1,80}):\s*")


def is_supported_transcript_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in {".txt", ".vtt"}


def transcript_file_type(filename: str) -> str:
    return Path(filename).suffix.lower().lstrip(".")


def convert_transcript_to_text(filename: str, raw_text: str) -> str:
    file_type = transcript_file_type(filename)
    if file_type == "txt":
        return clean_transcript_text(raw_text)
    if file_type == "vtt":
        return vtt_to_text(raw_text)
    raise ValueError("Only .txt and .vtt transcript files are supported.")


def vtt_to_text(raw_vtt: str) -> str:
    lines = raw_vtt.replace("\ufeff", "").splitlines()
    transcript_lines: list[str] = []
    previous_line = ""
    skip_note_block = False

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            skip_note_block = False
            continue

        upper_line = line.upper()
        if upper_line.startswith("WEBVTT") or upper_line.startswith(
            ("STYLE", "REGION", "X-TIMESTAMP-MAP")
        ):
            skip_note_block = upper_line.startswith(("STYLE", "REGION"))
            continue
        if upper_line.startswith("NOTE"):
            skip_note_block = True
            continue
        if skip_note_block or TIMESTAMP_RE.match(line) or "-->" in line or line.isdigit():
            continue

        cleaned = _clean_line(line)
        if not cleaned or cleaned == previous_line:
            continue
        transcript_lines.append(cleaned)
        previous_line = cleaned

    return clean_transcript_text("\n".join(transcript_lines))


def clean_transcript_text(raw_text: str) -> str:
    lines = raw_text.replace("\ufeff", "").splitlines()
    cleaned_lines: list[str] = []
    previous_line = ""

    for raw_line in lines:
        cleaned = _clean_line(raw_line)
        if not cleaned or cleaned == previous_line:
            continue
        cleaned_lines.append(cleaned)
        previous_line = cleaned

    return "\n".join(cleaned_lines).strip()


def _clean_line(raw_line: str) -> str:
    line = raw_line.strip()
    if not line or line.isdigit() or TIMESTAMP_RE.match(line) or "-->" in line:
        return ""
    if PROGRESS_RE.match(line):
        return ""

    cleaned = VOICE_RE.sub("", line)
    cleaned = TAG_RE.sub("", cleaned)
    cleaned = SPEAKER_RE.sub(r"\1: ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned
