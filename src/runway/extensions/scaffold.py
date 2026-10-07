"""File templates for ``runway new <kind> <name>``: a minimal installable plugin package with a conformance test."""

from __future__ import annotations

from runway.extensions.registry import API_VERSION

KINDS = {"validator": "runway.validators", "sink": "runway.event_sinks", "hook": "runway.hooks"}

_PYPROJECT = """[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "{dist}"
version = "0.1.0"
description = "Runway {kind} plugin"
requires-python = ">=3.11"
dependencies = ["runway-ai"]

[project.entry-points."{group}"]
{pkg} = "{pkg}:{symbol}"

[tool.hatch.build.targets.wheel]
packages = ["src/{pkg}"]
"""

_VALIDATOR = '''"""Deterministic validator: same output in, same verdict out. Never call an LLM here."""

from runway.extensions import FunctionValidator, ValidationIssue, ValidationResult


def _check(output) -> ValidationResult:
    text = str(output)
    if text.strip():
        return ValidationResult.accept()
    issue = ValidationIssue(code="empty", path="", message="output is empty", hint="Return non-empty content")
    return ValidationResult.reject("empty output", issues=[issue])


validator = FunctionValidator(_check, name="{pkg}", version="1")
validator.runway_api = "{api}"
'''

_VALIDATOR_TEST = """from runway.extensions.testing import check_validator

from {pkg} import validator


def test_conformance():
    check_validator(validator, good="hello", bad="   ")
"""

_SINK = '''"""Event sink: observes events, cannot change run results. Events never contain payloads; keep it that way."""

from runway.extensions import API_VERSION


def sink(event) -> None:
    print(f"{{event.seq}} {{event.type}}")


sink.runway_api = API_VERSION
'''

_SINK_TEST = """from types import SimpleNamespace

from {pkg} import sink


def test_sink_accepts_event(capsys):
    sink(SimpleNamespace(seq=1, type="run.created"))
    assert "run.created" in capsys.readouterr().out
"""

_HOOK = '''"""Lifecycle hook: implement any of before_run, after_task_commit, on_validation_failed, after_run."""

from runway.extensions import API_VERSION


class Hook:
    runway_api = API_VERSION

    def after_run(self, event) -> None:
        print(f"run finished: {{event.type}}")


hook = Hook()
'''

_HOOK_TEST = """from types import SimpleNamespace

from runway.extensions.hooks import hook_listener

from {pkg} import hook


def test_hook_receives_run_end(capsys):
    hook_listener(hook)(SimpleNamespace(type="run.completed"))
    assert "run finished" in capsys.readouterr().out
"""

_BODIES = {
    "validator": (_VALIDATOR, _VALIDATOR_TEST, "validator"),
    "sink": (_SINK, _SINK_TEST, "sink"),
    "hook": (_HOOK, _HOOK_TEST, "hook"),
}


def render(kind: str, name: str) -> dict[str, str]:
    """Return ``{relative_path: content}`` for a plugin package named ``name`` (distribution) of ``kind``."""
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}; choose from {sorted(KINDS)}")
    pkg = name.replace("-", "_")
    if not pkg.isidentifier():
        raise ValueError(f"{name!r} is not a valid package name")
    body, test, symbol = _BODIES[kind]
    ctx = {"dist": name, "pkg": pkg, "kind": kind, "group": KINDS[kind], "symbol": symbol, "api": API_VERSION}
    return {
        "pyproject.toml": _PYPROJECT.format(**ctx),
        f"src/{pkg}/__init__.py": body.format(**ctx),
        f"tests/test_{pkg}.py": test.format(**ctx),
    }
