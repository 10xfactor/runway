"""Entry-point plugin discovery. A broken plugin is reported, never allowed to crash a run."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from importlib.metadata import entry_points
from typing import Any

log = logging.getLogger(__name__)
API_VERSION = "1"
GROUPS = (
    "runway.validators",
    "runway.llm_clients",
    "runway.tool_providers",
    "runway.event_sinks",
    "runway.routers",
    "runway.evaluators",
    "runway.artifact_stores",
    "runway.redactors",
    "runway.flight_plans",
    "runway.ui_panels",
    "runway.cli",
    "runway.hooks",
)


@dataclass
class Plugin:
    group: str
    name: str
    dist: str
    version: str
    obj: Any = None
    error: str | None = None


def discover(group: str | None = None, allow: list[str] | None = None) -> list[Plugin]:
    """Load plugins from entry points. ``allow`` restricts to named distributions (regulated setups)."""
    out: list[Plugin] = []
    for g in [group] if group else GROUPS:
        for ep in entry_points(group=g):
            dist = ep.dist.name if ep.dist else "?"
            ver = ep.dist.version if ep.dist else "?"
            if allow is not None and dist not in allow:
                continue
            p = Plugin(g, ep.name, dist, ver)
            try:
                p.obj = ep.load()
                declared = getattr(p.obj, "runway_api", API_VERSION)
                if str(declared) != API_VERSION:
                    p.error = f"requires runway_api={declared}, host provides {API_VERSION}"
            except Exception as e:  # isolate plugin import errors
                p.error = type(e).__name__
                log.warning("plugin %s/%s failed to load: %s", g, ep.name, p.error)
            out.append(p)
    return out


def doctor(allow: list[str] | None = None) -> list[Plugin]:
    """Plugins that failed to load or are incompatible."""
    return [p for p in discover(allow=allow) if p.error]
