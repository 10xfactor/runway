"""Default redactor: masks emails, SSN-like and long digit sequences in free text."""

from __future__ import annotations

import re

_PATTERNS = [
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    re.compile(r"\b\d{9,}\b"),
]


class DefaultRedactor:
    def __init__(self, extra_patterns: list[str] | None = None) -> None:
        self.patterns = _PATTERNS + [re.compile(p) for p in extra_patterns or []]

    def redact(self, text: str) -> str:
        for p in self.patterns:
            text = p.sub("[REDACTED]", text)
        return text
