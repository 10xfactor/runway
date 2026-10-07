"""Spawn and track runner subprocesses started from the Console (demo, replay)."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

from runway.ports.events import EventStore


class Procs:
    def __init__(self, home: Path, store: EventStore) -> None:
        self.home, self.store = home, store
        self.by_run: dict[str, subprocess.Popen[bytes]] = {}

    def spawn(self, args: list[str], match: Callable[..., bool], timeout: float = 15.0) -> str:
        """Start ``python -m runway <args>`` and return the id of the run it creates."""
        before = {s.run.run_id for s in self.store.list_runs(1000)}
        proc = subprocess.Popen(
            [sys.executable, "-m", "runway", *args, "--home", str(self.home)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=os.environ.copy(),
            cwd=os.getcwd(),
        )
        deadline = time.time() + timeout
        while time.time() < deadline:
            for s in self.store.list_runs(1000):
                if s.run.run_id not in before and match(s):
                    self.by_run[s.run.run_id] = proc
                    return s.run.run_id
            if proc.poll() not in (None, 0):
                break
            time.sleep(0.1)
        raise RuntimeError("runner did not create a run")

    def cancel(self, run_id: str) -> bool:
        proc = self.by_run.get(run_id)
        if proc is None or proc.poll() is not None:
            return False
        proc.send_signal(signal.SIGTERM)
        return True
