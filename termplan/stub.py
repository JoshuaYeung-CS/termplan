"""A local OpenAI-compatible stub of the Token Factory chat API, for tests and offline runs.

It replays scripted replies for the sample syllabi (including deliberately broken ones that
exercise the repair loop) and falls back to a crude line scanner for any other syllabus.
It never calls the network.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from datetime import date
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from .agent import COACH_TAG, EXTRACT_TAG

STUB_DIR = Path(__file__).with_name("stubdata")

_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], start=1)}
_DATE_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\.?\s+(\d{1,2})\b", re.I)
_KIND_WORDS = [
    ("exam", ("exam", "midterm", "final")), ("quiz", ("quiz",)), ("lab", ("lab",)),
    ("project", ("project", "proposal")), ("paper", ("essay", "paper", "report")),
    ("reading", ("read", "chapter")), ("presentation", ("presentation", "poster")),
    ("assignment", ("problem set", "homework", "assignment", "due")),
]
_DEFAULT_HOURS = {"exam": 10, "quiz": 2, "lab": 4, "project": 10, "paper": 8, "reading": 2,
                  "presentation": 5, "assignment": 4, "other": 3}


def load_scripts() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(STUB_DIR.glob("*.json"))]


def _render(kind: str, extraction: dict) -> tuple[str, str]:
    """Turn a correct extraction into the reply for one scripted attempt."""
    clean = json.dumps(extraction, indent=1)
    if kind == "clean":
        return clean, "stop"
    if kind == "think_then_clean":
        return ("<think>The syllabus lists dated response papers, two essays, a quiz and a "
                "take-home final. Readings have discussion dates.</think>\n" + clean), "stop"
    if kind == "fenced_trailing_comma":
        broken = clean.rstrip()[:-1].rstrip() + ",\n}"
        return "Here is the extraction:\n```json\n" + broken + "\n```", "stop"
    if kind == "paraphrase_and_bad_time":
        bad = json.loads(clean)
        for it in bad["items"]:
            if it["title"].startswith("Lab 3"):
                it["source_quote"] = "Lab three report is due on the Friday of week nine"
            if it["title"] == "Field study draft":
                it["due_time"] = "5 pm"
        return json.dumps(bad), "stop"
    if kind == "wrong_year":
        bad = json.loads(clean)
        for it in bad["items"]:
            it["due_date"] = "2025" + it["due_date"][4:]
        return json.dumps(bad), "stop"
    if kind == "not_json":
        return "I could not find any deadlines in this document.", "stop"
    if kind == "truncated":
        return clean[: len(clean) // 2], "length"
    raise ValueError(f"unknown script step {kind}")


def scan_syllabus(text: str, year: int) -> dict:
    """Very rough fallback: one item per line that names a month and day."""
    code = re.search(r"\b([A-Z]{2,5})\s?(\d{3,4}[A-Z]?)\b", text)
    course_code = f"{code.group(1)} {code.group(2)}" if code else "COURSE"
    first_line = next((ln.strip() for ln in text.splitlines() if ln.strip()), course_code)
    items, seen = [], set()
    for line in text.splitlines():
        m = _DATE_RE.search(line)
        if not m:
            continue
        try:
            due = date(year, _MONTHS[m.group(1).lower()], int(m.group(2)))
        except ValueError:
            continue
        low = line.lower()
        kind = next((k for k, words in _KIND_WORDS if any(w in low for w in words)), "other")
        quote = line.strip()[:200]
        title = re.sub(r"\s+", " ", re.split(r"\s+(?:--|-|:|is due|due)\s+", line.strip())[0])[:120]
        if len(quote) < 8 or (title, due) in seen:
            continue
        seen.add((title, due))
        items.append({
            "title": title if len(title) >= 2 else kind.title(), "kind": kind,
            "due_date": due.isoformat(), "due_time": None, "weight_percent": None,
            "est_hours": _DEFAULT_HOURS[kind], "hours_rationale": "Default estimate for this kind of item.",
            "source_quote": quote,
        })
    return {"course_code": course_code, "course_title": first_line[:150], "items": items, "undated": []}


def _coach_reply(summary: dict) -> dict:
    conflicts = summary.get("conflicts") or []
    upcoming = summary.get("upcoming_3_weeks") or []
    starts = summary.get("start_by") or []
    headline = conflicts[0]["message"] if conflicts else "No clashes in the next three weeks."
    tips = []
    for s in starts[:2]:
        if s.get("unscheduled_hours"):
            tips.append(f"{s['course']} {s['title']} is short {s['unscheduled_hours']} h in your budget; "
                        "find extra time this week or ask for an extension early.")
        elif s.get("front_loaded"):
            tips.append(f"Start {s['course']} {s['title']} by {s['start_by']}; it is due in a crunch week.")
    big = sorted(upcoming, key=lambda u: -(u.get("est_hours") or 0))[:2]
    for u in big:
        tips.append(f"Block {u['est_hours']} hours for {u['course']} {u['title']} before {u['due']}.")
    if not tips:
        tips.append("Nothing urgent: use this week to get ahead on readings.")
    return {"headline": headline[:200], "tips": tips[:5]}


def _completion(model: str, content: str, finish: str) -> dict:
    return {
        "id": f"chatcmpl-stub-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                     "finish_reason": finish}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def create_stub_app(
    *,
    reject_json_schema: bool = False,
    scripts: Optional[list[dict]] = None,
    models: tuple[str, ...] = ("nvidia/Nemotron-3_5-Lightning",),
) -> FastAPI:
    app = FastAPI(title="Token Factory stub")
    app.state.scripts = scripts if scripts is not None else load_scripts()
    app.state.requests = []

    @app.get("/v1/models")
    def list_models() -> dict:
        return {"object": "list", "data": [
            {"id": m, "object": "model", "created": 0, "owned_by": "nvidia"} for m in models]}

    @app.post("/v1/chat/completions")
    async def chat(request: Request) -> Any:
        body = await request.json()
        app.state.requests.append(body)
        rf = (body.get("response_format") or {}).get("type")
        if reject_json_schema and rf == "json_schema":
            return JSONResponse(status_code=400, content={"detail": "json_schema is not supported for this model"})
        messages = body.get("messages") or []
        if not messages:
            raise HTTPException(400, "messages required")
        system = messages[0].get("content", "")
        model = body.get("model", "stub")
        attempt = sum(1 for m in messages if m.get("role") == "assistant")

        if COACH_TAG in system:
            summary = json.loads(messages[1]["content"])
            return _completion(model, json.dumps(_coach_reply(summary)), "stop")
        if EXTRACT_TAG not in system:
            return _completion(model, "{}", "stop")

        user = messages[1].get("content", "")
        for spec in app.state.scripts:
            if spec["match"] in user:
                steps = spec["script"]
                step = steps[min(attempt, len(steps) - 1)]
                content, finish = _render(step, spec["extraction"])
                return _completion(model, content, finish)
        year_m = re.search(r"term starts on (\d{4})", system)
        year = int(year_m.group(1)) if year_m else date.today().year
        return _completion(model, json.dumps(scan_syllabus(user, year)), "stop")

    return app
