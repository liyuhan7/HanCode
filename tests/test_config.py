from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import pytest

from hancode.core.config import HanCodeConfig, load_config
from hancode.core.errors import HanCodeError
from hancode.storage.workspace import init_project_workspace


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
            "assignment",
            "assignment.*",
            "assignment/**",
            "**/assignment",
            "**/assignment.*",
            "**/assignment/**",
            "requirements",
            "requirements.*",
            "requirements/**",
            "**/requirements",
            "**/requirements.*",
            "**/requirements/**",
            "rubric",
            "rubric.*",
            "rubric/**",
            "**/rubric",
            "**/rubric.*",
            "**/rubric/**",
            "course_constraints",
            "course_constraints.*",
            "course_constraints/**",
            "**/course_constraints",
            "**/course_constraints.*",
            "**/course_constraints/**",
            "tests/teacher_*",
            "**/tests/teacher_*",
            "teacher_tests/**",
            "**/teacher_tests/**",
            "grading/**",
            "**/grading/**",
            "samples/**",
            "**/samples/**",
            "sample_data/**",
            "**/sample_data/**",
            ".env",
            ".env.*",
            "**/.env",
            "**/.env.*",
            "credentials/**",
            "**/credentials/**",
            "secrets/**",
            "**/secrets/**",
            "*.key",
            "*.pem",
            "*.token",
        ),
        writable_roots=(tmp_path.resolve() / "src", tmp_path.resolve() / "tests"),
        provider_base_url=None,
        provider_timeout_seconds=60,
        provider_max_retries=2,
        provider_max_output_tokens=2048,
        provider_max_response_bytes=1048576,
        provider_response_mode="json_object",
    )


@pytest.mark.parametrize(
    "configured_patterns",
    [[], ["docs/SPEC.md", "credentials/**"]],
    ids=["empty_override", "additional_patterns"],
)
def test_config_keeps_mandatory_protected_patterns(
    tmp_path: Path, configured_patterns: list[str]
) -> None:
    workspace = init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )
    project_file = workspace / "project.json"
    project_data = json.loads(project_file.read_text(encoding="utf-8"))
    project_data["protected_patterns"] = configured_patterns
    project_file.write_text(json.dumps(project_data), encoding="utf-8")

    config = load_config(tmp_path)

    mandatory_patterns = {
        "assignment",
        "assignment.*",
        "assignment/**",
        "**/assignment",
        "**/assignment.*",
        "**/assignment/**",
        "requirements",
        "requirements.*",
        "requirements/**",
        "**/requirements",
        "**/requirements.*",
        "**/requirements/**",
        "rubric",
        "rubric.*",
        "rubric/**",
        "**/rubric",
        "**/rubric.*",
        "**/rubric/**",
        "course_constraints",
        "course_constraints.*",
        "course_constraints/**",
        "**/course_constraints",
        "**/course_constraints.*",
        "**/course_constraints/**",
        "tests/teacher_*",
        "**/tests/teacher_*",
        "teacher_tests/**",
        "**/teacher_tests/**",
        "grading/**",
        "**/grading/**",
        "samples/**",
        "**/samples/**",
        "sample_data/**",
        "**/sample_data/**",
        ".env",
        ".env.*",
        "**/.env",
        "**/.env.*",
        "credentials/**",
        "**/credentials/**",
        "secrets/**",
        "**/secrets/**",
        "*.key",
        "*.pem",
        "*.token",
    }
    assert mandatory_patterns.issubset(config.protected_patterns)
    assert config.protected_patterns.count("credentials/**") == 1
    if configured_patterns:
        assert config.protected_patterns[-1] == "docs/SPEC.md"


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
  "writable_roots": ["src/**", "tests"],
  "provider_base_url": "https://example-provider.invalid/v1",
  "provider_timeout_seconds": 45,
  "provider_max_retries": 3,
  "provider_max_output_tokens": 1024,
  "provider_max_response_bytes": 524288
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
    assert config.protected_patterns[-2:] == ("docs/SPEC.md", "fixtures/**")
    assert "credentials/**" in config.protected_patterns
    assert config.writable_roots == (
        tmp_path.resolve() / "src",
        tmp_path.resolve() / "tests",
    )
    assert config.provider_base_url == "https://example-provider.invalid/v1"
    assert config.provider_timeout_seconds == 45
    assert config.provider_max_retries == 3
    assert config.provider_max_output_tokens == 1024
    assert config.provider_max_response_bytes == 524288


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
    ("field", "value"),
    [
        ("workspace_version", 2),
        ("project_id", ""),
        ("project_root", "../outside"),
    ],
)
def test_config_reuses_project_workspace_metadata_validation(
    tmp_path: Path, field: str, value: int | str
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
        "error_code": "invalid_project_workspace",
        "message": "Project workspace metadata is invalid.",
        "phase": "spec",
        "denied_rule": "valid_project_metadata_required",
        "suggested_fix": "Repair project.json before creating a task workspace.",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("unsupported_option", "enabled"),
        ("provider", {"base_url": "https://example.invalid"}),
    ],
    ids=["unknown_top_level_field", "nested_configuration"],
)
def test_config_rejects_unknown_or_nested_configuration(
    tmp_path: Path, field: str, value: object
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
        "message": f"Project configuration field is invalid: {field}.",
        "phase": "spec",
        "denied_rule": "valid_project_config_required",
        "suggested_fix": f"Remove or repair {field} in project.json.",
    }


