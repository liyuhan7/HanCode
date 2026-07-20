"""Stage 1: TaskService lifecycle tests."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from hancode.app.task_models import TaskRunSummary, TaskSummary
from hancode.app.task_service import TaskService
from hancode.core.errors import HanCodeError
from hancode.core.models import Phase, TaskStatus
from hancode.providers.base import LLMClient
from hancode.runtime.agent_loop import AgentRunResult
from hancode.storage.workspace import init_project_workspace


def _make_project(tmp_path: Path) -> Path:
    init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Harness",
    )
    return tmp_path


# =========================================================================
# TaskSummary serialization
# =========================================================================


def test_task_summary_from_state_serializes_enums(tmp_path: Path) -> None:
    from hancode.core.state import TaskState

    _make_project(tmp_path)
    service = TaskService()
    service.create(tmp_path, "Implement login")

    state = TaskState(
        schema_version=1,
        task_id="task-001",
        goal="Implement login",
        status=TaskStatus.CREATED,
        current_phase=Phase.SPEC,
        files_changed=(),
        latest_checkpoint=None,
        checkpoint_seq=0,
        tests_run=(),
        latest_test_status="none",
        test_status_consumed=False,
        retry_budget_remaining=2,
        inconsistent=False,
        source_edits_this_phase=0,
        rollback_required=False,
        rollback_done=False,
        phase_completed={
            "spec": False,
            "plan": False,
            "code": False,
            "test": False,
            "review": False,
            "deliver": False,
        },
        artifacts={
            "SPEC.md": False,
            "PLAN.md": False,
            "TEST_REPORT.md": False,
            "REVIEW.md": False,
            "KNOWLEDGE.md": False,
            "DELIVERABLES.md": False,
        },
    )

    summary = TaskSummary.from_state(state)
    d = summary.to_dict()

    assert d["task_id"] == "task-001"
    assert d["goal"] == "Implement login"
    assert d["status"] == "created"
    assert d["current_phase"] == "spec"
    assert d["resumable"] is False


def test_task_summary_resumable_for_blocked(tmp_path: Path) -> None:
    from hancode.core.state import TaskState

    state = TaskState(
        schema_version=1,
        task_id="task-001",
        goal="test",
        status=TaskStatus.BLOCKED,
        current_phase=Phase.SPEC,
        files_changed=(),
        latest_checkpoint=None,
        checkpoint_seq=0,
        tests_run=(),
        latest_test_status="none",
        test_status_consumed=False,
        retry_budget_remaining=2,
        inconsistent=False,
        source_edits_this_phase=0,
        rollback_required=False,
        rollback_done=False,
        phase_completed={
            "spec": False,
            "plan": False,
            "code": False,
            "test": False,
            "review": False,
            "deliver": False,
        },
        artifacts={
            "SPEC.md": False,
            "PLAN.md": False,
            "TEST_REPORT.md": False,
            "REVIEW.md": False,
            "KNOWLEDGE.md": False,
            "DELIVERABLES.md": False,
        },
    )

    summary = TaskSummary.from_state(state)
    assert summary.resumable is True


# =========================================================================
# TaskService.create
# =========================================================================


def test_task_service_create_generates_task_001(tmp_path: Path) -> None:
    _make_project(tmp_path)
    service = TaskService()

    summary = service.create(tmp_path, "Implement login")

    assert summary.task_id == "task-001"
    assert summary.goal == "Implement login"
    assert summary.status is TaskStatus.CREATED
    assert summary.current_phase is Phase.SPEC


def test_task_service_create_generates_next_sequential_id(tmp_path: Path) -> None:
    _make_project(tmp_path)
    service = TaskService()

    service.create(tmp_path, "First task")
    summary = service.create(tmp_path, "Second task")

    assert summary.task_id == "task-002"


def test_task_service_create_accepts_custom_task_id(tmp_path: Path) -> None:
    _make_project(tmp_path)
    service = TaskService()

    summary = service.create(tmp_path, "Custom task", task_id="login-task")

    assert summary.task_id == "login-task"


def test_task_service_create_rejects_duplicate_task_id(tmp_path: Path) -> None:
    _make_project(tmp_path)
    service = TaskService()

    service.create(tmp_path, "First task", task_id="task-001")

    with pytest.raises(HanCodeError) as exc_info:
        service.create(tmp_path, "Second task", task_id="task-001")

    assert exc_info.value.structured_error.error_code == "task_already_exists"


def test_task_service_create_returns_task_summary(tmp_path: Path) -> None:
    _make_project(tmp_path)
    service = TaskService()

    summary = service.create(tmp_path, "Implement login")

    assert isinstance(summary, TaskSummary)
    assert summary.goal == "Implement login"


def test_task_service_create_rejects_blank_goal(tmp_path: Path) -> None:
    _make_project(tmp_path)
    service = TaskService()

    with pytest.raises(HanCodeError) as exc_info:
        service.create(tmp_path, "   ")

    assert exc_info.value.structured_error.error_code == "task_goal_required"


def test_task_service_create_skips_custom_id_in_sequential_count(tmp_path: Path) -> None:
    _make_project(tmp_path)
    service = TaskService()

    service.create(tmp_path, "Custom", task_id="login-task")
    summary = service.create(tmp_path, "Sequential")

    assert summary.task_id == "task-001"


def test_task_service_create_continues_after_high_number(tmp_path: Path) -> None:
    _make_project(tmp_path)
    service = TaskService()

    service.create(tmp_path, "Task 10", task_id="task-010")
    summary = service.create(tmp_path, "Next")

    assert summary.task_id == "task-011"


# =========================================================================
# TaskService.get
# =========================================================================


def test_task_service_get_returns_reconciled_state(tmp_path: Path) -> None:
    _make_project(tmp_path)
    service = TaskService()
    service.create(tmp_path, "Implement login")

    summary = service.get(tmp_path, "task-001")

    assert summary.task_id == "task-001"
    assert summary.goal == "Implement login"


def test_task_service_get_rejects_missing_task(tmp_path: Path) -> None:
    _make_project(tmp_path)
    service = TaskService()

    with pytest.raises(HanCodeError) as exc_info:
        service.get(tmp_path, "nonexistent-task")

    assert exc_info.value.structured_error.error_code == "task_not_found"


# =========================================================================
# TaskService.list_tasks
# =========================================================================


def test_task_service_list_returns_sorted_summaries(tmp_path: Path) -> None:
    _make_project(tmp_path)
    service = TaskService()
    service.create(tmp_path, "Second", task_id="task-002")
    service.create(tmp_path, "First", task_id="task-001")

    summaries = service.list_tasks(tmp_path)

    assert len(summaries) == 2
    assert summaries[0].task_id == "task-001"
    assert summaries[1].task_id == "task-002"


def test_task_service_list_returns_empty_when_no_tasks(tmp_path: Path) -> None:
    _make_project(tmp_path)
    service = TaskService()

    assert service.list_tasks(tmp_path) == ()


# =========================================================================
# TaskService.run and resume delegation
# =========================================================================


def test_task_service_run_keeps_provider_injection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _make_project(tmp_path)
    service = TaskService()
    service.create(tmp_path, "test goal")

    expected = object()
    provider = cast(LLMClient, object())
    calls: list[tuple[Path, str, bool, object]] = []

    def fake_run_task(
        project_root: Path,
        task_id: str,
        *,
        resume: bool,
        provider: object,
    ) -> object:
        calls.append((project_root, task_id, resume, provider))
        return expected

    monkeypatch.setattr("hancode.app.task_service.run_task", fake_run_task)

    result = service.run(tmp_path, "task-001", resume=False, provider=provider)

    assert result is expected
    assert calls == [(tmp_path, "task-001", False, provider)]


def test_task_service_resume_delegates_with_resume_true(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _make_project(tmp_path)
    service = TaskService()
    service.create(tmp_path, "test goal")

    expected = object()
    calls: list[tuple[Path, str, bool]] = []

    def fake_run_task(
        project_root: Path,
        task_id: str,
        *,
        resume: bool,
        provider: object,
    ) -> object:
        calls.append((project_root, task_id, resume))
        return expected

    monkeypatch.setattr("hancode.app.task_service.run_task", fake_run_task)

    result = service.resume(tmp_path, "task-001")

    assert result is expected
    assert calls == [(tmp_path, "task-001", True)]


def test_task_service_initialize_still_works(tmp_path: Path) -> None:
    _make_project(tmp_path)
    service = TaskService()

    task_root = service.initialize(tmp_path, "task-001")

    assert task_root.is_dir()
    assert (task_root / "state.json").is_file()


# =========================================================================
# TaskRunSummary
# =========================================================================


def test_task_run_summary_from_result(tmp_path: Path) -> None:
    from hancode.core.state import TaskState

    state = TaskState(
        schema_version=1,
        task_id="task-001",
        goal="test",
        status=TaskStatus.BLOCKED,
        current_phase=Phase.SPEC,
        files_changed=(),
        latest_checkpoint=None,
        checkpoint_seq=0,
        tests_run=(),
        latest_test_status="none",
        test_status_consumed=False,
        retry_budget_remaining=2,
        inconsistent=False,
        source_edits_this_phase=0,
        rollback_required=False,
        rollback_done=False,
        phase_completed={
            "spec": False,
            "plan": False,
            "code": False,
            "test": False,
            "review": False,
            "deliver": False,
        },
        artifacts={
            "SPEC.md": False,
            "PLAN.md": False,
            "TEST_REPORT.md": False,
            "REVIEW.md": False,
            "KNOWLEDGE.md": False,
            "DELIVERABLES.md": False,
        },
    )
    result = AgentRunResult(
        status=TaskStatus.BLOCKED,
        steps=1,
        tool_calls=(),
        risks=(),
        final_observation=None,
        error=None,
        final_state=state,
        retry_budget_remaining=2,
        trace_events=(),
    )

    summary = TaskRunSummary.from_result(result)

    assert summary.task.task_id == "task-001"
    assert summary.steps == 1
    assert summary.trace_event_count == 0
    assert summary.error is None


# =========================================================================
# Stage 2: Credential resolution and provider assembly
# =========================================================================


def test_task_service_prepare_provider_resolves_credential(
    tmp_path: Path,
) -> None:
    _make_project(tmp_path)
    project_file = tmp_path / ".hancode" / "project.json"
    import json

    data = json.loads(project_file.read_text(encoding="utf-8"))
    data.update(
        {
            "llm_provider": "openai_compatible",
            "model_name": "test-model",
            "credential_source": "env",
            "provider_base_url": "https://example.invalid/v1",
        }
    )
    project_file.write_text(json.dumps(data), encoding="utf-8")

    from hancode.providers.mock import MockLLM

    class FakeCredentialProvider:
        def get_secret(self, provider: str) -> str:
            return "fake-secret"

    class FakeFactory:
        def __call__(self, config, *, credential=None, **kwargs):
            return MockLLM([])

    service = TaskService(
        credential_provider=FakeCredentialProvider(),
        provider_factory=FakeFactory(),
    )

    provider = service.prepare_provider(tmp_path)

    assert isinstance(provider, MockLLM)


def test_task_service_passes_credential_source_and_project_root(
    tmp_path: Path,
) -> None:
    _make_project(tmp_path)
    project_file = tmp_path / ".hancode" / "project.json"
    import json

    data = json.loads(project_file.read_text(encoding="utf-8"))
    data.update(
        {
            "llm_provider": "openai_compatible",
            "model_name": "test-model",
            "credential_source": "env",
            "provider_base_url": "https://example.invalid/v1",
        }
    )
    project_file.write_text(json.dumps(data), encoding="utf-8")

    class RecordingCredentialProvider:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str | None, Path | None]] = []

        def get_secret(self, provider: str, *, source=None, project_root=None) -> str:
            self.calls.append((provider, source, project_root))
            return "fake-secret"

    class FakeFactory:
        def __call__(self, config, *, credential=None, **kwargs):
            from hancode.providers.mock import MockLLM

            return MockLLM([])

    credentials = RecordingCredentialProvider()
    service = TaskService(
        credential_provider=credentials, provider_factory=FakeFactory()
    )

    service.prepare_provider(tmp_path)

    assert credentials.calls == [
        ("openai_compatible", "env", tmp_path.resolve())
    ]


def test_task_service_credential_missing_raises_provider_error(
    tmp_path: Path,
) -> None:
    _make_project(tmp_path)
    project_file = tmp_path / ".hancode" / "project.json"
    import json

    data = json.loads(project_file.read_text(encoding="utf-8"))
    data.update(
        {
            "llm_provider": "openai_compatible",
            "model_name": "test-model",
            "credential_source": "env",
            "provider_base_url": "https://example.invalid/v1",
        }
    )
    project_file.write_text(json.dumps(data), encoding="utf-8")

    class MissingCredentialProvider:
        def get_secret(self, provider: str) -> str:
            raise HanCodeError(
                __import__(
                    "hancode.core.errors", fromlist=["StructuredError"]
                ).StructuredError(
                    error_code="credential_missing",
                    message="No credential is configured.",
                    phase="spec",
                    denied_rule="credential_required",
                    suggested_fix="Configure the provider.",
                )
            )

    service = TaskService(
        credential_provider=MissingCredentialProvider(),
    )

    with pytest.raises(HanCodeError) as exc_info:
        service.prepare_provider(tmp_path)

    assert exc_info.value.structured_error.error_code == "provider_credential_missing"
    assert exc_info.value.structured_error.denied_rule == "provider_credential_required"


def test_task_service_injected_provider_skips_credential_resolution(
    tmp_path: Path,
) -> None:
    _make_project(tmp_path)
    service = TaskService()
    service.create(tmp_path, "Test goal")

    from hancode.providers.mock import MockLLM

    injected = MockLLM([])
    result = service.run(tmp_path, "task-001", provider=injected)

    assert result is not None
