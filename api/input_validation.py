from __future__ import annotations

import re

from fastapi import HTTPException

INVALID_INPUT_MESSAGE = "Please enter correct input."

_COMMON_GIBBERISH_TOKENS = {
    "abc",
    "abcd",
    "asdf",
    "asdfg",
    "asdfgh",
    "hjk",
    "hjkl",
    "qwe",
    "qwer",
    "qwerty",
    "sdf",
    "sdfg",
    "xyz",
    "zxc",
    "zxcv",
}
_KEYBOARD_ROWS = ("qwertyuiop", "asdfghjkl", "zxcvbnm")


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _is_sequential_letters(token: str) -> bool:
    if len(token) < 3:
        return False

    alphabet = "abcdefghijklmnopqrstuvwxyz"
    return token in alphabet or token in alphabet[::-1]


def _is_keyboard_mash(token: str) -> bool:
    if len(token) < 3:
        return False

    for row in _KEYBOARD_ROWS:
        if token in row or token in row[::-1]:
            return True
    return False


def _is_repeated_pattern(token: str) -> bool:
    return re.fullmatch(r"(.{2,4})\1{1,}", token) is not None


def _looks_like_gibberish(token: str) -> bool:
    if len(token) <= 1:
        return True
    if len(set(token)) == 1:
        return True
    if token in _COMMON_GIBBERISH_TOKENS:
        return True
    if _is_sequential_letters(token) or _is_keyboard_mash(token):
        return True
    if _is_repeated_pattern(token):
        return True
    return False


def is_meaningful_text(value: str) -> bool:
    text = _normalize_text(value)
    if not text:
        return False
    if not re.search(r"[A-Za-z]", text):
        return False

    tokens = re.findall(r"[A-Za-z0-9]+", text.lower())
    if not tokens:
        return False

    alpha_tokens = [re.sub(r"[^a-z]", "", token) for token in tokens]
    alpha_tokens = [token for token in alpha_tokens if token]
    if not alpha_tokens:
        return False

    if all(len(token) == 1 for token in alpha_tokens):
        return False

    if len(tokens) == 1 and len(alpha_tokens) == 1 and _looks_like_gibberish(alpha_tokens[0]):
        return False

    return True


def ensure_meaningful_text(value: str, *, detail: str = INVALID_INPUT_MESSAGE) -> str:
    text = _normalize_text(value)
    if not is_meaningful_text(text):
        raise HTTPException(status_code=400, detail=detail)
    return text
