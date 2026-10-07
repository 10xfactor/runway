"""Artifact store port (content-addressed)."""

from __future__ import annotations

from typing import Protocol

from runway.core.artifact import ArtifactRecord


class ArtifactStore(Protocol):
    def put(self, record: ArtifactRecord) -> int:
        """Store a record (idempotent). Returns the size in bytes."""
        ...

    def get(self, artifact_id: str) -> ArtifactRecord: ...

    def exists(self, artifact_id: str) -> bool: ...
