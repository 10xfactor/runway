import asyncio

import pytest
from pydantic import BaseModel

from runway.adapters.llm_fake import FakeLLMClient
from runway.core.agent import Agent
from runway.core.errors import ProviderError, ReplayStaleError
from runway.core.graph import WorkGraph
from runway.core.snapshot import apply_event, initial_snapshot
from runway.core.states import RunStatus, TaskStatus
from runway.core.task import Task
from tests.conftest import BAD, GOOD, SRC, Report, ReportIn, Silver, Source, architect, single_graph


async def test_reject_then_accept_injects_feedback(h):
    llm = FakeLLMClient([BAD, GOOD])
    res = await h.run(single_graph(architect()), llm).execute(SRC)
    assert res.status == RunStatus.SUCCEEDED
    assert res.outputs["architect"] == GOOD
    # feedback reached the second prompt
    second = llm.calls[1].messages
    assert any("do not exist" in m["content"] for m in second)
    types = h.types(res.run_id, "architect")
    assert types.count("model.generated") == 2
    assert "validation.failed" in types and "agent.retry" in types and "task.committed" in types
    snap = h.store.snapshot(res.run_id)
    att = snap.tasks["architect"].attempts
    assert [a.outcome for a in att] == ["rejected", "accepted"]
    assert att[0].issues[0]["code"] == "lineage"


async def test_nothing_committed_before_validators_accept(h):
    llm = FakeLLMClient([Silver(model_name=f"m{i}", lineage_map={"a": "zzz"}) for i in range(4)])
    res = await h.run(single_graph(architect(retries=3)), llm).execute(SRC)
    assert res.status == RunStatus.FAILED and res.error_code == "RETRIES_EXHAUSTED"
    assert res.outputs == {}
    assert "task.committed" not in h.types(res.run_id)


async def test_repeated_output_stops_early(h):
    llm = FakeLLMClient([BAD, BAD, GOOD])
    res = await h.run(single_graph(architect()), llm).execute(SRC)
    assert res.error_code == "REPEATED_OUTPUT"
    assert len(llm.calls) == 2


async def test_validator_crash_is_error_not_retry(h):
    def boom(_o):
        raise RuntimeError("secret patient data")

    llm = FakeLLMClient([GOOD, GOOD])
    res = await h.run(single_graph(architect(validators=[boom])), llm).execute(SRC)
    assert res.error_code == "VALIDATOR_ERROR"
    assert len(llm.calls) == 1
    blob = " ".join(e.model_dump_json() for e in h.store.read(res.run_id, limit=999))
    assert "secret patient data" not in blob  # exception text never reaches events


async def test_parse_failure_counts_as_attempt_and_repairs(h):
    llm = FakeLLMClient(["not json", GOOD])
    res = await h.run(single_graph(architect(validators=[])), llm).execute(SRC)
    assert res.status == RunStatus.SUCCEEDED
    snap = h.store.snapshot(res.run_id)
    assert snap.tasks["architect"].attempts[0].issues[0]["code"] == "schema"


async def test_provider_error_fails_task(h):
    llm = FakeLLMClient([ProviderError("down")])
    res = await h.run(single_graph(architect()), llm).execute(SRC)
    assert res.error_code == "PROVIDER_ERROR"


async def test_budget_breach_stops_deterministically(h):
    llm = FakeLLMClient([BAD, GOOD])
    res = await h.run(single_graph(architect(max_tokens=50)), llm).execute(SRC)
    assert res.status == RunStatus.BUDGET_EXCEEDED
    exceeded = [e for e in h.store.read(res.run_id) if e.type == "budget.exceeded"]
    assert exceeded and exceeded[0].data["dimension"] == "tokens" and exceeded[0].data["scope"] == "task"
    assert h.store.snapshot(res.run_id).breach["dimension"] == "tokens"


async def test_run_scope_budget_and_cost(h):
    llm = FakeLLMClient([GOOD], cost_per_1k_tokens=100)  # absurd price -> cost breach
    res = await h.run(single_graph(architect(max_cost_usd=0.5)), llm).execute(SRC)
    assert res.status == RunStatus.BUDGET_EXCEEDED


async def test_time_budget(h):
    llm = FakeLLMClient([GOOD], delay_s=1.0)
    res = await h.run(single_graph(architect(max_time_s=0.05)), llm).execute(SRC)
    assert res.status == RunStatus.BUDGET_EXCEEDED
    ev = next(e for e in h.store.read(res.run_id) if e.type == "budget.exceeded")
    assert ev.data["dimension"] == "time_s"


class _Two(BaseModel):
    x: str
    y: str


def build_fan():
    a = Task("a", Agent(name="a", system_prompt="x"), Source, Silver)
    b = Task("b", Agent(name="b", system_prompt="x"), _One, Report)
    c = Task("c", Agent(name="c", system_prompt="x"), _One, Report)
    d = Task("d", Agent(name="d", system_prompt="x"), _Two, Report)
    g = WorkGraph("fan", input_model=Source)
    g.add(a)
    g.add(b, inputs={"x": a.out.model_name})
    g.add(c, inputs={"x": a.out.model_name})
    g.add(d, inputs={"x": b.out.summary, "y": c.out.summary})
    return g


class _One(BaseModel):
    x: str


