"""S4-R1-2: slash command execution (not just parsing).

These drive commands through the real ``submit_input`` path and assert the app
takes the corresponding action, closing the gap where several parsed commands
were silent no-ops.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from hancode.app.task_models import TaskSummary
from hancode.core.models import Phase, TaskStatus
from hancode.interfaces.tui.app import HanCodeTuiApp
from hancode.storage.workspace import init_project_workspace


def _project(tmp_path: Path) -> Path:
    init_project_workspace(tmp_path, "project-001", "Course", "Assignment")
    return tmp_path


def _summary(task_id: str = "task-001") -> TaskSummary:
    return TaskSummary(
        task_id=task_id,
        goal="Build it",
        status=TaskStatus.CREATED,
        current_phase=Phase.SPEC,
        retry_budget_remaining=2,
        latest_test_status="none",
        files_changed=(),
        tests_run=(),
        latest_checkpoint=None,
        rollback_required=False,
        inconsistent=False,
        artifacts={},
        resumable=False,
        requires_input=False,
        pending_interaction=None,
    )


class _FakeTaskService:
    def __init__(self, summaries: tuple[TaskSummary, ...]) -> None:
        self._summaries = summaries
        self.list_calls = 0

    def get(self, project_root: Path, task_id: str) -> TaskSummary:
        return next(s for s in self._summaries if s.task_id == task_id)

    def list_tasks(self, project_root: Path) -> tuple[TaskSummary, ...]:
        self.list_calls += 1
        return self._summaries


def _app(tmp_path: Path, task_service: _FakeTaskService) -> HanCodeTuiApp:
    return HanCodeTuiApp(
        project_root=tmp_path,
        task_service=task_service,  # type: ignore[arg-type]
    )


def _run_inputs(app: HanCodeTuiApp, *inputs: str) -> None:
    async def _run() -> None:
        async with app.run_test():
            for text in inputs:
                app.submit_input(text)
            await app.workers.wait_for_complete()

    asyncio.run(_run())


def test_help_command_shows_notice(tmp_path: Path) -> None:
    _project(tmp_path)
    notices: list[str] = []
    app = _app(tmp_path, _FakeTaskService((_summary(),)))
    app._notify = notices.append  # type: ignore[method-assign]

    _run_inputs(app, "/help")

    assert any("/task" in n or "命令" in n for n in notices)


def test_tasks_command_refreshes_task_list(tmp_path: Path) -> None:
    _project(tmp_path)
    service = _FakeTaskService((_summary("task-001"), _summary("task-002")))
    app = _app(tmp_path, service)

    _run_inputs(app, "/tasks")

    assert service.list_calls >= 1
    assert len(app.controller.state.tasks) == 2


def test_status_command_without_active_task_notifies(tmp_path: Path) -> None:
    _project(tmp_path)
    notices: list[str] = []
    app = _app(tmp_path, _FakeTaskService((_summary(),)))
    app._notify = notices.append  # type: ignore[method-assign]

    _run_inputs(app, "/status")

    assert notices  # a notice about no active task


def test_clear_command_empties_activity_without_touching_trace(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    from hancode.storage.trace import TraceEvent

    _project(tmp_path)
    app = _app(tmp_path, _FakeTaskService((_summary(),)))

    async def _run() -> None:
        async with app.run_test():
            app.controller.on_trace(
                TraceEvent(
                    event_id="evt-000001",
                    seq=1,
                    event_type="phase_started",
                    task_id="task-001",
                    phase=Phase.SPEC,
                    timestamp=datetime(2026, 7, 21, tzinfo=UTC),
                    status="running",
                )
            )
            assert app.controller.state.trace_events
            app.submit_input("/clear")
            await app.workers.wait_for_complete()

    asyncio.run(_run())

    assert app.controller.state.trace_events == ()


def test_quit_command_exits_app(tmp_path: Path) -> None:
    _project(tmp_path)
    app = _app(tmp_path, _FakeTaskService((_summary(),)))

    async def _run() -> None:
        async with app.run_test():
            app.submit_input("/quit")
            await app.workers.wait_for_complete()

    asyncio.run(_run())

    # After /quit the app is no longer running.
    assert app.is_running is False
