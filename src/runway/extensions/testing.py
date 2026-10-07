"""Conformance helpers for plugin authors (use inside your own pytest tests)."""

from __future__ import annotations

from typing import Any

from runway.core.validation import ValidationContext, ValidationStatus, as_validator


def check_validator(validator: Any, good: Any, bad: Any) -> None:
    """A validator must accept ``good``, reject ``bad`` with feedback, and be deterministic."""
    v = as_validator(validator)
    assert v.name and v.version, "validators declare name and version"
    ctx = ValidationContext()
    import asyncio
    import inspect

    async def _await(aw: Any) -> Any:
        return await aw

    def run(out: Any) -> list[Any]:
        res: Any = v.validate(out, ctx)
        if inspect.isawaitable(res):
            res = asyncio.run(_await(res))
        return res if isinstance(res, list) else [res]

    assert all(r.status == ValidationStatus.ACCEPTED for r in run(good)), "must accept good sample"
    rejected = run(bad)
    assert any(r.status == ValidationStatus.REJECTED and r.issues for r in rejected), "must reject with issues"
    assert [r.model_dump() for r in run(bad)] == [r.model_dump() for r in rejected], "must be deterministic"
