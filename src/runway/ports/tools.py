"""Tool provider port (stub; MCP implementation arrives post-MVP)."""

from __future__ import annotations

from typing import Any, Protocol


class ToolProvider(Protocol):
    name: str

    async def call(self, tool: str, args: dict[str, Any]) -> Any: ...
