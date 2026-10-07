"""Workspace: typed store of committed task outputs. Only the executor commits."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from runway.core.task import Binding, Task


def _dig(obj: Any, path: str) -> Any:
    for part in path.split("."):
        obj = getattr(obj, part)
    return obj


class Workspace:
    def __init__(self, run_input_id: str, run_input: BaseModel) -> None:
        self._outputs: dict[str | None, tuple[str, BaseModel]] = {None: (run_input_id, run_input)}

    def _commit(self, task_name: str, artifact_id: str, model: BaseModel) -> None:
        """Package-private: reachable only after validators accept (or a verified cache hit)."""
        self._outputs[task_name] = (artifact_id, model)

    def artifact_id(self, source: str | None) -> str:
        return self._outputs[source][0]

    def artifact_ids(self) -> dict[str | None, str]:
        return {k: v[0] for k, v in self._outputs.items()}

    def output(self, task_name: str) -> BaseModel:
        return self._outputs[task_name][1]

    def assemble_input(self, task: Task, bindings: dict[str, Binding]) -> BaseModel:
        """Build the task input from subscribed fields only (not whole upstream artifacts)."""
        if not bindings:
            return self._outputs[None][1]
        values = {f: _dig(self._outputs[b.source][1], b.path) for f, b in bindings.items()}
        return task.input_model.model_validate(values)
