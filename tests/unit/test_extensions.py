import subprocess
import sys
from types import SimpleNamespace

from runway.extensions import hooks
from runway.extensions.registry import Plugin
from runway.extensions.scaffold import render


def test_scaffolded_plugins_pass_their_own_tests(tmp_path):
    for kind in ("validator", "sink", "hook"):
        pkg = f"my_{kind}"
        for rel, text in render(kind, pkg).items():
            (tmp_path / kind / rel).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / kind / rel).write_text(text)
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(tmp_path / kind / "tests")],
            env={"PYTHONPATH": str(tmp_path / kind / "src")},
            capture_output=True,
            text=True,
        )
        assert r.returncode == 0, r.stdout + r.stderr


def test_load_listeners_skips_broken_and_wraps_hooks(monkeypatch):
    seen = []

    class H:
        def after_run(self, ev):
            seen.append(ev.type)

    def fake(group, allow=None):
        if group == "runway.event_sinks":
            return [
                Plugin(group, "s", "d", "1", obj=lambda ev: seen.append("sink")),
                Plugin(group, "x", "d", "1", error="E"),
            ]
        return [Plugin(group, "h", "d", "1", obj=H())]

    monkeypatch.setattr("runway.extensions.registry.discover", fake)
    ls = hooks.load_listeners()
    assert len(ls) == 2
    for fn in ls:
        fn(SimpleNamespace(type="run.completed"))
    assert seen == ["sink", "run.completed"]
