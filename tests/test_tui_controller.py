"""S4-T5: TuiSessionController orchestration and widget derivations.

The controller is the Textual-independent orchestration unit: it owns the
immutable view state, drives application services, and enforces the single-run
(busy) constraint. Widget rendering helpers (PhaseBar cells, ActivityLog lines,
compact layout) are pure functions tested here without mounting Textual.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from hancode.core.models import Phase, TaskStatus
from hancode.interfaces.tui.controller import TuiSessionController
from hancode.storage.trace import TraceEvent


class _FakeTaskService:
    def __init__(self, summaries: dict[str, object]) -> None:
        self._summaries = summaries
        self.get_calls: list[str] = []

    def get(self, project_root: Path, task_id: str) -> object:
        self.get_calls.append(task_id)
        return self._summaries[task_id]

    def list_tasks(self, project_root: Path) -> tuple[object, ...]:
        return tuple(self._summaries.values())


def _summary(
    task_id: str = "task-001",
    *,
    status: TaskStatus = TaskStatus.RUNNING,
    phase: Phase = Phase.CODE,
    requires_input: bool = False,
    pending: dict[str, object] | None = None,
) -> object:
    from hancode.app.task_models import TaskSummary

    return TaskSummary(
        task_id=task_id,
        goal="Build it",
        status=status,
        current_phase=phase,
        retry_budget_remaining=2,
        latest_test_status="none",
        files_changed=(),
        tests_run=(),
        latest_checkpoint=None,
        rollback_required=False,
        inconsistent=False,
        artifacts={},
        resumable=False,
        requires_input=requires_input,
        pending_interaction=pending,
    )


def _event(seq: int, event_type: str = "phase_started") -> TraceEvent:
    return TraceEvent(
        event_id=f"evt-{seq:06d}",
        seq=seq,
        event_type=event_type,
        task_id="task-001",
        phase=Phase.SPEC,
        timestamp=datetime(2026, 7, 21, tzinfo=UTC),
        status="running",
    )


def _controller(summaries: dict[str, object]) -> TuiSessionController:
    return TuiSessionController(
        Path("/tmp/project"),
        task_service=_FakeTaskService(summaries),  # type: ignore[arg-type]
    )


def test_selecting_task_refreshes_summary() -> None:
    summary = _summary("task-002", phase=Phase.PLAN)
    controller = _controller({"task-002": summary})

    controller.select_task("task-002")

    assert controller.state.active_task_id == "task-002"
    assert controller.state.active_task is summary


def test_run_disables_mutating_commands() -> None:
    controller = _controller({"task-001": _summary()})
    controller.select_task("task-001")

    assert controller.can_mutate() is True
    controller.mark_running("task-001")
    assert controller.state.busy is True
    assert controller.can_mutate() is False


def test_trace_message_updates_activity_log() -> None:
    controller = _controller({"task-001": _summary()})

    controller.on_trace(_event(1))
    controller.on_trace(_event(2))

    assert [e.seq for e in controller.state.trace_events] == [1, 2]


def test_run_finished_refreshes_task_state() -> None:
    running = _summary("task-001", status=TaskStatus.RUNNING)
    completed = _summary("task-001", status=TaskStatus.COMPLETED, phase=Phase.DELIVER)
    service = _FakeTaskService({"task-001": running})
    controller = TuiSessionController(
        Path("/tmp/project"), task_service=service  # type: ignore[arg-type]
    )
    controller.select_task("task-001")
    controller.mark_running("task-001")

    # Simulate the task completing; service now returns the completed summary.
    service._summaries["task-001"] = completed
    controller.on_run_finished()

    assert controller.state.busy is False
    assert controller.state.running_task_id is None
    assert controller.state.active_task is completed


def test_phase_bar_follows_task_summary() -> None:
    from hancode.interfaces.tui.widgets.phase_bar import phase_cells

    cells = dict(phase_cells(_summary(status=TaskStatus.RUNNING, phase=Phase.CODE)))

    assert cells["spec"] == "completed"
    assert cells["plan"] == "completed"
    assert cells["code"] == "current"
    assert cells["review"] == "not_started"


def test_phase_bar_marks_waiting_and_inconsistent() -> None:
    from hancode.interfaces.tui.widgets.phase_bar import phase_cells

    waiting = dict(
        phase_cells(_summary(status=TaskStatus.WAITING_INPUT, phase=Phase.SPEC))
    )
    assert waiting["spec"] == "waiting"

    from hancode.app.task_models import TaskSummary

    inconsistent = TaskSummary(
        task_id="task-001",
        goal="g",
        status=TaskStatus.INCONSISTENT,
        current_phase=Phase.CODE,
        retry_budget_remaining=0,
        latest_test_status="failed",
        files_changed=(),
        tests_run=(),
        latest_checkpoint="ckpt-001",
        rollback_required=True,
        inconsistent=True,
        artifacts={},
        resumable=True,
        requires_input=False,
        pending_interaction=None,
    )
    cells = dict(phase_cells(inconsistent))
    assert cells["code"] == "inconsistent"


def test_activity_log_formats_known_and_unknown_events() -> None:
    from hancode.interfaces.tui.widgets.activity_log import format_event

    line = format_event(_event(1, "tool_called"))
    assert "tool_called" in line or "TOOL" in line

    unknown = format_event(_event(2, "mystery_event"))
    # Unknown events are shown, not dropped.
    assert "mystery_event" in unknown


def test_small_terminal_uses_compact_layout() -> None:
    from hancode.interfaces.tui.screens.main import is_compact_width

    assert is_compact_width(60) is True
    assert is_compact_width(200) is False


def test_worker_unexpected_exception_clears_busy(tmp_path: Path) -> None:
    """A non-HanCodeError in the worker must not leave the TUI stuck busy."""
    import asyncio

    from hancode.app.task_service import TaskService
    from hancode.interfaces.tui.app import HanCodeTuiApp
    from hancode.storage.workspace import init_project_workspace

    init_project_workspace(tmp_path, "project-001", "Course", "Assignment")

    class _BoomFactory:
        def __call__(self, config: object, *, credential: object = None) -> object:
            raise RuntimeError("provider factory exploded")

    service = TaskService(provider_factory=_BoomFactory())
    notices: list[str] = []

    async def _run() -> None:
        app = HanCodeTuiApp(project_root=tmp_path, task_service=service)
        app._notify = notices.append  # type: ignore[method-assign]
        async with app.run_test() as pilot:
            app.submit_input("Write the spec.")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert app.controller.state.busy is False
            assert app.controller.can_mutate() is True

    asyncio.run(_run())

    # An internal-error notice was surfaced, without leaking the raw exception.
    assert notices
    assert all("provider factory exploded" not in n for n in notices)


def test_app_run_streams_trace_events_before_completion(tmp_path: Path) -> None:
    """End-to-end: a MockLLM run streams trace events into the activity log."""
    import asyncio

    from hancode.app.task_service import TaskService
    from hancode.interfaces.tui.app import HanCodeTuiApp
    from hancode.storage.workspace import init_project_workspace

    init_project_workspace(tmp_path, "project-001", "Course", "Assignment")

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

    class _MockFactory:
        def __call__(self, config: object, *, credential: object = None) -> object:
            from hancode.providers.mock import MockLLM

            return MockLLM(list(actions))

    service = TaskService(provider_factory=_MockFactory())

    async def _run() -> None:
        app = HanCodeTuiApp(project_root=tmp_path, task_service=service)
        async with app.run_test() as pilot:
            app.submit_input("Write the spec.")
            # Wait for the background worker to finish and messages to drain.
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert app.controller.state.trace_events, "no trace events streamed"
            assert app.controller.state.busy is False

    asyncio.run(_run())
