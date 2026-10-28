import json

import pytest
from fastapi.testclient import TestClient

from conftest import sample
from termplan.app import create_app
from termplan.config import Settings
from termplan.ics import parse_ics_events
from termplan.pdfmini import make_pdf


def settings(**kw):
    base = dict(api_key="", base_url="https://api.tokenfactory.nebius.com/v1/",
                model="nvidia/Nemotron-3_5-Lightning", coach_model="nvidia/Nemotron-3_5-Lightning",
                stub=True, max_attempts=3, request_timeout=10)
    base.update(kw)
    return Settings(**base)


@pytest.fixture
def api():
    return TestClient(create_app(settings()))


PLAN_ARGS = {"term_start": "2026-08-31", "term_end": "2026-12-18", "today": "2026-10-28", "weekly_hours": 25}


def test_health_reports_model_and_mode(api):
    h = api.get("/api/health").json()
    assert h["mode"] == "stub" and h["model"] == "nvidia/Nemotron-3_5-Lightning"
    assert h["base_url_host"] == "api.tokenfactory.nebius.com" and h["key_configured"] is False


def test_index_and_samples(api):
    assert "Termplan" in api.get("/").text
    names = [s["name"] for s in api.get("/api/samples").json()]
    assert len(names) == 3


def test_full_plan_from_three_samples(api):
    syllabi = api.get("/api/samples").json()
    r = api.post("/api/plan", json={"syllabi": syllabi, **PLAN_ARGS})
    assert r.status_code == 200, r.text
    d = r.json()
    assert len(d["courses"]) == 3 and len(d["items"]) == 36
    assert d["model_calls"] == 6  # STAT 1 + BIO 3 (two repairs) + HIST 1, plus one coach call
    assert all(i["verified"] for i in d["items"])
    kinds = {c["kind"] for c in d["conflicts"]}
    assert {"crunch_week", "back_to_back_exams", "deadline_pileup"} <= kinds
    nov2 = next(w for w in d["plan"]["weeks"] if w["week_start"] == "2026-11-02")
    assert nov2["is_crunch"]
    assert d["next7"]["from"] == "2026-10-28" and len(d["next7"]["due"]) >= 5
    assert d["coach"]["tips"]


def test_upload_mixes_pdf_and_text(api):
    files = [("files", ("stat.pdf", make_pdf(sample("stat3120")), "application/pdf"))]
    data = {"texts": json.dumps([{"name": "hist.txt", "text": sample("hist2290")}]), **PLAN_ARGS}
    r = api.post("/api/plan/upload", files=files, data={k: str(v) for k, v in data.items()})
    assert r.status_code == 200, r.text
    codes = {c["course_code"] for c in r.json()["courses"]}
    assert codes == {"STAT 3120", "HIST 2290"}
    assert all(i["verified"] for i in r.json()["items"])


def test_upload_rejects_empty_and_scans(api):
    assert api.post("/api/plan/upload", data={"texts": "[]"}).status_code == 422
    files = [("files", ("scan.pdf", make_pdf(""), "application/pdf"))]
    r = api.post("/api/plan/upload", files=files, data={"texts": "[]"})
    assert r.status_code == 422 and "no text layer" in r.json()["detail"]


def test_ics_endpoint_round_trip(api):
    d = api.post("/api/plan", json={"syllabi": api.get("/api/samples").json(), **PLAN_ARGS}).json()
    r = api.post("/api/ics", json={"items": d["items"], "plan": d["plan"], "include_study_blocks": True})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/calendar")
    events = parse_ics_events(r.text)
    assert len(events) == len(d["items"]) + len(d["plan"]["days"])


def test_unconfigured_server_says_how_to_fix():
    api = TestClient(create_app(settings(stub=False)))
    assert api.get("/api/health").json()["mode"] == "unconfigured"
    r = api.post("/api/plan", json={"syllabi": [{"name": "x", "text": "y"}]})
    assert r.status_code == 503 and "NEBIUS_API_KEY" in r.json()["detail"]


def test_rate_limit(monkeypatch):
    monkeypatch.setenv("TERMPLAN_RATE_LIMIT", "1")
    api = TestClient(create_app(settings()))
    body = {"syllabi": [{"name": "s", "text": sample("stat3120")}], **PLAN_ARGS, "coach": False}
    assert api.post("/api/plan", json=body).status_code == 200
    assert api.post("/api/plan", json=body).status_code == 429
