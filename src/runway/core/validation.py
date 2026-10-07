"""Validators: deterministic gatekeepers returning structured feedback."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Sequence
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class ValidationStatus(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ERROR = "error"


class ValidationIssue(BaseModel):
    code: str
    path: str = ""
    message: str = ""
    hint: str = ""
    severity: str = "error"


class ValidationResult(BaseModel):
    status: ValidationStatus
    reason: str | None = None
    feedback: str | None = None
    issues: list[ValidationIssue] = Field(default_factory=list)

    @classmethod
    def accept(cls) -> ValidationResult:
        return cls(status=ValidationStatus.ACCEPTED)

    @classmethod
    def reject(
        cls, reason: str, feedback: str | None = None, issues: Sequence[ValidationIssue] = ()
    ) -> ValidationResult:
        found = list(issues) or [ValidationIssue(code="rejected", message=reason, hint=feedback or "")]
        return cls(status=ValidationStatus.REJECTED, reason=reason, feedback=feedback, issues=found)

    @classmethod
    def error(cls, code: str) -> ValidationResult:
        return cls(
            status=ValidationStatus.ERROR,
            reason=code,
            issues=[ValidationIssue(code=code, message="validator crashed")],
        )


class ValidationContext(BaseModel):
    """Read-only context handed to validators. Deterministic: fixed seed, no clock."""

    run_id: str = ""
    task_name: str = ""
    attempt_no: int = 1
    seed: int = 0
    inputs: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class Validator(Protocol):
    name: str
    version: str
    deterministic: bool

    def validate(
        self, output: Any, ctx: ValidationContext
    ) -> ValidationResult | list[ValidationResult] | Awaitable[ValidationResult | list[ValidationResult]]: ...


class FunctionValidator:
    """Wrap a plain function ``fn(output[, ctx]) -> ValidationResult | bool | None``."""

    def __init__(
        self,
        fn: Callable[..., Any],
        name: str | None = None,
        version: str = "1",
        deterministic: bool = True,
    ) -> None:
        self.fn = fn
        self.name: str = name or str(getattr(fn, "__name__", "validator"))
        self.version = version
        self.deterministic = deterministic
        self._takes_ctx = len(inspect.signature(fn).parameters) >= 2

    def validate(self, output: Any, ctx: ValidationContext) -> Any:
        res = self.fn(output, ctx) if self._takes_ctx else self.fn(output)
        if inspect.isawaitable(res):
            return self._finish_async(res)
        return self._normalize(res)

    async def _finish_async(self, awaitable: Awaitable[Any]) -> Any:
        return self._normalize(await awaitable)

    def _normalize(self, res: Any) -> Any:
        if res is None or res is True:
            return ValidationResult.accept()
        if res is False:
            return ValidationResult.reject(f"{self.name} returned False")
        return res


def as_validator(v: Any) -> Validator:
    """Accept validator objects or plain callables."""
    if isinstance(v, Validator):
        return v
    if callable(v):
        return FunctionValidator(v)
    raise TypeError(f"not a validator: {v!r}")


def render_feedback(results: Sequence[ValidationResult], max_chars: int = 4000) -> str:
    """Stable feedback text for the repair prompt."""
    lines: list[str] = []
    for r in results:
        if r.status != ValidationStatus.REJECTED:
            continue
        if r.feedback:
            lines.append(r.feedback)
        for i in r.issues:
            loc = f" at `{i.path}`" if i.path else ""
            hint = f" Hint: {i.hint}" if i.hint and i.hint != r.feedback else ""
            lines.append(f"- [{i.code}]{loc}: {i.message}{hint}".rstrip())
    text = "\n".join(dict.fromkeys(lines))
    return text if len(text) <= max_chars else text[: max_chars - 3] + "..."
