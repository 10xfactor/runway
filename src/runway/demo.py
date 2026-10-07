"""Bundled offline demo: no API key needed. A scripted model makes mistakes the validators catch and repair.

Env: RUNWAY_DEMO_DELAY (seconds per model call, default 0.7), RUNWAY_DEMO_FAIL=<task> (that task's output is
garbage, so you can try replay from a failed node).
"""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel

from runway.adapters.llm_fake import FakeLLMClient
from runway.api import Flow, agent
from runway.core.budget import Limits
from runway.core.graph import WorkGraph
from runway.core.task import input_field
from runway.core.validation import ValidationContext
from runway.ports.llm import GenerateRequest
from runway.validators import min_items, references_exist


class SourceSchema(BaseModel):
    tables: list[str]
    raw_fields: dict[str, str]


class Profile(BaseModel):
    row_estimate: int
    key_candidates: list[str]


class ArchitectIn(BaseModel):
    raw_fields: dict[str, str]
    key_candidates: list[str]


class SilverModel(BaseModel):
    model_name: str
    lineage_map: dict[str, str]


class QualityIn(BaseModel):
    key_candidates: list[str]


class QualityNotes(BaseModel):
    notes: list[str]


class ReportIn(BaseModel):
    model_name: str
    notes: list[str]


class Report(BaseModel):
    summary: str


@agent(model="demo-model", budget=Limits(max_retries=3, max_cost_usd=1.0))
def profile(src: SourceSchema) -> Profile:
    """Profile the source tables and propose key candidates."""


def _lineage(out: SilverModel, ctx: ValidationContext) -> set[str]:
    return set(ctx.inputs["input"]["raw_fields"])


lineage = references_exist(
    lambda out: [(f"lineage_map.{k}", v) for k, v in out.lineage_map.items()], _lineage, code="lineage", name="lineage"
)


@agent(model="demo-model", validators=[lineage], budget=Limits(max_retries=3, max_cost_usd=1.0))
def architect(inp: ArchitectIn) -> SilverModel:
    """Design a silver-layer model. Every output field must map to a provided raw field."""


@agent(model="demo-model", validators=[min_items("notes", 2)])
def quality(inp: QualityIn) -> QualityNotes:
    """List data quality notes for the key candidates."""


@agent(model="demo-model")
def report(inp: ReportIn) -> Report:
    """Summarize the design and quality notes."""


SOURCE = SourceSchema(
    tables=["orders"], raw_fields={"id": "int", "customer": "str", "total": "float", "placed_at": "datetime"}
)
_ARCHITECT_ATTEMPTS = [
    {"order_id": "id", "amount": "total_amount", "customer_name": "cust_name", "placed": "placed_at"},
    {"order_id": "id", "amount": "total", "customer_name": "cust_name", "placed": "placed_at"},
    {"order_id": "id", "amount": "total", "customer_name": "customer", "placed": "placed_at"},
]


def _script() -> Any:
    state = {"architect": 0, "quality": 0}
    fail = os.environ.get("RUNWAY_DEMO_FAIL")

    def respond(req: GenerateRequest, _i: int) -> Any:
        name = req.output_schema_name
        if fail and name.lower() == _SCHEMA_OF.get(fail):
            return "this is not json"
        if name == "Profile":
            return Profile(row_estimate=120_000, key_candidates=["id", "customer"])
        if name == "SilverModel":
            k = min(state["architect"], 2)
            state["architect"] += 1
            return SilverModel(model_name="orders_silver", lineage_map=_ARCHITECT_ATTEMPTS[k])
        if name == "QualityNotes":
            state["quality"] += 1
            return QualityNotes(
                notes=["id is unique"] if state["quality"] == 1 else ["id is unique", "customer has nulls"]
            )
        return Report(summary="orders_silver maps 4 fields; id unique; customer has nulls.")

    return respond


_SCHEMA_OF = {"profile": "profile", "architect": "silvermodel", "quality": "qualitynotes", "report": "report"}


def flow() -> Flow:
    g = WorkGraph("offline_demo", input_model=SourceSchema)
    g.add(profile)
    g.add(architect, inputs={"raw_fields": input_field("raw_fields"), "key_candidates": profile.out.key_candidates})
    g.add(quality, inputs={"key_candidates": profile.out.key_candidates})
    g.add(report, inputs={"model_name": architect.out.model_name, "notes": quality.out.notes})
    llm = FakeLLMClient(
        fn=_script(), delay_s=float(os.environ.get("RUNWAY_DEMO_DELAY", "0.7")), cost_per_1k_tokens=0.002
    )
    return Flow(g, SOURCE, llm)
