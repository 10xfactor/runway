"""Runway Console server: read API + SSE over the local store, plus a few control endpoints."""

from __future__ import annotations

import asyncio
import os
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from runway import __version__
from runway.adapters.artifacts_fs import FsArtifactStore
from runway.adapters.events_sqlite import SqliteEventStore
from runway.api.flow import load_flow
from runway.core.errors import RunwayError
from runway.core.snapshot import RunSnapshot
from runway.core.states import OK_TASK, TERMINAL_RUN
from runway.core.validation import ValidationIssue, ValidationResult
from runway.core.validation import render_feedback as render
from runway.runtime.replay import plan_replay
from runway.server.diffing import diff_paths
from runway.server.procs import Procs
from runway.server.security import Guard, new_token

STATIC = Path(__file__).parent / "static"


class ReplayBody(BaseModel):
    from_task: str
    allow_stale: bool = False


def summary(s: RunSnapshot) -> dict[str, Any]:
    ok = sum(1 for t in s.tasks.values() if t.status in OK_TASK)
    return {
        "run_id": s.run.run_id,
        "graph_id": s.run.graph_id,
        "status": s.run.status.value,
        "created_at": s.run.created_at,
        "started_at": s.run.started_at,
        "ended_at": s.run.ended_at,
        "parent_run_id": s.run.parent_run_id,
        "replay_from": s.run.replay_from,
        "totals": s.totals,
        "tasks_ok": ok,
        "tasks_total": len(s.tasks),
        "tasks_failed": sum(1 for t in s.tasks.values() if t.status == "FAILED"),
        "retries": sum(max(len(t.attempts) - 1, 0) for t in s.tasks.values()),
        "error_code": s.run.error_code,
    }


