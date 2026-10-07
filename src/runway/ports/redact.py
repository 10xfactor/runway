"""Redactor port: scrubs free-text before it reaches the event log."""

from __future__ import annotations

from typing import Protocol


class Redactor(Protocol):
    def redact(self, text: str) -> str: ...
