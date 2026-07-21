"""S4-R1-3: TaskList is loaded on startup and selection is wired."""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual.widgets import ListView

from hancode.app.task_models import TaskSummary
from hancode.core.models import Phase, TaskStatus
from hancode.interfaces.tui.app import HanCodeTuiApp
from hancode.storage.workspace import init_project_workspace


def _project(tmp_path: Path) -> Path:
    init_project_workspace(tmp_path, "project-001", "Course", "Assignment")
    return tmp_path


def _summary(task_id: str, status: TaskStatus = TaskStatus.CREATED) -> TaskSummary:
    return TaskSummary(
        task_id=task_id,
        goal="Build it",
        status=status,
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
        self.summaries = summaries
        self.get_calls: list[str] = []

    def get(self, project_root: Path, task_id: str) -> TaskSummary:
        self.get_calls.append(task_id)
        return next(
            summary
            for summary in self.summaries
            if summary.task_id == task_id
        )

    def list_tasks(self, project_root: Path) -> tuple[TaskSummary, ...]:
        return self.summaries


def test_task_list_is_populated_on_startup(tmp_path: Path) -> None:
    _project(tmp_path)
    service = _FakeTaskService((_summary("task-001"), _summary("task-002")))
    app = HanCodeTuiApp(project_root=tmp_path, task_service=service)  # type: ignore[arg-type]

    async def _run() -> None:
        async with app.run_test() as pilot:
            await pilot.pause()
            view = app.screen.query_one("#tui-task-list", ListView)
            assert len(view.children) == 2
            assert app.controller.state.tasks

    asyncio.run(_run())


def test_task_list_selection_activates_task(tmp_path: Path) -> None:
    _project(tmp_path)
    service = _FakeTaskService((_summary("task-001"), _summary("task-002")))
    app = HanCodeTuiApp(project_root=tmp_path, task_service=service)  # type: ignore[arg-type]

    async def _run() -> None:
        async with app.run_test() as pilot:
            await pilot.pause()
            view = app.screen.query_one("#tui-task-list", ListView)
            view.index = 1
            # Emit the selection message the way a click/enter would.
            view.action_select_cursor()
            await pilot.pause()
            assert app.controller.state.active_task_id == "task-002"

    asyncio.run(_run())


def test_task_list_empty_project_starts_cleanly(tmp_path: Path) -> None:
    _project(tmp_path)
    service = _FakeTaskService(())
    app = HanCodeTuiApp(project_root=tmp_path, task_service=service)  # type: ignore[arg-type]

    async def _run() -> None:
        async with app.run_test() as pilot:
            await pilot.pause()
            view = app.screen.query_one("#tui-task-list", ListView)
            assert len(view.children) == 0
            assert app.controller.state.active_task_id is None

    asyncio.run(_run())


def test_run_finished_refreshes_task_list_widget(tmp_path: Path) -> None:
    from hancode.interfaces.tui.messages import RunFinished
    from textual.widgets import Label, ListView

    _project(tmp_path)

    service = _FakeTaskService(
        (_summary("task-001", TaskStatus.CREATED),)
    )
    app = HanCodeTuiApp(
        project_root=tmp_path,
        task_service=service,  # type: ignore[arg-type]
    )

    async def _run() -> None:
        async with app.run_test() as pilot:
            await pilot.pause()

            app.controller.set_active_summary(service.summaries[0])
            app.controller.mark_running("task-001")

            # Simulate persisted state changing after AgentLoop finishes.
            service.summaries = (
                _summary("task-001", TaskStatus.COMPLETED),
            )

            # The handler updates controller data AND rebuilds the ListView
            # synchronously (no call_after_refresh).
            app.on_run_finished(
                RunFinished(object())  # type: ignore[arg-type]
            )

            await pilot.pause()

            view = app.screen.query_one("#tui-task-list", ListView)
            assert len(view.children) == 1

            label = view.children[0].query_one(Label)
            rendered = str(label.render())

            assert "task-001" in rendered
            assert "completed" in rendered

    asyncio.run(_run())
