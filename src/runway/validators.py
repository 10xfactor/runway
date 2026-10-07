"""Built-in deterministic validators. Each returns structured issues (code + JSON path + hint)."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from typing import Any

from runway.core.validation import FunctionValidator, ValidationContext, ValidationIssue, ValidationResult


def _get(obj: Any, path: str) -> Any:
    for part in path.split("."):
        obj = obj[part] if isinstance(obj, dict) else getattr(obj, part)
    return obj


def _result(issues: list[ValidationIssue], reason: str) -> ValidationResult:
    return ValidationResult.reject(reason, issues=issues) if issues else ValidationResult.accept()


def regex(path: str, pattern: str, name: str | None = None) -> FunctionValidator:
    rx = re.compile(pattern)

    def check(out: Any) -> ValidationResult:
        v = str(_get(out, path))
        bad = (
            []
            if rx.fullmatch(v)
            else [
                ValidationIssue(
                    code="regex", path=path, message="value does not match pattern", hint=f"Must match /{pattern}/"
                )
            ]
        )
        return _result(bad, f"{path} format")

    return FunctionValidator(check, name or f"regex:{path}")


def min_items(path: str, n: int) -> FunctionValidator:
    def check(out: Any) -> ValidationResult:
        got = len(_get(out, path))
        bad = (
            []
            if got >= n
            else [
                ValidationIssue(
                    code="min_items",
                    path=path,
                    message=f"{got} items, need at least {n}",
                    hint=f"Provide at least {n} items",
                )
            ]
        )
        return _result(bad, f"{path} too short")

    return FunctionValidator(check, f"min_items:{path}")


def unique_items(path: str) -> FunctionValidator:
    def check(out: Any) -> ValidationResult:
        items = list(_get(out, path))
        dup = sorted({str(i) for i in items if items.count(i) > 1})
        bad = (
            [ValidationIssue(code="unique", path=path, message=f"duplicate entries: {dup}", hint="Remove duplicates")]
            if dup
            else []
        )
        return _result(bad, f"{path} not unique")

    return FunctionValidator(check, f"unique:{path}")


def references_exist(
    values: Callable[[Any], Iterable[tuple[str, str]]],
    allowed: Callable[[Any, ValidationContext], set[str]],
    code: str = "reference",
    name: str = "references_exist",
) -> FunctionValidator:
    """Every ``(path, value)`` from ``values(output)`` must be in ``allowed(output, ctx)`` (lineage-style checks)."""

    def check(out: Any, ctx: ValidationContext) -> ValidationResult:
        ok = allowed(out, ctx)
        bad = [
            ValidationIssue(
                code=code, path=p, message=f"{v!r} is not an allowed value", hint="Use only provided values"
            )
            for p, v in values(out)
            if v not in ok
        ]
        return _result(bad, "unknown references")

    return FunctionValidator(check, name)
