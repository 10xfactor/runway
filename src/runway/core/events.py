"""Event schema: the single source of truth for runs. Payload data never appears here."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from runway.core.validation import ValidationIssue

SCHEMA_VERSION = 1


class _D(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RunCreated(_D):
    graph_id: str
    graph_hash: str
    entrypoint: str | None = None
    input_artifact_id: str
    parent_run_id: str | None = None
    replay_from: str | None = None
    budget: dict[str, Any] = Field(default_factory=dict)
    graph: dict[str, Any] = Field(default_factory=dict)
    plugins: dict[str, str] = Field(default_factory=dict)


class Empty(_D):
    pass


class Totals(_D):
    tokens: int = 0
    cost_usd: float = 0.0
    duration_ms: int = 0


class RunCompleted(_D):
    status: str = "SUCCEEDED"
    totals: Totals = Field(default_factory=Totals)


class RunFailed(_D):
    status: str = "FAILED"
    error_code: str
    safe_message: str = ""
    totals: Totals = Field(default_factory=Totals)


class TaskReady(_D):
    deps: list[str] = Field(default_factory=list)


class TaskStarted(_D):
    cache_key: str
    cache_components: dict[str, str] = Field(default_factory=dict)
    input_artifact_ids: list[str] = Field(default_factory=list)


class TaskCached(_D):
    from_run_id: str
    artifact_id: str
    cache_key: str
    cache_components: dict[str, str] = Field(default_factory=dict)


class TaskCommitted(_D):
    artifact_id: str
    attempts: int
    tokens: int
    cost_usd: float
    duration_ms: int


class TaskFailed(_D):
    error_code: str
    attempts: int = 0


class TaskSkipped(_D):
    caused_by_task: str


class AttemptStarted(_D):
    kind: str = "initial"


class AttemptAborted(_D):
    reason: str


class ModelRequested(_D):
    model: str
    strategy: str = "native"
    prompt_tokens_est: int = 0
    feedback_issue_count: int = 0


class ModelGenerated(_D):
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    cost_unknown: bool = False
    latency_ms: int = 0
    proposal_artifact_id: str | None = None
    finish_reason: str = "stop"


class ValidationStarted(_D):
    stage: int
    validators: list[str]


class ValidationPassed(_D):
    stages_run: int


class ValidatorOutcome(_D):
    validator: str
    status: str
    duration_ms: int = 0
    issues: list[ValidationIssue] = Field(default_factory=list)


class ValidationFailed(_D):
    stage: int
    results: list[ValidatorOutcome]
    proposal_fingerprint: str = ""


class ValidationErrored(_D):
    validator: str
    error_code: str


class AgentRetry(_D):
    next_attempt: int
    feedback_artifact_id: str
    feedback_tokens: int = 0
    history_truncated: bool = False


class ArtifactCreated(_D):
    artifact_id: str
    schema_ref: str
    schema_hash: str
    size_bytes: int


class BudgetWarning(_D):
    scope: str
    dimension: str
    used: float
    limit: float


class BudgetExceeded(BudgetWarning):
    policy: str = "STOP"


EVENT_DATA: dict[str, type[BaseModel]] = {
    "run.created": RunCreated,
    "run.started": Empty,
    "run.completed": RunCompleted,
    "run.failed": RunFailed,
    "run.cancelled": Empty,
    "task.ready": TaskReady,
    "task.started": TaskStarted,
    "task.cached": TaskCached,
    "task.committed": TaskCommitted,
    "task.failed": TaskFailed,
    "task.skipped": TaskSkipped,
    "attempt.started": AttemptStarted,
    "attempt.aborted": AttemptAborted,
    "model.requested": ModelRequested,
    "model.generated": ModelGenerated,
    "validation.started": ValidationStarted,
    "validation.passed": ValidationPassed,
    "validation.failed": ValidationFailed,
    "validation.errored": ValidationErrored,
    "agent.retry": AgentRetry,
    "artifact.created": ArtifactCreated,
    "budget.warning": BudgetWarning,
    "budget.exceeded": BudgetExceeded,
}


class Event(BaseModel):
    run_id: str
    seq: int
    ts: datetime
    type: str
    schema_version: int = SCHEMA_VERSION
    task_name: str | None = None
    attempt_no: int | None = None
    parent_seq: int | None = None
    data: dict[str, Any] = Field(default_factory=dict)


def validate_event_data(event_type: str, data: dict[str, Any]) -> dict[str, Any]:
    """Validate ``data`` against the catalog and return its normalized JSON form."""
    model = EVENT_DATA.get(event_type)
    if model is None:
        raise ValueError(f"unknown event type {event_type!r}")
    return model.model_validate(data).model_dump(mode="json")


def event_json_schemas() -> dict[str, Any]:
    return {t: m.model_json_schema() for t, m in EVENT_DATA.items()}
