"""Pure budget arithmetic. Enforcement lives in runtime.budget_gate."""

from __future__ import annotations

from pydantic import BaseModel


class Limits(BaseModel):
    """Per-scope limits. ``None`` means unlimited."""

    max_tokens: int | None = 100_000
    max_cost_usd: float | None = 2.00
    max_time_s: float | None = None
    max_retries: int = 3
    max_tool_calls: int | None = None


class Usage(BaseModel):
    tokens: int = 0
    cost_usd: float = 0.0
    retries: int = 0
    tool_calls: int = 0


class Breach(BaseModel):
    dimension: str
    used: float
    limit: float


def check(limits: Limits, usage: Usage, extra_tokens: int = 0, extra_cost: float = 0.0) -> Breach | None:
    """Return the first exceeded dimension for ``usage`` plus a pending ``extra``."""
    tokens = usage.tokens + extra_tokens
    cost = usage.cost_usd + extra_cost
    if limits.max_tokens is not None and tokens > limits.max_tokens:
        return Breach(dimension="tokens", used=tokens, limit=limits.max_tokens)
    if limits.max_cost_usd is not None and cost > limits.max_cost_usd:
        return Breach(dimension="cost_usd", used=cost, limit=limits.max_cost_usd)
    if limits.max_tool_calls is not None and usage.tool_calls > limits.max_tool_calls:
        return Breach(dimension="tool_calls", used=usage.tool_calls, limit=limits.max_tool_calls)
    return None


def warnings(limits: Limits, usage: Usage, ratio: float = 0.8) -> list[Breach]:
    """Dimensions at or above ``ratio`` of their limit."""
    out: list[Breach] = []
    if limits.max_tokens and usage.tokens >= ratio * limits.max_tokens:
        out.append(Breach(dimension="tokens", used=usage.tokens, limit=limits.max_tokens))
    if limits.max_cost_usd and usage.cost_usd >= ratio * limits.max_cost_usd:
        out.append(Breach(dimension="cost_usd", used=usage.cost_usd, limit=limits.max_cost_usd))
    return out
