"""Lifecycle hooks and event sinks are the same thing: observers of the event stream.

Observers cannot mutate committed artifacts or bypass validators (Invariant 2): they only receive events.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from runway.core.events import Event

log = logging.getLogger(__name__)
Listener = Callable[[Event], None]

_HOOK_BY_EVENT = {
    "run.created": "before_run",
    "task.committed": "after_task_commit",
    "validation.failed": "on_validation_failed",
    "run.completed": "after_run",
    "run.failed": "after_run",
    "run.cancelled": "after_run",
}


def hook_listener(hook: Any) -> Listener:
    """Adapt an object with optional ``before_run/after_task_commit/on_validation_failed/after_run``."""

    def listener(ev: Event) -> None:
        method = getattr(hook, _HOOK_BY_EVENT.get(ev.type, ""), None)
        if method:
            method(ev)

    return listener


def safe_call(listener: Listener, ev: Event) -> None:
    try:
        listener(ev)
    except Exception as e:  # a faulty observer must never break a run
        log.warning("listener failed on %s: %s", ev.type, type(e).__name__)
