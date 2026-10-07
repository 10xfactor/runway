"""Contracts are plain Pydantic models; their identity is derived from the JSON schema."""

from __future__ import annotations

from pydantic import BaseModel

from runway.core.hashing import fingerprint


class ContractRef(BaseModel):
    name: str
    schema_hash: str


def schema_hash(model: type[BaseModel]) -> str:
    return fingerprint(model.model_json_schema())


def contract_ref(model: type[BaseModel]) -> ContractRef:
    return ContractRef(name=f"{model.__module__}.{model.__qualname__}", schema_hash=schema_hash(model))
