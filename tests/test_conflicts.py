from datetime import date

from conftest import mk_item
from termplan.conflicts import find_conflicts, week_loads, week_start


def kinds(conflicts):
    return [c.kind for c in conflicts]


def test_same_day_exams_across_courses():
    items = [mk_item("A 1", "Midterm", date(2026, 11, 4), "exam", 10, 20),
             mk_item("B 2", "Midterm", date(2026, 11, 4), "exam", 10, 20)]
    cs = find_conflicts(items, weekly_hours=40)
    assert "same_day_exams" in kinds(cs)
    c = next(c for c in cs if c.kind == "same_day_exams")
    assert set(c.item_ids) == {i.id for i in items}


def test_same_course_same_day_is_not_a_clash():
    items = [mk_item("A 1", "Part 1", date(2026, 11, 4), "exam", 2),
             mk_item("A 1", "Part 2", date(2026, 11, 4), "exam", 2)]
    assert "same_day_exams" not in kinds(find_conflicts(items, 40))


def test_back_to_back_exams():
    items = [mk_item("A 1", "Midterm", date(2026, 11, 4), "exam", 10),
             mk_item("B 2", "Midterm", date(2026, 11, 5), "exam", 10),
             mk_item("C 3", "Midterm", date(2026, 11, 9), "exam", 10)]
    b2b = [c for c in find_conflicts(items, 60) if c.kind == "back_to_back_exams"]
    assert len(b2b) == 1 and b2b[0].start == date(2026, 11, 4) and b2b[0].end == date(2026, 11, 5)


def test_deadline_pileup_within_72_hours():
    items = [mk_item("A 1", "PS5", date(2026, 10, 30)), mk_item("B 2", "Lab 3", date(2026, 10, 30), "lab"),
             mk_item("C 3", "Prospectus", date(2026, 10, 29), "paper"),
             mk_item("C 3", "Reading", date(2026, 10, 29), "reading")]
    piles = [c for c in find_conflicts(items, 60) if c.kind == "deadline_pileup"]
    assert len(piles) == 1 and len(piles[0].item_ids) == 3  # readings are not graded deadlines


def test_crunch_week_by_hours_and_by_major_count():
    heavy = [mk_item("A 1", f"Big {k}", date(2026, 11, 2 + k), "paper", 9) for k in range(3)]
    loads = week_loads(heavy, weekly_hours=20)
    assert loads[0].is_crunch and "27 h" in loads[0].reasons[0]
    majors = [mk_item("A 1", "Exam", date(2026, 11, 3), "exam", 2),
              mk_item("B 2", "Essay", date(2026, 11, 5), "paper", 2, 25),
              mk_item("C 3", "Exam", date(2026, 11, 6), "exam", 2)]
    loads = week_loads(majors, weekly_hours=20)
    assert loads[0].is_crunch and any("3 major" in r for r in loads[0].reasons)
    assert loads[0].week_start == date(2026, 11, 2)


def test_light_week_has_no_conflicts():
    items = [mk_item("A 1", "PS1", date(2026, 9, 11)), mk_item("B 2", "Lab 1", date(2026, 9, 18), "lab")]
    assert find_conflicts(items, 20) == []


def test_week_start_is_monday():
    assert week_start(date(2026, 11, 8)) == date(2026, 11, 2)  # Sunday -> previous Monday
    assert week_start(date(2026, 11, 2)) == date(2026, 11, 2)
