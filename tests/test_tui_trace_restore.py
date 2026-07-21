"""S4-R1-4: selecting a task restores its trace and clears the previous one.

Switching the active task must not mix trace events from different tasks in the
activity feed, and (re)selecting a task should restore its persisted trace via
InspectionService — this is also what makes a fresh TUI session recover history.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from hancode.app.inspection_service import TracePage
from hancode.app.task_models import TaskSummary
from hancode.core.models import Phase, TaskStatus
from hancode.interfaces.tui.controller import TuiSessionController
from hancode.storage.trace import TraceEvent


def _summary(task_id: str) -> TaskSummary:
    return TaskSummary(
        task_id=task_id,
        goal="Build it",
        status=TaskStatus.BLOCKED,
        current_phase=Phase.CODE,
        retry_budget_remaining=1,
        latest_test_status="failed",
        files_changed=(),
        tests_run=(),
        latest_checkpoint=None,
        rollback_required=False,
        inconsistent=False,
        artifacts={},
        resumable=True,
        requires_input=False,
        pending_interaction=None,
    )


def _event(task_id: str, seq: int) -> TraceEvent:
    return TraceEvent(
        event_id=f"evt-{seq:06d}",
        seq=seq,
        event_type="phase_started",
        task_id=task_id,
        phase=Phase.SPEC,
        timestamp=datetime(2026, 7, 21, tzinfo=UTC),
        status="running",
    )


class _FakeTaskService:
    def __init__(self, summaries: dict[str, TaskSummary]) -> None:
        self._summaries = summaries

    def get(self, project_root: Path, task_id: str) -> TaskSummary:
        return self._summaries[task_id]

    def list_tasks(self, project_root: Path) -> tuple[TaskSummary, ...]:
        return tuple(self._summaries.values())


class _FakeInspectionService:
    def __init__(self, traces: dict[str, list[TraceEvent]]) -> None:
        self._traces = traces
        self.read_calls: list[str] = []

    def read_trace(
        self, project_root: Path, task_id: str, *, after_seq: int = 0, limit: int = 200
    ) -> TracePage:
        self.read_calls.append(task_id)
        events = tuple(self._traces.get(task_id, ()))
        return TracePage(events=events, next_seq=None, has_more=False)


def _controller(
    summaries: dict[str, TaskSummary], traces: dict[str, list[TraceEvent]]
) -> TuiSessionController:
    return TuiSessionController(
        Path("/tmp/project"),
        task_service=_FakeTaskService(summaries),  # type: ignore[arg-type]
        inspection_service=_FakeInspectionService(traces),  # type: ignore[arg-type]
    )


def test_selecting_task_restores_its_trace() -> None:
    controller = _controller(
        {"task-001": _summary("task-001")},
        {"task-001": [_event("task-001", 1), _event("task-001", 2)]},
    )

    controller.select_task("task-001")

    assert [e.seq for e in controller.state.trace_events] == [1, 2]


def test_switching_task_clears_previous_trace() -> None:
    controller = _controller(
        {"task-001": _summary("task-001"), "task-002": _summary("task-002")},
        {
            "task-001": [_event("task-001", 1)],
            "task-002": [_event("task-002", 1), _event("task-002", 2)],
        },
    )

    controller.select_task("task-001")
    assert [e.task_id for e in controller.state.trace_events] == ["task-001"]

    controller.select_task("task-002")

    # No task-001 events remain after switching.
    assert all(e.task_id == "task-002" for e in controller.state.trace_events)
    assert [e.seq for e in controller.state.trace_events] == [1, 2]


def test_selecting_task_with_unreadable_trace_starts_empty() -> None:
    from hancode.core.errors import HanCodeError, StructuredError

    class _RaisingInspection:
        def read_trace(self, project_root: Path, task_id: str, **_: object) -> TracePage:
            raise HanCodeError(
                StructuredError(
                    error_code="inspection_trace_invalid",
                    message="bad trace",
                    phase="spec",
                    denied_rule="inspection_trace_invalid",
                    suggested_fix="repair",
                )
            )

    controller = TuiSessionController(
        Path("/tmp/project"),
        task_service=_FakeTaskService({"task-001": _summary("task-001")}),  # type: ignore[arg-type]
        inspection_service=_RaisingInspection(),  # type: ignore[arg-type]
    )

    controller.select_task("task-001")

    # A bad trace must not crash selection; the feed just starts empty.
    assert controller.state.active_task_id == "task-001"
    assert controller.state.trace_events == ()
