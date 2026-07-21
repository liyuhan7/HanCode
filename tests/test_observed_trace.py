"""S4-T2: ObservedTraceAppender and trace_observer wiring.

The observer is a UI concern layered on top of the audit-critical TraceAppender.
Contract:
- The inner appender persists the event first; the observer is notified only
  after persistence succeeds.
- An observer failure is swallowed and must not change the harness result.
- The observer never receives an event that was not persisted.
- ``create_agent_loop`` / ``run_task`` / ``TaskService.run`` / ``resume`` forward
  the optional ``trace_observer`` without changing existing headless behaviour.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from hancode.core.models import Phase
from hancode.runtime.observation import ObservedTraceAppender, TraceObserver
from hancode.storage.trace import TraceEvent


class _RecordingObserver:
    def __init__(self) -> None:
        self.events: list[TraceEvent] = []

    def on_trace(self, event: TraceEvent) -> None:
        self.events.append(event)


class _FailingObserver:
    def __init__(self) -> None:
        self.calls = 0

    def on_trace(self, event: TraceEvent) -> None:
        self.calls += 1
        raise RuntimeError("UI observer boom")


class _RecordingAppender:
    """Fake inner TraceAppender that records calls and returns a fixed event."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def append(
        self,
        task_id: str,
        *,
        event_type: str,
        phase: Phase,
        status: str,
        action: object | None = None,
        observation: object | None = None,
        error_summary: str | None = None,
        state_transition: object | None = None,
    ) -> TraceEvent:
        self.calls.append({"task_id": task_id, "event_type": event_type})
        return _make_event(task_id, len(self.calls), event_type, phase, status)


class _RaisingAppender:
    """Fake inner TraceAppender that fails to persist."""

    def append(
        self,
        task_id: str,
        *,
        event_type: str,
        phase: Phase,
        status: str,
        action: object | None = None,
        observation: object | None = None,
        error_summary: str | None = None,
        state_transition: object | None = None,
    ) -> TraceEvent:
        raise RuntimeError("disk full")


def _make_event(
    task_id: str, seq: int, event_type: str, phase: Phase, status: str
) -> TraceEvent:
    from datetime import UTC, datetime

    return TraceEvent(
        event_id=f"evt-{seq:06d}",
        seq=seq,
        event_type=event_type,
        task_id=task_id,
        phase=phase,
        timestamp=datetime(2026, 7, 21, tzinfo=UTC),
        status=status,
    )


def test_observer_receives_event_after_trace_persistence() -> None:
    inner = _RecordingAppender()
    observer = _RecordingObserver()
    appender = ObservedTraceAppender(inner, cast(TraceObserver, observer))

    returned = appender.append(
        "task-001", event_type="phase_started", phase=Phase.SPEC, status="running"
    )

    # Inner persisted first, and the observer saw exactly the persisted event.
    assert inner.calls == [{"task_id": "task-001", "event_type": "phase_started"}]
    assert observer.events == [returned]


def test_observer_failure_does_not_change_agent_result() -> None:
    inner = _RecordingAppender()
    observer = _FailingObserver()
    appender = ObservedTraceAppender(inner, cast(TraceObserver, observer))

    returned = appender.append(
        "task-001", event_type="tool_called", phase=Phase.CODE, status="running"
    )

    # Observer raised, but append still returned the persisted event.
    assert observer.calls == 1
    assert returned.event_type == "tool_called"
    assert len(inner.calls) == 1


def test_observer_never_receives_unpersisted_event() -> None:
    observer = _RecordingObserver()
    appender = ObservedTraceAppender(_RaisingAppender(), cast(TraceObserver, observer))

    with pytest.raises(RuntimeError, match="disk full"):
        appender.append(
            "task-001", event_type="phase_started", phase=Phase.SPEC, status="running"
        )

    # Persistence failed, so the observer must not have been notified.
    assert observer.events == []


def test_create_agent_loop_uses_observed_appender_when_observer_given(
    tmp_path: Path,
) -> None:
    from hancode.runtime.engine import create_agent_loop
    from hancode.storage.workspace import init_project_workspace, init_task_workspace

    init_project_workspace(tmp_path, "project-001", "Course", "Assignment")
    init_task_workspace(tmp_path, "task-001", goal="Write the spec.")

    observer = _RecordingObserver()
    loop = create_agent_loop(
        tmp_path, "task-001", trace_observer=cast(TraceObserver, observer)
    )

    assert isinstance(loop._trace_appender, ObservedTraceAppender)  # type: ignore[attr-defined]


def test_create_agent_loop_without_observer_is_unchanged(tmp_path: Path) -> None:
    from hancode.runtime.agent_loop import FilesystemTraceAppender
    from hancode.runtime.engine import create_agent_loop
    from hancode.storage.workspace import init_project_workspace, init_task_workspace

    init_project_workspace(tmp_path, "project-001", "Course", "Assignment")
    init_task_workspace(tmp_path, "task-001", goal="Write the spec.")

    loop = create_agent_loop(tmp_path, "task-001")

    assert isinstance(loop._trace_appender, FilesystemTraceAppender)  # type: ignore[attr-defined]


def test_task_service_forwards_trace_observer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from hancode.app.task_service import TaskService

    observer = _RecordingObserver()
    captured: dict[str, object] = {}

    def fake_run_task(
        project_root: Path,
        task_id: str,
        *,
        resume: bool,
        provider: object,
        trace_observer: object = None,
    ) -> object:
        captured["trace_observer"] = trace_observer
        captured["resume"] = resume
        return object()

    monkeypatch.setattr("hancode.app.task_service.run_task", fake_run_task)

    service = TaskService()
    service.run(
        tmp_path,
        "task-001",
        provider=cast("object", object()),  # type: ignore[arg-type]
        trace_observer=cast(TraceObserver, observer),
    )

    assert captured["trace_observer"] is observer
    assert captured["resume"] is False


def test_observer_receives_events_in_seq_order_during_mock_run(tmp_path: Path) -> None:
    from hancode.app.task_service import TaskService
    from hancode.core.models import Phase
    from hancode.providers.mock import MockLLM
    from hancode.storage.workspace import init_project_workspace

    init_project_workspace(tmp_path, "project-001", "Course", "Assignment")
    service = TaskService()
    service.create(tmp_path, "Write the spec.")

    actions: list[dict[str, object]] = [
        {
            "type": "tool_call",
            "phase": Phase.SPEC.value,
            "tool_name": "write_file",
            "args": {
                "path": ".hancode/tasks/task-001/SPEC.md",
                "content": "# SPEC\n\nDocument the target.\n",
            },
            "reason": "Persist the specification artifact.",
        },
        {
            "type": "finish_phase",
            "phase": Phase.SPEC.value,
            "tool_name": None,
            "args": {},
            "reason": None,
        },
    ]

    observer = _RecordingObserver()
    result = service.run(
        tmp_path,
        "task-001",
        provider=MockLLM(actions),
        trace_observer=cast(TraceObserver, observer),
    )

    # The observer saw at least one event, all after persistence, in seq order.
    assert observer.events, "observer received no trace events"
    seqs = [event.seq for event in observer.events]
    assert seqs == sorted(seqs)
    # Every observed event is part of the persisted audit trail returned by the run.
    persisted_seqs = {event.seq for event in result.trace_events}
    assert {event.seq for event in observer.events} <= persisted_seqs
