"""Clock and id ports with deterministic fakes for tests."""

from __future__ import annotations

import itertools
import uuid
from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FakeClock:
    """Advances by ``step_ms`` on every call so event order and durations are deterministic."""

    def __init__(self, start: datetime | None = None, step_ms: int = 100) -> None:
        self._t = start or datetime(2026, 1, 1, tzinfo=UTC)
        self._step = timedelta(milliseconds=step_ms)

    def now(self) -> datetime:
        self._t += self._step
        return self._t


class IdGenerator(Protocol):
    def run_id(self) -> str: ...


class UuidIds:
    def run_id(self) -> str:
        return f"run_{uuid.uuid4().hex[:10]}"


class CountingIds:
    def __init__(self) -> None:
        self._n = itertools.count(1)

    def run_id(self) -> str:
        return f"run_{next(self._n):04d}"
