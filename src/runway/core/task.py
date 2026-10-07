"""Task: Agent + input/output contracts + validators + budget, with typed field bindings."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel

from runway.core.agent import Agent
from runway.core.budget import Limits
from runway.core.errors import ContractError
from runway.core.hashing import fingerprint
from runway.core.validation import Validator, as_validator

ValidatorStage = Validator | Sequence[Validator]


class Binding(BaseModel, frozen=True):
    """Reference to a field of an upstream task output (``source=None``: the run input)."""

    source: str | None
    path: str


def input_field(path: str) -> Binding:
    """Bind a task input field to a field of the run input."""
    return Binding(source=None, path=path)


def resolve_field_type(model: type[BaseModel], path: str) -> Any:
    """Annotation of a dotted ``path`` inside ``model``; raises ContractError if missing."""
    current: Any = model
    for part in path.split("."):
        if not (isinstance(current, type) and issubclass(current, BaseModel)):
            raise ContractError(f"cannot descend into {part!r}: not a model")
        field = current.model_fields.get(part)
        if field is None:
            raise ContractError(f"{model.__name__} has no field {path!r}")
        current = field.annotation
    return current


class _OutProxy:
    def __init__(self, task: Task) -> None:
        self._task = task

    def __getattr__(self, path: str) -> Binding:
        resolve_field_type(self._task.output_model, path)
        return Binding(source=self._task.name, path=path)


class Task:
    def __init__(
        self,
        name: str,
        agent: Agent,
        input_model: type[BaseModel],
        output_model: type[BaseModel],
        validators: Sequence[Any] = (),
        budget: Limits | None = None,
        version: str = "1",
    ) -> None:
        self.name = name
        self.agent = agent
        self.input_model = input_model
        self.output_model = output_model
        self.budget = budget or Limits()
        self.version = version
        # A stage is a validator or a group of validators that run concurrently.
        self.stages: list[list[Validator]] = [
            [as_validator(v) for v in (s if isinstance(s, (list, tuple)) else [s])] for s in validators
        ]

    @property
    def out(self) -> _OutProxy:
        return _OutProxy(self)

    def validator_fingerprint(self) -> str:
        return fingerprint([[(v.name, v.version) for v in st] for st in self.stages])
