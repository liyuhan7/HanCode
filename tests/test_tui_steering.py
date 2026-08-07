"""TUI Runtime Steering routing tests (S17)."""

from __future__ import annotations

from pathlib import Path

from hancode.app.task_models import TaskSummary
from hancode.app.intervention_service import SteeringSubmission
from hancode.core.models import Phase, TaskStatus
from hancode.interfaces.tui.app import HanCodeTuiApp
from hancode.interfaces.tui.view_state import TuiViewState
from hancode.runtime.pause import PauseToken


class _RecordingInterventionService:
    def __init__(self) -> None:
        self.calls: list[tuple[Path, str, str]] = []

    def submit(
        self, project_root: Path, task_id: str, content: str
    ) -> SteeringSubmission:
        self.calls.append((project_root, task_id, content))
        return SteeringSubmission(
            intervention_id="iv-000001",
            sequence=1,
            revision=1,
        )


def _busy_app(tmp_path: Path) -> tuple[HanCodeTuiApp, _RecordingInterventionService]:
    service = _RecordingInterventionService()
    app = HanCodeTuiApp(
        project_root=tmp_path,
        intervention_service=service,  # type: ignore[arg-type]
    )
    app.controller._state = TuiViewState(
        project_root=tmp_path,
        active_task_id="task-001",
        busy=True,
        current_request_id="request-001",
        running_task_id="task-001",
    )
    app._active_pause_token = PauseToken()
    app._pause_request_id = "request-001"
    return app, service


def test_busy_plain_text_is_persisted_as_steering(tmp_path: Path) -> None:
    app, service = _busy_app(tmp_path)
    notices: list[str] = []
    app.notify = lambda message, *args, **kwargs: notices.append(str(message))  # type: ignore[method-assign]

    app.submit_input("Only touch API validation.")

    assert service.calls == [
        (tmp_path, "task-001", "Only touch API validation.")
    ]
    assert any("已接收新要求" in message for message in notices)


def test_steering_submission_does_not_start_a_second_worker(tmp_path: Path) -> None:
    app, _service = _busy_app(tmp_path)
    started: list[object] = []
    app.run_worker = lambda *args, **kwargs: started.append((args, kwargs))  # type: ignore[method-assign]

    app.submit_input("Do not modify the database layer.")

    assert started == []


def test_busy_non_agent_worker_accepts_steering_without_starting_worker(
    tmp_path: Path,
) -> None:
    service = _RecordingInterventionService()
    app = HanCodeTuiApp(
        project_root=tmp_path,
        intervention_service=service,  # type: ignore[arg-type]
    )
    app.controller._state = TuiViewState(
        project_root=tmp_path,
        active_task_id="task-001",
        busy=True,
        current_request_id="request-export",
        running_task_id="task-001",
    )
    notices: list[str] = []
    app.notify = lambda message, *args, **kwargs: notices.append(str(message))  # type: ignore[method-assign]

    app.submit_input("Do not steer during export.")

    assert service.calls == [(tmp_path, "task-001", "Do not steer during export.")]
    assert notices == ["已接收新要求（#1），将在下一个安全点生效。"]


def test_waiting_approval_plain_text_steers_and_auto_resumes(tmp_path: Path) -> None:
    service = _RecordingInterventionService()
    app = HanCodeTuiApp(
        project_root=tmp_path,
        intervention_service=service,  # type: ignore[arg-type]
    )
    app.controller._state = TuiViewState(
        project_root=tmp_path,
        active_task_id="task-001",
        pending_approval_id="apr-000001",
    )
    resumed: list[bool] = []
    app.start_run = lambda *, resume: resumed.append(resume)  # type: ignore[method-assign]

    app.submit_input("Use the safer implementation instead.")

    assert service.calls == [
        (tmp_path, "task-001", "Use the safer implementation instead.")
    ]
    assert resumed == [True]


def test_stale_running_view_accepts_steering_and_resumes(tmp_path: Path) -> None:
    service = _RecordingInterventionService()
    app = HanCodeTuiApp(
        project_root=tmp_path,
        intervention_service=service,  # type: ignore[arg-type]
    )
    app.controller._state = TuiViewState(
        project_root=tmp_path,
        active_task_id="task-001",
        active_task=TaskSummary(
            task_id="task-001",
            goal="g",
            status=TaskStatus.RUNNING,
            current_phase=Phase.CODE,
            retry_budget_remaining=1,
            latest_test_status="none",
            files_changed=(),
            tests_run=(),
            latest_checkpoint=None,
            rollback_required=False,
            inconsistent=False,
            artifacts={},
            resumable=False,
        ),
        busy=False,
    )
    resumed: list[bool] = []
    app.start_run = lambda *, resume: resumed.append(resume)  # type: ignore[method-assign]

    app.submit_input("Continue with the safer approach.")

    assert service.calls == [
        (tmp_path, "task-001", "Continue with the safer approach.")
    ]
    assert resumed == [True]