@pytest.mark.parametrize(
    ("project_json", "expected_error"),
    [
        (
            "{invalid",
            {
                "error_code": "invalid_project_workspace",
                "message": "Project workspace metadata is invalid.",
                "phase": "spec",
                "denied_rule": "valid_project_metadata_required",
                "suggested_fix": "Repair project.json before creating a task workspace.",
            },
        ),
        (
            "[]",
            {
                "error_code": "invalid_project_workspace",
                "message": "Project workspace metadata is invalid.",
                "phase": "spec",
                "denied_rule": "valid_project_metadata_required",
                "suggested_fix": "Repair project.json before creating a task workspace.",
            },
        ),
        (
            """{
  "workspace_version": 1,
  "project_id": "course-project",
  "course_name": "AI4SE",
  "assignment_name": "Coding Agent Harness",
  "project_root": ".",
  "max_steps": "30"
}
""",
            {
                "error_code": "invalid_project_config",
                "message": "Project configuration field is invalid: max_steps.",
                "phase": "spec",
                "denied_rule": "valid_project_config_required",
                "suggested_fix": "Remove or repair max_steps in project.json.",
            },
        ),
    ],
    ids=["malformed_json", "non_object_root", "invalid_field_type"],
)
def test_config_rejects_invalid_project_config(
    tmp_path: Path, project_json: str, expected_error: dict[str, object]
) -> None:
    workspace = init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )
    (workspace / "project.json").write_text(project_json, encoding="utf-8")

    with pytest.raises(HanCodeError) as exc_info:
        load_config(tmp_path)

    assert exc_info.value.to_dict() == expected_error


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
        "message": f"Project configuration field is invalid: {field}.",
        "phase": "spec",
        "denied_rule": "valid_project_config_required",
        "suggested_fix": f"Remove or repair {field} in project.json.",
    }


def test_config_reports_invalid_limit_field_without_value(tmp_path: Path) -> None:
    workspace = init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )
    project_file = workspace / "project.json"
    project_data = json.loads(project_file.read_text(encoding="utf-8"))
    project_data["max_steps"] = 0
    project_file.write_text(json.dumps(project_data), encoding="utf-8")

    with pytest.raises(HanCodeError) as exc_info:
        load_config(tmp_path)

    assert exc_info.value.to_dict() == {
        "error_code": "invalid_project_config",
        "message": "Project configuration field is invalid: max_steps.",
        "phase": "spec",
        "denied_rule": "valid_project_config_required",
        "suggested_fix": "Remove or repair max_steps in project.json.",
    }
    assert "0" not in str(exc_info.value)


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
                "message": "Project configuration field is invalid: model_name.",
                "phase": "spec",
                "denied_rule": "valid_project_config_required",
                "suggested_fix": "Remove or repair model_name in project.json.",
            },
        ),
        (
            {"credential_source": "file"},
            {
                "error_code": "invalid_project_config",
                "message": "Project configuration field is invalid: credential_source.",
                "phase": "spec",
                "denied_rule": "valid_project_config_required",
                "suggested_fix": "Remove or repair credential_source in project.json.",
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


@pytest.mark.parametrize("provider", ["openai_compatible", "anthropic"])
def test_config_requires_credential_source_for_remote_provider(
    tmp_path: Path, provider: str
) -> None:
    workspace = init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )
    project_file = workspace / "project.json"
    project_data = json.loads(project_file.read_text(encoding="utf-8"))
    project_data.update({"llm_provider": provider, "model_name": "configured-model"})
    project_file.write_text(json.dumps(project_data), encoding="utf-8")

    with pytest.raises(HanCodeError) as exc_info:
        load_config(tmp_path)

    assert exc_info.value.to_dict() == {
        "error_code": "invalid_project_config",
        "message": "Project configuration field is invalid: credential_source.",
        "phase": "spec",
        "denied_rule": "valid_project_config_required",
        "suggested_fix": "Remove or repair credential_source in project.json.",
    }


def test_config_allows_local_provider_without_credential_source(tmp_path: Path) -> None:
    workspace = init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )
    project_file = workspace / "project.json"
    project_data = json.loads(project_file.read_text(encoding="utf-8"))
    project_data.update({"llm_provider": "local", "model_name": "local-model"})
    project_file.write_text(json.dumps(project_data), encoding="utf-8")

    assert load_config(tmp_path).credential_source is None


