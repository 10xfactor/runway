"""Scripted LLM for offline, deterministic runs and tests."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from runway.core.hashing import to_jsonable
from runway.ports.llm import Estimate, GenerateRequest, GenerateResult, Usage

Item = BaseModel | dict[str, Any] | str | BaseException


class FakeLLMClient:
    """Responses come from a ``script`` list (consumed in order) or ``fn(req, index)``.

    Item types: model/dict -> JSON text, ``str`` -> raw text, exception -> raised.
    """

    def __init__(
        self,
        script: list[Item] | None = None,
        fn: Callable[[GenerateRequest, int], Item] | None = None,
        cost_per_1k_tokens: float = 0.001,
        delay_s: float = 0.0,
    ) -> None:
        self.script = list(script or [])
        self.fn = fn
        self.price = cost_per_1k_tokens
        self.delay_s = delay_s
        self.calls: list[GenerateRequest] = []

    def estimate(self, req: GenerateRequest) -> Estimate:
        tokens = sum(len(m["content"]) for m in req.messages) // 4 + req.max_output_tokens
        return Estimate(tokens=tokens, cost_usd=tokens / 1000 * self.price)

    async def generate(self, req: GenerateRequest) -> GenerateResult:
        index = len(self.calls)
        self.calls.append(req)
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        if self.fn is not None:
            item = self.fn(req, index)
        elif self.script:
            item = self.script.pop(0)
        else:
            raise RuntimeError("FakeLLMClient script exhausted")
        if isinstance(item, BaseException):
            raise item
        text = item if isinstance(item, str) else json.dumps(to_jsonable(item))
        prompt = sum(len(m["content"]) for m in req.messages) // 4
        completion = max(1, len(text) // 4)
        return GenerateResult(
            text=text,
            usage=Usage(
                prompt_tokens=prompt,
                completion_tokens=completion,
                cost_usd=(prompt + completion) / 1000 * self.price,
                latency_ms=self.delay_s_ms(),
            ),
        )

    def delay_s_ms(self) -> int:
        return int(self.delay_s * 1000) or 50
