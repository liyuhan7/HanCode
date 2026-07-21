"""Immutable TUI view state and pure reducers (S4-T4).

All UI updates flow through reducers that return a new :class:`TuiViewState`, so
state transitions can be unit-tested without Textual. The event buffer is capped
(the full audit trail stays in ``trace.jsonl``; dropping the oldest UI event
never touches the file).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

from hancode.app.task_models import TaskSummary
from hancode.core.errors import StructuredError
from hancode.storage.trace import TraceEvent


MAX_EVENT_BUFFER = 500


@dataclass(frozen=True, slots=True)
class TuiViewState:
    project_root: Path

    tasks: tuple[TaskSummary, ...] = ()
    active_task_id: str | None = None
    active_task: TaskSummary | None = None

    busy: bool = False
    running_task_id: str | None = None

    trace_events: tuple[TraceEvent, ...] = ()
    selected_event_id: str | None = None

    selected_artifact: str | None = None
    artifact_preview: str | None = None

    pending_question: str | None = None
    pending_interaction_id: str | None = None

    last_error: StructuredError | None = None
    notices: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def initial(cls, project_root: Path) -> TuiViewState:
        return cls(project_root=project_root)

    def with_busy(self, busy: bool, *, running_task_id: str | None) -> TuiViewState:
        return replace(self, busy=busy, running_task_id=running_task_id)


def reduce_trace_arrived(state: TuiViewState, event: TraceEvent) -> TuiViewState:
    events = (*state.trace_events, event)
    if len(events) > MAX_EVENT_BUFFER:
        events = events[len(events) - MAX_EVENT_BUFFER :]
    return replace(state, trace_events=events)


def reduce_run_finished(state: TuiViewState) -> TuiViewState:
    return replace(state, busy=False, running_task_id=None)


def reduce_task_selected(state: TuiViewState, summary: TaskSummary) -> TuiViewState:
    pending = summary.pending_interaction
    question = None
    interaction_id = None
    if summary.requires_input and pending is not None:
        question = pending.get("question") if isinstance(pending, dict) else None
        interaction_id = (
            pending.get("interaction_id") if isinstance(pending, dict) else None
        )
    return replace(
        state,
        active_task_id=summary.task_id,
        active_task=summary,
        pending_question=question if isinstance(question, str) else None,
        pending_interaction_id=(
            interaction_id if isinstance(interaction_id, str) else None
        ),
    )


__all__ = [
    "TuiViewState",
    "MAX_EVENT_BUFFER",
    "reduce_trace_arrived",
    "reduce_run_finished",
    "reduce_task_selected",
]
