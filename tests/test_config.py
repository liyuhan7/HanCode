from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import pytest

from hancode.config import HanCodeConfig, load_config
from hancode.errors import HanCodeError
from hancode.workspace import init_project_workspace


def test_config_loads_defaults(tmp_path: Path) -> None:
    init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )

    config = load_config(tmp_path)

    assert config == HanCodeConfig(
        project_root=tmp_path.resolve(),
        hancode_root=tmp_path.resolve() / ".hancode",
        allowed_workspace_root=tmp_path.resolve(),
        task_root=None,
        llm_provider="mock",
        model_name=None,
        credential_source=None,
        test_command=None,
        build_command=None,
        max_steps=30,
        retry_budget=2,
        max_checkpoints_per_task=5,
        max_observation_bytes=8192,
        max_context_chars=24000,
        max_trace_events=40,
        protected_patterns=(
            "assignment/**",
            "teacher_tests/**",
            "grading/**",
            "sample_data/**",
            ".env",
            ".env.*",
            "credentials/**",
        ),
        writable_roots=(tmp_path.resolve() / "src", tmp_path.resolve() / "tests"),
    )


def test_config_loads_project_json_overrides(tmp_path: Path) -> None:
    workspace = init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )
    (workspace / "project.json").write_text(
        """{
  "workspace_version": 1,
  "project_id": "course-project",
  "course_name": "AI4SE",
  "assignment_name": "Coding Agent Harness",
  "project_root": ".",
  "llm_provider": "anthropic",
  "model_name": "claude-sonnet",
  "credential_source": "keyring",
  "test_command": "pytest -q",
  "build_command": "python -m build",
  "max_steps": 12,
  "retry_budget": 1,
  "max_checkpoints_per_task": 3,
  "max_observation_bytes": 4096,
  "max_context_chars": 16000,
  "max_trace_events": 25,
  "protected_patterns": ["docs/SPEC.md", "fixtures/**"],
  "writable_roots": ["src/**", "tests"]
}
""",
        encoding="utf-8",
    )

    config = load_config(tmp_path)

    assert config.llm_provider == "anthropic"
    assert config.model_name == "claude-sonnet"
    assert config.credential_source == "keyring"
    assert config.test_command == "pytest -q"
    assert config.build_command == "python -m build"
    assert config.max_steps == 12
    assert config.retry_budget == 1
    assert config.max_checkpoints_per_task == 3
    assert config.max_observation_bytes == 4096
    assert config.max_context_chars == 16000
    assert config.max_trace_events == 25
    assert config.protected_patterns == ("docs/SPEC.md", "fixtures/**")
    assert config.writable_roots == (
        tmp_path.resolve() / "src",
        tmp_path.resolve() / "tests",
    )


def test_config_requires_initialized_project_workspace(tmp_path: Path) -> None:
    with pytest.raises(HanCodeError) as exc_info:
        load_config(tmp_path)

    assert exc_info.value.to_dict() == {
        "error_code": "project_workspace_not_initialized",
        "message": "Project workspace is not initialized.",
        "phase": "spec",
        "denied_rule": "project_workspace_required",
        "suggested_fix": "Initialize the project workspace before loading configuration.",
    }


@pytest.mark.parametrize(
    "project_json",
    [
        "{invalid",
        "[]",
        """{
  "workspace_version": 1,
  "project_id": "course-project",
  "course_name": "AI4SE",
  "assignment_name": "Coding Agent Harness",
  "project_root": ".",
  "max_steps": "30"
}
""",
    ],
    ids=["malformed_json", "non_object_root", "invalid_field_type"],
)
def test_config_rejects_invalid_project_config(tmp_path: Path, project_json: str) -> None:
    workspace = init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )
    (workspace / "project.json").write_text(project_json, encoding="utf-8")

    with pytest.raises(HanCodeError) as exc_info:
        load_config(tmp_path)

    assert exc_info.value.to_dict() == {
        "error_code": "invalid_project_config",
        "message": "Project configuration is invalid.",
        "phase": "spec",
        "denied_rule": "valid_project_config_required",
        "suggested_fix": "Repair project.json configuration fields and try again.",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_steps", 0),
        ("retry_budget", -1),
        ("max_checkpoints_per_task", 0),
        ("max_observation_bytes", 0),
        ("max_context_chars", 0),
        ("max_trace_events", 0),
        ("max_steps", True),
    ],
)
def test_config_rejects_invalid_limit_values(
    tmp_path: Path, field: str, value: int | bool
) -> None:
    workspace = init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )
    project_file = workspace / "project.json"
    project_data = json.loads(project_file.read_text(encoding="utf-8"))
    project_data[field] = value
    project_file.write_text(json.dumps(project_data), encoding="utf-8")

    with pytest.raises(HanCodeError) as exc_info:
        load_config(tmp_path)

    assert exc_info.value.to_dict() == {
        "error_code": "invalid_project_config",
        "message": "Project configuration is invalid.",
        "phase": "spec",
        "denied_rule": "valid_project_config_required",
        "suggested_fix": "Repair project.json configuration fields and try again.",
    }


