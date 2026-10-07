import pytest
from pydantic import BaseModel

from runway.core.budget import Limits, Usage, check
from runway.core.errors import ContractError
from runway.core.graph import WorkGraph
from runway.core.hashing import canonical_json, fingerprint
from runway.core.states import RunStatus, TaskStatus, can_transition_run, can_transition_task
from runway.core.validation import FunctionValidator, ValidationResult, render_feedback
from tests.conftest import GOOD, Report, ReportIn, Silver, Source, architect


def test_canonical_json_is_order_independent():
    assert canonical_json({"b": 1, "a": [1, 2]}) == b'{"a":[1,2],"b":1}'
    assert fingerprint({"a": 1, "b": 2}) == fingerprint({"b": 2, "a": 1})
    # golden vector: guards accidental hashing changes
    assert fingerprint({"a": 1}) == "015abd7f5cc57a2dd94b7590f04ad8084273905ee33ec5cebeae62276a97f862"


def test_state_machines():
    assert can_transition_task(TaskStatus.READY, TaskStatus.RUNNING)
    assert not can_transition_task(TaskStatus.COMMITTED, TaskStatus.RUNNING)
    assert can_transition_run(RunStatus.RUNNING, RunStatus.BUDGET_EXCEEDED)
    assert not can_transition_run(RunStatus.SUCCEEDED, RunStatus.RUNNING)


def test_budget_check():
    lim = Limits(max_tokens=100, max_cost_usd=1.0)
    assert check(lim, Usage(tokens=100)) is None
    assert check(lim, Usage(tokens=100), extra_tokens=1).dimension == "tokens"  # type: ignore[union-attr]
    assert check(lim, Usage(cost_usd=1.5)).dimension == "cost_usd"  # type: ignore[union-attr]


def test_feedback_rendering_is_stable():
    r = ValidationResult.reject("bad", feedback="Use provided fields.")
    text = render_feedback([r, ValidationResult.accept()])
    assert text.startswith("Use provided fields.")
    assert "[rejected]" in text


def test_function_validator_normalizes_returns():
    v = FunctionValidator(lambda o: False, name="f")
    assert v.validate(None, None).status == "rejected"  # type: ignore[arg-type]
    assert FunctionValidator(lambda o: None).validate(None, None).status == "accepted"  # type: ignore[arg-type]


def test_compile_detects_cycle_missing_field_and_unbound():
    t1, t2 = architect(), architect()
    t2.name = "second"
    g = WorkGraph("g", input_model=Source)
    g.add(t1)
    g.add(t2, after=[t1])
    t1_after = WorkGraph("c", input_model=Source)
    a, b = architect(), architect()
    b.name = "b"
    t1_after.add(a, after=[b])
    t1_after.add(b, after=[a])
    with pytest.raises(ContractError, match="cycles"):
        t1_after.compile()

    with pytest.raises(ContractError):
        _ = a.out.nope  # unknown output field is caught at access time

    rep = _report_task()
    g2 = WorkGraph("g2", input_model=Source)
    g2.add(a)
    g2.add(rep, inputs={"model_name": a.out.model_name})  # n_fields unbound
    with pytest.raises(ContractError, match="unbound"):
        g2.compile()


def test_compile_type_mismatch_and_ok():
    a = architect()
    rep = _report_task()
    g = WorkGraph("g", input_model=Source)
    g.add(a)
    g.add(rep, inputs={"model_name": a.out.model_name, "n_fields": a.out.lineage_map})
    with pytest.raises(ContractError, match="type mismatch"):
        g.compile()
    g = WorkGraph("g", input_model=Source)
    g.add(a)
    g.add(rep, inputs={"model_name": a.out.model_name, "n_fields": a.out.model_name})  # str -> int mismatch
    with pytest.raises(ContractError):
        g.compile()


def _report_task():
    from runway.core.agent import Agent
    from runway.core.task import Task

    return Task("report", Agent(name="r", system_prompt="x"), ReportIn, Report)


def test_graph_hash_changes_with_prompt():
    a = architect()
    g1 = WorkGraph("g", input_model=Source)
    g1.add(a)
    g1.compile()
    b = architect()
    b.agent = b.agent.model_copy(update={"system_prompt": "other"})
    g2 = WorkGraph("g", input_model=Source)
    g2.add(b)
    g2.compile()
    assert g1.graph_hash() != g2.graph_hash()
    assert isinstance(GOOD, Silver) and issubclass(Silver, BaseModel)
