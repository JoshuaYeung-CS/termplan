"""The extraction agent: Nemotron reads a syllabus, the app checks every claim, and the model
repairs its own output until it passes schema, grounding and calendar checks."""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Any, Optional

from pydantic import BaseModel, Field, ValidationError

from .llm import ChatClient, LLMError
from .schema import (
    KINDS, CourseExtraction, ExtractedItem, Item, UndatedItem, extraction_json_schema, make_item_id,
)
from .textutil import PayloadError, parse_json_payload, quote_in_source

log = logging.getLogger("termplan.agent")

MAX_SOURCE_CHARS = 60_000
EXTRACT_TAG = "TERMPLAN-EXTRACT v1"
COACH_TAG = "TERMPLAN-COACH v1"


def _system_prompt(term_start: Optional[date], term_end: Optional[date]) -> str:
    schema = json.dumps(extraction_json_schema(), separators=(",", ":"))
    term = ""
    if term_start:
        term += f"The term starts on {term_start.isoformat()} ({term_start.strftime('%A')}). "
        term += "If the syllabus gives dates as 'Week N, <weekday>', Week 1 is the week containing the term start date. "
    if term_end:
        term += f"The term (including finals) ends on {term_end.isoformat()}. "
    return f"""[{EXTRACT_TAG}]
You extract every graded deadline, exam, quiz, lab report, project milestone and assigned reading
from a university course syllabus. Students will import your output into their calendar, so
precision matters more than coverage.

Rules:
1. One item per dated event. Recurring work that the syllabus lists with explicit dates becomes one item per date.
   Recurring work with no dates (for example "weekly quizzes") is not an item.
2. due_date is the real calendar date in ISO format YYYY-MM-DD. {term}Assume the year shown in the syllabus.
3. due_time is 24-hour HH:MM when the syllabus states a time (for an exam, its start time), otherwise null.
4. kind is one of: {", ".join(KINDS)}.
5. weight_percent is the share of the course grade for this single item when the syllabus says it or it
   can be computed (for example "4 x 5%" gives 5 each); otherwise null.
6. est_hours is your estimate of the hours a typical student needs to prepare or complete the item
   (exam study time, writing time, reading time). Give a one-sentence hours_rationale.
7. source_quote is copied VERBATIM from the syllabus: the shortest exact span (under 200 characters) that
   states this item's date. It is checked character for character against the source.
8. Events with no determinable date (TBA, to be announced, to be determined) go in "undated", never in "items".
9. Reply with ONE JSON object that matches this JSON Schema, and nothing else:
{schema}"""


def _user_prompt(label: str, text: str) -> str:
    return f"Syllabus file: {label}\n\n<<<SYLLABUS\n{text}\nSYLLABUS>>>"


class AttemptLog(BaseModel):
    n: int
    mode: str = ""
    finish_reason: Optional[str] = None
    latency_s: float = 0.0
    errors: list[str] = Field(default_factory=list)


class CourseResult(BaseModel):
    label: str
    course_code: str = ""
    course_title: str = ""
    items: list[Item] = Field(default_factory=list)
    undated: list[UndatedItem] = Field(default_factory=list)
    attempts: list[AttemptLog] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error: Optional[str] = None
    model: str = ""


class _Checked(BaseModel):
    course_code: str = ""
    course_title: str = ""
    items: list[ExtractedItem] = Field(default_factory=list)
    undated: list[UndatedItem] = Field(default_factory=list)
    schema_errors: list[str] = Field(default_factory=list)
    grounding_errors: list[str] = Field(default_factory=list)
    calendar_errors: list[str] = Field(default_factory=list)
    ungrounded: set[int] = Field(default_factory=set)
    off_calendar: set[int] = Field(default_factory=set)

    @property
    def all_errors(self) -> list[str]:
        return self.schema_errors + self.grounding_errors + self.calendar_errors


def _fmt_validation(prefix: str, exc: ValidationError) -> list[str]:
    out = []
    for e in exc.errors():
        loc = ".".join(str(p) for p in e["loc"])
        out.append(f"{prefix}{'.' + loc if loc else ''}: {e['msg']}")
    return out


def check_payload(
    data: dict,
    source: str,
    term_start: Optional[date],
    term_end: Optional[date],
) -> _Checked:
    """Validate a parsed payload item by item so one bad item does not discard the rest."""
    checked = _Checked()
    top = {k: data.get(k) for k in ("course_code", "course_title")}
    for key, value in top.items():
        if not isinstance(value, str) or len(value.strip()) < 2:
            checked.schema_errors.append(f"{key}: required non-empty string")
        else:
            setattr(checked, key, value.strip())

    raw_items = data.get("items")
    if not isinstance(raw_items, list):
        checked.schema_errors.append("items: required array")
        raw_items = []
    for i, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            checked.schema_errors.append(f"items[{i}]: must be an object")
            continue
        try:
            item = ExtractedItem.model_validate(raw)
        except ValidationError as exc:
            checked.schema_errors.extend(_fmt_validation(f"items[{i}]", exc))
            continue
        idx = len(checked.items)
        checked.items.append(item)
        if not quote_in_source(item.source_quote, source):
            checked.ungrounded.add(idx)
            checked.grounding_errors.append(
                f"items[{i}] ({item.title}): source_quote is not a verbatim excerpt of the syllabus: "
                f"{item.source_quote!r}"
            )
        lo = term_start - timedelta(days=14) if term_start else None
        hi = term_end + timedelta(days=14) if term_end else None
        if (lo and item.due_date < lo) or (hi and item.due_date > hi):
            checked.off_calendar.add(idx)
            checked.calendar_errors.append(
                f"items[{i}] ({item.title}): due_date {item.due_date} is outside the term "
                f"({term_start} to {term_end}); recheck the year and week arithmetic"
            )

    for i, raw in enumerate(data.get("undated") or []):
        try:
            checked.undated.append(UndatedItem.model_validate(raw))
        except ValidationError as exc:
            checked.schema_errors.extend(_fmt_validation(f"undated[{i}]", exc))
    return checked


