"""WorkGraph: DAG of tasks with typed field bindings and compile-time checks."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import networkx as nx
from pydantic import BaseModel

from runway.core.contract import schema_hash
from runway.core.errors import ContractError
from runway.core.hashing import fingerprint
from runway.core.task import Binding, Task, resolve_field_type


def _assignable(src: Any, dst: Any) -> bool:
    if dst is Any or src == dst:
        return True
    return isinstance(src, type) and isinstance(dst, type) and issubclass(src, dst)


class WorkGraph:
    def __init__(self, name: str, input_model: type[BaseModel] | None = None) -> None:
        self.name = name
        self.input_model = input_model
        self.tasks: dict[str, Task] = {}
        self.bindings: dict[str, dict[str, Binding]] = {}
        self.after: dict[str, list[str]] = {}
        self.graph: nx.DiGraph[str] = nx.DiGraph()

    def add(
        self,
        task: Task,
        inputs: Mapping[str, Binding] | None = None,
        after: list[Task] | None = None,
    ) -> Task:
        if task.name in self.tasks:
            raise ContractError(f"duplicate task name {task.name!r}")
        self.tasks[task.name] = task
        self.bindings[task.name] = dict(inputs or {})
        self.after[task.name] = [t.name for t in after or []]
        self.graph.add_node(task.name)
        return task

    def upstream(self, name: str) -> list[str]:
        srcs = {b.source for b in self.bindings[name].values() if b.source}
        return sorted(srcs | set(self.after[name]))

    def compile(self) -> list[str]:
        """Validate the graph and return a topological order. Raises ContractError."""
        self.graph.clear_edges()
        for name in self.tasks:
            for up in self.upstream(name):
                if up not in self.tasks:
                    raise ContractError(f"{name}: unknown upstream task {up!r}")
                self.graph.add_edge(up, name)
        if not nx.is_directed_acyclic_graph(self.graph):
            raise ContractError(f"WorkGraph {self.name!r} contains cycles")
        for name, task in self.tasks.items():
            self._check_inputs(name, task)
        return list(nx.topological_sort(self.graph))

    def _check_inputs(self, name: str, task: Task) -> None:
        binds = self.bindings[name]
        if not binds:
            if self.input_model is None or not _assignable(self.input_model, task.input_model):
                raise ContractError(f"{name}: no bindings and run input is not {task.input_model.__name__}")
            return
        for field, b in binds.items():
            dst = task.input_model.model_fields.get(field)
            if dst is None:
                raise ContractError(f"{name}: input model has no field {field!r}")
            src_model = self.input_model if b.source is None else self.tasks[b.source].output_model
            if src_model is None:
                raise ContractError(f"{name}.{field}: graph has no input_model")
            if not _assignable(resolve_field_type(src_model, b.path), dst.annotation):
                raise ContractError(f"{name}.{field}: type mismatch with {b.source or 'input'}.{b.path}")
        missing = [f for f, i in task.input_model.model_fields.items() if i.is_required() and f not in binds]
        if missing:
            raise ContractError(f"{name}: unbound required inputs {missing}")

    def descendants(self, name: str) -> set[str]:
        return set(nx.descendants(self.graph, name))

    def graph_hash(self) -> str:
        return fingerprint(
            {
                "name": self.name,
                "tasks": {
                    n: [
                        t.agent.config_hash(),
                        schema_hash(t.input_model),
                        schema_hash(t.output_model),
                        t.validator_fingerprint(),
                    ]
                    for n, t in sorted(self.tasks.items())
                },
                "edges": sorted(self.graph.edges),
            }
        )

    def describe(self) -> dict[str, Any]:
        """Structure embedded in ``run.created`` for the UI."""
        return {
            "nodes": [
                {
                    "name": n,
                    "model": t.agent.model,
                    "input_contract": t.input_model.__name__,
                    "output_contract": t.output_model.__name__,
                    "validators": [[v.name for v in st] for st in t.stages],
                    "max_retries": t.budget.max_retries,
                }
                for n, t in self.tasks.items()
            ],
            "edges": [{"source": a, "target": b} for a, b in sorted(self.graph.edges)],
        }
