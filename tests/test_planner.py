from collections import defaultdict
from datetime import date, timedelta

from conftest import mk_item
from termplan.conflicts import week_start
from termplan.planner import build_plan, next_seven_days

TODAY = date(2026, 10, 5)


def hours_by_day(plan):
    return {d.day: d.hours for d in plan.days}


def item_days(plan, item_id):
    return {d.day: b.hours for d in plan.days for b in d.blocks if b.item_id == item_id}


def test_all_hours_land_before_the_deadline_when_capacity_allows():
    items = [mk_item("A 1", "PS", date(2026, 10, 12), hours=6),
             mk_item("B 2", "Exam", date(2026, 10, 20), "exam", 10, 20)]
    plan = build_plan(items, TODAY, weekly_hours=21)
    for it in items:
        days = item_days(plan, it.id)
        assert abs(sum(days.values()) - it.est_hours) < 1e-6
        assert max(days) < it.due_date and min(days) >= TODAY
    assert not any(s.at_risk for s in plan.schedule)


def test_daily_capacity_is_respected():
    items = [mk_item("A 1", f"Task {k}", date(2026, 10, 9), hours=5) for k in range(4)]
    plan = build_plan(items, TODAY, weekly_hours=14)
    assert all(h <= 2.0 + 1e-9 for h in hours_by_day(plan).values())
    assert any(s.at_risk for s in plan.schedule)  # 20 h cannot fit in 4 days x 2 h


def test_at_risk_reports_the_shortfall():
    it = mk_item("A 1", "Essay", date(2026, 10, 7), "paper", 12)
    plan = build_plan([it], TODAY, weekly_hours=14)
    s = plan.schedule[0]
    assert s.at_risk and s.scheduled_hours == 4.0 and s.unscheduled_hours == 8.0


def test_past_items_are_skipped_and_due_today_is_worked_today():
    past = mk_item("A 1", "Old", date(2026, 10, 1))
    today_item = mk_item("A 1", "Now", TODAY, hours=1)
    plan = build_plan([past, today_item], TODAY, weekly_hours=21)
    assert [s.item_id for s in plan.schedule] == [today_item.id]
    assert item_days(plan, today_item.id) == {TODAY: 1.0}


def test_front_loading_moves_work_out_of_the_crunch_week():
    crunch_day = date(2026, 10, 28)
    items = [mk_item("A 1", "Exam A", crunch_day, "exam", 10, 20),
             mk_item("B 2", "Exam B", crunch_day + timedelta(days=1), "exam", 10, 20),
             mk_item("C 3", "Essay", crunch_day + timedelta(days=2), "paper", 12, 25)]
    on = build_plan(items, TODAY, weekly_hours=21, front_load=True)
    off = build_plan(items, TODAY, weekly_hours=21, front_load=False)
    crunch_ws = week_start(crunch_day)

    def in_week(plan, ws):
        return sum(d.hours for d in plan.days if week_start(d.day) == ws)

    assert next(w for w in on.weeks if w.week_start == crunch_ws).is_crunch
    assert in_week(on, crunch_ws) < in_week(off, crunch_ws)
    before = lambda plan: sum(d.hours for d in plan.days if d.day < crunch_ws)  # noqa: E731
    assert before(on) > before(off)
    assert not any(s.at_risk for s in on.schedule)
    assert all(s.front_loaded for s in on.schedule)
    assert min(s.start_by for s in on.schedule) < min(s.start_by for s in off.schedule)


def test_weekly_totals_match_daily_blocks():
    items = [mk_item("A 1", f"PS{k}", date(2026, 10, 9) + timedelta(days=7 * k), hours=5) for k in range(4)]
    plan = build_plan(items, TODAY, weekly_hours=20)
    per_week = defaultdict(float)
    for d in plan.days:
        per_week[week_start(d.day)] += d.hours
    for w in plan.weeks:
        assert abs(w.planned_hours - per_week.get(w.week_start, 0)) < 1e-6


def test_next_seven_days_window():
    items = [mk_item("A 1", "Soon", TODAY + timedelta(days=3)), mk_item("A 1", "Later", TODAY + timedelta(days=9))]
    plan = build_plan(items, TODAY, weekly_hours=21)
    n7 = next_seven_days(items, plan, TODAY)
    assert n7["due"] == [items[0].id]
    assert n7["to"] == TODAY + timedelta(days=6)
    assert all(TODAY <= d["day"] <= n7["to"] for d in n7["study_days"])
    assert n7["study_hours"] > 0
