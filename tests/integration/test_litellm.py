"""Contract test for the LiteLLM adapter using LiteLLM's built-in offline mock (no network)."""

from runway.adapters.llm_litellm import LiteLLMClient
from runway.ports.llm import GenerateRequest


async def test_native_strategy_and_usage():
    client = LiteLLMClient(mock_response='{"summary": "hi"}')
    req = GenerateRequest(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
        output_schema={"type": "object"},
    )
    res = await client.generate(req)
    assert res.text == '{"summary": "hi"}' and res.strategy == "native"
    assert res.usage.total_tokens > 0
    assert client.estimate(req).tokens > 0
