"""The strict schema every extracted item must satisfy."""

from __future__ import annotations

import hashlib
import re
from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

Kind = Literal[
    "exam", "quiz", "assignment", "project", "lab", "paper", "reading", "presentation", "other"
]
KINDS: tuple[str, ...] = Kind.__args__  # type: ignore[attr-defined]

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class ExtractedItem(BaseModel):
    """One graded deadline, exam or reading, exactly as the model must return it."""

    model_config = ConfigDict(extra="ignore")

    title: str = Field(min_length=2, max_length=160)
    kind: Kind
    due_date: date = Field(description="ISO date YYYY-MM-DD, resolved to the real calendar date")
    due_time: Optional[str] = Field(default=None, description="24-hour HH:MM, or null")
    weight_percent: Optional[float] = Field(default=None, ge=0, le=100)
    est_hours: float = Field(gt=0, le=80, description="Estimated hours of work for a typical student")
    hours_rationale: Optional[str] = Field(default=None, max_length=300)
    source_quote: str = Field(
        min_length=8, max_length=400,
        description="A short verbatim excerpt from the syllabus that states this deadline",
    )

    @field_validator("title", "source_quote")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    @field_validator("due_time")
    @classmethod
    def _check_time(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        v = v.strip()
        if not _TIME_RE.match(v):
            raise ValueError("due_time must be 24-hour HH:MM (for example 17:00) or null")
        return v


class UndatedItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = Field(min_length=2, max_length=160)
    source_quote: str = Field(min_length=4, max_length=400)
    note: Optional[str] = Field(default=None, max_length=300)


class CourseExtraction(BaseModel):
    """Top-level object the model returns for one syllabus."""

    model_config = ConfigDict(extra="ignore")

    course_code: str = Field(min_length=2, max_length=40)
    course_title: str = Field(min_length=2, max_length=160)
    items: list[ExtractedItem]
    undated: list[UndatedItem] = Field(default_factory=list)


class Item(ExtractedItem):
    """An extracted item after grounding checks, tagged with its course."""

    id: str
    course: str
    verified: bool = True
    warnings: list[str] = Field(default_factory=list)

    @property
    def is_major(self) -> bool:
        return self.kind == "exam" or (self.weight_percent or 0) >= 10


def make_item_id(course: str, title: str, due: date) -> str:
    digest = hashlib.sha1(f"{course}|{title}|{due.isoformat()}".encode()).hexdigest()
    return digest[:10]


def extraction_json_schema() -> dict:
    """JSON Schema sent to the model (response_format and prompt)."""
    return CourseExtraction.model_json_schema()
