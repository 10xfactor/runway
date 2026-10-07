"""SQLite event store: append-only events plus an atomically maintained snapshot projection."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from runway.adapters.migrator import migrate
from runway.core.events import SCHEMA_VERSION, Event, validate_event_data
from runway.core.snapshot import RunSnapshot, apply_event, initial_snapshot
from runway.ports.clock import Clock, SystemClock


class SqliteEventStore:
    def __init__(self, path: Path | str, clock: Clock | None = None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock or SystemClock()
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        migrate(self._conn)

    def close(self) -> None:
        self._conn.close()

    # --- writes -----------------------------------------------------------------
    def append(
        self,
        run_id: str,
        type: str,
        data: dict[str, Any],
        *,
        task_name: str | None = None,
        attempt_no: int | None = None,
        parent_seq: int | None = None,
    ) -> Event:
        clean = validate_event_data(type, data)
        with self._lock:
            c = self._conn
            c.execute("BEGIN IMMEDIATE")
            try:
                row = c.execute("SELECT COALESCE(MAX(seq),0) FROM events WHERE run_id=?", (run_id,)).fetchone()
                ev = Event(
                    run_id=run_id,
                    seq=row[0] + 1,
                    ts=self.clock.now(),
                    type=type,
                    task_name=task_name,
                    attempt_no=attempt_no,
                    parent_seq=parent_seq,
                    data=clean,
                )
                snap = self._load_snapshot(run_id) or initial_snapshot(run_id)
                snap = apply_event(snap, ev)
                c.execute(
                    "INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        run_id,
                        ev.seq,
                        ev.ts.isoformat(),
                        type,
                        task_name,
                        attempt_no,
                        parent_seq,
                        SCHEMA_VERSION,
                        json.dumps(clean),
                    ),
                )
                self._save_snapshot(snap)
                c.execute("COMMIT")
            except Exception:
                c.execute("ROLLBACK")
                raise
        return ev

    def _save_snapshot(self, snap: RunSnapshot) -> None:
        self._conn.execute(
            "INSERT INTO runs(run_id, graph_id, status, created_at, parent_run_id, snapshot_json) "
            "VALUES (?,?,?,?,?,?) ON CONFLICT(run_id) DO UPDATE SET status=excluded.status, "
            "snapshot_json=excluded.snapshot_json",
            (
                snap.run.run_id,
                snap.run.graph_id,
                snap.run.status.value,
                (snap.run.created_at.isoformat() if snap.run.created_at else ""),
                snap.run.parent_run_id,
                snap.model_dump_json(),
            ),
        )

    def _load_snapshot(self, run_id: str) -> RunSnapshot | None:
        row = self._conn.execute("SELECT snapshot_json FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return RunSnapshot.model_validate_json(row[0]) if row else None

    # --- reads ------------------------------------------------------------------
    def snapshot(self, run_id: str) -> RunSnapshot | None:
        with self._lock:
            return self._load_snapshot(run_id)

    def read(
        self,
        run_id: str,
        after_seq: int = 0,
        limit: int = 1000,
        types: list[str] | None = None,
        task: str | None = None,
    ) -> list[Event]:
        sql = "SELECT run_id,seq,ts,type,task_name,attempt_no,parent_seq,schema_version,data_json FROM events WHERE run_id=? AND seq>?"
        args: list[Any] = [run_id, after_seq]
        if types:
            sql += f" AND type IN ({','.join('?' * len(types))})"
            args += types
        if task:
            sql += " AND task_name=?"
            args.append(task)
        sql += " ORDER BY seq LIMIT ?"
        args.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, args).fetchall()
        return [
            Event(
                run_id=r[0],
                seq=r[1],
                ts=r[2],
                type=r[3],
                task_name=r[4],
                attempt_no=r[5],
                parent_seq=r[6],
                schema_version=r[7],
                data=json.loads(r[8]),
            )
            for r in rows
        ]

    def list_runs(self, limit: int = 50, status: str | None = None, offset: int = 0) -> list[RunSnapshot]:
        sql = "SELECT snapshot_json FROM runs"
        args: list[Any] = []
        if status:
            sql += " WHERE status=?"
            args.append(status)
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        args += [limit, offset]
        with self._lock:
            rows = self._conn.execute(sql, args).fetchall()
        return [RunSnapshot.model_validate_json(r[0]) for r in rows]

    def rebuild(self) -> int:
        """Recompute every snapshot from the event log. Returns the number of runs rebuilt."""
        with self._lock:
            ids = [r[0] for r in self._conn.execute("SELECT DISTINCT run_id FROM events")]
        for run_id in ids:
            snap = initial_snapshot(run_id)
            for ev in self.read(run_id, limit=10**9):
                snap = apply_event(snap, ev)
            with self._lock:
                self._save_snapshot(snap)
        return len(ids)
