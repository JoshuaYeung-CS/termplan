"""End-to-end pipeline: syllabi in, verified items + conflicts + plan + coach notes out."""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from typing import Optional

from pydantic import BaseModel, Field

from .agent import CoachNotes, CourseResult, coach_notes, extract_course
from .conflicts import Conflict, find_conflicts
from .llm import ChatClient
from .planner import Plan, build_plan, next_seven_days
from .schema import Item

log = logging.getLogger("termplan.service")


class SyllabusInput(BaseModel):
    name: str
    text: str


class PlanRequest(BaseModel):
    syllabi: list[SyllabusInput] = Field(min_length=1, max_length=8)
    term_start: Optional[date] = None
    term_end: Optional[date] = None
    weekly_hours: float = Field(default=20.0, ge=3, le=80)
    today: Optional[date] = None
    front_load: bool = True
    coach: bool = True


class PlanResult(BaseModel):
    today: date
    model: str
    mode: str
    elapsed_s: float
    model_calls: int
    courses: list[CourseResult]
    items: list[Item]
    conflicts: list[Conflict]
    plan: Plan
    next7: dict
    coach: Optional[CoachNotes] = None


def run_pipeline(
    req: PlanRequest,
    client: ChatClient,
    *,
    model: str,
    coach_model: str,
    mode: str,
    max_attempts: int = 3,
) -> PlanResult:
    t0 = time.perf_counter()
    today = req.today or date.today()
    calls_before = client.calls

    def _one(s: SyllabusInput) -> CourseResult:
        return extract_course(
            client, model, s.text, label=s.name, term_start=req.term_start,
            term_end=req.term_end, max_attempts=max_attempts,
        )

    with ThreadPoolExecutor(max_workers=min(4, len(req.syllabi))) as pool:
        courses = list(pool.map(_one, req.syllabi))

    items: list[Item] = []
    seen: set[str] = set()
    for c in courses:
        for it in c.items:
            if it.id not in seen:
                seen.add(it.id)
                items.append(it)
    items.sort(key=lambda i: (i.due_date, i.due_time or "99:99", i.course))

    conflicts = [c for c in find_conflicts(items, req.weekly_hours) if c.end >= today]
    plan = build_plan(items, today, req.weekly_hours, front_load=req.front_load)
    next7 = next_seven_days(items, plan, today)

    notes = None
    if req.coach and items:
        notes = coach_notes(client, coach_model, _coach_summary(items, conflicts, plan, today))

    return PlanResult(
        today=today, model=model, mode=mode,
        elapsed_s=round(time.perf_counter() - t0, 2),
        model_calls=client.calls - calls_before,
        courses=courses, items=items, conflicts=conflicts, plan=plan, next7=next7, coach=notes,
    )


def _coach_summary(items: list[Item], conflicts: list[Conflict], plan: Plan, today: date) -> dict:
    by_id = {i.id: i for i in items}
    soon = [i for i in items if today <= i.due_date <= today + timedelta(days=21)]
    return {
        "today": today,
        "weekly_hours_budget": plan.weekly_hours,
        "upcoming_3_weeks": [
            {"course": i.course, "title": i.title, "kind": i.kind, "due": i.due_date,
             "weight_percent": i.weight_percent, "est_hours": i.est_hours}
            for i in soon
        ],
        "conflicts": [{"kind": c.kind, "message": c.message} for c in conflicts if c.end >= today][:8],
        "start_by": [
            {"course": by_id[s.item_id].course, "title": by_id[s.item_id].title,
             "start_by": s.start_by, "front_loaded": s.front_loaded,
             "unscheduled_hours": s.unscheduled_hours}
            for s in plan.schedule if s.front_loaded or s.at_risk
        ][:10],
    }