@pytest.mark.parametrize(
    ("updates", "field_name"),
    [
        ({"api_key": "live-secret-value"}, "api_key"),
        ({"provider": {"access_token": "live-secret-value"}}, "access_token"),
        ({"credentials": {"value": "live-secret-value"}}, "credentials"),
        ({"private_key": "live-secret-value"}, "private_key"),
        ({"api_key_value": "live-secret-value"}, "api_key_value"),
    ],
    ids=["top_level", "nested", "credentials_container", "private_key", "key_value"],
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


@pytest.mark.parametrize("writable_root", ["", ".", "/**"])
def test_config_rejects_project_root_as_writable_root(
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
        "error_code": "invalid_project_config",
        "message": "Project configuration field is invalid: writable_roots.",
        "phase": "spec",
        "denied_rule": "valid_project_config_required",
        "suggested_fix": "Remove or repair writable_roots in project.json.",
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


def test_config_accepts_openai_compatible_settings(tmp_path: Path) -> None:
    workspace = init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )
    project_file = workspace / "project.json"
    project_data = json.loads(project_file.read_text(encoding="utf-8"))
    project_data.update(
        {
            "llm_provider": "openai_compatible",
            "model_name": "configured-model",
            "credential_source": "keyring",
            "provider_base_url": "https://example-provider.invalid/v1",
            "provider_timeout_seconds": 45,
            "provider_max_retries": 3,
            "provider_max_output_tokens": 1024,
            "provider_max_response_bytes": 524288,
        }
    )
    project_file.write_text(json.dumps(project_data), encoding="utf-8")

    config = load_config(tmp_path)

    assert config.llm_provider == "openai_compatible"
    assert config.provider_base_url == "https://example-provider.invalid/v1"
    assert config.provider_timeout_seconds == 45
    assert config.provider_max_retries == 3
    assert config.provider_max_output_tokens == 1024
    assert config.provider_max_response_bytes == 524288


def test_config_requires_provider_base_url_for_openai_compatible(
    tmp_path: Path,
) -> None:
    workspace = init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )
    project_file = workspace / "project.json"
    project_data = json.loads(project_file.read_text(encoding="utf-8"))
    project_data.update(
        {
            "llm_provider": "openai_compatible",
            "model_name": "configured-model",
            "credential_source": "keyring",
        }
    )
    project_file.write_text(json.dumps(project_data), encoding="utf-8")

    with pytest.raises(HanCodeError) as exc_info:
        load_config(tmp_path)

    assert exc_info.value.to_dict() == {
        "error_code": "provider_base_url_invalid",
        "message": "Provider base URL is required for remote providers.",
        "phase": "spec",
        "denied_rule": "valid_provider_config_required",
        "suggested_fix": "Set provider_base_url to a valid HTTPS URL.",
    }


@pytest.mark.parametrize(
    "base_url",
    [
        "http://example.com/v1",
        "http://10.0.0.1/v1",
        "http://provider.invalid/v1",
    ],
    ids=["hostname", "ip", "remote_host"],
)
def test_config_rejects_http_remote_url(tmp_path: Path, base_url: str) -> None:
    workspace = init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )
    project_file = workspace / "project.json"
    project_data = json.loads(project_file.read_text(encoding="utf-8"))
    project_data.update(
        {
            "llm_provider": "openai_compatible",
            "model_name": "configured-model",
            "credential_source": "keyring",
            "provider_base_url": base_url,
        }
    )
    project_file.write_text(json.dumps(project_data), encoding="utf-8")

    with pytest.raises(HanCodeError) as exc_info:
        load_config(tmp_path)

    assert exc_info.value.to_dict() == {
        "error_code": "provider_base_url_invalid",
        "message": "Provider base URL must use HTTPS for remote hosts.",
        "phase": "spec",
        "denied_rule": "valid_provider_config_required",
        "suggested_fix": "Use an HTTPS URL or http://localhost for local debugging.",
    }


