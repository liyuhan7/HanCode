"""S4-T6: HITL auto-answer and resume orchestration in the TUI app.

These tests drive the app layer with fake services to verify the presentation
orchestration (answer → auto-resume), without echoing answer text and using the
pending interaction id. They do not re-test the S3 state machine.
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


def _waiting_summary(interaction_id: str = "ask-000001") -> TaskSummary:
    return TaskSummary(
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
            "interaction_id": interaction_id,
            "phase": "spec",
            "question": "Which framework should be used?",
            "answer_received": False,
        },
    )


class _FakeInteractionService:
    def __init__(self, *, error: HanCodeError | None = None) -> None:
        self.calls: list[tuple[str, str, str | None]] = []
        self._error = error

    def answer(
        self,
        project_root: Path,
        task_id: str,
        answer: str,
        *,
        interaction_id: str | None = None,
    ) -> TaskSummary:
        self.calls.append((task_id, answer, interaction_id))
        if self._error is not None:
            raise self._error
        return _waiting_summary()


class _FakeTaskService:
    def __init__(self) -> None:
        self.run_calls: list[tuple[str, bool]] = []

    def get(self, project_root: Path, task_id: str) -> TaskSummary:
        return _waiting_summary()

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
    interaction: _FakeInteractionService,
    task_service: _FakeTaskService | None = None,
) -> HanCodeTuiApp:
    app = HanCodeTuiApp(
        project_root=tmp_path,
        task_service=task_service,  # type: ignore[arg-type]
        interaction_service=interaction,  # type: ignore[arg-type]
    )
    app.controller.set_active_summary(_waiting_summary())
    return app


def test_answer_uses_pending_interaction_id(tmp_path: Path) -> None:
    _project(tmp_path)
    interaction = _FakeInteractionService()
    task_service = _FakeTaskService()

    async def _run() -> None:
        app = _app_with_pending(tmp_path, interaction, task_service)
        async with app.run_test():
            app.submit_answer("Use FastAPI.")
            await app.workers.wait_for_complete()

    asyncio.run(_run())

    assert interaction.calls == [("task-001", "Use FastAPI.", "ask-000001")]


def test_answer_success_automatically_resumes_task(tmp_path: Path) -> None:
    _project(tmp_path)
    interaction = _FakeInteractionService()
    task_service = _FakeTaskService()

    async def _run() -> None:
        app = _app_with_pending(tmp_path, interaction, task_service)
        async with app.run_test():
            app.submit_answer("Use FastAPI.")
            await app.workers.wait_for_complete()

    asyncio.run(_run())

    assert task_service.run_calls == [("task-001", True)]


def test_answer_failure_does_not_resume(tmp_path: Path) -> None:
    _project(tmp_path)
    interaction = _FakeInteractionService(error=_error("interaction_id_mismatch"))
    task_service = _FakeTaskService()

    async def _run() -> None:
        app = _app_with_pending(tmp_path, interaction, task_service)
        async with app.run_test():
            app.submit_answer("Use FastAPI.")
            await app.workers.wait_for_complete()

    asyncio.run(_run())

    assert task_service.run_calls == []


def test_secret_only_answer_is_rejected_without_echo(tmp_path: Path) -> None:
    _project(tmp_path)
    interaction = _FakeInteractionService(
        error=_error("interaction_answer_contains_only_sensitive_content")
    )
    task_service = _FakeTaskService()
    notices: list[str] = []

    async def _run() -> None:
        app = _app_with_pending(tmp_path, interaction, task_service)
        app._notify = notices.append  # type: ignore[method-assign]
        async with app.run_test():
            app.submit_answer("sk-secretvalue")
            await app.workers.wait_for_complete()

    asyncio.run(_run())

    assert task_service.run_calls == []
    # The rejection notice must not contain the answer text.
    assert all("sk-secretvalue" not in notice for notice in notices)


def test_answer_confirmation_reports_length_not_content(tmp_path: Path) -> None:
    _project(tmp_path)
    interaction = _FakeInteractionService()
    task_service = _FakeTaskService()
    notices: list[str] = []

    async def _run() -> None:
        app = _app_with_pending(tmp_path, interaction, task_service)
        app._notify = notices.append  # type: ignore[method-assign]
        async with app.run_test():
            app.submit_answer("Use FastAPI.")
            await app.workers.wait_for_complete()

    asyncio.run(_run())

    assert any("chars" in notice for notice in notices)
    assert all("Use FastAPI." not in notice for notice in notices)


def test_answer_without_pending_interaction_is_noop(tmp_path: Path) -> None:
    _project(tmp_path)
    interaction = _FakeInteractionService()
    task_service = _FakeTaskService()

    async def _run() -> None:
        app = HanCodeTuiApp(
            project_root=tmp_path,
            task_service=task_service,  # type: ignore[arg-type]
            interaction_service=interaction,  # type: ignore[arg-type]
        )
        async with app.run_test():
            app.submit_answer("orphan answer")
            await app.workers.wait_for_complete()

    asyncio.run(_run())

    assert interaction.calls == []
    assert task_service.run_calls == []


def test_end_to_end_ask_answer_resume_writes_spec(tmp_path: Path) -> None:
    """Real ASK_USER round trip inside one TUI session using MockLLM."""
    import json

    from hancode.app.task_service import TaskService

    init_project_workspace(tmp_path, "project-001", "Course", "Assignment")
    project_file = tmp_path / ".hancode" / "project.json"
    project = json.loads(project_file.read_text(encoding="utf-8"))
    project["interaction_mode"] = "ask_user"
    project_file.write_text(json.dumps(project), encoding="utf-8")

    ask_actions: list[dict[str, object]] = [
        {
            "type": "ask_user",
            "phase": Phase.SPEC.value,
            "tool_name": None,
            "args": {"question": "Which framework should be used?"},
            "reason": "The framework is ambiguous.",
        }
    ]
    resume_actions: list[dict[str, object]] = [
        {
            "type": "tool_call",
            "phase": Phase.SPEC.value,
            "tool_name": "write_file",
            "args": {
                "path": ".hancode/tasks/task-001/SPEC.md",
                "content": "# SPEC\n\nUse FastAPI.\n",
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

    class _SequencedFactory:
        def __init__(self) -> None:
            self._sequences = [ask_actions, resume_actions]

        def __call__(self, config: object, *, credential: object = None) -> object:
            from hancode.providers.mock import MockLLM

            return MockLLM(list(self._sequences.pop(0)))

    service = TaskService(provider_factory=_SequencedFactory())

    async def _run() -> None:
        app = HanCodeTuiApp(project_root=tmp_path, task_service=service)
        async with app.run_test():
            app.submit_input("Write the spec.")
            await app.workers.wait_for_complete()
            # Paused for input.
            assert app.controller.state.pending_interaction_id is not None
            app.submit_answer("Use FastAPI.")
            await app.workers.wait_for_complete()

    asyncio.run(_run())

    spec = tmp_path / ".hancode" / "tasks" / "task-001" / "SPEC.md"
    assert spec.is_file()
    assert "Use FastAPI." in spec.read_text(encoding="utf-8")
