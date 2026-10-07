"""The Python reducer must reproduce every golden snapshot (the UI reducer is tested against the same files)."""

import json
from pathlib import Path

import pytest

from runway.core.events import Event, validate_event_data
from runway.core.snapshot import RunSnapshot, apply_event, initial_snapshot

FIXTURES = sorted((Path(__file__).parents[2] / "fixtures" / "scenarios").glob("*.jsonl"))


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
def test_reducer_reproduces_snapshot(path: Path) -> None:
    events = [Event.model_validate_json(line) for line in path.read_text().splitlines()]
    assert [e.seq for e in events] == list(range(1, len(events) + 1))
    snap = initial_snapshot(events[0].run_id)
    for ev in events:
        validate_event_data(ev.type, ev.data)  # every fixture event matches the catalog
        snap = apply_event(snap, ev)
    expected = RunSnapshot.model_validate(json.loads(path.with_suffix(".snapshot.json").read_text()))
    assert snap == expected