def _repair_message(errors: list[str]) -> str:
    shown = errors[:25]
    more = f"\n(and {len(errors) - len(shown)} more)" if len(errors) > len(shown) else ""
    bullet = "\n".join(f"- {e}" for e in shown)
    return (
        "Your previous reply failed validation:\n"
        f"{bullet}{more}\n\n"
        "Return the COMPLETE corrected JSON object (every item, not only the fixed ones). "
        "Copy each source_quote exactly from the syllabus. JSON only, no commentary."
    )


def extract_course(
    client: ChatClient,
    model: str,
    text: str,
    *,
    label: str,
    term_start: Optional[date] = None,
    term_end: Optional[date] = None,
    max_attempts: int = 3,
) -> CourseResult:
    result = CourseResult(label=label, model=model)
    source = text[:MAX_SOURCE_CHARS]
    if len(text) > MAX_SOURCE_CHARS:
        result.warnings.append(f"Syllabus truncated to the first {MAX_SOURCE_CHARS} characters.")
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _system_prompt(term_start, term_end)},
        {"role": "user", "content": _user_prompt(label, source)},
    ]
    schema = extraction_json_schema()
    max_tokens = 8192  # reasoning tokens count toward the limit
    best: Optional[_Checked] = None

    for n in range(1, max_attempts + 1):
        attempt = AttemptLog(n=n)
        result.attempts.append(attempt)
        try:
            completion = client.complete(
                model=model, messages=messages, schema=schema, max_tokens=max_tokens
            )
        except LLMError as exc:
            attempt.errors.append(str(exc))
            result.error = str(exc)
            break
        attempt.mode = completion.mode
        attempt.finish_reason = completion.finish_reason
        attempt.latency_s = round(completion.latency_s, 3)

        errors: list[str]
        try:
            data = parse_json_payload(completion.text)
        except PayloadError as exc:
            errors = [str(exc)]
            if completion.finish_reason == "length":
                errors.insert(0, "The reply was cut off by the token limit; keep source_quote and hours_rationale short.")
                max_tokens = min(max_tokens * 2, 32768)
            checked = None
        else:
            checked = check_payload(data, source, term_start, term_end)
            errors = checked.all_errors
            if best is None or _score(checked) > _score(best):
                best = checked
        attempt.errors = errors
        if not errors:
            break
        log.info("%s attempt %d: %d problem(s); asking for a repair", label, n, len(errors))
        messages.append({"role": "assistant", "content": completion.text or ""})
        messages.append({"role": "user", "content": _repair_message(errors)})

    if best is None:
        result.error = result.error or "Could not get valid JSON from the model."
        return result

    result.course_code = best.course_code or label
    result.course_title = best.course_title or label
    result.undated = best.undated
    seen: set[str] = set()
    for idx, ex in enumerate(best.items):
        item_id = make_item_id(result.course_code, ex.title, ex.due_date)
        if item_id in seen:
            continue
        seen.add(item_id)
        warnings = []
        if idx in best.ungrounded:
            warnings.append("Quote not found verbatim in the syllabus; check this date by hand.")
        if idx in best.off_calendar:
            warnings.append("Date falls outside the term window.")
        result.items.append(Item(
            **ex.model_dump(), id=item_id, course=result.course_code,
            verified=idx not in best.ungrounded and idx not in best.off_calendar,
            warnings=warnings,
        ))
    if best.schema_errors:
        result.warnings.append(
            f"{len(best.schema_errors)} malformed field(s) were dropped after {len(result.attempts)} attempt(s)."
        )
    result.items.sort(key=lambda it: (it.due_date, it.due_time or "99:99"))
    return result


def _score(c: _Checked) -> tuple[int, int]:
    return (len(c.items) - len(c.ungrounded) - len(c.off_calendar), -len(c.all_errors))


# ---------------------------------------------------------------- coach


class CoachNotes(BaseModel):
    headline: str = Field(min_length=4, max_length=200)
    tips: list[str] = Field(min_length=1, max_length=5)


def coach_notes(client: ChatClient, model: str, summary: dict) -> Optional[CoachNotes]:
    """Second Nemotron pass: short, concrete advice grounded in the computed plan."""
    schema = CoachNotes.model_json_schema()
    messages = [
        {"role": "system", "content": (
            f"[{COACH_TAG}]\nYou are a blunt, practical study coach. You get a computed term plan "
            "(crunch weeks, conflicts, upcoming deadlines). Write one headline and 3 to 5 tips. "
            "Every tip must name a specific course item and date from the input. No generic advice. "
            f"Reply with one JSON object matching this schema: {json.dumps(schema, separators=(',', ':'))}"
        )},
        {"role": "user", "content": json.dumps(summary, default=str)},
    ]
    for _ in range(2):
        try:
            completion = client.complete(model=model, messages=messages, schema=schema, max_tokens=1200)
            return CoachNotes.model_validate(parse_json_payload(completion.text))
        except (PayloadError, ValidationError) as exc:
            messages.append({"role": "assistant", "content": completion.text or ""})
            messages.append({"role": "user", "content": f"Invalid: {exc}. Return the JSON object only."})
        except LLMError as exc:
            log.warning("coach step skipped: %s", exc)
            return None
    return None
