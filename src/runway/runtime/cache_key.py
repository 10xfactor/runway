"""Cache keys: identify a task execution by everything that could change its result."""

from __future__ import annotations

from collections.abc import Mapping

from runway.core.contract import schema_hash
from runway.core.hashing import fingerprint
from runway.core.task import Binding, Task


def input_refs(bindings: Mapping[str, Binding], artifact_ids: Mapping[str | None, str]) -> dict[str, str]:
    """Stable references to the inputs of a task (artifact id + field path)."""
    if not bindings:
        return {"$input": artifact_ids[None]}
    return {f: f"{artifact_ids[b.source]}:{b.path}" for f, b in sorted(bindings.items())}


def cache_parts(task: Task, refs: Mapping[str, str]) -> dict[str, str]:
    return {
        "task": f"{task.name}@{task.version}",
        "agent": task.agent.config_hash(),
        "input_schema": schema_hash(task.input_model),
        "output_schema": schema_hash(task.output_model),
        "validators": task.validator_fingerprint(),
        "inputs": fingerprint(dict(refs)),
    }


def cache_key(parts: Mapping[str, str]) -> str:
    return fingerprint(dict(parts))


def diff_parts(old: Mapping[str, str], new: Mapping[str, str]) -> list[str]:
    return sorted(k for k in new if old.get(k) != new[k])
