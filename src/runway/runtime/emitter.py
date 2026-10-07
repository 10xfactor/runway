"""Single choke point for appending events; redacts free text before it reaches the log."""

from __future__ import annotations

from typing import Any

from runway.core.events import Event
from runway.extensions.hooks import Listener, safe_call
from runway.ports.events import EventStore
from runway.ports.redact import Redactor


class Emitter:
    def __init__(
        self, store: EventStore, run_id: str, redactor: Redactor, listeners: list[Listener] | None = None
    ) -> None:
        self.store, self.run_id, self.redactor = store, run_id, redactor
        self.listeners = listeners or []

    def emit(
        self,
        type: str,
        data: dict[str, Any] | None = None,
        *,
        task: str | None = None,
        attempt: int | None = None,
        parent: Event | None = None,
    ) -> Event:
        ev = self.store.append(
            self.run_id,
            type,
            self._redact(type, data or {}),
            task_name=task,
            attempt_no=attempt,
            parent_seq=parent.seq if parent else None,
        )
        for fn in self.listeners:
            safe_call(fn, ev)
        return ev

    def _redact(self, type: str, data: dict[str, Any]) -> dict[str, Any]:
        r = self.redactor.redact
        if type == "validation.failed":
            for res in data["results"]:
                for i in res["issues"]:
                    i["message"], i["hint"] = r(i.get("message", "")), r(i.get("hint", ""))
        if type == "run.failed":
            data["safe_message"] = r(data.get("safe_message", ""))
        return data
