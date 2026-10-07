"""Content-addressed artifact store on the local filesystem (mode 0600, atomic writes)."""

from __future__ import annotations

import os
from pathlib import Path

from runway.core.artifact import ArtifactRecord


class FsArtifactStore:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, artifact_id: str) -> Path:
        return self.root / artifact_id[:2] / f"{artifact_id[2:]}.json"

    def put(self, record: ArtifactRecord) -> int:
        path = self._path(record.artifact_id)
        data = record.model_dump_json().encode()
        if path.exists():
            return len(data)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".tmp{os.getpid()}")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        return len(data)

    def get(self, artifact_id: str) -> ArtifactRecord:
        return ArtifactRecord.model_validate_json(self._path(artifact_id).read_text("utf-8"))

    def exists(self, artifact_id: str) -> bool:
        return self._path(artifact_id).exists()
