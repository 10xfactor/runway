"""Flow: the unit the CLI/Console can run (graph + input + optional LLM)."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from runway.core.errors import ConfigError
from runway.core.graph import WorkGraph
from runway.ports.llm import LLMClient


@dataclass
class Flow:
    graph: WorkGraph
    input: BaseModel
    llm: LLMClient | None = None  # None -> LiteLLM


def load_flow(entrypoint: str) -> Flow:
    """Import ``package.module:attribute``; the attribute is a Flow or a zero-arg callable returning one."""
    mod_name, _, attr = entrypoint.partition(":")
    if not attr:
        raise ConfigError("entrypoint must look like 'package.module:flow'")
    obj: Any = getattr(importlib.import_module(mod_name), attr)
    flow = obj() if callable(obj) and not isinstance(obj, Flow) else obj
    if not isinstance(flow, Flow):
        raise ConfigError(f"{entrypoint} is not a runway Flow")
    return flow