@pytest.mark.parametrize(
    "base_url",
    [
        "http://localhost:8080/v1",
        "http://127.0.0.1:8080/v1",
        "http://localhost/v1",
    ],
    ids=["localhost_port", "loopback_ip", "localhost_no_port"],
)
def test_config_allows_http_localhost(tmp_path: Path, base_url: str) -> None:
    workspace = init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )
    project_file = workspace / "project.json"
    project_data = json.loads(project_file.read_text(encoding="utf-8"))
    project_data.update(
        {
            "llm_provider": "openai_compatible",
            "model_name": "configured-model",
            "credential_source": "keyring",
            "provider_base_url": base_url,
        }
    )
    project_file.write_text(json.dumps(project_data), encoding="utf-8")

    config = load_config(tmp_path)

    assert config.provider_base_url == base_url


@pytest.mark.parametrize(
    "base_url",
    [
        "https://user:pass@example.com/v1",
        "https://apikey@gateway.invalid/v1",
    ],
    ids=["user_password", "token_only"],
)
def test_config_rejects_url_embedded_credentials(
    tmp_path: Path, base_url: str
) -> None:
    workspace = init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )
    project_file = workspace / "project.json"
    project_data = json.loads(project_file.read_text(encoding="utf-8"))
    project_data.update(
        {
            "llm_provider": "openai_compatible",
            "model_name": "configured-model",
            "credential_source": "keyring",
            "provider_base_url": base_url,
        }
    )
    project_file.write_text(json.dumps(project_data), encoding="utf-8")

    with pytest.raises(HanCodeError) as exc_info:
        load_config(tmp_path)

    assert exc_info.value.to_dict() == {
        "error_code": "provider_base_url_invalid",
        "message": "Provider base URL must not contain embedded credentials.",
        "phase": "spec",
        "denied_rule": "valid_provider_config_required",
        "suggested_fix": "Remove credentials from the URL and use credential_source.",
    }
    assert "user" not in str(exc_info.value)
    assert "pass" not in str(exc_info.value)
    assert "apikey" not in str(exc_info.value)


def test_config_rejects_url_with_query(tmp_path: Path) -> None:
    workspace = init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )
    project_file = workspace / "project.json"
    project_data = json.loads(project_file.read_text(encoding="utf-8"))
    project_data.update(
        {
            "llm_provider": "openai_compatible",
            "model_name": "configured-model",
            "credential_source": "keyring",
            "provider_base_url": "https://example.invalid/v1?key=value",
        }
    )
    project_file.write_text(json.dumps(project_data), encoding="utf-8")

    with pytest.raises(HanCodeError) as exc_info:
        load_config(tmp_path)

    assert exc_info.value.to_dict() == {
        "error_code": "provider_base_url_invalid",
        "message": "Provider base URL must not contain a query string.",
        "phase": "spec",
        "denied_rule": "valid_provider_config_required",
        "suggested_fix": "Remove query parameters from provider_base_url.",
    }


