"""S5: TUI approval decision + auto-resume orchestration.

Drives the app layer with fake services to verify presentation orchestration
(approve/reject → auto-resume), using the pending approval id and never
deciding an approval from plain text. Does not re-test the S3 state machine.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from hancode.app.task_models import TaskSummary
from hancode.core.errors import HanCodeError, StructuredError
from hancode.core.models import Phase, TaskStatus
from hancode.interfaces.tui.app import HanCodeTuiApp
from hancode.storage.workspace import init_project_workspace


def _project(tmp_path: Path) -> Path:
    init_project_workspace(tmp_path, "project-001", "Course", "Assignment")
    return tmp_path


def _waiting_approval_summary(approval_id: str = "apr-000001") -> TaskSummary:
    return TaskSummary(
        task_id="task-001",
        goal="Write the spec.",
        status=TaskStatus.WAITING_APPROVAL,
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
        requires_approval=True,
        pending_approval={"approval_id": approval_id, "status": "pending"},
    )


class _FakeApprovalService:
    def __init__(self, *, error: HanCodeError | None = None) -> None:
        self.approve_calls: list[tuple[str, str | None]] = []
        self.reject_calls: list[tuple[str, str | None, str | None]] = []
        self._error = error

    def approve(
        self, task_id: str, *, approval_id: str | None = None
    ) -> TaskSummary:
        self.approve_calls.append((task_id, approval_id))
        if self._error is not None:
            raise self._error
        return _waiting_approval_summary()

    def reject(
        self,
        task_id: str,
        *,
        approval_id: str | None = None,
        reason: str | None = None,
    ) -> TaskSummary:
        self.reject_calls.append((task_id, approval_id, reason))
        if self._error is not None:
            raise self._error
        return _waiting_approval_summary()

    def get_pending(self, task_id: str) -> dict[str, object] | None:
        return {
            "approval_id": "apr-000001",
            "tool_name": "write_file",
            "targets": [".hancode/tasks/task-001/SPEC.md"],
            "status": "pending",
            "preview": {"unified_diff": "+# Spec", "truncated": False},
        }


class _FakeTaskService:
    def __init__(self) -> None:
        self.run_calls: list[tuple[str, bool]] = []

    def get(self, project_root: Path, task_id: str) -> TaskSummary:
        return _waiting_approval_summary()

    def list_tasks(self, project_root: Path) -> tuple[TaskSummary, ...]:
        return ()

    def run(
        self,
        project_root: Path,
        task_id: str,
        *,
        resume: bool = False,
        provider: object = None,
        trace_observer: object = None,
    ) -> object:
        self.run_calls.append((task_id, resume))
        return object()


def _error(code: str) -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code=code,
            message=f"boom: {code}",
            phase="spec",
            denied_rule=code,
            suggested_fix="fix it",
        )
    )


def _app_with_pending(
    tmp_path: Path,
    approval: _FakeApprovalService,
    task_service: _FakeTaskService | None = None,
) -> HanCodeTuiApp:
    app = HanCodeTuiApp(
        project_root=tmp_path,
        task_service=task_service,  # type: ignore[arg-type]
        approval_service=approval,  # type: ignore[arg-type]
    )
    app.controller.set_active_summary(_waiting_approval_summary())
    return app


def test_approve_uses_pending_approval_id(tmp_path: Path) -> None:
    _project(tmp_path)
    approval = _FakeApprovalService()
    task_service = _FakeTaskService()

    async def _run() -> None:
        app = _app_with_pending(tmp_path, approval, task_service)
        async with app.run_test():
            app.submit_approval()
            await app.workers.wait_for_complete()

    asyncio.run(_run())

    assert approval.approve_calls == [("task-001", "apr-000001")]


def test_approve_automatically_resumes_task(tmp_path: Path) -> None:
    _project(tmp_path)
    approval = _FakeApprovalService()
    task_service = _FakeTaskService()

    async def _run() -> None:
        app = _app_with_pending(tmp_path, approval, task_service)
        async with app.run_test():
            app.submit_approval()
            await app.workers.wait_for_complete()

    asyncio.run(_run())

    assert task_service.run_calls == [("task-001", True)]


def test_reject_passes_reason_and_resumes(tmp_path: Path) -> None:
    _project(tmp_path)
    approval = _FakeApprovalService()
    task_service = _FakeTaskService()

    async def _run() -> None:
        app = _app_with_pending(tmp_path, approval, task_service)
        async with app.run_test():
            app.submit_rejection("wrong path")
            await app.workers.wait_for_complete()

    asyncio.run(_run())

    assert approval.reject_calls == [("task-001", "apr-000001", "wrong path")]
    assert task_service.run_calls == [("task-001", True)]


def test_approval_failure_does_not_resume(tmp_path: Path) -> None:
    _project(tmp_path)
    approval = _FakeApprovalService(error=_error("approval_decision_conflict"))
    task_service = _FakeTaskService()

    async def _run() -> None:
        app = _app_with_pending(tmp_path, approval, task_service)
        async with app.run_test():
            app.submit_approval()
            await app.workers.wait_for_complete()

    asyncio.run(_run())

    assert task_service.run_calls == []


def test_approve_without_pending_is_noop(tmp_path: Path) -> None:
    _project(tmp_path)
    approval = _FakeApprovalService()
    task_service = _FakeTaskService()

    async def _run() -> None:
        app = HanCodeTuiApp(
            project_root=tmp_path,
            task_service=task_service,  # type: ignore[arg-type]
            approval_service=approval,  # type: ignore[arg-type]
        )
        async with app.run_test():
            app.submit_approval()
            await app.workers.wait_for_complete()

    asyncio.run(_run())

    assert approval.approve_calls == []
    assert task_service.run_calls == []


def test_plain_text_during_approval_does_not_decide(tmp_path: Path) -> None:
    _project(tmp_path)
    approval = _FakeApprovalService()
    task_service = _FakeTaskService()
    notices: list[str] = []

    async def _run() -> None:
        app = _app_with_pending(tmp_path, approval, task_service)
        app._notify = notices.append  # type: ignore[method-assign]
        async with app.run_test():
            app.submit_input("yes do it")
            await app.workers.wait_for_complete()

    asyncio.run(_run())

    # Plain text must not approve, reject, or resume.
    assert approval.approve_calls == []
    assert approval.reject_calls == []
    assert task_service.run_calls == []
    assert any("/approve" in n or "批准" in n for n in notices)


def test_end_to_end_approve_resume_writes_spec(tmp_path: Path) -> None:
    """Real approval round trip inside one TUI session using MockLLM."""
    import json

    from hancode.app.task_service import TaskService

    init_project_workspace(tmp_path, "project-001", "Course", "Assignment")
    project_file = tmp_path / ".hancode" / "project.json"
    project = json.loads(project_file.read_text(encoding="utf-8"))
    project["approval_mode"] = "first_source_write"
    project_file.write_text(json.dumps(project), encoding="utf-8")

    write_action = {
        "type": "tool_call",
        "phase": Phase.SPEC.value,
        "tool_name": "write_file",
        "args": {
            "path": ".hancode/tasks/task-001/SPEC.md",
            "content": "# SPEC\n\nUse FastAPI.\n",
        },
        "reason": "Persist the specification artifact.",
    }
    finish = {
        "type": "finish_phase",
        "phase": Phase.SPEC.value,
        "tool_name": None,
        "args": {},
        "reason": None,
    }

    class _SequencedFactory:
        def __init__(self) -> None:
            # First run pauses at approval; resume executes the write + finish.
            self._sequences = [[write_action], [write_action, finish]]

        def __call__(self, config: object, *, credential: object = None) -> object:
            from hancode.providers.mock import MockLLM

            return MockLLM(list(self._sequences.pop(0)))

    service = TaskService(provider_factory=_SequencedFactory())

    async def _run() -> None:
        app = HanCodeTuiApp(project_root=tmp_path, task_service=service)
        async with app.run_test():
            app.submit_input("Write the spec.")
            await app.workers.wait_for_complete()
            # Paused for approval.
            assert app.controller.state.pending_approval_id is not None
            app.submit_approval()
            await app.workers.wait_for_complete()

    asyncio.run(_run())

    spec = tmp_path / ".hancode" / "tasks" / "task-001" / "SPEC.md"
    assert spec.is_file()
    assert "Use FastAPI." in spec.read_text(encoding="utf-8")
