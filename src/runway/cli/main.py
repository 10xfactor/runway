"""Plain-text CLI. The web Console (``runway dev``) is the rich interface."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from runway.adapters.artifacts_fs import FsArtifactStore
from runway.adapters.events_sqlite import SqliteEventStore
from runway.api.flow import Flow, load_flow
from runway.core.errors import ConfigError, ReplayStaleError, RunwayError
from runway.core.events import Event
from runway.core.states import RunStatus
from runway.extensions.registry import discover
from runway.ports.llm import LLMClient
from runway.runtime.run import Run, RunResult

app = typer.Typer(help="Runway: agentic + deterministic framework.", no_args_is_help=True, add_completion=False)
ext_app = typer.Typer(help="Inspect installed extensions.")
db_app = typer.Typer(help="Store maintenance.")
app.add_typer(ext_app, name="ext")
app.add_typer(db_app, name="db")
out = Console(highlight=False)
err = Console(stderr=True, highlight=False)

EXIT = {RunStatus.SUCCEEDED: 0, RunStatus.FAILED: 1, RunStatus.BUDGET_EXCEEDED: 2, RunStatus.CANCELLED: 130}
Home = Annotated[Path, typer.Option("--home", envvar="RUNWAY_HOME", help="Store directory.")]


def open_store(home: Path) -> tuple[SqliteEventStore, FsArtifactStore]:
    return SqliteEventStore(home / "runway.db"), FsArtifactStore(home / "blobs")


def _line(ev: Event) -> None:
    where = f"{ev.task_name or '-'}" + (f"#{ev.attempt_no}" if ev.attempt_no else "")
    extra = ""
    if ev.type in ("validation.failed",):
        extra = " " + ",".join(sorted({f"{i['code']}@{i['path']}" for r in ev.data["results"] for i in r["issues"]}))
    elif ev.type in ("task.failed", "run.failed"):
        extra = f" {ev.data['error_code']}"
    elif ev.type == "model.generated":
        extra = f" tokens={ev.data['prompt_tokens'] + ev.data['completion_tokens']} cost=${ev.data['cost_usd']:.4f}"
    print(f"{ev.seq:>4} {ev.type:<20} {where}{extra}", flush=True)  # no payloads, ever


def _exec(flow: Flow, home: Path, entrypoint: str, parent: tuple[str, str, bool] | None = None) -> RunResult:
    store, artifacts = open_store(home)
    llm: LLMClient
    if flow.llm is None:
        from runway.adapters.llm_litellm import LiteLLMClient

        for t in flow.graph.tasks.values():
            LiteLLMClient.check_env(t.agent.model)
        llm = LiteLLMClient()
    else:
        llm = flow.llm
    run = Run(flow.graph, store, artifacts, llm, entrypoint=entrypoint, listeners=[_line])

    async def main() -> RunResult:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, run.cancel)
        if parent:
            return await run.replay(parent[0], parent[1], allow_stale=parent[2])
        return await run.execute(flow.input)

    return asyncio.run(main())


def _finish(res: RunResult) -> None:
    err.print(f"run {res.run_id}: {res.status.value}" + (f" ({res.error_code})" if res.error_code else ""))
    raise typer.Exit(EXIT.get(res.status, 1))


@app.command()
def run(entrypoint: str, home: Home = Path(".runway")) -> None:
    """Run a flow, e.g. ``runway run runway.demo:flow``."""
    sys.path.insert(0, os.getcwd())
    _finish(_exec(load_flow(entrypoint), home, entrypoint))


@app.command()
def demo(
    fail_at: Annotated[str | None, typer.Option(help="Task whose output is garbage (try replay).")] = None,
    home: Home = Path(".runway"),
) -> None:
    """Run the bundled offline demo (no API key)."""
    if fail_at:
        os.environ["RUNWAY_DEMO_FAIL"] = fail_at
    _finish(_exec(load_flow("runway.demo:flow"), home, "runway.demo:flow"))


@app.command()
def replay(
    run_id: str,
    from_task: Annotated[str, typer.Option("--from", help="Task to restart from.")],
    allow_stale: Annotated[bool, typer.Option(help="Re-run upstream tasks whose cache key changed.")] = False,
    home: Home = Path(".runway"),
) -> None:
    """Child run: reuse verified upstream outputs and re-run from a task."""
    sys.path.insert(0, os.getcwd())
    store, _ = open_store(home)
    snap = store.snapshot(run_id)
    if snap is None or not snap.run.entrypoint:
        raise ConfigError(f"run {run_id!r} not found or has no entrypoint")
    os.environ.pop("RUNWAY_DEMO_FAIL", None)
    try:
        _finish(_exec(load_flow(snap.run.entrypoint), home, snap.run.entrypoint, (run_id, from_task, allow_stale)))
    except ReplayStaleError as e:
        err.print(f"stale: {e}. Use --allow-stale to re-run those tasks.")
        raise typer.Exit(3) from e


@app.command()
def runs(limit: int = 20, home: Home = Path(".runway")) -> None:
    """List recent runs."""
    store, _ = open_store(home)
    t = Table("run", "graph", "status", "tasks ok", "cost", "tokens")
    for s in store.list_runs(limit):
        ok = sum(1 for x in s.tasks.values() if x.status in ("COMMITTED", "CACHED"))
        t.add_row(
            s.run.run_id,
            s.run.graph_id,
            s.run.status.value,
            f"{ok}/{len(s.tasks)}",
            f"${s.totals['cost_usd']:.4f}",
            str(int(s.totals["tokens"])),
        )
    out.print(t)


@app.command()
def inspect(
    run_id: str, json_out: Annotated[bool, typer.Option("--json")] = False, home: Home = Path(".runway")
) -> None:
    """Print the causal event log of a run (never payloads)."""
    store, _ = open_store(home)
    events = store.read(run_id, limit=10**9)
    if not events:
        raise typer.Exit(_fail(f"unknown run {run_id!r}"))
    for ev in events:
        if json_out:
            print(ev.model_dump_json())
        else:
            _line(ev)


def _fail(msg: str) -> int:
    err.print(msg)
    return 3


@app.command()
def dev(
    entrypoint: Annotated[str | None, typer.Argument(help="Optional flow to register for replay/runs.")] = None,
    home: Home = Path(".runway"),
    host: str = "127.0.0.1",
    port: int = 7777,
    no_open: Annotated[bool, typer.Option("--no-open")] = False,
    expose_payloads: Annotated[
        bool, typer.Option("--expose-payloads", help="Show artifact bodies in the Console.")
    ] = False,
) -> None:
    """Start the Runway Console (local web UI)."""
    try:
        from runway.server.app import serve
    except ImportError as e:
        raise typer.Exit(_fail('Console needs extras: pip install "runway-ai[ui]"')) from e
    serve(home, host, port, open_browser=not no_open, expose_payloads=expose_payloads)


@app.command()
def init(home: Home = Path(".runway")) -> None:
    """Create the local store."""
    open_store(home)
    out.print(f"initialized {home}/ (runway demo, then runway dev)")


@app.command()
def doctor(home: Home = Path(".runway")) -> None:
    """Check store health and installed extensions."""
    store, _ = open_store(home)
    out.print(f"store ok: {home}/runway.db ({len(store.list_runs(10**6))} runs)")
    bad = [p for p in discover() if p.error]
    for p in discover():
        out.print(f"ext {p.group}:{p.name} ({p.dist} {p.version}) {'ERROR ' + p.error if p.error else 'ok'}")
    raise typer.Exit(1 if bad else 0)


@ext_app.command("list")
def ext_list() -> None:
    """List installed extensions."""
    for p in discover():
        out.print(f"{p.group:<24} {p.name:<20} {p.dist} {p.version} {p.error or ''}")


@db_app.command("rebuild")
def db_rebuild(home: Home = Path(".runway")) -> None:
    """Recompute projections from the event log."""
    store, _ = open_store(home)
    out.print(f"rebuilt {store.rebuild()} runs")


@app.command("events-schema")
def events_schema() -> None:
    """Print JSON Schemas for all event types."""
    from runway.core.events import event_json_schemas

    print(json.dumps(event_json_schemas(), indent=2))


def main() -> None:
    """Console-script entry point: Runway errors print one line, not a traceback."""
    try:
        app()
    except RunwayError as e:
        raise SystemExit(_fail(f"error: {e}")) from None
