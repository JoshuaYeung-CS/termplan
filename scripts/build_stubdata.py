"""Write the scripted extractions the local stub server replays for the three sample syllabi.

Every quote is checked against the sample text, so the stub data can never drift from the
examples. Run: .venv/bin/python scripts/build_stubdata.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from termplan.schema import CourseExtraction  # noqa: E402
from termplan.textutil import quote_in_source  # noqa: E402

PS = 25 / 6  # seven problem sets, lowest dropped -> six count

COURSES = {
    "stat3120": {
        "file": "stat3120_applied_regression.txt",
        "match": "STAT 3120",
        "script": ["clean"],
        "data": {
            "course_code": "STAT 3120",
            "course_title": "Applied Regression Analysis",
            "items": [
                ("Read Notes chapters 1-2", "reading", "2026-09-04", None, None, 2,
                 "Two short chapters of course notes.",
                 "Read Notes chapters 1-2 before the first lab on September 4."),
                ("Problem Set 1 (simple regression)", "assignment", "2026-09-11", "23:59", PS, 5,
                 "Early sets are shorter R exercises.",
                 "Problem Set 1 (simple regression) -- due Friday, September 11"),
                ("Problem Set 2 (inference for slopes)", "assignment", "2026-09-25", "23:59", PS, 5,
                 "Standard weekly set.",
                 "Problem Set 2 (inference for slopes) -- due Friday, September 25"),
                ("Midterm 1", "exam", "2026-10-01", "10:10", 15, 9,
                 "Covers four chapters; about two evenings of review plus practice exams.",
                 "Midterm 1 is in class on Thursday, October 1"),
                ("Problem Set 3 (multiple regression)", "assignment", "2026-10-09", "23:59", PS, 6,
                 "Multiple regression sets take longer in R.",
                 "Problem Set 3 (multiple regression) -- due Friday, October 9"),
                ("Problem Set 4 (diagnostics and residual plots)", "assignment", "2026-10-23", "23:59", PS, 6,
                 "Diagnostics need many plots.",
                 "Problem Set 4 (diagnostics and residual plots) -- due Friday, October 23"),
                ("Problem Set 5 (transformations and interactions)", "assignment", "2026-10-30", "23:59", PS, 6,
                 "Interaction terms are a common stumbling block.",
                 "Problem Set 5 (transformations and interactions) -- due Friday, October 30"),
                ("Final project proposal", "project", "2026-11-02", "23:59", 5, 3,
                 "One page, but finding a usable data set takes time.",
                 "Project proposal (one page: question, data source, planned model) due Monday, November 2 at 11:59 pm."),
                ("Midterm 2", "exam", "2026-11-05", "19:30", 20, 12,
                 "Four chapters including influence and leverage; worth 20%.",
                 "Midterm 2 is an evening exam on Thursday, November 5, 7:30-9:00 pm"),
                ("Reread Notes chapter 7 (influence and leverage)", "reading", "2026-11-05", None, None, 1.5,
                 "One chapter reread before the exam.",
                 "Before Midterm 2, reread Notes chapter 7 on influence and leverage"),
                ("Problem Set 6 (model selection)", "assignment", "2026-11-13", "23:59", PS, 6,
                 "Model selection requires comparing several fits.",
                 "Problem Set 6 (model selection) -- due Friday, November 13"),
                ("Problem Set 7 (logistic regression)", "assignment", "2026-12-04", "23:59", PS, 7,
                 "New model family.",
                 "Problem Set 7 (logistic regression) -- due Friday, December 4"),
                ("Final project report", "project", "2026-12-11", "23:59", 15, 20,
                 "8-10 pages of analysis and code with a partner.",
                 "Final project report (8-10 pages with code appendix) due Friday, December 11 at 11:59 pm."),
                ("Final exam (cumulative)", "exam", "2026-12-16", "14:00", 20, 15,
                 "Cumulative exam worth 20%.",
                 "Wednesday, December 16, 2:00-4:30 pm"),
            ],
            "undated": [],
        },
    },
    "bio2450": {
        "file": "bio2450_marine_ecology.txt",
        "match": "BIO 2450",
        # First reply is fenced JSON with a trailing comma; the second parses but paraphrases one
        # quote and writes a time as "5 pm"; the third is clean. Exercises the repair loop.
        "script": ["fenced_trailing_comma", "paraphrase_and_bad_time", "clean"],
        "data": {
            "course_code": "BIO 2450",
            "course_title": "Marine Ecology",
            "items": [
                ("Lab 1 report (intertidal transects)", "lab", "2026-09-18", "13:25", 5, 4,
                 "Data analysis plus a short write-up.",
                 "Lab 1 report (intertidal transects) -- Week 3, Friday"),
                ("Lab 2 report (plankton tows and counts)", "lab", "2026-10-09", "13:25", 5, 4,
                 "Counting data and a short write-up.",
                 "Lab 2 report (plankton tows and counts) -- Week 6, Friday"),
                ("Read Chapter 7, Kelp Forests", "reading", "2026-10-26", None, None, 2,
                 "One textbook chapter.",
                 "Chapter 7, Kelp Forests: read before Week 9 Monday."),
                ("Lab 3 report (kelp holdfast communities)", "lab", "2026-10-30", "13:25", 5, 4,
                 "Community data from the holdfast lab.",
                 "Lab 3 report (kelp holdfast communities) -- Week 9, Friday"),
                ("Read Chapter 9, Coral Reefs and Bleaching", "reading", "2026-11-02", None, None, 2,
                 "One textbook chapter.",
                 "Chapter 9, Coral Reefs and Bleaching: read before Week 10 Monday."),
                ("Midterm exam", "exam", "2026-11-04", "13:25", 20, 12,
                 "Covers nine weeks including labs.",
                 "The midterm exam is in class on Week 10, Wednesday."),
                ("Field study draft", "project", "2026-11-06", "17:00", 5, 6,
                 "Methods section and first figures with a team of three.",
                 "Field study draft (methods + preliminary figures): Week 10, Friday, by 5 pm."),
                ("Lab 4 report (reef fish surveys from video)", "lab", "2026-11-20", "13:25", 5, 4,
                 "Video survey counts.",
                 "Lab 4 report (reef fish surveys from video) -- Week 12, Friday"),
                ("Read Chapter 12, Fisheries and Bycatch", "reading", "2026-11-30", None, None, 2,
                 "One textbook chapter.",
                 "Chapter 12, Fisheries and Bycatch: read before Week 14 Monday."),
                ("Final field study report", "project", "2026-12-04", "17:00", 20, 16,
                 "Full report worth 20%.",
                 "Final field study report: Week 14, Friday, by 5 pm."),
                ("Final exam (cumulative)", "exam", "2026-12-17", "09:00", 25, 15,
                 "Cumulative final worth 25%.",
                 "Thursday, December 17, 9:00-11:30 am."),
            ],
            "undated": [
                {"title": "Field study poster session",
                 "source_quote": "A field study poster session will be scheduled during Week 15; the exact date is TBA.",
                 "note": "Date to be announced; add it when the course posts it."},
            ],
        },
    },
    "hist2290": {
        "file": "hist2290_cities_and_empires.txt",
        "match": "HIST 2290",
        "script": ["think_then_clean"],
        "data": {
            "course_code": "HIST 2290",
            "course_title": "Cities and Empires, 1200-1800",
            "items": [
                ("Response paper 1", "paper", "2026-09-22", "10:00", 5, 3,
                 "Two pages on one week's reading.",
                 "Response papers are due on Canvasboard by 10:00 am on Tuesday, September 22;"),
                ("Essay 1 (single city before 1500)", "paper", "2026-10-02", "17:00", 15, 12,
                 "4-5 pages with sources.",
                 "Essay 1, on a single city of your choice before 1500, is due Friday, October 2 at 5:00 pm."),
                ("Response paper 2", "paper", "2026-10-20", "10:00", 5, 3,
                 "Two pages on one week's reading.",
                 "Tuesday, October 20;"),
                ("Unit 4 reading: Port Cities of the Indian Ocean", "reading", "2026-10-27", "14:55", None, 3,
                 "About 30 pages of primary sources.",
                 "Reader pp. 112-140, for the October 27 discussion"),
                ("Essay 2 prospectus", "paper", "2026-10-29", "17:00", 5, 4,
                 "One page plus finding five sources.",
                 "by Thursday, October 29 at 5:00 pm"),
                ("Map quiz", "quiz", "2026-11-03", "14:55", 5, 3,
                 "Memorizing place names and routes.",
                 "The map quiz is in class on Tuesday, November 3"),
                ("Essay 2 (comparing two cities)", "paper", "2026-11-05", "17:00", 25, 18,
                 "8-10 pages, the largest written assignment.",
                 "The full essay is due Thursday, November 5 at 5:00 pm."),
                ("Unit 5 reading: Capitals and Courts", "reading", "2026-11-10", "14:55", None, 4,
                 "About 48 pages.",
                 "Reader pp. 141-188, for the November 10 discussion"),
                ("Response paper 3", "paper", "2026-11-17", "10:00", 5, 3,
                 "Two pages on one week's reading.",
                 "Tuesday, November 17."),
                ("Unit 6 reading: Cities in Crisis", "reading", "2026-12-01", "14:55", None, 3.5,
                 "About 40 pages.",
                 "Reader pp. 189-230, for the December 1 discussion"),
                ("Final take-home exam", "exam", "2026-12-14", "12:00", 25, 14,
                 "Two essays over four days.",
                 "Monday, December 14 at 12:00 pm (noon)"),
            ],
            "undated": [
                {"title": "Museum map collection reflection",
                 "source_quote": "announced once the gallery reopens (date to be determined)",
                 "note": "No due date yet."},
            ],
        },
    },
}

FIELDS = ("title", "kind", "due_date", "due_time", "weight_percent", "est_hours",
          "hours_rationale", "source_quote")


def main() -> None:
    out_dir = ROOT / "termplan" / "stubdata"
    out_dir.mkdir(parents=True, exist_ok=True)
    for key, spec in COURSES.items():
        text = (ROOT / "examples" / spec["file"]).read_text(encoding="utf-8")
        data = dict(spec["data"])
        data["items"] = [
            {k: (round(v, 2) if isinstance(v, float) else v) for k, v in zip(FIELDS, row)}
            for row in data["items"]
        ]
        CourseExtraction.model_validate(data)
        for it in data["items"] + data["undated"]:
            assert quote_in_source(it["source_quote"], text), (key, it["source_quote"])
        payload = {"match": spec["match"], "script": spec["script"], "extraction": data}
        (out_dir / f"{key}.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {key}.json: {len(data['items'])} items, {len(data['undated'])} undated")


if __name__ == "__main__":
    main()
