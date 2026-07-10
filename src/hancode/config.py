from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import cast

from hancode.errors import HanCodeError, StructuredError
from hancode.workspace import load_project_metadata, task_path


_DEFAULT_PROTECTED_PATTERNS = (
    "assignment.md",
    "assignment/**",
    "tests/teacher_*",
    "teacher_tests/**",
    "grading/**",
    "samples/**",
    "sample_data/**",
    ".env",
    ".env.*",
    "credentials/**",
    "secrets/**",
    "*.key",
    "*.pem",
    "*.token",
)
_OPTIONAL_STRING_FIELDS = (
    "model_name",
    "credential_source",
    "test_command",
    "build_command",
)
_INTEGER_FIELDS = (
    "max_steps",
    "retry_budget",
    "max_checkpoints_per_task",
    "max_observation_bytes",
    "max_context_chars",
    "max_trace_events",
)
_POSITIVE_INTEGER_FIELDS = tuple(
    field for field in _INTEGER_FIELDS if field != "retry_budget"
)
_STRING_LIST_FIELDS = ("protected_patterns", "writable_roots")
_SUPPORTED_LLM_PROVIDERS = frozenset(
    {"mock", "openai_compatible", "anthropic", "local"}
)
_SUPPORTED_CREDENTIAL_SOURCES = frozenset({"keyring", "env", "dotenv"})
_REMOTE_LLM_PROVIDERS = frozenset({"openai_compatible", "anthropic"})
_SENSITIVE_FIELD_MARKERS = (
    "apikey",
    "token",
    "secret",
    "password",
    "authorization",
    "privatekey",
    "credential",
)
_PROJECT_METADATA_FIELDS = frozenset(
    {"workspace_version", "project_id", "course_name", "assignment_name", "project_root"}
)
_ACTIVE_CONFIG_FIELDS = frozenset(
    {
        "llm_provider",
        "model_name",
        "credential_source",
        "test_command",
        "build_command",
        "max_steps",
        "retry_budget",
        "max_checkpoints_per_task",
        "max_observation_bytes",
        "max_context_chars",
        "max_trace_events",
        "protected_patterns",
        "writable_roots",
    }
)
_ALLOWED_PROJECT_FIELDS = _PROJECT_METADATA_FIELDS | _ACTIVE_CONFIG_FIELDS


@dataclass(frozen=True, slots=True)
class HanCodeConfig:
    project_root: Path
    hancode_root: Path
    allowed_workspace_root: Path
    task_root: Path | None
    llm_provider: str
    model_name: str | None
    credential_source: str | None
    test_command: str | None
    build_command: str | None
    max_steps: int
    retry_budget: int
    max_checkpoints_per_task: int
    max_observation_bytes: int
    max_context_chars: int
    max_trace_events: int
    protected_patterns: tuple[str, ...]
    writable_roots: tuple[Path, ...]


def load_config(project_root: Path, task_id: str | None = None) -> HanCodeConfig:
    resolved_project_root = project_root.resolve()
    project_file = resolved_project_root / ".hancode" / "project.json"
    if not project_file.is_file():
        raise HanCodeError(
            StructuredError(
                error_code="project_workspace_not_initialized",
                message="Project workspace is not initialized.",
                phase="spec",
                denied_rule="project_workspace_required",
                suggested_fix="Initialize the project workspace before loading configuration.",
            )
        )
    project_data = _read_project_config(project_file)
    task_root = task_path(resolved_project_root, task_id) if task_id is not None else None
    writable_root_values = cast(
        list[str], project_data.get("writable_roots", ["src", "tests"])
    )
    return HanCodeConfig(
        project_root=resolved_project_root,
        hancode_root=resolved_project_root / ".hancode",
        allowed_workspace_root=resolved_project_root,
        task_root=task_root,
        llm_provider=cast(str, project_data.get("llm_provider", "mock")),
        model_name=cast(str | None, project_data.get("model_name")),
        credential_source=cast(str | None, project_data.get("credential_source")),
        test_command=cast(str | None, project_data.get("test_command")),
        build_command=cast(str | None, project_data.get("build_command")),
        max_steps=cast(int, project_data.get("max_steps", 30)),
        retry_budget=cast(int, project_data.get("retry_budget", 2)),
        max_checkpoints_per_task=cast(
            int, project_data.get("max_checkpoints_per_task", 5)
        ),
        max_observation_bytes=cast(
            int, project_data.get("max_observation_bytes", 8192)
        ),
        max_context_chars=cast(int, project_data.get("max_context_chars", 24000)),
        max_trace_events=cast(int, project_data.get("max_trace_events", 40)),
        protected_patterns=tuple(
            _merge_protected_patterns(
                cast(list[str], project_data.get("protected_patterns", []))
            )
        ),
        writable_roots=tuple(
            _resolve_writable_root(resolved_project_root, value)
            for value in writable_root_values
        ),
    )


