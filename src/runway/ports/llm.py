"""LLM port."""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    cost_unknown: bool = False
    latency_ms: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class GenerateRequest(BaseModel):
    model: str
    messages: list[dict[str, str]]
    output_schema: dict[str, Any]
    output_schema_name: str = "Output"
    temperature: float = 0.0
    max_output_tokens: int = 2048
    timeout_s: float | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class GenerateResult(BaseModel):
    text: str
    usage: Usage = Field(default_factory=Usage)
    finish_reason: str = "stop"
    strategy: str = "native"


class Estimate(BaseModel):
    tokens: int
    cost_usd: float | None = None


class LLMClient(Protocol):
    async def generate(self, req: GenerateRequest) -> GenerateResult: ...

    def estimate(self, req: GenerateRequest) -> Estimate: ...
