"""RFC 5545 calendar export (no third-party dependency)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from .planner import Plan
from .schema import Item

PRODID = "-//Termplan//Syllabus Planner 0.1//EN"


def _escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
        .replace("\r\n", "\\n").replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """Fold content lines at 75 octets, never splitting a UTF-8 character."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    parts, current, limit = [], b"", 75
    for ch in line:
        b = ch.encode("utf-8")
        if len(current) + len(b) > limit:
            parts.append(current.decode("utf-8"))
            current, limit = b"", 74  # continuation lines start with a space
        current += b
    parts.append(current.decode("utf-8"))
    return "\r\n ".join(parts)


def _describe(item: Item) -> str:
    lines = [f"{item.course}: {item.title} ({item.kind})"]
    if item.weight_percent is not None:
        lines.append(f"Weight: {item.weight_percent:g}% of the course grade")
    lines.append(f"Estimated work: {item.est_hours:g} h")
    lines.append(f'Syllabus says: "{item.source_quote}"')
    if not item.verified:
        lines.append("Check this one: the quote could not be matched to the syllabus.")
    return "\n".join(lines)


def build_ics(
    items: Iterable[Item],
    plan: Optional[Plan] = None,
    *,
    include_study_blocks: bool = False,
    calendar_name: str = "Termplan",
    now: Optional[datetime] = None,
) -> str:
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    out = [
        "BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{PRODID}", "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH", f"X-WR-CALNAME:{_escape(calendar_name)}",
    ]
    for it in items:
        out += ["BEGIN:VEVENT", f"UID:{it.id}@termplan", f"DTSTAMP:{stamp}"]
        if it.due_time:
            hh, mm = (int(x) for x in it.due_time.split(":"))
            start = datetime(it.due_date.year, it.due_date.month, it.due_date.day, hh, mm)
            minutes = 120 if it.kind == "exam" else 30
            end = start + timedelta(minutes=minutes)
            out += [f"DTSTART:{start:%Y%m%dT%H%M%S}", f"DTEND:{end:%Y%m%dT%H%M%S}"]
        else:
            out += [
                f"DTSTART;VALUE=DATE:{it.due_date:%Y%m%d}",
                f"DTEND;VALUE=DATE:{it.due_date + timedelta(days=1):%Y%m%d}",
            ]
        label = "Exam" if it.kind == "exam" else ("Read" if it.kind == "reading" else "Due")
        out.append(f"SUMMARY:{_escape(f'{label}: {it.course} {it.title}')}")
        out.append(f"DESCRIPTION:{_escape(_describe(it))}")
        out.append(f"CATEGORIES:{_escape(it.course)},{it.kind.upper()}")
        out.append("TRANSP:TRANSPARENT")
        if it.kind != "reading":
            trigger = "-P2D" if it.is_major else "-P1D"
            out += [
                "BEGIN:VALARM", "ACTION:DISPLAY", f"TRIGGER:{trigger}",
                f"DESCRIPTION:{_escape(f'{it.course} {it.title}')}", "END:VALARM",
            ]
        out.append("END:VEVENT")

    if include_study_blocks and plan is not None:
        for dp in plan.days:
            names = "; ".join(f"{b.course} {b.title} {b.hours:g}h" for b in dp.blocks)
            out += [
                "BEGIN:VEVENT", f"UID:study-{dp.day:%Y%m%d}@termplan", f"DTSTAMP:{stamp}",
                f"DTSTART;VALUE=DATE:{dp.day:%Y%m%d}",
                f"DTEND;VALUE=DATE:{dp.day + timedelta(days=1):%Y%m%d}",
                f"SUMMARY:{_escape(f'Study {dp.hours:g}h')}",
                f"DESCRIPTION:{_escape(names)}", "TRANSP:TRANSPARENT", "END:VEVENT",
            ]
    out.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in out) + "\r\n"


def parse_ics_events(text: str) -> list[dict[str, str]]:
    """Tiny reader used by tests: unfolds lines and returns VEVENT properties."""
    lines = text.replace("\r\n ", "").split("\r\n")
    events, current = [], None
    for line in lines:
        if line == "BEGIN:VEVENT":
            current = {}
        elif line == "END:VEVENT":
            events.append(current)
            current = None
        elif current is not None and ":" in line and not line.startswith(("BEGIN:VALARM", "END:VALARM")):
            key, value = line.split(":", 1)
            current.setdefault(key, value)
    return events

