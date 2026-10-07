"""Structural diff of two JSON documents as (path, change) pairs; values only on request."""

from __future__ import annotations

from typing import Any


def diff_paths(old: Any, new: Any, path: str = "", values: bool = False) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    def add(p: str, change: str, a: Any = None, b: Any = None) -> None:
        item: dict[str, Any] = {"path": p, "change": change}
        if values:
            item.update(old=a, new=b)
        out.append(item)

    def join(p: str, k: Any) -> str:
        return f"{p}.{k}" if p else str(k)

    if isinstance(old, dict) and isinstance(new, dict):
        for k in sorted(set(old) | set(new), key=str):
            if k not in old:
                add(join(path, k), "added", None, new[k])
            elif k not in new:
                add(join(path, k), "removed", old[k], None)
            else:
                out.extend(diff_paths(old[k], new[k], join(path, k), values))
    elif isinstance(old, list) and isinstance(new, list):
        for i in range(max(len(old), len(new))):
            if i >= len(old):
                add(join(path, i), "added", None, new[i])
            elif i >= len(new):
                add(join(path, i), "removed", old[i], None)
            else:
                out.extend(diff_paths(old[i], new[i], join(path, i), values))
    elif old != new:
        add(path, "changed", old, new)
    return out
