"""S5-R4 explicit human-in-the-loop modal contracts."""

from __future__ import annotations

import asyncio
from pathlib import Path

from hancode.app.recovery_service import RollbackPreview
from hancode.app.task_models import TaskSummary
from hancode.core.models import Phase, TaskStatus
from hancode.interfaces.tui.app import HanCodeTuiApp
from hancode.interfaces.tui.dialogs import ApprovalDialog, RollbackDialog
from hancode.interfaces.tui.presenters import ApprovalView, RollbackView
from hancode.storage.workspace import init_project_workspace


def _summary() -> TaskSummary:
    return TaskSummary(
        task_id="task-001",
        goal="Rollback safely",
        status=TaskStatus.COMPLETED,
        current_phase=Phase.CODE,
        retry_budget_remaining=2,
        latest_test_status="passed",
        files_changed=(),
        tests_run=(),
        latest_checkpoint="ckpt-001",
        rollback_required=False,
        inconsistent=False,
        artifacts={},
        resumable=False,
    )


def test_approval_modal_accepts_only_explicit_y_decision() -> None:
    results: list[str | None] = []
    view = ApprovalView(
        approval_id="apr-001",
        tool_name="write_file",
        category="source_write",
        risk_level="high",
        reason="write a file",
        targets=("src/main.py",),
        diff_preview="+safe",
    )

    async def _run() -> None:
        app = HanCodeTuiApp(project_root=Path("."))
        async with app.run_test() as pilot:
            app.push_screen(ApprovalDialog(view), results.append)
            await pilot.pause()
            await pilot.press("y")
            await pilot.pause()

    asyncio.run(_run())
    assert results == ["approve"]


def test_approval_modal_escape_cancels_without_decision() -> None:
    results: list[str | None] = []
    view = ApprovalView(
        approval_id="apr-001",
        tool_name="write_file",
        category="source_write",
        risk_level="high",
        reason="write a file",
        targets=(),
        diff_preview="",
    )

    async def _run() -> None:
        app = HanCodeTuiApp(project_root=Path("."))
        async with app.run_test() as pilot:
            app.push_screen(ApprovalDialog(view), results.append)
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()

    asyncio.run(_run())
    assert results == [None]


def test_rollback_modal_escape_does_not_call_recovery(tmp_path: Path) -> None:
    init_project_workspace(tmp_path, "project-001", "Course", "Assignment")
    rollback_calls: list[str] = []

    class _Recovery:
        def preview_last(self, project_root: Path, task_id: str) -> RollbackPreview:
            return RollbackPreview("ckpt-001", True, ("src/main.py",))

        def rollback_last(
            self,
            project_root: Path,
            task_id: str,
            *,
            expected_checkpoint_id: str | None = None,
        ) -> object:
            rollback_calls.append(task_id)
            return object()

    async def _run() -> None:
        app = HanCodeTuiApp(
            project_root=tmp_path,
            recovery_service=_Recovery(),  # type: ignore[arg-type]
        )
        app.controller.set_active_summary(_summary())
        async with app.run_test() as pilot:
            app.request_rollback()
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()

    asyncio.run(_run())
    assert rollback_calls == []


def test_rollback_presenter_hides_absolute_paths() -> None:
    view = RollbackView(
        checkpoint_id="ckpt-001",
        available=True,
        files=("<absolute-path-hidden>",),
    )
    results: list[str | None] = []

    async def _run() -> None:
        app = HanCodeTuiApp(project_root=Path("."))
        async with app.run_test() as pilot:
            app.push_screen(RollbackDialog(view), results.append)
            await pilot.pause()
            await pilot.press("n")
            await pilot.pause()

    asyncio.run(_run())
    assert results == ["cancel"]
