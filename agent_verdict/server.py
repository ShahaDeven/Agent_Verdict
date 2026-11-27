"""Agent Verdict's local backend: the review queue API.

    agent-verdict serve              # http://127.0.0.1:8000, API docs at /docs

Reading, reviewing and importing runs is free. Judging a run calls Muse Ember, so it is OFF unless
the server is started with spending allowed (agent-verdict serve --allow-spend --max-usd 0.10); the
spend ledger's caps apply either way. If AGENT_VERDICT_WEBHOOK is set, every new verdict that needs a
person is POSTed there (one JSON call; failures are logged, never fatal).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ember_core.ember import REPO_ROOT

from ember_core.budget import BudgetExceeded

from . import api
from .store import Store, save_data_url
from .trace import from_generic
from .verdict_v2 import FAILURE_TYPES

UI_DIST = REPO_ROOT / "frontend" / "dist"


def screens_dir(store: Store) -> Path:
    """Imported screenshots live next to the database they belong to."""
    return store.path.parent / "screens"


class ReviewIn(BaseModel):
    decision: Literal["agree", "override"]
    success: bool
    failure_type: str | None = None
    note: str | None = None
    reviewer: str | None = None


class TraceIn(BaseModel):
    """The generic trace format; screenshots must be data URLs here (no server-side file paths)."""
    key: str
    goal: str
    steps: list[dict]
    final_screenshot: str | None = None
    agent: str | None = None
    source: str = "generic"


def _notify(run: dict) -> None:
    url = os.environ.get("AGENT_VERDICT_WEBHOOK")
    if not url:
        return
    import requests
    v = run["verdict"]
    try:
        requests.post(url, timeout=5, json={
            "event": "needs_review", "run_id": run["id"], "key": run["key"], "goal": run["goal"],
            "flag": v["flag"], "failure_type": v["failure_type"], "confidence": v["confidence"],
            "reasoning": v["reasoning"]})
    except requests.RequestException as e:
        print(f"webhook failed: {e}")


def create_app(store: Store | None = None, *, allow_spend: bool = False, max_usd: float = 0.10,
               dry_run: bool = False, ledger_path: str | Path | None = None) -> FastAPI:
    store = store or Store()
    store.summary()  # warm the database pages once at startup, so the first page load isn't a cold disk read
    app = FastAPI(title="Agent Verdict", version="0.1")
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                       allow_methods=["*"], allow_headers=["*"])
    # one client (one session cap) for the server's lifetime
    client = (api.make_client(dry_run=dry_run, max_usd=max_usd, ledger_path=ledger_path)
              if (allow_spend or dry_run) else None)

    @app.get("/api/summary")
    def summary():
        s = store.summary()
        s["spend"] = ({"session_usd": client.ledger.session_spent, "total_usd": client.ledger.total_spent,
                       "cap_usd": client.ledger.cap_usd, "session_cap_usd": client.ledger.session_cap_usd}
                      if client else None)
        s["judging_enabled"] = client is not None
        return s

    @app.get("/api/queue")
    def queue(status: Literal["to_review", "reviewed", "auto", "all"] = "to_review",
              flag: Literal["yellow", "green", "red"] | None = None,
              benchmark: str | None = None, q: str | None = None,
              limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
        rows, total = store.queue(status=status, flag_=flag, benchmark=benchmark, q=q, limit=limit, offset=offset)
        return {"total": total, "items": rows}

    @app.get("/api/featured")
    def featured():
        """The run the front page previews (a flagged "claimed done, but failed" run)."""
        rid = store.featured()
        return {"id": rid, "run": store.run(rid) if rid else None}

    @app.get("/api/live")
    def live(limit: int = Query(30, ge=1, le=200)):
        """Runs from your own agents (anything not from the benchmark), newest first; verdict is null
        while a run waits to be judged. The Live screen polls this."""
        return {"items": store.recent(limit=limit), "judging_enabled": client is not None}

    @app.get("/api/runs/{run_id}")
    def run(run_id: int):
        r = store.run(run_id)
        if not r:
            raise HTTPException(404, "run not found")
        return r

    @app.get("/api/runs/{run_id}/screens/{state}")
    def screen(run_id: int, state: int):
        p = store.screen_path(run_id, state)
        if not p or not p.exists():
            raise HTTPException(404, "no screenshot for that state")
        # a run's screenshots never change once stored, so let the browser keep them
        return FileResponse(p, headers={"Cache-Control": "public, max-age=86400"})

    @app.post("/api/runs/{run_id}/review")
    def review(run_id: int, body: ReviewIn):
        if body.failure_type is not None and body.failure_type not in FAILURE_TYPES:
            raise HTTPException(422, f"failure_type must be one of {FAILURE_TYPES}")
        try:
            return store.add_review(run_id, body.decision, body.success, failure_type=body.failure_type,
                                    note=body.note, reviewer=body.reviewer)
        except KeyError:
            raise HTTPException(404, "run not found") from None

    @app.post("/api/runs")
    def import_run(body: TraceIn):
        """Import a run (free). Judge it with POST /api/runs/{id}/judge."""
        with tempfile.TemporaryDirectory() as tmp:  # screenshots must be inline; no paths
            try:
                trace = from_generic(body.model_dump(), Path(tmp))
            except (OSError, ValueError) as e:
                raise HTTPException(422, f"bad trace: {e}") from None
        if not trace.steps:
            raise HTTPException(422, "the run has no steps")
        safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in body.key)
        screens = {i: save_data_url(u, screens_dir(store) / safe / f"state_{i}") for i, u in trace.screenshots.items()}
        run_id = store.add_run(body.key, trace, source=body.source, screens=screens, agent=body.agent)
        return {"id": run_id}

    @app.post("/api/runs/{run_id}/judge")
    def judge(run_id: int, effort: str = api.DEFAULT_EFFORT, frames: int = api.DEFAULT_FRAMES):
        if client is None:
            raise HTTPException(403, "judging is off: start the server with --allow-spend (or --dry-run)")
        r = store.run(run_id)
        if not r:
            raise HTTPException(404, "run not found")
        trace = _trace_from_store(store, r)
        try:
            res = api.judge(trace, client=client, effort=effort, frames=frames, run_key=r["key"])
        except BudgetExceeded as e:
            raise HTTPException(402, f"spend cap reached, nothing was sent: {e}") from None
        if res.get("error"):
            raise HTTPException(502, res["error"])
        judge_name = f"v2-{effort}-f{frames}" + ("-dryrun" if client.dry_run else "")
        store.add_verdict(run_id, judge_name, res)
        out = store.run(run_id)
        if out["verdict"]["needs_review"]:
            _notify(out)
        return out

    # The review UI: the built frontend (cd frontend; npm run build) at /. Without a build, / points
    # to the API docs; during UI development use the Vite dev server instead (npm run dev, :5173).
    if (UI_DIST / "index.html").exists():
        app.mount("/", StaticFiles(directory=UI_DIST, html=True), name="ui")
    else:
        @app.get("/", include_in_schema=False)
        def root():
            return RedirectResponse("/docs")

    return app


def _trace_from_store(store: Store, r: dict):
    """Rebuild a Trace (with screenshots as data URLs) from a stored run."""
    import base64
    import mimetypes

    from .trace import Step, Trace
    shots = {}
    for i in r["screens"]:
        p = store.screen_path(r["id"], i)
        if p and p.exists():
            mime = mimetypes.guess_type(p.name)[0] or "image/png"
            shots[i] = f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode()
    steps = [Step(s["n"], s["url"], s["action"], s["reasoning"]) for s in r["steps"]]
    return Trace(goal=r["goal"], steps=steps, final_screenshot=shots.get(r["n_states"] - 1), screenshots=shots)
