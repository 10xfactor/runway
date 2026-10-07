"""Execute -> validate -> reject -> repair loop for a single task."""

from __future__ import annotations

import asyncio
import inspect
import time
from dataclasses import dataclass, field

from pydantic import BaseModel, ValidationError

from runway.core.artifact import FeedbackArtifact, make_record
from runway.core.errors import (
    BudgetExceededError,
    ProviderError,
    RepeatedOutputError,
    RunwayError,
    TaskFailed,
)
from runway.core.events import Event
from runway.core.hashing import fingerprint
from runway.core.task import Task
from runway.core.validation import (
    ValidationContext,
    ValidationIssue,
    ValidationResult,
    ValidationStatus,
    Validator,
    render_feedback,
)
from runway.ports.artifacts import ArtifactStore
from runway.ports.llm import GenerateRequest, LLMClient
from runway.runtime.budget_gate import BudgetLedger
from runway.runtime.emitter import Emitter

MAX_FEEDBACK_CHARS = 4000


@dataclass
class _Past:
    n: int
    text: str
    feedback: str
    summary: str


@dataclass
class Outcome:
    proposal: BaseModel
    artifact_id: str
    attempts: int


@dataclass
class _Chain:
    status: ValidationStatus
    stage: int = 0
    results: list[tuple[str, ValidationResult, int]] = field(default_factory=list)


def build_messages(task: Task, task_input: BaseModel, past: list[_Past]) -> list[dict[str, str]]:
    """Inputs are delimited data, never instructions (prompt-injection posture)."""
    msgs = [
        {"role": "system", "content": task.agent.system_prompt},
        {"role": "user", "content": f"<input>\n{task_input.model_dump_json(indent=2)}\n</input>"},
    ]
    if len(past) > 1:
        earlier = "\n".join(f"attempt {p.n}: {p.summary}" for p in past[:-1])
        msgs.append({"role": "user", "content": f"Earlier rejected attempts (summary):\n{earlier}"})
    if past:
        last = past[-1]
        msgs.append({"role": "assistant", "content": last.text})
        msgs.append(
            {
                "role": "user",
                "content": "CRITICAL: your previous submission failed verification.\n"
                f"{last.feedback}\nFix all issues and regenerate.",
            }
        )
    return msgs


def parse_failure(err: ValidationError) -> ValidationResult:
    issues = [
        ValidationIssue(code="schema", path=".".join(str(p) for p in e["loc"]), message=e["msg"]) for e in err.errors()
    ]
    return ValidationResult.reject("Output did not match the required schema", issues=issues)


async def _call(v: Validator, output: BaseModel, ctx: ValidationContext) -> tuple[str, list[ValidationResult], int]:
    t0 = time.perf_counter()
    try:
        res = v.validate(output, ctx)
        if inspect.isawaitable(res):
            res = await res
        out = res if isinstance(res, list) else [res]
    except Exception as e:  # validator bugs are errors, never rejects
        out = [ValidationResult.error(type(e).__name__)]
    return v.name, out, int((time.perf_counter() - t0) * 1000)