def _read_project_config(project_file: Path) -> dict[str, object]:
    project_data = load_project_metadata(project_file)

    plaintext_secret_field = _find_plaintext_secret_field(project_data)
    if plaintext_secret_field is not None:
        raise _plaintext_secret_error(plaintext_secret_field)

    for field_name, value in project_data.items():
        if field_name not in _ALLOWED_PROJECT_FIELDS or isinstance(value, dict):
            raise _invalid_project_config_error(field_name)

    if "llm_provider" in project_data and not isinstance(
        project_data["llm_provider"], str
    ):
        raise _invalid_project_config_error("llm_provider")

    for field in _OPTIONAL_STRING_FIELDS:
        if field in project_data and project_data[field] is not None and not isinstance(
            project_data[field], str
        ):
            raise _invalid_project_config_error(field)

    for field in _INTEGER_FIELDS:
        if field in project_data and type(project_data[field]) is not int:
            raise _invalid_project_config_error(field)

    for field in _POSITIVE_INTEGER_FIELDS:
        if field in project_data and cast(int, project_data[field]) <= 0:
            raise _invalid_project_config_error(field)

    if "retry_budget" in project_data and cast(int, project_data["retry_budget"]) < 0:
        raise _invalid_project_config_error("retry_budget")

    for field in _STRING_LIST_FIELDS:
        if field in project_data and (
            not isinstance(project_data[field], list)
            or not all(
                isinstance(value, str)
                for value in cast(list[object], project_data[field])
            )
        ):
            raise _invalid_project_config_error(field)

    provider = cast(str, project_data.get("llm_provider", "mock"))
    if provider not in _SUPPORTED_LLM_PROVIDERS:
        raise _unknown_llm_provider_error()

    if provider != "mock":
        model_name = project_data.get("model_name")
        if not isinstance(model_name, str) or not model_name.strip():
            raise _invalid_project_config_error("model_name")

    credential_source = project_data.get("credential_source")
    if provider in _REMOTE_LLM_PROVIDERS and credential_source is None:
        raise _invalid_project_config_error("credential_source")
    if (
        credential_source is not None
        and credential_source not in _SUPPORTED_CREDENTIAL_SOURCES
    ):
        raise _invalid_project_config_error("credential_source")

    return project_data


def _resolve_writable_root(project_root: Path, configured_path: str) -> Path:
    normalized_path = configured_path.removesuffix("/**")
    if normalized_path in {"", "."}:
        raise _invalid_project_config_error("writable_roots")
    path = Path(normalized_path)
    windows_path = PureWindowsPath(normalized_path)
    candidate = (project_root / path).resolve()
    if (
        path.is_absolute()
        or windows_path.is_absolute()
        or ".." in path.parts
        or ".." in windows_path.parts
        or not candidate.is_relative_to(project_root)
    ):
        raise _config_path_outside_project_root_error()
    if candidate == project_root:
        raise _invalid_project_config_error("writable_roots")
    return candidate


def _merge_protected_patterns(project_patterns: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys((*_DEFAULT_PROTECTED_PATTERNS, *project_patterns)))


def _invalid_project_config_error(field_name: str | None = None) -> HanCodeError:
    if field_name is None:
        message = "Project configuration is invalid."
        suggested_fix = "Repair project.json configuration fields and try again."
    else:
        message = f"Project configuration field is invalid: {field_name}."
        suggested_fix = f"Remove or repair {field_name} in project.json."
    return HanCodeError(
        StructuredError(
            error_code="invalid_project_config",
            message=message,
            phase="spec",
            denied_rule="valid_project_config_required",
            suggested_fix=suggested_fix,
        )
    )


def _unknown_llm_provider_error() -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code="unknown_llm_provider",
            message="LLM provider is not supported.",
            phase="spec",
            denied_rule="supported_provider_required",
            suggested_fix="Use a supported LLM provider.",
        )
    )


def _config_path_outside_project_root_error() -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code="config_path_outside_project_root",
            message="Configuration path must stay inside the project workspace.",
            phase="spec",
            denied_rule="workspace_root_boundary",
            suggested_fix="Use a relative path inside the project workspace.",
        )
    )


def _find_plaintext_secret_field(value: object) -> str | None:
    if isinstance(value, dict):
        for field_name, nested_value in value.items():
            if isinstance(field_name, str) and _is_plaintext_secret_field(field_name):
                return field_name
            nested_field = _find_plaintext_secret_field(nested_value)
            if nested_field is not None:
                return nested_field
    elif isinstance(value, list):
        for nested_value in value:
            nested_field = _find_plaintext_secret_field(nested_value)
            if nested_field is not None:
                return nested_field
    return None


def _is_plaintext_secret_field(field_name: str) -> bool:
    normalized_name = "".join(
        character for character in field_name.lower() if character.isalnum()
    )
    return (
        normalized_name != "credentialsource"
        and any(marker in normalized_name for marker in _SENSITIVE_FIELD_MARKERS)
    )


def _plaintext_secret_error(field_name: str) -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code="plaintext_secret_not_allowed",
            message=f"Plaintext credential field is not allowed: {field_name}.",
            phase="spec",
            denied_rule="plaintext_credentials_forbidden",
            suggested_fix="Remove the field and use credential_source instead.",
        )
    )
