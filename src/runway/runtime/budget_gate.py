"""Budget enforcement: pre-flight (estimate) and post-flight (actual) checks per scope."""

from __future__ import annotations

from collections.abc import Callable

from runway.core.budget import Breach, Limits, Usage, check, warnings
from runway.core.errors import BudgetExceededError
from runway.core.events import Event
from runway.core.task import Task

Emit = Callable[..., Event]


class BudgetLedger:
    """Runtime-owned counters for the run scope and each task scope."""

    def __init__(self, run_limits: Limits, emit: Emit) -> None:
        self.run_limits = run_limits
        self.run_usage = Usage()
        self.task_usage: dict[str, Usage] = {}
        self._emit = emit
        self._warned: set[tuple[str, str, str]] = set()

    def usage(self, task: str) -> Usage:
        return self.task_usage.setdefault(task, Usage())

    def _scopes(self, task: Task) -> list[tuple[str, str, Limits, Usage]]:
        return [
            ("task", task.name, task.budget, self.usage(task.name)),
            ("run", "", self.run_limits, self.run_usage),
        ]

    def _breach(self, task: Task, scope: str, b: Breach, attempt: int | None) -> BudgetExceededError:
        self._emit(
            "budget.exceeded",
            {"scope": scope, "dimension": b.dimension, "used": b.used, "limit": b.limit, "policy": "STOP"},
            task=task.name,
            attempt=attempt,
        )
        return BudgetExceededError(scope, b.dimension, b.used, b.limit)

    def preflight(self, task: Task, est_tokens: int, est_cost: float | None, attempt: int) -> None:
        for scope, _, limits, usage in self._scopes(task):
            b = check(limits, usage, est_tokens, est_cost or 0.0)
            if b:
                raise self._breach(task, scope, b, attempt)

    def record(self, task: Task, tokens: int, cost: float, attempt: int) -> None:
        for scope, _, limits, usage in self._scopes(task):
            usage.tokens += tokens
            usage.cost_usd += cost
            for w in warnings(limits, usage):
                key = (scope, task.name if scope == "task" else "", w.dimension)
                if key not in self._warned:
                    self._warned.add(key)
                    self._emit(
                        "budget.warning",
                        {"scope": scope, "dimension": w.dimension, "used": w.used, "limit": w.limit},
                        task=task.name,
                        attempt=attempt,
                    )
        for scope, _, limits, usage in self._scopes(task):
            b = check(limits, usage)
            if b:
                raise self._breach(task, scope, b, attempt)

    def time_exceeded(self, task: Task, scope: str, limit: float, attempt: int) -> BudgetExceededError:
        return self._breach(task, scope, Breach(dimension="time_s", used=limit, limit=limit), attempt)
