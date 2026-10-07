"""RunSnapshot: projection of an event stream, plus the pure reducer shared with the UI."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from runway.core.events import Event
from runway.core.states import RunStatus, TaskStatus


class AttemptState(BaseModel):
    n: int
    kind: str = "initial"
    outcome: str = "in_flight"  # in_flight | accepted | rejected | error | aborted
    tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    issue_count: int = 0
    issues: list[dict[str, Any]] = Field(default_factory=list)
    proposal_artifact_id: str | None = None
    feedback_artifact_id: str | None = None
    proposal_fingerprint: str = ""


class TaskState(BaseModel):
    status: TaskStatus = TaskStatus.PENDING
    attempts: list[AttemptState] = Field(default_factory=list)
    cache_key: str | None = None
    cache_components: dict[str, str] = Field(default_factory=dict)
    from_run_id: str | None = None
    artifact_id: str | None = None
    error_code: str | None = None
    tokens: int = 0
    cost_usd: float = 0.0
    duration_ms: int = 0
    started_ts: datetime | None = None


class RunInfo(BaseModel):
    run_id: str
    graph_id: str = ""
    graph_hash: str = ""
    entrypoint: str | None = None
    input_artifact_id: str = ""
    parent_run_id: str | None = None
    replay_from: str | None = None
    status: RunStatus = RunStatus.CREATED
    started_at: datetime | None = None
    ended_at: datetime | None = None
    created_at: datetime | None = None
    error_code: str | None = None


class Meter(BaseModel):
    used: float = 0
    limit: float | None = None


class RunSnapshot(BaseModel):
    seq: int = 0
    run: RunInfo
    graph: dict[str, Any] = Field(default_factory=dict)
    tasks: dict[str, TaskState] = Field(default_factory=dict)
    totals: dict[str, float] = Field(default_factory=lambda: {"tokens": 0, "cost_usd": 0.0, "duration_ms": 0})
    budget: dict[str, Meter] = Field(default_factory=dict)
    breach: dict[str, Any] | None = None


def initial_snapshot(run_id: str) -> RunSnapshot:
    return RunSnapshot(run=RunInfo(run_id=run_id))


def _attempt(ts: TaskState, n: int | None) -> AttemptState | None:
    if n is None:
        return None
    return next((a for a in reversed(ts.attempts) if a.n == n), None)


def apply_event(snap: RunSnapshot, ev: Event) -> RunSnapshot:
    """Pure reducer: returns a new snapshot. Must stay in sync with ui/src/lib/reducer.ts."""
    s = snap.model_copy(deep=True)
    s.seq = ev.seq
    d = ev.data
    t = ev.type
    ts = s.tasks.get(ev.task_name) if ev.task_name else None
    if t == "run.created":
        s.run = RunInfo(
            run_id=ev.run_id,
            graph_id=d["graph_id"],
            graph_hash=d["graph_hash"],
            entrypoint=d.get("entrypoint"),
            input_artifact_id=d["input_artifact_id"],
            parent_run_id=d.get("parent_run_id"),
            replay_from=d.get("replay_from"),
            status=RunStatus.CREATED,
            created_at=ev.ts,
        )
        s.graph = d.get("graph", {})
        s.tasks = {n["name"]: TaskState() for n in s.graph.get("nodes", [])}
        b = d.get("budget", {})
        s.budget = {
            "tokens": Meter(limit=b.get("max_tokens")),
            "cost_usd": Meter(limit=b.get("max_cost_usd")),
        }
    elif t == "run.started":
        s.run.status, s.run.started_at = RunStatus.RUNNING, ev.ts
    elif t in ("run.completed", "run.failed"):
        s.run.status = RunStatus(d["status"])
        s.run.ended_at = ev.ts
        s.run.error_code = d.get("error_code")
        s.totals = dict(d["totals"])
    elif t == "run.cancelled":
        s.run.status, s.run.ended_at = RunStatus.CANCELLED, ev.ts
    elif ts is not None:
        _apply_task_event(s, ts, ev)
    if t == "budget.exceeded":
        s.breach = {
            "scope": d["scope"],
            "dimension": d["dimension"],
            "used": d["used"],
            "limit": d["limit"],
            "task": ev.task_name,
        }
    return s


def _apply_task_event(s: RunSnapshot, ts: TaskState, ev: Event) -> None:
    d, t = ev.data, ev.type
    att = _attempt(ts, ev.attempt_no)
    if t == "task.ready":
        ts.status = TaskStatus.READY
    elif t == "task.started":
        ts.status, ts.cache_key, ts.started_ts = TaskStatus.RUNNING, d["cache_key"], ev.ts
        ts.cache_components = d["cache_components"]
    elif t == "task.cached":
        ts.status, ts.from_run_id, ts.artifact_id = TaskStatus.CACHED, d["from_run_id"], d["artifact_id"]
        ts.cache_key, ts.cache_components = d["cache_key"], d["cache_components"]
    elif t == "task.committed":
        ts.status, ts.artifact_id = TaskStatus.COMMITTED, d["artifact_id"]
        ts.duration_ms = d["duration_ms"]
    elif t == "task.failed":
        ts.status, ts.error_code = TaskStatus.FAILED, d["error_code"]
    elif t == "task.skipped":
        ts.status = TaskStatus.SKIPPED
    elif t == "attempt.started":
        ts.attempts.append(AttemptState(n=ev.attempt_no or len(ts.attempts) + 1, kind=d["kind"]))
        ts.status = TaskStatus.RUNNING
    elif t == "attempt.aborted" and att:
        att.outcome = "aborted"
    elif t == "model.generated" and att:
        att.tokens, att.cost_usd, att.latency_ms = (
            d["prompt_tokens"] + d["completion_tokens"],
            d["cost_usd"],
            d["latency_ms"],
        )
        att.proposal_artifact_id = d.get("proposal_artifact_id")
        ts.tokens += att.tokens
        ts.cost_usd += att.cost_usd
        s.totals["tokens"] += att.tokens
        s.totals["cost_usd"] += att.cost_usd
        s.budget["tokens"].used = s.totals["tokens"]
        s.budget["cost_usd"].used = s.totals["cost_usd"]
    elif t == "validation.started":
        ts.status = TaskStatus.VALIDATING
    elif t == "validation.passed" and att:
        att.outcome = "accepted"
    elif t == "validation.failed" and att:
        att.outcome = "rejected"
        att.issues = [i for r in d["results"] for i in r["issues"]]
        att.issue_count = len(att.issues)
        att.proposal_fingerprint = d.get("proposal_fingerprint", "")
    elif t == "validation.errored" and att:
        att.outcome = "error"
    elif t == "agent.retry":
        ts.status = TaskStatus.REPAIRING
        prev = _attempt(ts, (ev.attempt_no or 0))
        if prev:
            prev.feedback_artifact_id = d["feedback_artifact_id"]
