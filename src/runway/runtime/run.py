"""Run: executes a WorkGraph, owns the event log, workspace, budgets, and replay."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from runway.adapters.redact_default import DefaultRedactor
from runway.core.artifact import make_record
from runway.core.budget import Limits
from runway.core.errors import BudgetExceededError, ConfigError, TaskFailed
from runway.core.graph import WorkGraph
from runway.core.states import OK_TASK, RunStatus, TaskStatus
from runway.core.task import Task
from runway.core.validation import ValidationContext
from runway.extensions.hooks import Listener
from runway.ports.artifacts import ArtifactStore
from runway.ports.clock import Clock, IdGenerator, SystemClock, UuidIds
from runway.ports.events import EventStore
from runway.ports.llm import LLMClient
from runway.ports.redact import Redactor
from runway.runtime.budget_gate import BudgetLedger
from runway.runtime.cache_key import cache_key, cache_parts, input_refs
from runway.runtime.emitter import Emitter
from runway.runtime.repair import RepairLoop
from runway.runtime.replay import ReplayPlan, plan_replay
from runway.runtime.workspace import Workspace


@dataclass
class RunResult:
    run_id: str
    status: RunStatus
    outputs: dict[str, BaseModel] = field(default_factory=dict)
    error_code: str | None = None


class Run:
    def __init__(
        self,
        graph: WorkGraph,
        store: EventStore,
        artifacts: ArtifactStore,
        llm: LLMClient,
        *,
        clock: Clock | None = None,
        ids: IdGenerator | None = None,
        redactor: Redactor | None = None,
        max_concurrency: int = 4,
        run_limits: Limits | None = None,
        entrypoint: str | None = None,
        plugins: dict[str, str] | None = None,
        listeners: list[Listener] | None = None,
    ) -> None:
        self.listeners = listeners or []
        self.graph, self.store, self.artifacts, self.llm = graph, store, artifacts, llm
        self.clock = clock or SystemClock()
        self.ids = ids or UuidIds()
        self.redactor = redactor or DefaultRedactor()
        self.max_concurrency = max_concurrency
        self.run_limits = run_limits or Limits(max_cost_usd=10.0, max_tokens=1_000_000)
        self.entrypoint = entrypoint
        self.plugins = plugins or {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._cancelled = False

    def cancel(self) -> None:
        """Graceful cancel: in-flight attempts are aborted; the run stays replayable."""
        self._cancelled = True
        for t in self._tasks.values():
            t.cancel()

    # --- public entry points -------------------------------------------------------
    async def execute(self, run_input: BaseModel) -> RunResult:
        self.graph.compile()
        if self.graph.input_model and not isinstance(run_input, self.graph.input_model):
            raise ConfigError(f"run input must be {self.graph.input_model.__name__}")
        rec = make_record(run_input)
        self.artifacts.put(rec)
        return await self._run(run_input, rec.artifact_id, None, None)

    def plan_replay(self, parent_run_id: str, from_task: str) -> ReplayPlan:
        parent = self.store.snapshot(parent_run_id)
        if parent is None:
            raise ConfigError(f"unknown run {parent_run_id!r}")
        return plan_replay(self.graph, parent, from_task)

    async def replay(self, parent_run_id: str, from_task: str, *, allow_stale: bool = False) -> RunResult:
        """Child run: reuse verified upstream outputs, re-run ``from_task`` and downstream."""
        plan = self.plan_replay(parent_run_id, from_task)
        if not allow_stale:
            plan.raise_if_stale()
        parent = self.store.snapshot(parent_run_id)
        assert parent is not None
        if not self.graph.input_model:
            raise ConfigError("replay requires graph.input_model")
        record = self.artifacts.get(parent.run.input_artifact_id)
        run_input = self.graph.input_model.model_validate(record.payload)
        return await self._run(run_input, parent.run.input_artifact_id, plan, parent_run_id)

    # --- internals -----------------------------------------------------------------
    async def _run(
        self, run_input: BaseModel, input_id: str, plan: ReplayPlan | None, parent_id: str | None
    ) -> RunResult:
        run_id = self.ids.run_id()
        em = Emitter(self.store, run_id, self.redactor, self.listeners)
        ledger = BudgetLedger(self.run_limits, em.emit)
        ws = Workspace(input_id, run_input)
        t0 = self.clock.now()
        em.emit(
            "run.created",
            {
                "graph_id": self.graph.name,
                "graph_hash": self.graph.graph_hash(),
                "entrypoint": self.entrypoint,
                "input_artifact_id": input_id,
                "parent_run_id": parent_id,
                "replay_from": plan.from_task if plan else None,
                "budget": self.run_limits.model_dump(),
                "graph": self.graph.describe(),
                "plugins": self.plugins,
            },
        )
        em.emit("run.started")
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.run_limits.max_time_s if self.run_limits.max_time_s else None
        status: dict[str, TaskStatus] = {n: TaskStatus.PENDING for n in self.graph.tasks}
        done = {n: asyncio.Event() for n in self.graph.tasks}
        sem = asyncio.Semaphore(self.max_concurrency)
        failures: list[tuple[str, str]] = []
        repair = RepairLoop(self.llm, em, ledger, self.artifacts, deadline)

        def finish(name: str, st: TaskStatus) -> None:
            status[name] = st
            done[name].set()

        async def node(name: str) -> None:
            task = self.graph.tasks[name]
            try:
                await asyncio.gather(*(done[d].wait() for d in self.graph.upstream(name)))
                bad = next((d for d in self.graph.upstream(name) if status[d] not in OK_TASK), None)
                if bad:
                    em.emit("task.skipped", {"caused_by_task": bad}, task=name)
                    return finish(name, TaskStatus.SKIPPED)
                em.emit("task.ready", {"deps": self.graph.upstream(name)}, task=name)
                status[name] = TaskStatus.READY
                if plan and name in plan.reuse_info:
                    self._reuse(em, ws, task, plan, parent_id or "")
                    return finish(name, TaskStatus.CACHED)
                async with sem:
                    await self._execute_task(em, ws, ledger, repair, task, run_id)
                finish(name, TaskStatus.COMMITTED)
            except asyncio.CancelledError:
                if status[name] not in OK_TASK | {TaskStatus.FAILED, TaskStatus.SKIPPED}:
                    if status[name] in (TaskStatus.PENDING,):
                        em.emit("task.skipped", {"caused_by_task": failures[0][0] if failures else "run"}, task=name)
                        finish(name, TaskStatus.SKIPPED)
                    else:
                        em.emit("task.failed", {"error_code": "CANCELLED"}, task=name)
                        finish(name, TaskStatus.FAILED)
                raise
            except TaskFailed as e:
                failures.append((name, e.error_code))
                em.emit("task.failed", {"error_code": e.error_code, "attempts": e.attempts}, task=name)
                finish(name, TaskStatus.FAILED)
                for other, t in self._tasks.items():
                    if other != name and not t.done():
                        t.cancel()

        order = self.graph.compile()
        self._tasks = {n: asyncio.create_task(node(n)) for n in order}
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)

        for name in order:  # nodes cancelled before they ever started
            if status[name] == TaskStatus.PENDING:
                em.emit("task.skipped", {"caused_by_task": failures[0][0] if failures else "run"}, task=name)
                status[name] = TaskStatus.SKIPPED
        totals = {
            "tokens": ledger.run_usage.tokens,
            "cost_usd": ledger.run_usage.cost_usd,
            "duration_ms": int((self.clock.now() - t0).total_seconds() * 1000),
        }
        outputs = {n: ws.output(n) for n, s in status.items() if s in OK_TASK}
        if self._cancelled:
            em.emit("run.cancelled")
            return RunResult(run_id, RunStatus.CANCELLED, outputs)
        if failures:
            code = failures[0][1]
            st = RunStatus.BUDGET_EXCEEDED if code == BudgetExceededError.code else RunStatus.FAILED
            em.emit("run.failed", {"status": st.value, "error_code": code, "totals": totals})
            return RunResult(run_id, st, outputs, code)
        em.emit("run.completed", {"status": "SUCCEEDED", "totals": totals})
        return RunResult(run_id, RunStatus.SUCCEEDED, outputs)

    def _reuse(self, em: Emitter, ws: Workspace, task: Task, plan: ReplayPlan, parent_id: str) -> None:
        info = plan.reuse_info[task.name]
        rec = self.artifacts.get(info.artifact_id)
        ws._commit(task.name, info.artifact_id, task.output_model.model_validate(rec.payload))
        em.emit(
            "task.cached",
            {
                "from_run_id": parent_id,
                "artifact_id": info.artifact_id,
                "cache_key": info.cache_key,
                "cache_components": info.parts,
            },
            task=task.name,
        )

    async def _execute_task(
        self, em: Emitter, ws: Workspace, ledger: BudgetLedger, repair: RepairLoop, task: Task, run_id: str
    ) -> None:
        started = self.clock.now()
        binds = self.graph.bindings[task.name]
        task_input = ws.assemble_input(task, binds)
        refs = input_refs(binds, ws.artifact_ids())
        parts = cache_parts(task, refs)
        input_ids = sorted({v.split(":")[0] for v in refs.values()})
        em.emit(
            "task.started",
            {"cache_key": cache_key(parts), "cache_components": parts, "input_artifact_ids": input_ids},
            task=task.name,
        )
        ctx = ValidationContext(
            run_id=run_id, task_name=task.name, inputs={"input": task_input.model_dump(mode="json")}
        )
        outcome = await repair.run(task, task_input, input_ids, ctx)
        # The ONLY commit path (Invariant 2): reached after every validator accepted.
        ws._commit(task.name, outcome.artifact_id, outcome.proposal)
        use = ledger.usage(task.name)
        em.emit(
            "task.committed",
            {
                "artifact_id": outcome.artifact_id,
                "attempts": outcome.attempts,
                "tokens": use.tokens,
                "cost_usd": use.cost_usd,
                "duration_ms": int((self.clock.now() - started).total_seconds() * 1000),
            },
            task=task.name,
        )


__all__: list[Any] = ["Run", "RunResult"]
