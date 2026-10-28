import pytest
from pydantic import ValidationError

from termplan.schema import CourseExtraction, ExtractedItem, extraction_json_schema

BASE = dict(title="Midterm", kind="exam", due_date="2026-11-04", est_hours=10,
            source_quote="The midterm exam is in class")


def test_valid_item_parses_and_strips():
    it = ExtractedItem.model_validate({**BASE, "title": "  Midterm  ", "due_time": "13:25"})
    assert it.title == "Midterm" and it.due_time == "13:25" and it.due_date.isoformat() == "2026-11-04"


@pytest.mark.parametrize("patch", [
    {"due_time": "5 pm"}, {"due_time": "25:00"}, {"kind": "homework"}, {"due_date": "Nov 4"},
    {"est_hours": 0}, {"est_hours": 500}, {"weight_percent": 140}, {"source_quote": "short"},
])
def test_invalid_fields_rejected(patch):
    with pytest.raises(ValidationError):
        ExtractedItem.model_validate({**BASE, **patch})


def test_missing_quote_rejected():
    data = dict(BASE)
    data.pop("source_quote")
    with pytest.raises(ValidationError):
        ExtractedItem.model_validate(data)


def test_empty_time_becomes_null():
    assert ExtractedItem.model_validate({**BASE, "due_time": ""}).due_time is None


def test_schema_lists_required_fields():
    schema = extraction_json_schema()
    item = schema["$defs"]["ExtractedItem"]
    assert {"title", "kind", "due_date", "est_hours", "source_quote"} <= set(item["required"])
    assert set(schema["required"]) >= {"course_code", "course_title", "items"}
    CourseExtraction.model_validate({"course_code": "X 1", "course_title": "Xx", "items": [BASE]})
