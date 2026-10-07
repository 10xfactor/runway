"""Agent: stateless configuration of a probabilistic worker. Holds no budget or run state."""

from __future__ import annotations

from pydantic import BaseModel

from runway.core.hashing import fingerprint


class Agent(BaseModel, frozen=True):
    name: str
    system_prompt: str
    model: str = "gpt-4o-mini"
    temperature: float = 0.0
    max_output_tokens: int = 2048

    def config_hash(self) -> str:
        return fingerprint(self.model_dump())
