from __future__ import annotations

import copy
import sys
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from termplan.llm import ChatClient  # noqa: E402
from termplan.schema import Item, make_item_id  # noqa: E402
from termplan.stub import create_stub_app, load_scripts  # noqa: E402

EXAMPLES = ROOT / "examples"
TERM_START = date(2026, 8, 31)
TERM_END = date(2026, 12, 18)


def sample(name: str) -> str:
    return next(EXAMPLES.glob(f"{name}*.txt")).read_text(encoding="utf-8")


def client_for(app) -> ChatClient:
    return ChatClient(api_key="stub", base_url="http://stub.local/v1/",
                      http_client=TestClient(app, base_url="http://stub.local"), max_retries=0)


@pytest.fixture
def stub_app():
    return create_stub_app()


@pytest.fixture
def stub_client(stub_app):
    return client_for(stub_app)


def scripts_with(match: str, steps: list[str]) -> list[dict]:
    scripts = copy.deepcopy(load_scripts())
    for s in scripts:
        if s["match"] == match:
            s["script"] = steps
    return scripts


def mk_item(course: str, title: str, due: date, kind: str = "assignment", hours: float = 4.0,
            weight: float | None = None, time: str | None = None) -> Item:
    return Item(
        id=make_item_id(course, title, due), course=course, title=title, kind=kind, due_date=due,
        due_time=time, weight_percent=weight, est_hours=hours, source_quote=f"{title} is due soon",
    )