class RepairLoop:
    def __init__(
        self,
        llm: LLMClient,
        emitter: Emitter,
        ledger: BudgetLedger,
        artifacts: ArtifactStore,
        deadline: float | None = None,
    ) -> None:
        self.llm, self.em, self.ledger, self.artifacts = llm, emitter, ledger, artifacts
        self.deadline = deadline  # absolute loop.time() for the run scope

    def _remaining(self, task: Task, started: float) -> tuple[float | None, str]:
        loop_now = asyncio.get_running_loop().time()
        opts: list[tuple[float, str]] = []
        if task.budget.max_time_s is not None:
            opts.append((started + task.budget.max_time_s - loop_now, "task"))
        if self.deadline is not None:
            opts.append((self.deadline - loop_now, "run"))
        if not opts:
            return None, ""
        rem, scope = min(opts)
        return max(rem, 0.0), scope

    async def run(
        self,
        task: Task,
        task_input: BaseModel,
        input_ids: list[str],
        validation_ctx: ValidationContext,
    ) -> Outcome:
        name = task.name
        max_attempts = task.budget.max_retries + 1
        past: list[_Past] = []
        seen: dict[str, int] = {}
        last_event: Event | None = None
        started = asyncio.get_running_loop().time()
        n = 0
        try:
            for n in range(1, max_attempts + 1):
                self.ledger.usage(name).retries = n - 1
                self.em.emit(
                    "attempt.started",
                    {"kind": "repair" if n > 1 else "initial"},
                    task=name,
                    attempt=n,
                    parent=last_event,
                )
                msgs = build_messages(task, task_input, past)
                req = GenerateRequest(
                    model=task.agent.model,
                    messages=msgs,
                    temperature=task.agent.temperature,
                    output_schema=task.output_model.model_json_schema(),
                    output_schema_name=task.output_model.__name__,
                    max_output_tokens=task.agent.max_output_tokens,
                )
                est = self.llm.estimate(req)
                self.ledger.preflight(task, est.tokens, est.cost_usd, n)
                req_ev = self.em.emit(
                    "model.requested",
                    {"model": req.model, "prompt_tokens_est": est.tokens, "feedback_issue_count": sum(1 for _ in past)},
                    task=name,
                    attempt=n,
                )
                rem, scope = self._remaining(task, started)
                try:
                    async with asyncio.timeout(rem):
                        result = await self.llm.generate(req)
                except TimeoutError:
                    raise self.ledger.time_exceeded(task, scope, rem or 0.0, n) from None
                except ProviderError as e:
                    raise TaskFailed(e.code, n) from e
                u = result.usage
                self.ledger.record(task, u.total_tokens, u.cost_usd, n)
                proposal, art_id, failure = self._parse(task, result.text, input_ids, n)
                gen_ev = self.em.emit(
                    "model.generated",
                    {
                        "model": req.model,
                        "prompt_tokens": u.prompt_tokens,
                        "completion_tokens": u.completion_tokens,
                        "cost_usd": u.cost_usd,
                        "cost_unknown": u.cost_unknown,
                        "latency_ms": u.latency_ms,
                        "proposal_artifact_id": art_id,
                        "finish_reason": result.finish_reason,
                    },
                    task=name,
                    attempt=n,
                    parent=req_ev,
                )
                fp = fingerprint(proposal) if proposal is not None else fingerprint(result.text)
                if fp in seen:
                    self.em.emit(
                        "attempt.aborted",
                        {"reason": f"repeated_output:{seen[fp]}"},
                        task=name,
                        attempt=n,
                        parent=gen_ev,
                    )
                    raise TaskFailed(RepeatedOutputError.code, n)
                seen[fp] = n
                if proposal is not None:
                    chain = await self._chain(
                        task, proposal, validation_ctx.model_copy(update={"attempt_no": n}), n, gen_ev
                    )
                else:
                    assert failure is not None
                    chain = _Chain(ValidationStatus.REJECTED, 0, [("schema", failure, 0)])
                if chain.status == ValidationStatus.ACCEPTED and proposal is not None and art_id:
                    self.em.emit("validation.passed", {"stages_run": chain.stage}, task=name, attempt=n, parent=gen_ev)
                    return Outcome(proposal, art_id, n)
                if chain.status == ValidationStatus.ERROR:
                    bad = next(r for r in chain.results if r[1].status == ValidationStatus.ERROR)
                    self.em.emit(
                        "validation.errored",
                        {"validator": bad[0], "error_code": bad[1].reason or "ERROR"},
                        task=name,
                        attempt=n,
                        parent=gen_ev,
                    )
                    raise TaskFailed("VALIDATOR_ERROR", n)
                fail_ev = self.em.emit(
                    "validation.failed",
                    {
                        "stage": chain.stage,
                        "results": [
                            {
                                "validator": v,
                                "status": r.status.value,
                                "duration_ms": ms,
                                "issues": [i.model_dump() for i in r.issues],
                            }
                            for v, r, ms in chain.results
                        ],
                        "proposal_fingerprint": fp,
                    },
                    task=name,
                    attempt=n,
                    parent=gen_ev,
                )
                if n >= max_attempts:
                    raise TaskFailed("RETRIES_EXHAUSTED", n)
                feedback = render_feedback([r for _, r, _ in chain.results], MAX_FEEDBACK_CHARS)
                summary = ", ".join(sorted({f"{i.code}@{i.path}" for _, r, _ in chain.results for i in r.issues}))
                past.append(_Past(n, result.text, feedback, summary))
                fb_rec = make_record(FeedbackArtifact(text=feedback), parents=input_ids)
                self.artifacts.put(fb_rec)
                last_event = self.em.emit(
                    "agent.retry",
                    {
                        "next_attempt": n + 1,
                        "feedback_artifact_id": fb_rec.artifact_id,
                        "feedback_tokens": len(feedback) // 4,
                        "history_truncated": len(past) > 1,
                    },
                    task=name,
                    attempt=n,
                    parent=fail_ev,
                )
        except asyncio.CancelledError:
            self.em.emit("attempt.aborted", {"reason": "cancelled"}, task=name, attempt=n or None)
            raise
        except BudgetExceededError as e:
            raise TaskFailed(e.code, n) from e
        except TaskFailed:
            raise
        except RunwayError as e:
            raise TaskFailed(e.code, n) from e
        raise TaskFailed("RETRIES_EXHAUSTED", n)  # pragma: no cover

    def _parse(
        self, task: Task, text: str, input_ids: list[str], n: int
    ) -> tuple[BaseModel | None, str | None, ValidationResult | None]:
        try:
            proposal = task.output_model.model_validate_json(text)
        except ValidationError as e:
            return None, None, parse_failure(e)
        rec = make_record(proposal, parents=input_ids, created_by={"task": task.name, "attempt": n})
        size = self.artifacts.put(rec)
        self.em.emit(
            "artifact.created",
            {
                "artifact_id": rec.artifact_id,
                "schema_ref": rec.schema_ref,
                "schema_hash": rec.schema_hash,
                "size_bytes": size,
            },
            task=task.name,
            attempt=n,
        )
        return proposal, rec.artifact_id, None

    async def _chain(self, task: Task, output: BaseModel, ctx: ValidationContext, n: int, parent: Event) -> _Chain:
        """Ordered stages; validators within a stage run concurrently; short-circuits on failure."""
        collected: list[tuple[str, ValidationResult, int]] = []
        for i, stage in enumerate(task.stages, start=1):
            self.em.emit(
                "validation.started",
                {"stage": i, "validators": [v.name for v in stage]},
                task=task.name,
                attempt=n,
                parent=parent,
            )
            done = await asyncio.gather(*(_call(v, output, ctx) for v in stage))
            stage_results = [(name, r, ms) for name, rs, ms in done for r in rs]
            collected = stage_results
            if any(r.status == ValidationStatus.ERROR for _, r, _ in stage_results):
                return _Chain(ValidationStatus.ERROR, i, stage_results)
            if any(r.status == ValidationStatus.REJECTED for _, r, _ in stage_results):
                return _Chain(
                    ValidationStatus.REJECTED, i, [x for x in stage_results if x[1].status == ValidationStatus.REJECTED]
                )
        return _Chain(ValidationStatus.ACCEPTED, len(task.stages), collected)