async def test_fan_out_fan_in_runs_concurrently_and_binds_fields(h):
    active = peak = 0

    def fn(req, i):
        nonlocal active, peak
        name = req.output_schema_name
        return GOOD if name == "Silver" else Report(summary=f"s{i}")

    class Counting(FakeLLMClient):
        async def generate(self, req):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            try:
                return await super().generate(req)
            finally:
                active -= 1

    llm = Counting(fn=fn, delay_s=0.05)
    res = await h.run(build_fan(), llm, max_concurrency=4).execute(SRC)
    assert res.status == RunStatus.SUCCEEDED
    assert peak == 2  # b and c ran in parallel
    # d only saw the subscribed fields, not whole upstream artifacts
    d_prompt = next(c for c in llm.calls if c.messages[0]["content"] == "x" and '"y"' in c.messages[1]["content"])
    assert "lineage_map" not in d_prompt.messages[1]["content"]


async def test_failure_skips_dependents_and_cancels(h):
    llm = FakeLLMClient(
        fn=lambda req, i: ProviderError("x") if req.output_schema_name == "Silver" else Report(summary="s")
    )
    res = await h.run(build_fan(), llm).execute(SRC)
    snap = h.store.snapshot(res.run_id)
    assert snap.tasks["a"].status == TaskStatus.FAILED
    assert {snap.tasks[n].status for n in "bcd"} == {TaskStatus.SKIPPED}
    assert res.status == RunStatus.FAILED


async def test_cancel_mid_run_is_replayable_state(h):
    llm = FakeLLMClient([GOOD], delay_s=5)
    run = h.run(single_graph(architect()), llm)
    t = asyncio.create_task(run.execute(SRC))
    await asyncio.sleep(0.1)
    run.cancel()
    res = await t
    assert res.status == RunStatus.CANCELLED
    types = h.types(res.run_id)
    assert "attempt.aborted" in types and types[-1] == "run.cancelled"


def two_step():
    a = architect()
    rep = Task("report", Agent(name="r", system_prompt="x"), ReportIn, Report)
    g = WorkGraph("two", input_model=Source)
    g.add(a)
    g.add(rep, inputs={"model_name": a.out.model_name, "n_fields": a.out.model_name})
    return g


def two_step_ok():
    class RIn(BaseModel):
        model_name: str
        note: str

    a = architect()
    rep = Task("report", Agent(name="r", system_prompt="x"), RIn, Report)
    g = WorkGraph("two", input_model=Source)
    g.add(a)
    g.add(rep, inputs={"model_name": a.out.model_name, "note": a.out.model_name})
    return g


async def test_replay_reuses_upstream_without_model_calls(h):
    fn = lambda req, i: GOOD if req.output_schema_name == "Silver" else Report(summary="ok")  # noqa: E731
    first = await h.run(two_step_ok(), FakeLLMClient(fn=fn)).execute(SRC)
    assert first.status == RunStatus.SUCCEEDED
    llm2 = FakeLLMClient(fn=fn)
    child = await h.run(two_step_ok(), llm2).replay(first.run_id, "report")
    assert child.status == RunStatus.SUCCEEDED
    assert [c.output_schema_name for c in llm2.calls] == ["Report"]  # upstream not re-executed
    types = h.types(child.run_id, "architect")
    assert "task.cached" in types and "model.requested" not in types
    snap = h.store.snapshot(child.run_id)
    assert snap.run.parent_run_id == first.run_id and snap.run.replay_from == "report"
    assert snap.tasks["architect"].status == TaskStatus.CACHED
    assert h.store.snapshot(first.run_id).run.status == RunStatus.SUCCEEDED  # parent untouched


async def test_replay_detects_stale_when_prompt_changes(h):
    fn = lambda req, i: GOOD if req.output_schema_name == "Silver" else Report(summary="ok")  # noqa: E731
    first = await h.run(two_step_ok(), FakeLLMClient(fn=fn)).execute(SRC)
    g = two_step_ok()
    g.tasks["architect"].agent = g.tasks["architect"].agent.model_copy(update={"system_prompt": "changed"})
    run = h.run(g, FakeLLMClient(fn=fn))
    plan = run.plan_replay(first.run_id, "report")
    assert plan.stale and "agent" in plan.stale[0].reason
    with pytest.raises(ReplayStaleError):
        await run.replay(first.run_id, "report")
    child = await run.replay(first.run_id, "report", allow_stale=True)
    assert child.status == RunStatus.SUCCEEDED


async def test_replay_from_failed_node(h):
    state = {"fail": True}

    def fn(req, i):
        if req.output_schema_name == "Silver":
            return GOOD
        return Report(summary="x") if not state["fail"] else "garbage"

    first = await h.run(two_step_ok(), FakeLLMClient(fn=fn)).execute(SRC)
    assert first.status == RunStatus.FAILED
    state["fail"] = False
    llm = FakeLLMClient(fn=fn)
    child = await h.run(two_step_ok(), llm).replay(first.run_id, "report")
    assert child.status == RunStatus.SUCCEEDED
    assert [c.output_schema_name for c in llm.calls] == ["Report"]


async def test_reducer_matches_stored_snapshot_and_rebuild(h):
    res = await h.run(single_graph(architect()), FakeLLMClient([BAD, GOOD])).execute(SRC)
    snap = initial_snapshot(res.run_id)
    for ev in h.store.read(res.run_id):
        snap = apply_event(snap, ev)
    assert snap == h.store.snapshot(res.run_id)
    before = h.store.snapshot(res.run_id).model_dump_json()
    assert h.store.rebuild() == 1
    assert h.store.snapshot(res.run_id).model_dump_json() == before


async def test_events_never_contain_payloads(h):
    res = await h.run(single_graph(architect()), FakeLLMClient([BAD, GOOD])).execute(SRC)
    blob = " ".join(e.model_dump_json() for e in h.store.read(res.run_id, limit=999))
    assert "orders_silver" not in blob and "raw_fields" not in blob
