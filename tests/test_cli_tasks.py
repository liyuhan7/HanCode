"""Stage 1: CLI task command tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from hancode.app.task_models import TaskSummary
from hancode.app.task_service import TaskService
from hancode.core.models import Phase, TaskStatus
from hancode.core.state import TaskState
from hancode.interfaces import cli
from hancode.runtime.agent_loop import AgentRunResult
from hancode.storage.workspace import init_project_workspace


runner = CliRunner()


def _payload(result: object) -> dict[str, object]:
    output = getattr(result, "stdout")
    value = json.loads(output)
    assert isinstance(value, dict)
    return value


def _make_project(tmp_path: Path) -> Path:
    init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Harness",
    )
    return tmp_path


def _make_task_summary(
    task_id: str = "task-001",
    goal: str = "test goal",
    status: TaskStatus = TaskStatus.CREATED,
) -> TaskSummary:
    return TaskSummary(
        task_id=task_id,
        goal=goal,
        status=status,
        current_phase=Phase.SPEC,
        retry_budget_remaining=2,
        latest_test_status="none",
        files_changed=(),
        tests_run=(),
        latest_checkpoint=None,
        rollback_required=False,
        inconsistent=False,
        artifacts={
            "SPEC.md": False,
            "PLAN.md": False,
            "TEST_REPORT.md": False,
            "REVIEW.md": False,
            "KNOWLEDGE.md": False,
            "DELIVERABLES.md": False,
        },
        resumable=False,
    )


def _make_run_result(
    status: TaskStatus = TaskStatus.BLOCKED,
    task_id: str = "task-001",
) -> AgentRunResult:
    state = TaskState(
        schema_version=1,
        task_id=task_id,
        goal="test goal",
        status=status,
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
    return AgentRunResult(
        status=status,
        steps=1,
        tool_calls=(),
        risks=(),
        final_observation=None,
        error=None,
        final_state=state,
        retry_budget_remaining=2,
        trace_events=(),
    )


# =========================================================================
# Help tests
# =========================================================================


def test_cli_help_displays_run_and_task() -> None:
    result = runner.invoke(cli.app, ["--help"])

    assert result.exit_code == 0
    assert "run" in result.stdout
    assert "task" in result.stdout


def test_cli_task_help_displays_five_commands() -> None:
    result = runner.invoke(cli.app, ["task", "--help"])

    assert result.exit_code == 0
    assert "create" in result.stdout
    assert "run" in result.stdout
    assert "resume" in result.stdout
    assert "status" in result.stdout
    assert "list" in result.stdout


# =========================================================================
# task create
# =========================================================================


def test_cli_task_create_returns_structured_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _make_project(tmp_path)
    summary = _make_task_summary()

    class FakeTaskService:
        def create(self, project_root: Path, goal: str, *, task_id: str | None = None) -> TaskSummary:
            return summary

    monkeypatch.setattr(cli, "task_service", FakeTaskService())

    result = runner.invoke(
        cli.app,
        ["task", "create", "Implement login", "--project-root", str(tmp_path)],
    )

    assert result.exit_code == 0
    payload = _payload(result)
    assert payload["command"] == "task create"
    assert payload["status"] == "completed"
    assert payload["task"]["task_id"] == "task-001"


def test_cli_task_create_persists_goal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _make_project(tmp_path)

    result = runner.invoke(
        cli.app,
        ["task", "create", "Implement login", "--project-root", str(tmp_path)],
    )

    assert result.exit_code == 0
    payload = _payload(result)
    assert payload["task"]["goal"] == "Implement login"


def test_cli_task_create_rejects_blank_goal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _make_project(tmp_path)

    result = runner.invoke(
        cli.app,
        ["task", "create", "   ", "--project-root", str(tmp_path)],
    )

    assert result.exit_code == 2
    payload = _payload(result)
    assert payload["status"] == "failed"
    assert payload["error"]["error_code"] == "task_goal_required"


def test_cli_task_create_rejects_duplicate_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _make_project(tmp_path)
    runner.invoke(
        cli.app,
        ["task", "create", "First", "--task-id", "task-001", "--project-root", str(tmp_path)],
    )

    result = runner.invoke(
        cli.app,
        ["task", "create", "Second", "--task-id", "task-001", "--project-root", str(tmp_path)],
    )

    assert result.exit_code == 2
    payload = _payload(result)
    assert payload["error"]["error_code"] == "task_already_exists"


# =========================================================================
# task status
# =========================================================================


def test_cli_task_status_returns_task_summary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _make_project(tmp_path)
    runner.invoke(
        cli.app,
        ["task", "create", "Implement login", "--project-root", str(tmp_path)],
    )

    result = runner.invoke(
        cli.app,
        ["task", "status", "task-001", "--project-root", str(tmp_path)],
    )

    assert result.exit_code == 0
    payload = _payload(result)
    assert payload["command"] == "task status"
    assert payload["task"]["task_id"] == "task-001"


def test_cli_task_status_rejects_missing_task(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _make_project(tmp_path)

    result = runner.invoke(
        cli.app,
        ["task", "status", "nonexistent", "--project-root", str(tmp_path)],
    )

    assert result.exit_code == 2
    payload = _payload(result)
    assert payload["error"]["error_code"] == "task_not_found"


# =========================================================================
# task list
# =========================================================================


def test_cli_task_list_returns_sorted_tasks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _make_project(tmp_path)
    runner.invoke(
        cli.app,
        ["task", "create", "Second", "--task-id", "task-002", "--project-root", str(tmp_path)],
    )
    runner.invoke(
        cli.app,
        ["task", "create", "First", "--task-id", "task-001", "--project-root", str(tmp_path)],
    )

    result = runner.invoke(
        cli.app,
        ["task", "list", "--project-root", str(tmp_path)],
    )

    assert result.exit_code == 0
    payload = _payload(result)
    assert payload["command"] == "task list"
    assert len(payload["tasks"]) == 2
    assert payload["tasks"][0]["task_id"] == "task-001"
    assert payload["tasks"][1]["task_id"] == "task-002"


def test_cli_task_list_rejects_uninitialized_project(tmp_path: Path) -> None:
    result = runner.invoke(
        cli.app,
        ["task", "list", "--project-root", str(tmp_path)],
    )

    assert result.exit_code == 2
    payload = _payload(result)
    assert payload["error"]["error_code"] == "project_workspace_not_initialized"


# =========================================================================
# task run and resume
# =========================================================================


def test_cli_task_run_calls_service_with_resume_false(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _make_project(tmp_path)
    runner.invoke(
        cli.app,
        ["task", "create", "test", "--project-root", str(tmp_path)],
    )

    calls: list[bool] = []

    def fake_run(self, project_root: Path, task_id: str, *, resume: bool, provider: object = None) -> AgentRunResult:
        calls.append(resume)
        return _make_run_result()

    monkeypatch.setattr(TaskService, "run", fake_run)

    result = runner.invoke(
        cli.app,
        ["task", "run", "task-001", "--project-root", str(tmp_path)],
    )

    assert result.exit_code == 1
    assert calls == [False]


def test_cli_task_resume_calls_service_with_resume_true(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _make_project(tmp_path)
    runner.invoke(
        cli.app,
        ["task", "create", "test", "--project-root", str(tmp_path)],
    )

    calls: list[bool] = []

    def fake_resume(self, project_root: Path, task_id: str, *, provider: object = None) -> AgentRunResult:
        calls.append(True)
        return _make_run_result()

    monkeypatch.setattr(TaskService, "resume", fake_resume)

    result = runner.invoke(
        cli.app,
        ["task", "resume", "task-001", "--project-root", str(tmp_path)],
    )

    assert result.exit_code == 1
    assert calls == [True]


# =========================================================================
# Root-level run
# =========================================================================


def test_cli_run_creates_then_runs_task(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _make_project(tmp_path)

    result = runner.invoke(
        cli.app,
        ["run", "Implement login", "--project-root", str(tmp_path)],
    )

    assert result.exit_code == 1
    payload = _payload(result)
    assert payload["command"] == "run"
    assert payload["task"]["task_id"] == "task-001"
    assert payload["task"]["goal"] == "Implement login"
    # Top-level task must reflect final run state, not pre-run creation state
    assert payload["task"]["status"] == "blocked"


def test_cli_run_top_level_task_matches_run_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _make_project(tmp_path)

    result = runner.invoke(
        cli.app,
        ["run", "test goal", "--project-root", str(tmp_path)],
    )

    assert result.exit_code == 1
    payload = _payload(result)
    # Top-level task.status must equal run.task.status
    assert payload["task"]["status"] == payload["run"]["task"]["status"]
    assert payload["task"]["task_id"] == payload["run"]["task"]["task_id"]


def test_cli_run_returns_task_id_when_agent_blocks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _make_project(tmp_path)

    result = runner.invoke(
        cli.app,
        ["run", "test goal", "--project-root", str(tmp_path)],
    )

    assert result.exit_code == 1
    payload = _payload(result)
    assert payload["status"] == "blocked"
    assert payload["task"]["task_id"] == "task-001"


# =========================================================================
# Exit codes
# =========================================================================


def test_cli_task_completed_returns_exit_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _make_project(tmp_path)
    runner.invoke(
        cli.app,
        ["task", "create", "test", "--project-root", str(tmp_path)],
    )

    def fake_run(self, project_root: Path, task_id: str, *, resume: bool, provider: object = None) -> AgentRunResult:
        return _make_run_result(status=TaskStatus.COMPLETED)

    monkeypatch.setattr(TaskService, "run", fake_run)

    result = runner.invoke(
        cli.app,
        ["task", "run", "task-001", "--project-root", str(tmp_path)],
    )

    assert result.exit_code == 0


def test_cli_task_blocked_returns_exit_one(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _make_project(tmp_path)
    runner.invoke(
        cli.app,
        ["task", "create", "test", "--project-root", str(tmp_path)],
    )

    def fake_run(self, project_root: Path, task_id: str, *, resume: bool, provider: object = None) -> AgentRunResult:
        return _make_run_result(status=TaskStatus.BLOCKED)

    monkeypatch.setattr(TaskService, "run", fake_run)

    result = runner.invoke(
        cli.app,
        ["task", "run", "task-001", "--project-root", str(tmp_path)],
    )

    assert result.exit_code == 1


def test_cli_task_inconsistent_returns_exit_three(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _make_project(tmp_path)
    runner.invoke(
        cli.app,
        ["task", "create", "test", "--project-root", str(tmp_path)],
    )

    def fake_run(self, project_root: Path, task_id: str, *, resume: bool, provider: object = None) -> AgentRunResult:
        return _make_run_result(status=TaskStatus.INCONSISTENT)

    monkeypatch.setattr(TaskService, "run", fake_run)

    result = runner.invoke(
        cli.app,
        ["task", "run", "task-001", "--project-root", str(tmp_path)],
    )

    assert result.exit_code == 3


# =========================================================================
# OSError boundary
# =========================================================================


def test_cli_task_create_filesystem_failure_returns_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _make_project(tmp_path)

    def fake_create(self, project_root: Path, goal: str, *, task_id: str | None = None) -> object:
        raise OSError("Permission denied")

    monkeypatch.setattr(TaskService, "create", fake_create)

    result = runner.invoke(
        cli.app,
        ["task", "create", "test", "--project-root", str(tmp_path)],
    )

    assert result.exit_code == 2
    payload = _payload(result)
    assert payload["error"]["error_code"] == "cli_task_operation_failed"


def test_cli_task_list_filesystem_failure_returns_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _make_project(tmp_path)

    def fake_list_tasks(self, project_root: Path) -> tuple:
        raise OSError("Permission denied")

    monkeypatch.setattr(TaskService, "list_tasks", fake_list_tasks)

    result = runner.invoke(
        cli.app,
        ["task", "list", "--project-root", str(tmp_path)],
    )

    assert result.exit_code == 2
    payload = _payload(result)
    assert payload["error"]["error_code"] == "cli_task_operation_failed"
