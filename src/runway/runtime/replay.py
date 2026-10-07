"""Replay planning: decide which tasks to reuse from a parent run and which to re-run."""

from __future__ import annotations

from pydantic import BaseModel, Field

from runway.core.errors import ReplayStaleError
from runway.core.graph import WorkGraph
from runway.core.snapshot import RunSnapshot
from runway.core.states import OK_TASK
from runway.runtime.cache_key import cache_key, cache_parts, diff_parts, input_refs


class ReuseInfo(BaseModel):
    artifact_id: str
    cache_key: str
    parts: dict[str, str]


class StaleTask(BaseModel):
    task: str
    reason: str


class ReplayPlan(BaseModel):
    from_task: str
    reuse: list[str]
    rerun: list[str]
    stale: list[StaleTask] = Field(default_factory=list)
    estimated_cost_usd_max: float = 0.0
    reuse_info: dict[str, ReuseInfo] = Field(default_factory=dict)

    def raise_if_stale(self) -> None:
        if self.stale:
            names = ", ".join(f"{s.task} ({s.reason})" for s in self.stale)
            raise ReplayStaleError(f"stale upstream tasks: {names}")


def plan_replay(graph: WorkGraph, parent: RunSnapshot, from_task: str) -> ReplayPlan:
    """Pure planning step; never calls a model. Requires ``graph.compile()`` to have run."""
    if from_task not in graph.tasks:
        raise ValueError(f"unknown task {from_task!r}")
    order = graph.compile()
    rerun = {from_task} | graph.descendants(from_task)
    ids: dict[str | None, str] = {None: parent.run.input_artifact_id}
    reuse_info: dict[str, ReuseInfo] = {}
    stale: list[StaleTask] = []
    for name in order:
        if name in rerun:
            continue
        task, ps = graph.tasks[name], parent.tasks.get(name)
        if ps is None or ps.status not in OK_TASK or not ps.artifact_id:
            reason = "no committed output in parent run"
        else:
            parts = cache_parts(task, input_refs(graph.bindings[name], ids))
            key = cache_key(parts)
            if key == ps.cache_key:
                ids[name] = ps.artifact_id
                reuse_info[name] = ReuseInfo(artifact_id=ps.artifact_id, cache_key=key, parts=parts)
                continue
            changed = diff_parts(ps.cache_components, parts)
            reason = "changed: " + ", ".join(changed) if changed else "cache key mismatch"
        stale.append(StaleTask(task=name, reason=reason))
        rerun |= {name} | graph.descendants(name)
    rerun_ordered = [n for n in order if n in rerun]
    cost = sum(graph.tasks[n].budget.max_cost_usd or 0.0 for n in rerun_ordered)
    return ReplayPlan(
        from_task=from_task,
        reuse=[n for n in order if n in reuse_info],
        rerun=rerun_ordered,
        stale=stale,
        estimated_cost_usd_max=cost,
        reuse_info=reuse_info,
    )
