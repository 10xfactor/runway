"""Event store port. The store assigns ``seq``/``ts`` and maintains projections atomically."""

from __future__ import annotations

from typing import Any, Protocol

from runway.core.events import Event
from runway.core.snapshot import RunSnapshot


class EventStore(Protocol):
    def append(
        self,
        run_id: str,
        type: str,
        data: dict[str, Any],
        *,
        task_name: str | None = None,
        attempt_no: int | None = None,
        parent_seq: int | None = None,
    ) -> Event: ...

    def read(
        self,
        run_id: str,
        after_seq: int = 0,
        limit: int = 1000,
        types: list[str] | None = None,
        task: str | None = None,
    ) -> list[Event]: ...

    def snapshot(self, run_id: str) -> RunSnapshot | None: ...

    def list_runs(self, limit: int = 50, status: str | None = None, offset: int = 0) -> list[RunSnapshot]: ...
