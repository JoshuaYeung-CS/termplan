"""Text helpers: grounding checks for source quotes and lenient JSON payload parsing."""

from __future__ import annotations

import json
import re
import unicodedata

_THINK_RE = re.compile(r"<think>.*?</think>", re.S | re.I)
_FENCE_RE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.S)

_TRANSLATE = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "―": "-",
    "−": "-", " ": " ", " ": " ", " ": " ", "…": "...",
}
_DROP = {"­", "​", "‌", "‍", "﻿"}


def normalize(text: str) -> str:
    """Normalize for quote matching: unicode forms, quotes, dashes, hyphenation, whitespace, case."""
    text = unicodedata.normalize("NFKC", text)
    text = "".join(_TRANSLATE.get(ch, ch) for ch in text if ch not in _DROP)
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)  # words split across lines by a PDF
    text = re.sub(r"-{2,}", "-", text)  # "--" used as a dash in plain-text syllabi
    text = re.sub(r"\s*-\s*", "-", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def quote_in_source(quote: str, source: str) -> bool:
    """True if the quote appears in the source after normalization.

    Leading/trailing ellipses and punctuation are ignored. A quote that the model stitched
    together from two nearby fragments with "..." passes if every fragment is present.
    """
    norm_source = normalize(source)
    parts = [p.strip(" .,;:\"'") for p in normalize(quote).split("...")]
    parts = [p for p in parts if p]
    if not parts:
        return False
    if sum(len(p) for p in parts) < 6:
        return False
    return all(p in norm_source for p in parts)


def strip_reasoning(text: str) -> str:
    """Remove <think>...</think> blocks; also drop an unterminated leading think block."""
    text = _THINK_RE.sub("", text)
    lowered = text.lower()
    if "<think>" in lowered and "</think>" not in lowered:
        text = text[: lowered.index("<think>")]
    if "</think>" in lowered:
        text = text[lowered.rindex("</think>") + len("</think>"):]
    return text.strip()


class PayloadError(ValueError):
    pass


def parse_json_payload(raw: str) -> dict:
    """Pull the JSON object out of a model reply.

    Handles reasoning blocks, markdown fences and prose around the object. Raises PayloadError
    with a message that is sent back to the model during repair.
    """
    if raw is None or not raw.strip():
        raise PayloadError("The reply was empty. Return the JSON object only.")
    text = strip_reasoning(raw)
    fence = _FENCE_RE.search(text)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise PayloadError("No JSON object found in the reply. Return one JSON object only.")
    candidate = text[start : end + 1]
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise PayloadError(
            f"The reply is not valid JSON ({exc.msg} at line {exc.lineno}, column {exc.colno}). "
            "Check for trailing commas, unquoted keys or comments."
        ) from exc
    if not isinstance(value, dict):
        raise PayloadError("The top-level JSON value must be an object.")
    return value
