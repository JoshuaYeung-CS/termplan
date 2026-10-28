"""FastAPI app: JSON API plus the single-page frontend."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import defaultdict, deque
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field, ValidationError

from . import __version__
from .config import Settings, get_settings
from .ics import build_ics
from .llm import ChatClient
from .pdftext import SyllabusFileError, read_syllabus
from .planner import Plan
from .schema import Item
from .service import PlanRequest, PlanResult, SyllabusInput, run_pipeline

logging.basicConfig(level=os.environ.get("TERMPLAN_LOG_LEVEL", "INFO"),
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("termplan.app")

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
EXAMPLES = ROOT.parent / "examples"


class IcsRequest(BaseModel):
    items: list[Item]
    plan: Optional[Plan] = None
    include_study_blocks: bool = False
    calendar_name: str = Field(default="Termplan", max_length=80)


class _RateLimiter:
    """Per-client sliding window, so a public demo cannot drain the API credits."""

    def __init__(self, limit: int, window_s: float = 3600.0) -> None:
        self.limit, self.window = limit, window_s
        self.hits: dict[str, deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key: str) -> bool:
        if self.limit <= 0:
            return True
        now = time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True


def make_client(settings: Settings) -> Optional[ChatClient]:
    if settings.stub:
        from fastapi.testclient import TestClient

        from .stub import create_stub_app

        return ChatClient(api_key="stub", base_url="http://stub.local/v1/",
                          http_client=TestClient(create_stub_app(), base_url="http://stub.local"))
    if not settings.key_configured:
        return None
    return ChatClient(api_key=settings.api_key, base_url=settings.base_url,
                      timeout=settings.request_timeout)


def create_app(settings: Optional[Settings] = None, client: Optional[ChatClient] = None) -> FastAPI:
    settings = settings or get_settings()
    client = client or make_client(settings)
    limiter = _RateLimiter(int(os.environ.get("TERMPLAN_RATE_LIMIT", "30")))
    gate = threading.BoundedSemaphore(int(os.environ.get("TERMPLAN_MAX_CONCURRENT", "3")))
    app = FastAPI(title="Termplan", version=__version__)
    log.info("termplan %s mode=%s model=%s base_url=%s", __version__, settings.mode,
             settings.model, settings.base_url_host)

    def _run(req: PlanRequest, request: Request) -> PlanResult:
        if client is None:
            raise HTTPException(503, "No model configured: set NEBIUS_API_KEY (or TERMPLAN_STUB=1 for offline mode).")
        ip = request.client.host if request.client else "local"
        if not limiter.allow(ip):
            raise HTTPException(429, "Too many plans from this address; try again in an hour.")
        if not gate.acquire(timeout=60):
            raise HTTPException(503, "Server busy; try again shortly.")
        try:
            return run_pipeline(req, client, model=settings.model, coach_model=settings.coach_model,
                                mode=settings.mode, max_attempts=settings.max_attempts)
        finally:
            gate.release()

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.get("/api/health")
    def health() -> dict:
        return {
            "ok": True, "version": __version__, "mode": settings.mode, "model": settings.model,
            "coach_model": settings.coach_model, "base_url_host": settings.base_url_host,
            "key_configured": settings.key_configured, "today": date.today().isoformat(),
        }

    @app.get("/api/samples")
    def samples() -> list[dict]:
        return [{"name": p.name, "text": p.read_text(encoding="utf-8")}
                for p in sorted(EXAMPLES.glob("*.txt"))]

    @app.post("/api/plan", response_model=PlanResult)
    def plan_json(req: PlanRequest, request: Request) -> PlanResult:
        return _run(req, request)

    @app.post("/api/plan/upload", response_model=PlanResult)
    async def plan_upload(
        request: Request,
        files: list[UploadFile] = File(default=[]),
        texts: str = Form(default="[]"),
        term_start: Optional[str] = Form(default=None),
        term_end: Optional[str] = Form(default=None),
        weekly_hours: float = Form(default=20.0),
        today: Optional[str] = Form(default=None),
        front_load: bool = Form(default=True),
        coach: bool = Form(default=True),
    ) -> PlanResult:
        syllabi: list[SyllabusInput] = []
        try:
            for t in json.loads(texts or "[]"):
                if t.get("text", "").strip():
                    syllabi.append(SyllabusInput(name=t.get("name") or "pasted syllabus", text=t["text"]))
        except (json.JSONDecodeError, AttributeError, ValidationError) as exc:
            raise HTTPException(422, f"texts must be a JSON list of {{name, text}}: {exc}") from exc
        for f in files:
            data = await f.read()
            if not data:
                continue
            try:
                syllabi.append(SyllabusInput(name=f.filename or "upload", text=read_syllabus(f.filename or "", data)))
            except SyllabusFileError as exc:
                raise HTTPException(422, str(exc)) from exc
        if not syllabi:
            raise HTTPException(422, "Add at least one syllabus (paste text or upload a PDF/TXT).")
        try:
            req = PlanRequest(
                syllabi=syllabi, term_start=term_start or None, term_end=term_end or None,
                weekly_hours=weekly_hours, today=today or None, front_load=front_load, coach=coach,
            )
        except ValidationError as exc:
            raise HTTPException(422, json.loads(exc.json())) from exc
        from starlette.concurrency import run_in_threadpool

        return await run_in_threadpool(_run, req, request)

    @app.post("/api/ics")
    def ics(req: IcsRequest) -> Response:
        body = build_ics(req.items, req.plan, include_study_blocks=req.include_study_blocks,
                         calendar_name=req.calendar_name)
        return Response(content=body, media_type="text/calendar; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="termplan.ics"'})

    return app


app = create_app()