@pytest.mark.parametrize(
    ("updates", "expected_error"),
    [
        (
            {"llm_provider": "unsupported"},
            {
                "error_code": "unknown_llm_provider",
                "message": "LLM provider is not supported.",
                "phase": "spec",
                "denied_rule": "supported_provider_required",
                "suggested_fix": "Use a supported LLM provider.",
            },
        ),
        (
            {"llm_provider": "anthropic", "model_name": ""},
            {
                "error_code": "invalid_project_config",
                "message": "Project configuration is invalid.",
                "phase": "spec",
                "denied_rule": "valid_project_config_required",
                "suggested_fix": "Repair project.json configuration fields and try again.",
            },
        ),
        (
            {"credential_source": "file"},
            {
                "error_code": "invalid_project_config",
                "message": "Project configuration is invalid.",
                "phase": "spec",
                "denied_rule": "valid_project_config_required",
                "suggested_fix": "Repair project.json configuration fields and try again.",
            },
        ),
    ],
    ids=["unknown_provider", "empty_real_model", "unknown_credential_source"],
)
def test_config_rejects_invalid_provider_settings(
    tmp_path: Path, updates: dict[str, str], expected_error: dict[str, object]
) -> None:
    workspace = init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )
    project_file = workspace / "project.json"
    project_data = json.loads(project_file.read_text(encoding="utf-8"))
    project_data.update(updates)
    project_file.write_text(json.dumps(project_data), encoding="utf-8")

    with pytest.raises(HanCodeError) as exc_info:
        load_config(tmp_path)

    assert exc_info.value.to_dict() == expected_error


@pytest.mark.parametrize(
    ("updates", "field_name"),
    [
        ({"api_key": "live-secret-value"}, "api_key"),
        ({"provider": {"access_token": "live-secret-value"}}, "access_token"),
    ],
    ids=["top_level", "nested"],
)
def test_config_does_not_accept_plaintext_secret(
    tmp_path: Path, updates: dict[str, object], field_name: str
) -> None:
    workspace = init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )
    project_file = workspace / "project.json"
    project_data = json.loads(project_file.read_text(encoding="utf-8"))
    project_data.update(updates)
    project_file.write_text(json.dumps(project_data), encoding="utf-8")

    with pytest.raises(HanCodeError) as exc_info:
        load_config(tmp_path)

    assert exc_info.value.to_dict() == {
        "error_code": "plaintext_secret_not_allowed",
        "message": f"Plaintext credential field is not allowed: {field_name}.",
        "phase": "spec",
        "denied_rule": "plaintext_credentials_forbidden",
        "suggested_fix": "Remove the field and use credential_source instead.",
    }
    assert "live-secret-value" not in str(exc_info.value)


@pytest.mark.parametrize("writable_root", ["../outside", "C:/outside", "/outside"])
def test_config_rejects_writable_root_outside_project(
    tmp_path: Path, writable_root: str
) -> None:
    workspace = init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )
    project_file = workspace / "project.json"
    project_data = json.loads(project_file.read_text(encoding="utf-8"))
    project_data["writable_roots"] = [writable_root]
    project_file.write_text(json.dumps(project_data), encoding="utf-8")

    with pytest.raises(HanCodeError) as exc_info:
        load_config(tmp_path)

    assert exc_info.value.to_dict() == {
        "error_code": "config_path_outside_project_root",
        "message": "Configuration path must stay inside the project workspace.",
        "phase": "spec",
        "denied_rule": "workspace_root_boundary",
        "suggested_fix": "Use a relative path inside the project workspace.",
    }


def test_config_rejects_writable_root_link_escape(tmp_path: Path) -> None:
    workspace = init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )
    outside_root = tmp_path.parent / f"{tmp_path.name}-outside-root"
    outside_root.mkdir()
    _link_directory(tmp_path / "linked", outside_root)

    project_file = workspace / "project.json"
    project_data = json.loads(project_file.read_text(encoding="utf-8"))
    project_data["writable_roots"] = ["linked"]
    project_file.write_text(json.dumps(project_data), encoding="utf-8")

    with pytest.raises(HanCodeError) as exc_info:
        load_config(tmp_path)

    assert exc_info.value.to_dict() == {
        "error_code": "config_path_outside_project_root",
        "message": "Configuration path must stay inside the project workspace.",
        "phase": "spec",
        "denied_rule": "workspace_root_boundary",
        "suggested_fix": "Use a relative path inside the project workspace.",
    }


def test_config_derives_task_root_from_task_id(tmp_path: Path) -> None:
    init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )

    config = load_config(tmp_path, task_id="task-001")

    assert config.task_root == tmp_path.resolve() / ".hancode" / "tasks" / "task-001"


@pytest.mark.parametrize("task_id", ["../outside", "C:/outside"])
def test_config_reuses_task_id_path_boundary(tmp_path: Path, task_id: str) -> None:
    init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )

    with pytest.raises(HanCodeError) as exc_info:
        load_config(tmp_path, task_id=task_id)

    assert exc_info.value.to_dict() == {
        "error_code": "workspace_path_outside_project_root",
        "message": "Task workspace path must stay inside the project workspace.",
        "phase": "spec",
        "denied_rule": "workspace_root_boundary",
        "suggested_fix": "Use a relative task ID without parent-directory segments.",
    }


def _link_directory(link_path: Path, target_path: Path) -> None:
    try:
        link_path.symlink_to(target_path, target_is_directory=True)
        return
    except OSError as exc:
        if os.name != "nt":
            pytest.skip(f"Directory symlink unsupported in this environment: {exc}")

    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link_path), str(target_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip(
            "Directory link creation unavailable in this environment: "
            f"{result.stdout}{result.stderr}"
        )
