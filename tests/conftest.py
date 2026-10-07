"""Shared fixtures: tiny domain models and a deterministic runtime harness."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest
from pydantic import BaseModel

from runway.adapters.artifacts_fs import FsArtifactStore
from runway.adapters.events_sqlite import SqliteEventStore
from runway.adapters.llm_fake import FakeLLMClient
from runway.core.agent import Agent
from runway.core.budget import Limits
from runway.core.graph import WorkGraph
from runway.core.task import Task
from runway.core.validation import ValidationIssue, ValidationResult
from runway.ports.clock import CountingIds, FakeClock
from runway.runtime.run import Run


class Source(BaseModel):
    tables: list[str]
    raw_fields: dict[str, str]


class Silver(BaseModel):
    model_name: str
    lineage_map: dict[str, str]


class Report(BaseModel):
    summary: str


class ReportIn(BaseModel):
    model_name: str
    n_fields: int


SRC = Source(tables=["orders"], raw_fields={"id": "int", "total": "float"})
GOOD = Silver(model_name="orders_silver", lineage_map={"order_id": "id", "amount": "total"})
BAD = Silver(model_name="orders_silver", lineage_map={"order_id": "id", "amount": "missing_col"})


def lineage_validator(output: Silver, ctx) -> ValidationResult:  # type: ignore[no-untyped-def]
    raw = ctx.inputs["input"]["raw_fields"]
    missing = [v for v in output.lineage_map.values() if v not in raw]
    if missing:
        return ValidationResult.reject(
            "Lineage constraint violated",
            feedback=f"You mapped to fields {missing} which do not exist. Only use provided raw_fields.",
            issues=[ValidationIssue(code="lineage", path="lineage_map", message=f"unknown fields {missing}")],
        )
    return ValidationResult.accept()


def architect(retries: int = 3, validators: list | None = None, **limits) -> Task:  # type: ignore[type-arg]
    return Task(
        "architect",
        Agent(name="architect", system_prompt="Design silver models."),
        Source,
        Silver,
        validators=validators if validators is not None else [lineage_validator],
        budget=Limits(max_retries=retries, **limits),
    )


def single_graph(task: Task) -> WorkGraph:
    g = WorkGraph("g", input_model=Source)
    g.add(task)
    return g


@dataclass
class Harness:
    store: SqliteEventStore
    artifacts: FsArtifactStore
    root: Path
    ids: CountingIds = field(default_factory=CountingIds)

    def run(self, graph: WorkGraph, llm: FakeLLMClient, **kw) -> Run:  # type: ignore[no-untyped-def]
        return Run(graph, self.store, self.artifacts, llm, clock=self.store.clock, ids=self.ids, **kw)

    def types(self, run_id: str, task: str | None = None) -> list[str]:
        return [e.type for e in self.store.read(run_id, task=task)]


@pytest.fixture
def h(tmp_path: Path) -> Harness:
    clock = FakeClock()
    return Harness(SqliteEventStore(tmp_path / "runway.db", clock), FsArtifactStore(tmp_path / "blobs"), tmp_path)