def test_config_rejects_negative_provider_retries(tmp_path: Path) -> None:
    workspace = init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )
    project_file = workspace / "project.json"
    project_data = json.loads(project_file.read_text(encoding="utf-8"))
    project_data.update(
        {
            "llm_provider": "openai_compatible",
            "model_name": "configured-model",
            "credential_source": "keyring",
            "provider_base_url": "https://example.invalid/v1",
            "provider_max_retries": -1,
        }
    )
    project_file.write_text(json.dumps(project_data), encoding="utf-8")

    with pytest.raises(HanCodeError) as exc_info:
        load_config(tmp_path)

    assert exc_info.value.to_dict() == {
        "error_code": "provider_retry_config_invalid",
        "message": "Provider retry count must be a non-negative integer.",
        "phase": "spec",
        "denied_rule": "valid_provider_config_required",
        "suggested_fix": "Set provider_max_retries to a non-negative integer.",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider_timeout_seconds", 0),
        ("provider_timeout_seconds", -5),
    ],
    ids=["zero_timeout", "negative_timeout"],
)
def test_config_rejects_invalid_provider_timeout(
    tmp_path: Path, field: str, value: int
) -> None:
    workspace = init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )
    project_file = workspace / "project.json"
    project_data = json.loads(project_file.read_text(encoding="utf-8"))
    project_data.update(
        {
            "llm_provider": "openai_compatible",
            "model_name": "configured-model",
            "credential_source": "keyring",
            "provider_base_url": "https://example.invalid/v1",
            field: value,
        }
    )
    project_file.write_text(json.dumps(project_data), encoding="utf-8")

    with pytest.raises(HanCodeError) as exc_info:
        load_config(tmp_path)

    assert exc_info.value.to_dict() == {
        "error_code": "provider_timeout_invalid",
        "message": "Provider timeout must be a positive integer.",
        "phase": "spec",
        "denied_rule": "valid_provider_config_required",
        "suggested_fix": "Set provider_timeout_seconds to a positive integer.",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider_max_output_tokens", 0),
        ("provider_max_response_bytes", 0),
        ("provider_max_output_tokens", -1),
        ("provider_max_response_bytes", -1),
    ],
    ids=[
        "zero_output_tokens",
        "zero_response_bytes",
        "negative_output_tokens",
        "negative_response_bytes",
    ],
)
def test_config_rejects_invalid_provider_output_limits(
    tmp_path: Path, field: str, value: int
) -> None:
    workspace = init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )
    project_file = workspace / "project.json"
    project_data = json.loads(project_file.read_text(encoding="utf-8"))
    project_data.update(
        {
            "llm_provider": "openai_compatible",
            "model_name": "configured-model",
            "credential_source": "keyring",
            "provider_base_url": "https://example.invalid/v1",
            field: value,
        }
    )
    project_file.write_text(json.dumps(project_data), encoding="utf-8")

    with pytest.raises(HanCodeError) as exc_info:
        load_config(tmp_path)

    assert exc_info.value.to_dict() == {
        "error_code": "provider_output_limit_invalid",
        "message": "Provider output limits must be positive integers.",
        "phase": "spec",
        "denied_rule": "valid_provider_config_required",
        "suggested_fix": "Set provider_max_output_tokens and provider_max_response_bytes to positive integers.",
    }


def test_config_provider_fields_default_when_missing(tmp_path: Path) -> None:
    workspace = init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )
    project_file = workspace / "project.json"
    project_data = json.loads(project_file.read_text(encoding="utf-8"))
    project_data.update(
        {
            "llm_provider": "openai_compatible",
            "model_name": "configured-model",
            "credential_source": "keyring",
            "provider_base_url": "https://example.invalid/v1",
        }
    )
    project_file.write_text(json.dumps(project_data), encoding="utf-8")

    config = load_config(tmp_path)

    assert config.provider_timeout_seconds == 60
    assert config.provider_max_retries == 2
    assert config.provider_max_output_tokens == 2048
    assert config.provider_max_response_bytes == 1048576


def test_config_mock_provider_does_not_require_base_url(tmp_path: Path) -> None:
    init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )

    config = load_config(tmp_path)

    assert config.llm_provider == "mock"
    assert config.provider_base_url is None


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


def test_provider_response_mode_defaults_to_json_object(tmp_path: Path) -> None:
    init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )

    config = load_config(tmp_path)

    assert config.provider_response_mode == "json_object"


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_supported_provider_response_modes_are_loaded(
    tmp_path: Path, mode: str
) -> None:
    init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )
    project_file = tmp_path / ".hancode" / "project.json"
    project_data = json.loads(project_file.read_text(encoding="utf-8"))
    project_data["provider_response_mode"] = mode
    project_data["llm_provider"] = "openai_compatible"
    project_data["model_name"] = "test-model"
    project_data["credential_source"] = "env"
    project_data["provider_base_url"] = "https://example.invalid/v1"
    project_file.write_text(
        json.dumps(project_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    config = load_config(tmp_path)

    assert config.provider_response_mode == mode


def test_invalid_provider_response_mode_is_rejected(tmp_path: Path) -> None:
    init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )
    project_file = tmp_path / ".hancode" / "project.json"
    project_data = json.loads(project_file.read_text(encoding="utf-8"))
    project_data["provider_response_mode"] = "yaml"
    project_data["llm_provider"] = "openai_compatible"
    project_data["model_name"] = "test-model"
    project_data["credential_source"] = "env"
    project_data["provider_base_url"] = "https://example.invalid/v1"
    project_file.write_text(
        json.dumps(project_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    with pytest.raises(HanCodeError) as exc_info:
        load_config(tmp_path)

    assert exc_info.value.structured_error.denied_rule == "config_provider_response_mode"
