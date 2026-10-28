"""Week-by-week study planner.

Each item's estimated hours are spread over a lead window before its deadline, within a daily
capacity. Items due in a crunch week get a longer lead window, so their preparation lands in the
weeks before the crunch instead of inside it. Work that does not fit spills to earlier days; work
that cannot fit at all is reported as at risk.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from pydantic import BaseModel, Field

from .conflicts import week_loads, week_start
from .schema import Item

LEAD_DAYS = {
    "exam": 10, "project": 21, "paper": 14, "presentation": 7, "lab": 5,
    "assignment": 6, "quiz": 4, "reading": 3, "other": 5,
}
STEP = 0.25  # hours are allocated in quarter-hour slices


class Block(BaseModel):
    item_id: str
    course: str
    title: str
    hours: float


class DayPlan(BaseModel):
    day: date
    blocks: list[Block] = Field(default_factory=list)

    @property
    def hours(self) -> float:
        return round(sum(b.hours for b in self.blocks), 2)


class WeekPlan(BaseModel):
    week_start: date
    planned_hours: float
    due_item_ids: list[str]
    is_crunch: bool
    crunch_reasons: list[str] = Field(default_factory=list)
    by_item: list[Block] = Field(default_factory=list)


class ItemSchedule(BaseModel):
    item_id: str
    start_by: date | None
    scheduled_hours: float
    unscheduled_hours: float
    at_risk: bool
    front_loaded: bool


class Plan(BaseModel):
    today: date
    weekly_hours: float
    days: list[DayPlan]
    weeks: list[WeekPlan]
    schedule: list[ItemSchedule]


def build_plan(
    items: list[Item],
    today: date,
    weekly_hours: float = 20.0,
    front_load: bool = True,
) -> Plan:
    daily_cap = weekly_hours / 7.0
    upcoming = [i for i in items if i.due_date >= today]
    loads = {w.week_start: w for w in week_loads(upcoming, weekly_hours)}
    crunch_weeks = {ws for ws, w in loads.items() if w.is_crunch}

    used: dict[date, float] = defaultdict(float)
    alloc: dict[date, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    schedule: list[ItemSchedule] = []

    # Earliest deadline first: near-term work claims capacity before later work.
    for it in sorted(upcoming, key=lambda i: (i.due_date, -i.est_hours)):
        lead = LEAD_DAYS.get(it.kind, 5)
        boosted = front_load and week_start(it.due_date) in crunch_weeks
        if boosted:
            lead = max(lead * 2, lead + 7)
        last_day = it.due_date - timedelta(days=1) if it.due_date > today else today
        first_day = max(today, it.due_date - timedelta(days=lead))
        window = _days(first_day, last_day)
        remaining = _round(it.est_hours)

        remaining = _water_fill(window, remaining, daily_cap, used, alloc, it.id)
        if remaining > 0:  # spill to days before the window, nearest first
            spill = list(reversed(_days(today, first_day - timedelta(days=1))))
            for d in spill:
                if remaining <= 0:
                    break
                remaining = _water_fill([d], remaining, daily_cap, used, alloc, it.id)
        scheduled_days = sorted(d for d in alloc if alloc[d].get(it.id))
        scheduled = _round(it.est_hours) - remaining
        schedule.append(ItemSchedule(
            item_id=it.id,
            start_by=scheduled_days[0] if scheduled_days else None,
            scheduled_hours=round(scheduled, 2),
            unscheduled_hours=round(remaining, 2),
            at_risk=remaining > 0,
            front_loaded=boosted,
        ))

    by_id = {i.id: i for i in items}
    days = []
    for d in sorted(alloc):
        blocks = [
            Block(item_id=iid, course=by_id[iid].course, title=by_id[iid].title, hours=round(h, 2))
            for iid, h in sorted(alloc[d].items(), key=lambda kv: by_id[kv[0]].due_date)
            if h > 0
        ]
        if blocks:
            days.append(DayPlan(day=d, blocks=blocks))

    weeks_index: dict[date, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for dp in days:
        for b in dp.blocks:
            weeks_index[week_start(dp.day)][b.item_id] += b.hours
    all_weeks = sorted(set(weeks_index) | set(loads))
    weeks = []
    for ws in all_weeks:
        per_item = weeks_index.get(ws, {})
        load = loads.get(ws)
        weeks.append(WeekPlan(
            week_start=ws,
            planned_hours=round(sum(per_item.values()), 2),
            due_item_ids=[i.id for i in upcoming if week_start(i.due_date) == ws],
            is_crunch=bool(load and load.is_crunch),
            crunch_reasons=load.reasons if load else [],
            by_item=[
                Block(item_id=iid, course=by_id[iid].course, title=by_id[iid].title, hours=round(h, 2))
                for iid, h in sorted(per_item.items(), key=lambda kv: -kv[1])
            ],
        ))
    return Plan(today=today, weekly_hours=weekly_hours, days=days, weeks=weeks, schedule=schedule)


def _days(first: date, last: date) -> list[date]:
    if last < first:
        return []
    return [first + timedelta(days=k) for k in range((last - first).days + 1)]


def _round(h: float) -> float:
    return max(STEP, round(h / STEP) * STEP)


def _water_fill(window, remaining, cap, used, alloc, item_id) -> float:
    """Spread `remaining` hours evenly over `window`, a quarter hour at a time, within capacity."""
    while remaining > 1e-9:
        open_days = [d for d in window if cap - used[d] >= STEP - 1e-9]
        if not open_days:
            break
        progressed = False
        for d in open_days:
            if remaining <= 1e-9:
                break
            if cap - used[d] >= STEP - 1e-9:
                used[d] += STEP
                alloc[d][item_id] += STEP
                remaining -= STEP
                progressed = True
        if not progressed:
            break
    return round(max(remaining, 0.0), 2)


def next_seven_days(items: list[Item], plan: Plan, today: date) -> dict:
    horizon = today + timedelta(days=6)
    due = [i for i in items if today <= i.due_date <= horizon]
    due.sort(key=lambda i: (i.due_date, i.due_time or "99:99"))
    blocks = [dp for dp in plan.days if today <= dp.day <= horizon]
    return {
        "from": today,
        "to": horizon,
        "due": [i.id for i in due],
        "study_days": [
            {"day": dp.day, "hours": dp.hours, "blocks": [b.model_dump() for b in dp.blocks]}
            for dp in blocks
        ],
        "study_hours": round(sum(dp.hours for dp in blocks), 2),
    }
