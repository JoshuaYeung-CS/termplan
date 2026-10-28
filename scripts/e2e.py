"""End-to-end run of the whole app against the local Token Factory stub.

Starts the stub (an OpenAI-compatible server) and the Termplan app with uvicorn on 127.0.0.1,
points the app at the stub through NEBIUS_BASE_URL exactly as it would point at Token Factory,
uploads the three sample syllabi (one as a PDF), and saves the outputs to docs/.
If the machine does not allow binding a local port, it falls back to FastAPI's TestClient.

Run: .venv/bin/python scripts/e2e.py
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DOCS = ROOT / "docs"
EX = ROOT / "examples"
PLAN_FORM = {"term_start": "2026-08-31", "term_end": "2026-12-18", "today": "2026-10-28",
             "weekly_hours": "25", "front_load": "true"}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_up(url: str, timeout: float = 20) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if httpx.get(url, timeout=1).status_code < 500:
                return
        except httpx.HTTPError:
            time.sleep(0.2)
    raise RuntimeError(f"{url} did not come up")


def upload_payload():
    stat_pdf = (EX / "stat3120_applied_regression.pdf").read_bytes()
    texts = [{"name": p.name, "text": p.read_text(encoding="utf-8")}
             for p in [EX / "bio2450_marine_ecology.txt", EX / "hist2290_cities_and_empires.txt"]]
    files = [("files", ("stat3120_applied_regression.pdf", stat_pdf, "application/pdf"))]
    return files, {**PLAN_FORM, "texts": json.dumps(texts)}


def run_with_uvicorn(log_lines: list[str]):
    stub_port, app_port = free_port(), free_port()
    py = str(ROOT / ".venv" / "bin" / "python")
    env = {**os.environ, "NEBIUS_API_KEY": "stub-key-not-real",
           "NEBIUS_BASE_URL": f"http://127.0.0.1:{stub_port}/v1/", "TERMPLAN_STUB": "",
           "TERMPLAN_ENV_FILE": "/nonexistent"}
    stub_log = open(DOCS / "e2e" / "stub-server.log", "w")
    app_log = open(DOCS / "e2e" / "app-server.log", "w")
    procs = [
        subprocess.Popen([py, "-m", "uvicorn", "--factory", "termplan.stub:create_stub_app",
                          "--host", "127.0.0.1", "--port", str(stub_port)], cwd=ROOT, env=env,
                         stdout=stub_log, stderr=subprocess.STDOUT),
        subprocess.Popen([py, "-m", "uvicorn", "termplan.app:app", "--host", "127.0.0.1",
                          "--port", str(app_port)], cwd=ROOT, env=env,
                         stdout=app_log, stderr=subprocess.STDOUT),
    ]
    try:
        wait_up(f"http://127.0.0.1:{stub_port}/v1/models")
        wait_up(f"http://127.0.0.1:{app_port}/api/health")
        log_lines.append(f"uvicorn: stub on 127.0.0.1:{stub_port}, app on 127.0.0.1:{app_port}")
        http = httpx.Client(base_url=f"http://127.0.0.1:{app_port}", timeout=120)
        yield http
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            p.wait(timeout=10)
        stub_log.close()
        app_log.close()


def run_with_testclient(log_lines: list[str]):
    from fastapi.testclient import TestClient

    from termplan.app import create_app
    from termplan.config import Settings
    from termplan.llm import ChatClient
    from termplan.stub import create_stub_app

    log_lines.append("TestClient fallback: binding a local port was not allowed")
    client = ChatClient(api_key="stub", base_url="http://stub.local/v1/",
                        http_client=TestClient(create_stub_app(), base_url="http://stub.local"))
    s = Settings(api_key="stub-key-not-real", base_url="http://stub.local/v1/",
                 model="nvidia/Nemotron-3_5-Lightning", coach_model="nvidia/Nemotron-3_5-Lightning",
                 stub=False, max_attempts=3, request_timeout=30)
    yield TestClient(create_app(s, client))


def main() -> None:
    (DOCS / "e2e").mkdir(parents=True, exist_ok=True)
    if not (EX / "stat3120_applied_regression.pdf").exists():
        sys.exit("run scripts/make_sample_pdf.py first")
    log_lines: list[str] = []
    try:
        socket.socket().bind(("127.0.0.1", 0))
        runner = run_with_uvicorn(log_lines)
    except OSError:
        runner = run_with_testclient(log_lines)

    for http in runner:
        health = http.get("/api/health").json()
        assert http.get("/").status_code == 200
        files, form = upload_payload()
        t0 = time.time()
        r = http.post("/api/plan/upload", files=files, data=form)
        r.raise_for_status()
        result = r.json()
        log_lines.append(f"POST /api/plan/upload -> {r.status_code} in {time.time() - t0:.2f}s")
        ics = http.post("/api/ics", json={"items": result["items"], "plan": result["plan"]})
        ics.raise_for_status()
        ics_study = http.post("/api/ics", json={"items": result["items"], "plan": result["plan"],
                                                "include_study_blocks": True})
        ics_study.raise_for_status()

    (DOCS / "e2e" / "health.json").write_text(json.dumps(health, indent=2) + "\n")
    (DOCS / "e2e" / "plan-result.json").write_text(json.dumps(result, indent=2) + "\n")
    (DOCS / "sample-termplan.ics").write_text(ics.text, newline="")
    (DOCS / "sample-termplan-with-study.ics").write_text(ics_study.text, newline="")
    (DOCS / "sample-plan.md").write_text(render_markdown(result), encoding="utf-8")

    summary = [
        f"mode={health['mode']} model={health['model']} base_url_host={health['base_url_host']}",
        f"courses={len(result['courses'])} items={len(result['items'])} "
        f"verified={sum(i['verified'] for i in result['items'])} conflicts={len(result['conflicts'])} "
        f"model_calls={result['model_calls']}",
    ]
    for c in result["courses"]:
        summary.append(f"  {c['course_code']}: {len(c['items'])} items, {len(c['attempts'])} attempt(s)")
        for a in c["attempts"]:
            summary.append(f"    attempt {a['n']} ({a['mode']}): " + ("; ".join(a["errors"]) or "passed"))
    (DOCS / "e2e" / "run-log.txt").write_text("\n".join(log_lines + summary) + "\n")
    print("\n".join(log_lines + summary))


def render_markdown(r: dict) -> str:
    by_id = {i["id"]: i for i in r["items"]}
    out = [f"# Sample term plan (planned from {r['today']}, {r['plan']['weekly_hours']:g} h/week)", ""]
    if r.get("coach"):
        out += [f"**{r['coach']['headline']}**", ""] + [f"- {t}" for t in r["coach"]["tips"]] + [""]
    out += ["## Next 7 days", "", "| Due | Course | Item | Work |", "|---|---|---|---|"]
    for iid in r["next7"]["due"]:
        i = by_id[iid]
        out.append(f"| {i['due_date']} {i['due_time'] or ''} | {i['course']} | {i['title']} | {i['est_hours']:g} h |")
    out += ["", "## Week by week", ""]
    for w in r["plan"]["weeks"]:
        flag = " **CRUNCH**" if w["is_crunch"] else ""
        out.append(f"### Week of {w['week_start']}{flag} ({w['planned_hours']:g} h planned)")
        if w["crunch_reasons"]:
            out.append(f"_{'; '.join(w['crunch_reasons'])}_")
        for b in w["by_item"]:
            out.append(f"- work: {b['course']} {b['title']} - {b['hours']:g} h")
        for iid in w["due_item_ids"]:
            i = by_id[iid]
            out.append(f"- due {i['due_date']}: {i['course']} {i['title']}")
        out.append("")
    out += ["## Conflicts", ""] + [f"- [{c['severity']}] {c['message']}" for c in r["conflicts"]]
    out += ["", "## Every item with its source quote", "", "| Due | Course | Item | Kind | Weight | Hours | Quote |",
            "|---|---|---|---|---|---|---|"]
    for i in r["items"]:
        w = f"{i['weight_percent']:g}%" if i["weight_percent"] is not None else ""
        q = i["source_quote"].replace("|", "/")
        out.append(f"| {i['due_date']} | {i['course']} | {i['title']} | {i['kind']} | {w} | {i['est_hours']:g} | \"{q}\" |")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    main()
