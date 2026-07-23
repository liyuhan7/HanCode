"""S4-T4: TuiViewState immutable transitions (Textual-independent)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from hancode.core.models import Phase
from hancode.interfaces.tui.view_state import (
    TuiViewState,
    reduce_run_finished,
    reduce_trace_arrived,
)
from hancode.interfaces.tui.presenters import DetailKind
from hancode.storage.trace import TraceEvent


def _event(seq: int) -> TraceEvent:
    return TraceEvent(
        event_id=f"evt-{seq:06d}",
        seq=seq,
        event_type="phase_started",
        task_id="task-001",
        phase=Phase.SPEC,
        timestamp=datetime(2026, 7, 21, tzinfo=UTC),
        status="running",
    )


def test_initial_state_is_empty() -> None:
    state = TuiViewState.initial(Path("/tmp/project"))

    assert state.trace_events == ()
    assert state.busy is False
    assert state.active_task_id is None
    assert state.detail_kind is DetailKind.TASK
    assert state.detail is None


def test_view_state_reducer_preserves_event_order() -> None:
    state = TuiViewState.initial(Path("/tmp/project"))

    for seq in (1, 2, 3):
        state = reduce_trace_arrived(state, _event(seq))

    assert [event.seq for event in state.trace_events] == [1, 2, 3]


def test_reduce_trace_arrived_returns_new_instance() -> None:
    state = TuiViewState.initial(Path("/tmp/project"))
    updated = reduce_trace_arrived(state, _event(1))

    assert updated is not state
    assert state.trace_events == ()
    assert updated.trace_events == (_event(1),)


def test_view_state_caps_event_buffer() -> None:
    state = TuiViewState.initial(Path("/tmp/project"))

    for seq in range(1, 605):
        state = reduce_trace_arrived(state, _event(seq))

    # Buffer capped at 500; oldest dropped, newest retained.
    assert len(state.trace_events) == 500
    assert state.trace_events[0].seq == 105
    assert state.trace_events[-1].seq == 604


def test_reduce_run_finished_clears_busy() -> None:
    state = TuiViewState.initial(Path("/tmp/project"))
    state = state.with_busy(True, running_task_id="task-001")
    assert state.busy is True

    finished = reduce_run_finished(state)

    assert finished.busy is False
    assert finished.running_task_id is None
