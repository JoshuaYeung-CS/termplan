"""Deterministic cross-course checks: exam clashes, deadline pile-ups and crunch weeks."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel

from .schema import Item

GRADED_KINDS = {"exam", "quiz", "assignment", "project", "lab", "paper", "presentation"}


class Conflict(BaseModel):
    kind: Literal["same_day_exams", "back_to_back_exams", "deadline_pileup", "crunch_week"]
    severity: Literal["high", "medium"]
    start: date
    end: date
    item_ids: list[str]
    message: str


class WeekLoad(BaseModel):
    week_start: date
    due_hours: float
    graded_count: int
    major_count: int
    is_crunch: bool
    reasons: list[str]


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def week_loads(items: list[Item], weekly_hours: float) -> list[WeekLoad]:
    """Workload attributed to the week each item is due in."""
    buckets: dict[date, list[Item]] = defaultdict(list)
    for it in items:
        buckets[week_start(it.due_date)].append(it)
    loads = []
    for ws in sorted(buckets):
        group = buckets[ws]
        hours = round(sum(i.est_hours for i in group), 2)
        graded = [i for i in group if i.kind in GRADED_KINDS]
        major = [i for i in group if i.is_major]
        reasons = []
        if hours > weekly_hours:
            reasons.append(f"{hours:g} h of work due vs. a {weekly_hours:g} h weekly budget")
        if len(major) >= 3:
            reasons.append(f"{len(major)} major items (exams or 10%+ of a grade)")
        if len({i.course for i in major}) >= 2 and len(graded) >= 4:
            reasons.append(f"{len(graded)} graded deadlines across {len({i.course for i in graded})} courses")
        loads.append(WeekLoad(
            week_start=ws, due_hours=hours, graded_count=len(graded), major_count=len(major),
            is_crunch=bool(reasons), reasons=reasons,
        ))
    return loads


def find_conflicts(items: list[Item], weekly_hours: float = 20.0) -> list[Conflict]:
    out: list[Conflict] = []
    exams = sorted((i for i in items if i.kind == "exam"), key=lambda i: i.due_date)

    by_day: dict[date, list[Item]] = defaultdict(list)
    for e in exams:
        by_day[e.due_date].append(e)
    for day, group in sorted(by_day.items()):
        if len({e.course for e in group}) >= 2:
            out.append(Conflict(
                kind="same_day_exams", severity="high", start=day, end=day,
                item_ids=[e.id for e in group],
                message=f"{len(group)} exams on {day:%a %b %d}: " + ", ".join(f"{e.course} {e.title}" for e in group),
            ))

    for a, b in zip(exams, exams[1:]):
        if a.course != b.course and (b.due_date - a.due_date).days == 1:
            out.append(Conflict(
                kind="back_to_back_exams", severity="medium", start=a.due_date, end=b.due_date,
                item_ids=[a.id, b.id],
                message=f"Back-to-back exams: {a.course} {a.title} ({a.due_date:%a %b %d}) then "
                        f"{b.course} {b.title} ({b.due_date:%a %b %d})",
            ))

    graded = sorted((i for i in items if i.kind in GRADED_KINDS), key=lambda i: i.due_date)
    used: set[str] = set()
    for i, first in enumerate(graded):
        if first.id in used:
            continue
        window = [g for g in graded[i:] if (g.due_date - first.due_date).days <= 2]
        if len(window) >= 3 and len({g.course for g in window}) >= 2:
            used.update(g.id for g in window)
            out.append(Conflict(
                kind="deadline_pileup", severity="high" if len(window) >= 4 else "medium",
                start=window[0].due_date, end=window[-1].due_date,
                item_ids=[g.id for g in window],
                message=f"{len(window)} graded deadlines within 72 hours "
                        f"({window[0].due_date:%b %d} to {window[-1].due_date:%b %d})",
            ))

    for load in week_loads(items, weekly_hours):
        if load.is_crunch:
            ids = [i.id for i in items if week_start(i.due_date) == load.week_start]
            out.append(Conflict(
                kind="crunch_week", severity="high", start=load.week_start,
                end=load.week_start + timedelta(days=6), item_ids=ids,
                message=f"Crunch week of {load.week_start:%b %d}: " + "; ".join(load.reasons),
            ))
    out.sort(key=lambda c: (c.start, c.kind))
    return out