def create_app(home: Path, token: str, expose_payloads: bool = False, hosts: set[str] | None = None) -> FastAPI:
    store = SqliteEventStore(home / "runway.db")
    artifacts = FsArtifactStore(home / "blobs")
    procs = Procs(home, store)
    app = FastAPI(title="Runway Console", docs_url=None, redoc_url=None)
    app.add_middleware(Guard, token=token, allowed_hosts=hosts or {"127.0.0.1", "localhost"})
    api = APIRouter(prefix="/api")

    def snap(run_id: str) -> RunSnapshot:
        s = store.snapshot(run_id)
        if s is None:
            raise HTTPException(404, "unknown run")
        return s

    @api.get("/health")
    def health() -> dict[str, Any]:
        return {"version": __version__, "payloads_exposed": expose_payloads}

    @api.get("/runs")
    def list_runs(limit: int = 50, offset: int = 0, status: str | None = None) -> list[dict[str, Any]]:
        return [summary(s) for s in store.list_runs(limit, status, offset)]

    @api.get("/runs/{run_id}/snapshot")
    def snapshot(run_id: str) -> RunSnapshot:
        return snap(run_id)

    @api.get("/runs/{run_id}/events")
    def events(
        run_id: str, after_seq: int = 0, limit: int = 1000, types: str | None = None, task: str | None = None
    ) -> Any:
        snap(run_id)
        return store.read(run_id, after_seq, min(limit, 5000), types.split(",") if types else None, task)

    @api.get("/runs/{run_id}/stream")
    async def stream(run_id: str, request: Request, after: int = 0) -> EventSourceResponse:
        snap(run_id)
        last = int(request.headers.get("last-event-id") or after)

        async def gen() -> Any:
            nonlocal last
            while True:
                batch = store.read(run_id, last, 500)
                for ev in batch:
                    last = ev.seq
                    yield {"id": str(ev.seq), "event": ev.type, "data": ev.model_dump_json()}
                if not batch:
                    s = store.snapshot(run_id)
                    if s and s.run.status in TERMINAL_RUN:
                        yield {"event": "stream.end", "data": "{}"}
                        return
                    await asyncio.sleep(0.15)
                if await request.is_disconnected():
                    return

        return EventSourceResponse(gen(), ping=15)

    @api.get("/runs/{run_id}/tasks/{task}")
    def task_detail(run_id: str, task: str) -> dict[str, Any]:
        s = snap(run_id)
        ts = s.tasks.get(task)
        if ts is None:
            raise HTTPException(404, "unknown task")
        node: dict[str, Any] = next((n for n in s.graph.get("nodes", []) if n["name"] == task), {})
        attempts = []
        for a in ts.attempts:
            d = a.model_dump()
            issues = [ValidationIssue.model_validate(i) for i in a.issues]
            d["feedback_preview"] = render([ValidationResult.reject("rejected", issues=issues)]) if issues else ""
            if expose_payloads and a.feedback_artifact_id and artifacts.exists(a.feedback_artifact_id):
                d["feedback_text"] = artifacts.get(a.feedback_artifact_id).payload["text"]
            attempts.append(d)
        return {"task": task, "state": ts.model_dump(mode="json") | {"attempts": attempts}, "node": node}

    @api.get("/runs/{run_id}/attempts/{task}/{n}/diff")
    def attempt_diff(run_id: str, task: str, n: int) -> dict[str, Any]:
        s = snap(run_id)
        att = {a.n: a for a in s.tasks[task].attempts}
        cur, prev = att.get(n), att.get(n - 1)
        if not cur or not prev or not cur.proposal_artifact_id or not prev.proposal_artifact_id:
            return {"changes": [], "available": False}
        a, b = artifacts.get(prev.proposal_artifact_id).payload, artifacts.get(cur.proposal_artifact_id).payload
        failing = {i["path"] for i in prev.issues}
        changes = diff_paths(a, b, values=expose_payloads)
        still = {i["path"] for i in cur.issues}
        return {
            "available": True,
            "changes": changes,
            "fixed_paths": sorted(failing - still),
            "still_failing_paths": sorted(failing & still),
            "new_failing_paths": sorted(still - failing),
        }

    @api.get("/artifacts/{artifact_id}")
    def artifact(artifact_id: str, meta: bool = False) -> Any:
        if not artifacts.exists(artifact_id):
            raise HTTPException(404, "unknown artifact")
        rec = artifacts.get(artifact_id)
        info = rec.model_dump(exclude={"payload"})
        if meta:
            return info
        if not expose_payloads:
            raise HTTPException(403, "payloads are hidden; start with `runway dev --expose-payloads`")
        return rec

    @api.post("/runs/{run_id}/cancel")
    def cancel(run_id: str) -> dict[str, bool]:
        snap(run_id)
        if not procs.cancel(run_id):
            raise HTTPException(409, "run is not controllable from this server")
        return {"cancelled": True}

    def _plan(run_id: str, body: ReplayBody) -> Any:
        s = snap(run_id)
        if not s.run.entrypoint:
            raise HTTPException(409, "run has no entrypoint; cannot plan replay")
        sys.path.insert(0, os.getcwd())
        try:
            flow = load_flow(s.run.entrypoint)
            flow.graph.compile()
            return plan_replay(flow.graph, s, body.from_task)
        except (RunwayError, ValueError, ImportError, AttributeError) as e:
            raise HTTPException(422, type(e).__name__) from e

    @api.post("/runs/{run_id}/replay/plan")
    def replay_plan(run_id: str, body: ReplayBody) -> Any:
        return _plan(run_id, body).model_dump(exclude={"reuse_info"})

    @api.post("/runs/{run_id}/replay")
    def replay_start(run_id: str, body: ReplayBody) -> dict[str, str]:
        plan = _plan(run_id, body)
        if plan.stale and not body.allow_stale:
            raise HTTPException(409, "stale upstream tasks; set allow_stale")
        args = ["replay", run_id, "--from", body.from_task] + (["--allow-stale"] if body.allow_stale else [])
        child = procs.spawn(args, lambda s: s.run.parent_run_id == run_id and s.run.replay_from == body.from_task)
        return {"child_run_id": child}

    @api.post("/demo/start")
    def demo_start(fail_at: str | None = None) -> dict[str, str]:
        args = ["demo"] + (["--fail-at", fail_at] if fail_at else [])
        return {"run_id": procs.spawn(args, lambda s: s.run.graph_id == "offline_demo")}

    @api.get("/compare")
    def compare(a: str, b: str) -> dict[str, Any]:
        sa, sb = snap(a), snap(b)
        rows = []
        for name in sorted(set(sa.tasks) | set(sb.tasks)):
            ta, tb = sa.tasks.get(name), sb.tasks.get(name)
            rows.append(
                {
                    "task": name,
                    "a": ta
                    and {
                        "status": ta.status,
                        "attempts": len(ta.attempts),
                        "cost_usd": ta.cost_usd,
                        "duration_ms": ta.duration_ms,
                    },
                    "b": tb
                    and {
                        "status": tb.status,
                        "attempts": len(tb.attempts),
                        "cost_usd": tb.cost_usd,
                        "duration_ms": tb.duration_ms,
                    },
                    "same_output": bool(ta and tb and ta.artifact_id and ta.artifact_id == tb.artifact_id),
                }
            )
        return {"a": summary(sa), "b": summary(sb), "tasks": rows}

    app.include_router(api)

    if STATIC.exists():

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> Any:
            f = (STATIC / path).resolve()
            if path and f.is_file() and STATIC.resolve() in f.parents:
                return FileResponse(f)
            return FileResponse(STATIC / "index.html")
    else:

        @app.get("/", include_in_schema=False)
        def no_ui() -> JSONResponse:
            return JSONResponse({"detail": "Console UI not built. Run `pnpm build` in ui/ (see README)."})

    return app


def serve(home: Path, host: str, port: int, open_browser: bool = True, expose_payloads: bool = False) -> None:
    import uvicorn

    if host not in ("127.0.0.1", "localhost", "::1"):
        raise SystemExit("refusing to bind a non-loopback address; the Console is local-only")
    token = os.environ.get("RUNWAY_TOKEN") or new_token()
    url = f"http://{host}:{port}/#token={token}"
    print(f"Runway Console: {url}", flush=True)
    if expose_payloads:
        print("WARNING: artifact payloads are exposed in the Console", flush=True)
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    uvicorn.run(create_app(home, token, expose_payloads), host=host, port=port, log_level="warning")
