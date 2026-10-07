"""Tiny forward-only SQLite migrator: one version at a time, stop on failure, idempotent."""

from __future__ import annotations

import logging
import sqlite3
from importlib import resources

log = logging.getLogger(__name__)


def _migrations() -> list[tuple[int, str, str]]:
    root = resources.files("runway") / "_schema" / "sql"
    out = []
    for entry in sorted(root.iterdir(), key=lambda e: e.name):
        if entry.name.endswith(".sql"):
            out.append((int(entry.name.split("_", 1)[0]), entry.name, entry.read_text("utf-8")))
    return out


def migrate(conn: sqlite3.Connection) -> int:
    """Apply pending migrations in order. Returns the current schema version."""
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT)")
    done = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
    current = max(done, default=0)
    for version, name, sql in _migrations():
        if version in done:
            continue
        if version != current + 1:
            raise RuntimeError(f"migration gap: have {current}, next is {version} ({name})")
        try:
            conn.execute("BEGIN")
            for stmt in sql.split(";\n"):
                if stmt.strip():
                    conn.execute(stmt)
            conn.execute("INSERT INTO schema_migrations VALUES (?, datetime('now'))", (version,))
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            log.error("migration %s failed", name)
            raise
        current = version
        log.info("applied migration %s", name)
    return current
