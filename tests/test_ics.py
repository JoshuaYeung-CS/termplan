from datetime import date, datetime, timezone

from conftest import mk_item
from termplan.ics import _fold, build_ics, parse_ics_events
from termplan.planner import build_plan

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)


def test_calendar_structure_and_line_endings():
    items = [mk_item("STAT 3120", "Midterm 2", date(2026, 11, 5), "exam", 12, 20, "19:30"),
             mk_item("BIO 2450", "Read Chapter 9", date(2026, 11, 2), "reading", 2)]
    text = build_ics(items, now=NOW)
    assert text.startswith("BEGIN:VCALENDAR\r\nVERSION:2.0\r\n") and text.endswith("END:VCALENDAR\r\n")
    assert "\n" not in text.replace("\r\n", "")
    events = parse_ics_events(text)
    assert len(events) == 2
    exam, reading = events
    assert exam["DTSTART"] == "20261105T193000" and exam["DTEND"] == "20261105T213000"
    assert exam["SUMMARY"] == "Exam: STAT 3120 Midterm 2"
    assert reading["DTSTART;VALUE=DATE"] == "20261102" and reading["DTEND;VALUE=DATE"] == "20261103"
    assert text.count("BEGIN:VALARM") == 1  # readings get no alarm
    assert "TRIGGER:-P2D" in text  # major item -> two-day reminder
    assert all(e["DTSTAMP"] == "20261028T120000Z" for e in events)
    assert len({e["UID"] for e in events}) == 2


def test_text_is_escaped():
    it = mk_item("HIST 2290", "Essay; draft, part 2", date(2026, 11, 5), "paper", 3)
    text = build_ics([it], now=NOW)
    assert "SUMMARY:Due: HIST 2290 Essay\\; draft\\, part 2" in text
    desc = parse_ics_events(text)[0]["DESCRIPTION"]
    assert "\\n" in desc and "\n" not in desc


def test_long_lines_fold_at_75_octets_without_breaking_utf8():
    line = "DESCRIPTION:" + "é" * 120
    folded = _fold(line)
    for part in folded.split("\r\n"):
        assert len(part.encode("utf-8")) <= 75
    assert folded.replace("\r\n ", "") == line


def test_study_blocks_are_optional():
    items = [mk_item("A 1", "PS", date(2026, 11, 6), hours=4)]
    plan = build_plan(items, date(2026, 11, 2), weekly_hours=21)
    plain = parse_ics_events(build_ics(items, plan, now=NOW))
    withstudy = parse_ics_events(build_ics(items, plan, include_study_blocks=True, now=NOW))
    assert len(plain) == 1 and len(withstudy) == 1 + len(plan.days)
    assert all(e["SUMMARY"].startswith("Study") for e in withstudy[1:])


def test_unverified_items_say_so():
    it = mk_item("A 1", "PS", date(2026, 11, 6)).model_copy(update={"verified": False})
    assert "Check this one" in build_ics([it], now=NOW)
