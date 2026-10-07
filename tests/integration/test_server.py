import asyncio
import os

import pytest
from fastapi.testclient import TestClient

from runway import demo
from runway.adapters.artifacts_fs import FsArtifactStore
from runway.adapters.events_sqlite import SqliteEventStore
from runway.runtime.run import Run
from runway.server.app import create_app

TOKEN = "t0ken"
H = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def client(tmp_path):
    os.environ["RUNWAY_DEMO_DELAY"] = "0"
    store = SqliteEventStore(tmp_path / "runway.db")
    flow = demo.flow()
    res = asyncio.run(
        Run(flow.graph, store, FsArtifactStore(tmp_path / "blobs"), flow.llm, entrypoint="runway.demo:flow").execute(
            flow.input
        )
    )
    store.close()
    app = create_app(tmp_path, TOKEN, hosts={"testserver"})
    c = TestClient(app)
    c.run_id = res.run_id  # type: ignore[attr-defined]
    return c


def test_auth_and_host_guard(client):
    assert client.get("/api/runs").status_code == 401
    assert client.get("/api/runs", headers=H).status_code == 200
    assert client.get("/api/runs", headers={**H, "host": "evil.com"}).status_code == 403
    assert client.get("/api/health").json()["payloads_exposed"] is False
    r = client.get("/api/runs", headers=H)
    assert r.headers["cache-control"] == "no-store" and "default-src 'self'" in r.headers["content-security-policy"]


def test_snapshot_events_and_task_detail(client):
    rid = client.run_id
    snap = client.get(f"/api/runs/{rid}/snapshot", headers=H).json()
    assert snap["run"]["status"] == "SUCCEEDED" and len(snap["tasks"]) == 4
    evs = client.get(f"/api/runs/{rid}/events?after_seq=10&limit=5", headers=H).json()
    assert [e["seq"] for e in evs] == [11, 12, 13, 14, 15]
    d = client.get(f"/api/runs/{rid}/tasks/architect", headers=H).json()
    assert len(d["state"]["attempts"]) == 3
    assert d["state"]["attempts"][0]["issues"] and "lineage" in d["state"]["attempts"][0]["feedback_preview"]
    assert "feedback_text" not in d["state"]["attempts"][0]  # payload-gated


def test_payload_gate_and_diff_paths_only(client):
    rid = client.run_id
    aid = client.get(f"/api/runs/{rid}/snapshot", headers=H).json()["tasks"]["architect"]["artifact_id"]
    assert client.get(f"/api/artifacts/{aid}?meta=1", headers=H).status_code == 200
    assert client.get(f"/api/artifacts/{aid}", headers=H).status_code == 403
    diff = client.get(f"/api/runs/{rid}/attempts/architect/2/diff", headers=H).json()
    assert diff["available"] and all("old" not in c for c in diff["changes"])  # values hidden
    assert "lineage_map.amount" in diff["fixed_paths"]


def test_sse_replays_all_events_then_ends(client):
    rid = client.run_id
    with client.stream("GET", f"/api/runs/{rid}/stream?after=50&token={TOKEN}") as r:
        body = "".join(r.iter_text())
    assert "id: 51" in body and "event: run.completed" in body and "event: stream.end" in body


def test_replay_plan_and_compare(client):
    rid = client.run_id
    plan = client.post(f"/api/runs/{rid}/replay/plan", headers=H, json={"from_task": "report"}).json()
    assert plan["reuse"] == ["profile", "architect", "quality"] or set(plan["reuse"]) == {
        "profile",
        "architect",
        "quality",
    }
    assert plan["rerun"] == ["report"] and plan["stale"] == []
    cmp = client.get(f"/api/compare?a={rid}&b={rid}", headers=H).json()
    assert all(row["same_output"] for row in cmp["tasks"])
