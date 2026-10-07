"""LiteLLM adapter: provider-agnostic structured output, retries, and cost accounting.

Credentials are read from the environment by LiteLLM (never from config files or events).
Point ``api_base`` at your gateway/bridge endpoint for air-gapped deployments.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import time
from typing import Any

# Air-gapped safe: never fetch the model price map from the internet at import time.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
os.environ.setdefault("LITELLM_TELEMETRY", "False")

import litellm  # noqa: E402

from runway.core.errors import ConfigError, ProviderError  # noqa: E402
from runway.ports.llm import Estimate, GenerateRequest, GenerateResult, Usage

log = logging.getLogger(__name__)

_RETRYABLE = (
    litellm.RateLimitError,
    litellm.APIConnectionError,
    litellm.Timeout,
    litellm.InternalServerError,
    litellm.ServiceUnavailableError,
)
# Structured-output ladder: native JSON schema -> forced tool call -> schema-in-prompt text.
STRATEGIES = ("native", "tool", "text")


class LiteLLMClient:
    def __init__(
        self,
        *,
        api_base: str | None = None,
        max_retries: int = 3,
        base_delay_s: float = 1.0,
        max_concurrency: int = 8,  # ponytail: concurrency cap only; upgrade to a token bucket for RPM/TPM limits
        **completion_kwargs: Any,
    ) -> None:
        self.api_base = api_base
        self.max_retries = max_retries
        self.base_delay_s = base_delay_s
        self.extra = completion_kwargs
        self._sem = asyncio.Semaphore(max_concurrency)
        self._strategy_by_model: dict[str, int] = {}

    @staticmethod
    def check_env(model: str) -> None:
        """Fail fast when required provider credentials are missing."""
        res = litellm.validate_environment(model=model)
        if not res.get("keys_in_environment", True):
            raise ConfigError(f"missing credentials for {model!r}: set {res.get('missing_keys')}")

    def estimate(self, req: GenerateRequest) -> Estimate:
        tokens = litellm.token_counter(model=req.model, messages=req.messages) + req.max_output_tokens
        try:
            p, c = litellm.cost_per_token(
                model=req.model, prompt_tokens=tokens - req.max_output_tokens, completion_tokens=req.max_output_tokens
            )
            return Estimate(tokens=tokens, cost_usd=p + c)
        except Exception:  # unknown pricing (local models)
            return Estimate(tokens=tokens, cost_usd=None)

    async def generate(self, req: GenerateRequest) -> GenerateResult:
        start = self._strategy_by_model.get(req.model, 0)
        last: Exception | None = None
        for idx in range(start, len(STRATEGIES)):
            try:
                result = await self._with_retries(req, STRATEGIES[idx])
                self._strategy_by_model[req.model] = idx
                return result
            except litellm.BadRequestError as e:  # model rejects this strategy -> next rung
                log.info("strategy %s unsupported for %s", STRATEGIES[idx], req.model)
                last = e
        raise ProviderError(f"no structured-output strategy worked for {req.model}") from last

    async def _with_retries(self, req: GenerateRequest, strategy: str) -> GenerateResult:
        for attempt in range(self.max_retries + 1):
            try:
                async with self._sem:
                    return await self._once(req, strategy)
            except _RETRYABLE as e:
                if attempt >= self.max_retries:
                    raise ProviderError(type(e).__name__, retryable=True) from e
                retry_after = getattr(getattr(e, "response", None), "headers", {}).get("retry-after")
                delay = float(retry_after) if retry_after else self.base_delay_s * 2**attempt
                await asyncio.sleep(delay + random.uniform(0, delay / 4))
            except litellm.BadRequestError:
                raise
            except litellm.AuthenticationError as e:
                raise ProviderError("AuthenticationError") from e
            except Exception as e:
                raise ProviderError(type(e).__name__) from e
        raise ProviderError("exhausted")  # pragma: no cover

    def _kwargs(self, req: GenerateRequest, strategy: str) -> dict[str, Any]:
        messages = list(req.messages)
        kw: dict[str, Any] = {
            "model": req.model,
            "temperature": req.temperature,
            "max_tokens": req.max_output_tokens,
            "timeout": req.timeout_s,
            **self.extra,
        }
        if self.api_base:
            kw["api_base"] = self.api_base
        if strategy == "native":
            kw["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": req.output_schema_name, "schema": req.output_schema},
            }
        elif strategy == "tool":
            kw["tools"] = [
                {
                    "type": "function",
                    "function": {"name": "submit", "description": "Submit the result", "parameters": req.output_schema},
                }
            ]
            kw["tool_choice"] = {"type": "function", "function": {"name": "submit"}}
        else:
            messages[0] = {
                "role": "system",
                "content": messages[0]["content"]
                + "\nRespond with ONLY JSON matching this schema:\n"
                + json.dumps(req.output_schema),
            }
        kw["messages"] = messages
        return kw

    async def _once(self, req: GenerateRequest, strategy: str) -> GenerateResult:
        t0 = time.perf_counter()
        resp = await litellm.acompletion(**self._kwargs(req, strategy))
        msg = resp.choices[0].message
        calls = getattr(msg, "tool_calls", None)
        text = calls[0].function.arguments if (strategy == "tool" and calls) else (msg.content or "")
        u = resp.usage
        try:
            cost, unknown = float(litellm.completion_cost(completion_response=resp)), False
        except Exception:
            cost, unknown = 0.0, True
        return GenerateResult(
            text=text,
            strategy=strategy,
            finish_reason=resp.choices[0].finish_reason or "stop",
            usage=Usage(
                prompt_tokens=u.prompt_tokens,
                completion_tokens=u.completion_tokens,
                cost_usd=cost,
                cost_unknown=unknown,
                latency_ms=int((time.perf_counter() - t0) * 1000),
            ),
        )
