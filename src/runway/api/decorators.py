"""``@agent`` sugar: type hints are the contract, the docstring is the system prompt."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Sequence
from typing import Any, cast, get_type_hints

from pydantic import BaseModel

from runway.core.agent import Agent
from runway.core.budget import Limits
from runway.core.errors import ContractError
from runway.core.task import Task


def agent(
    model: str = "gpt-4o-mini",
    budget: dict[str, Any] | Limits | None = None,
    validators: Sequence[Any] = (),
    name: str | None = None,
    temperature: float = 0.0,
) -> Callable[[Callable[..., Any]], Task]:
    """Turn ``def f(input: In) -> Out`` into a :class:`Task`. Decorators only construct core objects."""

    def wrap(fn: Callable[..., Any]) -> Task:
        hints = get_type_hints(fn)
        params = list(inspect.signature(fn).parameters)
        in_model, out_model = hints.get(params[0]) if params else None, hints.get("return")
        for label, m in (("input", in_model), ("return", out_model)):
            if not (isinstance(m, type) and issubclass(m, BaseModel)):
                raise ContractError(f"@agent {fn.__name__}: {label} annotation must be a pydantic model")
        prompt = inspect.getdoc(fn) or ""
        limits = budget if isinstance(budget, Limits) else Limits(**(budget or {}))
        return Task(
            name or fn.__name__,
            Agent(name=name or fn.__name__, system_prompt=prompt, model=model, temperature=temperature),
            cast("type[BaseModel]", in_model),
            cast("type[BaseModel]", out_model),
            validators=validators,
            budget=limits,
        )

    return wrap
