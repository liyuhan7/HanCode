"""S4-T7: RecoveryService and TUI rollback/artifact orchestration.

RecoveryService is the only rollback path the TUI uses; it must not call the
storage RollbackManager directly. Rollback requires explicit confirmation, and
the affected-files preview comes from the checkpoint manifest, never a guess.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hancode.app.recovery_service import RecoveryService, RollbackPreview
from hancode.core.errors import HanCodeError
from hancode.storage.workspace import init_project_workspace, init_task_workspace


def _project(tmp_path: Path) -> Path:
    init_project_workspace(tmp_path, "project-001", "Course", "Assignment")
    init_task_workspace(tmp_path, "task-001", goal="Write code.")
    return tmp_path


def test_preview_last_reports_no_checkpoint(tmp_path: Path) -> None:
    _project(tmp_path)

    preview = RecoveryService().preview_last(tmp_path, "task-001")

    assert isinstance(preview, RollbackPreview)
    assert preview.checkpoint_id is None
    assert preview.available is False
    assert preview.files == ()


def test_rollback_last_without_checkpoint_is_structured_error(tmp_path: Path) -> None:
    _project(tmp_path)

    with pytest.raises(HanCodeError):
        RecoveryService().rollback_last(tmp_path, "task-001")


def test_rollback_last_uses_rollback_manager(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """RecoveryService delegates the actual restore to the storage rollback."""
    _project(tmp_path)

    from dataclasses import replace

    from hancode.app import recovery_service as module
    from hancode.core.models import OperationStatus, Phase, TaskStatus
    from hancode.core.state import load_state, save_state
    from hancode.storage.checkpoints import RollbackResult

    # Give the task a checkpoint so the rollback guard is satisfied.
    task_root = tmp_path / ".hancode" / "tasks" / "task-001"
    state = load_state(task_root)
    save_state(
        task_root,
        replace(
            state,
            current_phase=Phase.REVIEW,
            status=TaskStatus.BLOCKED,
            latest_checkpoint="ckpt-001",
            checkpoint_seq=1,
        ),
    )

    called: list[Path] = []

    def fake_rollback(task_root: Path, *, record_trace: bool = True) -> RollbackResult:
        called.append(task_root)
        return RollbackResult(
            status=OperationStatus.SUCCEEDED,
            checkpoint_id="ckpt-001",
            restored_files=("src/main.py",),
            failed_files=(),
            error=None,
        )

    monkeypatch.setattr(module, "rollback_last_checkpoint", fake_rollback)

    summary = RecoveryService().rollback_last(tmp_path, "task-001")

    assert called, "rollback_last_checkpoint was not delegated to"
    assert summary.checkpoint_id == "ckpt-001"
    assert "src/main.py" in summary.restored_files


def test_rollback_last_rejects_stale_preview(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _project(tmp_path)

    from dataclasses import replace

    from hancode.app import recovery_service as module
    from hancode.core.models import Phase, TaskStatus
    from hancode.core.state import load_state, save_state

    task_root = tmp_path / ".hancode" / "tasks" / "task-001"
    state = load_state(task_root)
    save_state(
        task_root,
        replace(
            state,
            current_phase=Phase.REVIEW,
            status=TaskStatus.BLOCKED,
            latest_checkpoint="ckpt-004",
            checkpoint_seq=4,
        ),
    )
    called = False

    def fake_rollback(*args: object, **kwargs: object) -> object:
        nonlocal called
        called = True
        raise AssertionError("stale preview must not reach rollback storage")

    monkeypatch.setattr(module, "rollback_last_checkpoint", fake_rollback)

    with pytest.raises(HanCodeError) as caught:
        RecoveryService().rollback_last(
            tmp_path,
            "task-001",
            expected_checkpoint_id="ckpt-003",
        )

    assert caught.value.structured_error.error_code == "rollback_preview_stale"
    assert called is False


# ---------------------------------------------------------------------------
# TUI rollback confirmation flow
# ---------------------------------------------------------------------------


class _FakeRecoveryService:
    def __init__(self) -> None:
        self.preview_calls: list[str] = []
        self.rollback_calls: list[str] = []

    def preview_last(self, project_root: Path, task_id: str) -> RollbackPreview:
        self.preview_calls.append(task_id)
        return RollbackPreview(
            checkpoint_id="ckpt-001",
            available=True,
            files=("src/main.py", "src/parser.py"),
        )

    def rollback_last(
        self,
        project_root: Path,
        task_id: str,
        *,
        expected_checkpoint_id: str | None = None,
    ):  # type: ignore[no-untyped-def]
        self.rollback_calls.append(task_id)
        from hancode.app.recovery_service import RecoverySummary

        return RecoverySummary(
            checkpoint_id="ckpt-001",
            restored_files=("src/main.py",),
            failed_files=(),
        )


def _app_with_active_task(tmp_path: Path, recovery: _FakeRecoveryService):  # type: ignore[no-untyped-def]
    from hancode.app.task_models import TaskSummary
    from hancode.core.models import Phase, TaskStatus
    from hancode.interfaces.tui.app import HanCodeTuiApp

    summary = TaskSummary(
        task_id="task-001",
        goal="Write code.",
        status=TaskStatus.BLOCKED,
        current_phase=Phase.REVIEW,
        retry_budget_remaining=0,
        latest_test_status="failed",
        files_changed=(),
        tests_run=(),
        latest_checkpoint="ckpt-001",
        rollback_required=True,
        inconsistent=False,
        artifacts={},
        resumable=True,
        requires_input=False,
        pending_interaction=None,
    )
    app = HanCodeTuiApp(
        project_root=tmp_path,
        recovery_service=recovery,  # type: ignore[arg-type]
    )
    app.controller.set_active_summary(summary)
    return app


def test_rollback_requires_confirmation(tmp_path: Path) -> None:
    import asyncio

    _project(tmp_path)
    recovery = _FakeRecoveryService()

    async def _run() -> None:
        app = _app_with_active_task(tmp_path, recovery)
        async with app.run_test():
            app.request_rollback()
            await app.workers.wait_for_complete()

    asyncio.run(_run())

    # Requesting rollback previews (for confirmation) but does not execute yet.
    assert recovery.preview_calls == ["task-001"]
    assert recovery.rollback_calls == []


def test_confirmed_rollback_executes(tmp_path: Path) -> None:
    import asyncio

    _project(tmp_path)
    recovery = _FakeRecoveryService()

    async def _run() -> None:
        app = _app_with_active_task(tmp_path, recovery)
        async with app.run_test():
            app.request_rollback()
            app.confirm_rollback()
            await app.workers.wait_for_complete()

    asyncio.run(_run())

    assert recovery.rollback_calls == ["task-001"]


def test_cancelled_rollback_does_not_mutate_state(tmp_path: Path) -> None:
    import asyncio

    _project(tmp_path)
    recovery = _FakeRecoveryService()

    async def _run() -> None:
        app = _app_with_active_task(tmp_path, recovery)
        async with app.run_test():
            app.request_rollback()
            app.cancel_rollback()
            await app.workers.wait_for_complete()

    asyncio.run(_run())

    assert recovery.rollback_calls == []


# ---------------------------------------------------------------------------
# Rollback via the real command path (/rollback, /rollback confirm|cancel)
# ---------------------------------------------------------------------------


def test_rollback_command_previews_without_executing(tmp_path: Path) -> None:
    import asyncio

    _project(tmp_path)
    recovery = _FakeRecoveryService()

    async def _run() -> None:
        app = _app_with_active_task(tmp_path, recovery)
        async with app.run_test():
            app.submit_input("/rollback")
            await app.workers.wait_for_complete()

    asyncio.run(_run())

    assert recovery.preview_calls == ["task-001"]
    assert recovery.rollback_calls == []


def test_rollback_confirm_command_executes(tmp_path: Path) -> None:
    import asyncio

    _project(tmp_path)
    recovery = _FakeRecoveryService()

    async def _run() -> None:
        app = _app_with_active_task(tmp_path, recovery)
        async with app.run_test():
            app.submit_input("/rollback")
            app.submit_input("/rollback confirm")
            await app.workers.wait_for_complete()

    asyncio.run(_run())

    assert recovery.rollback_calls == ["task-001"]


def test_rollback_cancel_command_cancels(tmp_path: Path) -> None:
    import asyncio

    _project(tmp_path)
    recovery = _FakeRecoveryService()

    async def _run() -> None:
        app = _app_with_active_task(tmp_path, recovery)
        async with app.run_test():
            app.submit_input("/rollback")
            app.submit_input("/rollback cancel")
            app.submit_input("/rollback confirm")
            await app.workers.wait_for_complete()

    asyncio.run(_run())

    # After cancel, a subsequent confirm must not execute a rollback.
    assert recovery.rollback_calls == []


def test_rollback_unknown_subcommand_is_rejected(tmp_path: Path) -> None:
    import asyncio

    _project(tmp_path)
    recovery = _FakeRecoveryService()
    notices: list[str] = []

    async def _run() -> None:
        app = _app_with_active_task(tmp_path, recovery)
        app._notify = notices.append  # type: ignore[method-assign]
        async with app.run_test():
            app.submit_input("/rollback frobnicate")
            await app.workers.wait_for_complete()

    asyncio.run(_run())

    assert recovery.preview_calls == []
    assert recovery.rollback_calls == []
    assert notices  # a rejection notice was shown
