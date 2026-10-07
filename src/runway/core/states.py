"""Task and run state machines as pure transition tables."""

from __future__ import annotations

from enum import StrEnum


class TaskStatus(StrEnum):
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    VALIDATING = "VALIDATING"
    REPAIRING = "REPAIRING"
    COMMITTED = "COMMITTED"
    CACHED = "CACHED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class RunStatus(StrEnum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    AWAITING_HUMAN = "AWAITING_HUMAN"


TERMINAL_TASK = {TaskStatus.COMMITTED, TaskStatus.CACHED, TaskStatus.FAILED, TaskStatus.SKIPPED}
OK_TASK = {TaskStatus.COMMITTED, TaskStatus.CACHED}
TERMINAL_RUN = {
    RunStatus.SUCCEEDED,
    RunStatus.FAILED,
    RunStatus.CANCELLED,
    RunStatus.BUDGET_EXCEEDED,
}

_T = TaskStatus
TASK_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    _T.PENDING: {_T.READY, _T.SKIPPED, _T.FAILED},
    _T.READY: {_T.RUNNING, _T.CACHED, _T.SKIPPED, _T.FAILED},
    _T.RUNNING: {_T.VALIDATING, _T.FAILED},
    _T.VALIDATING: {_T.COMMITTED, _T.REPAIRING, _T.FAILED},
    _T.REPAIRING: {_T.RUNNING, _T.FAILED},
    _T.COMMITTED: set(),
    _T.CACHED: set(),
    _T.FAILED: set(),
    _T.SKIPPED: set(),
}

_R = RunStatus
RUN_TRANSITIONS: dict[RunStatus, set[RunStatus]] = {
    _R.CREATED: {_R.RUNNING, _R.FAILED, _R.CANCELLED},
    _R.RUNNING: {_R.SUCCEEDED, _R.FAILED, _R.CANCELLED, _R.BUDGET_EXCEEDED, _R.AWAITING_HUMAN},
    _R.AWAITING_HUMAN: {_R.RUNNING, _R.CANCELLED, _R.FAILED},
    _R.SUCCEEDED: set(),
    _R.FAILED: set(),
    _R.CANCELLED: set(),
    _R.BUDGET_EXCEEDED: set(),
}


def can_transition_task(src: TaskStatus, dst: TaskStatus) -> bool:
    return dst in TASK_TRANSITIONS[src]


def can_transition_run(src: RunStatus, dst: RunStatus) -> bool:
    return dst in RUN_TRANSITIONS[src]
