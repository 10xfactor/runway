"""Generate golden event streams + snapshots for the UI mock mode and reducer tests.

Usage: uv run python scripts/gen_fixtures.py
Deterministic: FakeClock, CountingIds, scripted FakeLLM. Validator wall-clock durations are zeroed.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path

from pydantic import BaseModel

from runway.adapters.artifacts_fs import FsArtifactStore
from runway.adapters.events_sqlite import SqliteEventStore
from runway.adapters.llm_fake import FakeLLMClient
from runway.api import agent
from runway.api.flow import Flow
from runway.core.budget import Limits
from runway.core.graph import WorkGraph
from runway.ports.clock import CountingIds, FakeClock
from runway.runtime.run import Run
from runway.validators import references_exist

OUT = Path(__file__).resolve().parent.parent / "fixtures" / "scenarios"


class Src(BaseModel):
    raw_fields: dict[str, str]


class Silver(BaseModel):
    lineage_map: dict[str, str]


lineage = references_exist(
    lambda o: [(f"lineage_map.{k}", v) for k, v in o.lineage_map.items()],
    lambda o, ctx: set(ctx.inputs["input"]["raw_fields"]),
    code="lineage",
    name="lineage",
)
SRC = Src(raw_fields={"id": "int", "total": "float"})


def architect(retries: int = 3, **limits: float) -> object:
    @agent(model="demo-model", validators=[lineage], budget=Limits(max_retries=retries, **limits))  # type: ignore[arg-type]
    def architect(inp: Src) -> Silver:
        """Design a silver model."""

    return architect


def single(task: object) -> WorkGraph:
    g = WorkGraph("single", input_model=Src)
    g.add(task)  # type: ignore[arg-type]
    return g


def silver(**m: str) -> Silver:
    return Silver(lineage_map=m)


def export(store: SqliteEventStore, run_id: str, name: str) -> None:
    events = []
    for ev in store.read(run_id, limit=10**9):
        d = json.loads(ev.model_dump_json())
        for r in d["data"].get("results", []):
            r["duration_ms"] = 0
        events.append(d)
    (OUT / f"{name}.jsonl").write_text("\n".join(json.dumps(e, sort_keys=True) for e in events) + "\n")
    snap = store.snapshot(run_id)
    assert snap is not None
    (OUT / f"{name}.snapshot.json").write_text(
        json.dumps(json.loads(snap.model_dump_json()), indent=2, sort_keys=True) + "\n"
    )


def make_run(tmp: Path, graph: WorkGraph, llm: FakeLLMClient, **kw: object) -> tuple[SqliteEventStore, Run]:
    clock = FakeClock()
    store = SqliteEventStore(tmp / "r.db", clock)
    run = Run(graph, store, FsArtifactStore(tmp / "b"), llm, clock=clock, ids=CountingIds(), **kw)  # type: ignore[arg-type]
    return store, run


async def scenarios() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, build in {
        "happy_path": lambda: (single(architect()), FakeLLMClient([silver(a="id")])),
        "retries_exhausted": lambda: (
            single(architect(retries=2)),
            FakeLLMClient([silver(a="x1"), silver(a="x2"), silver(a="x3")]),
        ),
        "budget_exceeded": lambda: (single(architect(max_tokens=60)), FakeLLMClient([silver(a="x1"), silver(a="id")])),
    }.items():
        with tempfile.TemporaryDirectory() as t:
            graph, llm = build()
            store, run = make_run(Path(t), graph, llm)
            res = await run.execute(SRC)
            export(store, res.run_id, name)
            store.close()
    # Demo flow scenarios (parallel fan-out/fan-in + repair + replay)
    from runway import demo

    os.environ["RUNWAY_DEMO_DELAY"] = "0"
    for name, fail in (("repair_then_pass", None), ("task_failed", "report")):
        with tempfile.TemporaryDirectory() as t:
            if fail:
                os.environ["RUNWAY_DEMO_FAIL"] = fail
            else:
                os.environ.pop("RUNWAY_DEMO_FAIL", None)
            flow: Flow = demo.flow()
            store, run = make_run(Path(t), flow.graph, flow.llm)  # type: ignore[arg-type]
            res = await run.execute(flow.input)
            export(store, res.run_id, name)
            if fail:
                os.environ.pop("RUNWAY_DEMO_FAIL", None)
                flow2 = demo.flow()
                run2 = Run(
                    flow2.graph, store, FsArtifactStore(Path(t) / "b"), flow2.llm, clock=store.clock, ids=run.ids
                )  # type: ignore[arg-type]
                child = await run2.replay(res.run_id, "report")
                export(store, child.run_id, "cached_replay")
            store.close()


if __name__ == "__main__":
    asyncio.run(scenarios())
    print(f"wrote scenarios to {OUT}")
