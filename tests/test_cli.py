from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from typer.testing import CliRunner

from hancode import cli
from hancode.errors import HanCodeError, StructuredError
from hancode.state import load_state, save_state
from hancode.workspace import init_project_workspace, init_task_workspace


runner = CliRunner()


def _payload(result: object) -> dict[str, object]:
    output = getattr(result, "stdout")
    value = json.loads(output)
    assert isinstance(value, dict)
    return value


def test_cli_help_displays_supported_commands() -> None:
    result = runner.invoke(cli.app, ["--help"])

    assert result.exit_code == 0
    assert "init" in result.stdout
    assert "demo" in result.stdout
    assert "export" in result.stdout
    assert "auth" not in result.stdout


def test_cli_init_creates_workspace_with_deterministic_defaults(tmp_path: Path) -> None:
    project_root = tmp_path / "course-project"
    project_root.mkdir()

    result = runner.invoke(cli.app, ["init", str(project_root)])

    assert result.exit_code == 0
    payload = _payload(result)
    assert payload["status"] == "completed"
    assert list(payload) == ["command", "status", "workspace"]
    project_data = json.loads(
        (project_root / ".hancode" / "project.json").read_text(encoding="utf-8")
    )
    assert project_data["project_id"] == "course-project"
    assert project_data["course_name"] == "unspecified-course"
    assert project_data["assignment_name"] == "unspecified-assignment"


def test_cli_init_accepts_explicit_project_metadata(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()

    result = runner.invoke(
        cli.app,
        [
            "init",
            str(project_root),
            "--project-id",
            "course-001",
            "--course-name",
            "软件工程",
            "--assignment-name",
            "作业一",
        ],
    )

    assert result.exit_code == 0
    project_data = json.loads(
        (project_root / ".hancode" / "project.json").read_text(encoding="utf-8")
    )
    assert project_data["project_id"] == "course-001"
    assert project_data["course_name"] == "软件工程"
    assert project_data["assignment_name"] == "作业一"


def test_cli_demo_runs_with_mock_provider_without_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "HANCODE_API_KEY"):
        monkeypatch.delenv(name, raising=False)

    result = runner.invoke(cli.app, ["demo", "--provider", "mock"])

    assert result.exit_code == 0
    assert _payload(result)["status"] == "completed"


def test_cli_unknown_provider_returns_clear_error() -> None:
    result = runner.invoke(cli.app, ["demo", "--provider", "openai"])

    assert result.exit_code == 1
    payload = _payload(result)
    assert payload["status"] == "failed"
    assert payload["error"]["error_code"] == "cli_unknown_provider"  # type: ignore[index]
    assert "mock" in payload["error"]["suggested_fix"]  # type: ignore[index]


def test_cli_config_error_uses_stable_exit_code(tmp_path: Path) -> None:
    invalid_root = tmp_path / "not-a-directory"
    invalid_root.write_text("not a project directory", encoding="utf-8")

    result = runner.invoke(cli.app, ["init", str(invalid_root)])

    assert result.exit_code == 2
    payload = _payload(result)
    assert payload["status"] == "failed"
    assert payload["error"]["error_code"]  # type: ignore[index]


def test_cli_trace_error_uses_unrecoverable_exit_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_demo() -> object:
        raise HanCodeError(
            StructuredError(
                error_code="trace_write_failed",
                message="trace unavailable",
                phase="code",
                denied_rule="trace_required",
                suggested_fix="repair trace storage",
            )
        )

    monkeypatch.setattr(cli, "run_packaged_mock_demo", fail_demo)

    result = runner.invoke(cli.app, ["demo", "--provider", "mock"])

    assert result.exit_code == 3
    assert _payload(result)["error"]["error_code"] == "trace_write_failed"  # type: ignore[index]


def test_cli_export_copies_declared_artifacts(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    init_project_workspace(project_root, "project-001", "Course", "Assignment")
    task_root = init_task_workspace(project_root, "task-001")
    state = load_state(task_root)
    artifacts = dict(state.artifacts)
    artifacts["SPEC.md"] = True
    (task_root / "SPEC.md").write_text("# SPEC\n", encoding="utf-8")
    save_state(task_root, replace(state, artifacts=artifacts))
    output_dir = tmp_path / "deliverables"

    result = runner.invoke(
        cli.app,
        [
            "export",
            "--project-root",
            str(project_root),
            "--task",
            "task-001",
            "--out",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0
    payload = _payload(result)
    assert payload["command"] == "export"
    assert payload["status"] == "completed"
    assert (output_dir / "SPEC.md").read_text(encoding="utf-8") == "# SPEC\n"


def test_cli_export_missing_required_options_uses_typer_exit_code() -> None:
    result = runner.invoke(cli.app, ["export", "--task", "task-001"])

    assert result.exit_code == 2
    assert "Missing option" in (result.stdout + result.stderr)
