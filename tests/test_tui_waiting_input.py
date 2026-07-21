"""S4-R1-5: WAITING_INPUT renders the question, updates composer, and focuses it."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from textual.widgets import Input, Static

from hancode.app.task_service import TaskService
from hancode.core.models import Phase, TaskStatus
from hancode.interfaces.tui.app import HanCodeTuiApp
from hancode.storage.workspace import init_project_workspace


def _enable_interaction(tmp_path: Path) -> Path:
    init_project_workspace(tmp_path, "project-001", "Course", "Assignment")
    project_file = tmp_path / ".hancode" / "project.json"
    project = json.loads(project_file.read_text(encoding="utf-8"))
    project["interaction_mode"] = "ask_user"
    project_file.write_text(json.dumps(project), encoding="utf-8")
    return tmp_path


class _AskFactory:
    def __call__(self, config: object, *, credential: object = None):  # type: ignore[no-untyped-def]
        from hancode.providers.mock import MockLLM

        return MockLLM(
            [
                {
                    "type": "ask_user",
                    "phase": Phase.SPEC.value,
                    "tool_name": None,
                    "args": {"question": "Which framework should be used?"},
                    "reason": "The framework is ambiguous.",
                }
            ]
        )


def _run_to_waiting(app: HanCodeTuiApp) -> None:
    async def _run() -> None:
        async with app.run_test() as pilot:
            app.submit_input("Write the spec.")
            await app.workers.wait_for_complete()
            await pilot.pause()
            # capture assertions inside the running app
            app._captured_focus = app.focused  # type: ignore[attr-defined]

    asyncio.run(_run())


def test_waiting_input_renders_question_in_detail_panel(tmp_path: Path) -> None:
    _enable_interaction(tmp_path)
    app = HanCodeTuiApp(
        project_root=tmp_path,
        task_service=TaskService(provider_factory=_AskFactory()),
    )

    captured: dict[str, str] = {}

    async def _run() -> None:
        async with app.run_test() as pilot:
            app.submit_input("Write the spec.")
            await app.workers.wait_for_complete()
            await pilot.pause()
            panel = app.screen.query_one("#tui-detail-panel", Static)
            captured["detail"] = str(panel.render())

    asyncio.run(_run())

    assert app.controller.state.active_task is not None
    assert app.controller.state.active_task.status is TaskStatus.WAITING_INPUT
    assert "Which framework should be used?" in captured["detail"]


def test_waiting_input_updates_composer_placeholder_and_focus(tmp_path: Path) -> None:
    _enable_interaction(tmp_path)
    app = HanCodeTuiApp(
        project_root=tmp_path,
        task_service=TaskService(provider_factory=_AskFactory()),
    )

    captured: dict[str, object] = {}

    async def _run() -> None:
        async with app.run_test() as pilot:
            app.submit_input("Write the spec.")
            await app.workers.wait_for_complete()
            await pilot.pause()
            composer = app.screen.query_one("#tui-composer", Input)
            captured["placeholder"] = composer.placeholder
            captured["focused"] = app.focused is composer

    asyncio.run(_run())

    # Placeholder should prompt for an answer, and the composer should be focused.
    assert "回答" in str(captured["placeholder"])
    assert captured["focused"] is True


def test_switching_from_waiting_task_clears_old_question(
    tmp_path: Path,
) -> None:
    from hancode.app.task_models import TaskSummary
    from textual.widgets import Static

    _enable_interaction(tmp_path)

    waiting = TaskSummary(
        task_id="task-001",
        goal="Write the spec.",
        status=TaskStatus.WAITING_INPUT,
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
        requires_input=True,
        pending_interaction={
            "interaction_id": "ask-000001",
            "phase": "spec",
            "question": "Which framework should be used?",
            "answer_received": False,
        },
    )

    normal = TaskSummary(
        task_id="task-002",
        goal="Write tests.",
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

    class _TaskService:
        def get(self, project_root: Path, task_id: str) -> TaskSummary:
            return waiting if task_id == "task-001" else normal

        def list_tasks(
            self,
            project_root: Path,
        ) -> tuple[TaskSummary, ...]:
            return waiting, normal

    app = HanCodeTuiApp(
        project_root=tmp_path,
        task_service=_TaskService(),  # type: ignore[arg-type]
    )

    captured: dict[str, str] = {}

    async def _run() -> None:
        async with app.run_test() as pilot:
            await pilot.pause()

            app._select("task-001")
            await pilot.pause()

            panel = app.screen.query_one("#tui-detail-panel", Static)
            assert "Which framework should be used?" in str(panel.render())

            app._select("task-002")
            await pilot.pause()

            captured["detail"] = str(panel.render())

    asyncio.run(_run())

    assert "Which framework should be used?" not in captured["detail"]
    assert "task-002" in captured["detail"]
    assert "created" in captured["detail"]