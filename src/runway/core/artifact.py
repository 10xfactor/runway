"""Immutable, content-addressed artifacts."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from runway.core.contract import contract_ref
from runway.core.hashing import fingerprint, to_jsonable


class ArtifactRecord(BaseModel):
    """Storage envelope. ``artifact_id`` = sha256(schema_hash + payload)."""

    artifact_id: str
    schema_ref: str
    schema_hash: str
    payload: Any
    parents: list[str] = Field(default_factory=list)
    created_by: dict[str, Any] = Field(default_factory=dict)


class FeedbackArtifact(BaseModel):
    """Repair feedback injected into a retry prompt (stored for inspection)."""

    text: str


def make_record(
    model: BaseModel, parents: list[str] | None = None, created_by: dict[str, Any] | None = None
) -> ArtifactRecord:
    ref = contract_ref(type(model))
    payload = to_jsonable(model)
    return ArtifactRecord(
        artifact_id=fingerprint({"schema": ref.schema_hash, "payload": payload}),
        schema_ref=ref.name,
        schema_hash=ref.schema_hash,
        payload=payload,
        parents=sorted(parents or []),
        created_by=created_by or {},
    )
