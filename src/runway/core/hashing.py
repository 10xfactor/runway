"""Canonical JSON and hashing helpers. One implementation, used everywhere."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel


def to_jsonable(obj: Any) -> Any:
    """Convert pydantic models (recursively) to plain JSON-compatible data."""
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    return obj


def canonical_json(obj: Any) -> bytes:
    """Deterministic UTF-8 JSON: sorted keys, no whitespace."""
    return json.dumps(to_jsonable(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode(
        "utf-8"
    )


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fingerprint(obj: Any) -> str:
    """SHA-256 of the canonical JSON of ``obj``."""
    return sha256_hex(canonical_json(obj))
