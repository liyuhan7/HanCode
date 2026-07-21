from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Literal, cast
from urllib.parse import urlparse

from hancode.core.errors import HanCodeError, StructuredError
from hancode.storage.workspace import load_project_metadata, task_path


_DEFAULT_PROTECTED_PATTERNS = (
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
)
_OPTIONAL_STRING_FIELDS = (
    "model_name",
    "credential_source",
    "test_command",
    "build_command",
    "provider_base_url",
    "interaction_mode",
)
_INTEGER_FIELDS = (
    "max_steps",
    "retry_budget",
    "max_checkpoints_per_task",
    "max_observation_bytes",
    "max_context_chars",
    "max_trace_events",
    "provider_timeout_seconds",
    "provider_max_retries",
    "provider_max_output_tokens",
    "provider_max_response_bytes",
    "max_interactions_per_phase",
    "max_interaction_question_chars",
    "max_interaction_answer_chars",
)
_PROVIDER_INTEGER_FIELDS = frozenset(
    {
        "provider_timeout_seconds",
        "provider_max_retries",
        "provider_max_output_tokens",
        "provider_max_response_bytes",
    }
)
_POSITIVE_INTEGER_FIELDS = tuple(
    field
    for field in _INTEGER_FIELDS
    if field != "retry_budget" and field not in _PROVIDER_INTEGER_FIELDS
)
_STRING_LIST_FIELDS = ("protected_patterns", "writable_roots")
_SUPPORTED_LLM_PROVIDERS = frozenset(
    {"mock", "openai_compatible", "anthropic", "local"}
)
_SUPPORTED_CREDENTIAL_SOURCES = frozenset({"keyring", "env", "dotenv"})
_SUPPORTED_INTERACTION_MODES = frozenset({"disabled", "ask_user"})
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
_PROVIDER_FIELD_EXEMPTIONS = frozenset(
    {
        "credentialsource",
        "providermaxoutputtokens",
    }
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
        "provider_base_url",
        "provider_timeout_seconds",
        "provider_max_retries",
        "provider_max_output_tokens",
        "provider_max_response_bytes",
        "interaction_mode",
        "max_interactions_per_phase",
        "max_interaction_question_chars",
        "max_interaction_answer_chars",
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
    provider_base_url: str | None = None
    provider_timeout_seconds: int = 60
    provider_max_retries: int = 2
    provider_max_output_tokens: int = 2048
    provider_max_response_bytes: int = 1048576
    interaction_mode: Literal["disabled", "ask_user"] = "disabled"
    max_interactions_per_phase: int = 8
    max_interaction_question_chars: int = 2048
    max_interaction_answer_chars: int = 8192


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
    config = HanCodeConfig(
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
        provider_base_url=cast(
            str | None, project_data.get("provider_base_url")
        ),
        provider_timeout_seconds=cast(
            int, project_data.get("provider_timeout_seconds", 60)
        ),
        provider_max_retries=cast(
            int, project_data.get("provider_max_retries", 2)
        ),
        provider_max_output_tokens=cast(
            int, project_data.get("provider_max_output_tokens", 2048)
        ),
        provider_max_response_bytes=cast(
            int, project_data.get("provider_max_response_bytes", 1048576)
        ),
        interaction_mode=cast(
            Literal["disabled", "ask_user"],
            project_data.get("interaction_mode", "disabled"),
        ),
        max_interactions_per_phase=cast(
            int, project_data.get("max_interactions_per_phase", 8)
        ),
        max_interaction_question_chars=cast(
            int, project_data.get("max_interaction_question_chars", 2048)
        ),
        max_interaction_answer_chars=cast(
            int, project_data.get("max_interaction_answer_chars", 8192)
        ),
    )
    _validate_interaction_config(config)
    return config


def _validate_interaction_config(config: HanCodeConfig) -> None:
    if config.interaction_mode == "ask_user":
        if config.max_interaction_question_chars > 2048:
            raise HanCodeError(
                StructuredError(
                    error_code="config_invalid",
                    message="max_interaction_question_chars cannot exceed 2048 (protocol limit).",
                    phase="spec",
                    denied_rule="config_interaction_limit",
                    suggested_fix="Set max_interaction_question_chars to 2048 or lower.",
                )
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

    interaction_mode = project_data.get("interaction_mode", "disabled")
    if interaction_mode not in _SUPPORTED_INTERACTION_MODES:
        raise _invalid_project_config_error("interaction_mode")

    _validate_provider_connection_fields(project_data, provider)

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


def _validate_provider_connection_fields(
    project_data: dict[str, object],
    provider: str,
) -> None:
    base_url = cast(str | None, project_data.get("provider_base_url"))

    if provider in _REMOTE_LLM_PROVIDERS:
        if base_url is None or not base_url.strip():
            raise _provider_base_url_invalid_error(
                "Provider base URL is required for remote providers.",
                "Set provider_base_url to a valid HTTPS URL.",
            )
        _validate_provider_base_url(base_url)

    if "provider_timeout_seconds" in project_data:
        timeout = cast(int, project_data["provider_timeout_seconds"])
        if timeout <= 0:
            raise _provider_timeout_invalid_error()

    if "provider_max_retries" in project_data:
        retries = cast(int, project_data["provider_max_retries"])
        if retries < 0:
            raise _provider_retry_config_invalid_error()

    if "provider_max_output_tokens" in project_data:
        tokens = cast(int, project_data["provider_max_output_tokens"])
        if tokens <= 0:
            raise _provider_output_limit_invalid_error()

    if "provider_max_response_bytes" in project_data:
        size = cast(int, project_data["provider_max_response_bytes"])
        if size <= 0:
            raise _provider_output_limit_invalid_error()


def _validate_provider_base_url(base_url: str) -> None:
    parsed = urlparse(base_url)
    if not parsed.scheme or not parsed.netloc:
        raise _provider_base_url_invalid_error(
            "Provider base URL is malformed.",
            "Set provider_base_url to a valid HTTPS URL.",
        )

    if parsed.scheme not in ("http", "https"):
        raise _provider_base_url_invalid_error(
            "Provider base URL must use HTTP or HTTPS.",
            "Use an HTTPS URL or http://localhost for local debugging.",
        )

    if parsed.scheme == "http" and parsed.hostname not in (
        "localhost",
        "127.0.0.1",
    ):
        raise _provider_base_url_invalid_error(
            "Provider base URL must use HTTPS for remote hosts.",
            "Use an HTTPS URL or http://localhost for local debugging.",
        )

    if parsed.username or parsed.password:
        raise _provider_base_url_invalid_error(
            "Provider base URL must not contain embedded credentials.",
            "Remove credentials from the URL and use credential_source.",
        )

    if parsed.query:
        raise _provider_base_url_invalid_error(
            "Provider base URL must not contain a query string.",
            "Remove query parameters from provider_base_url.",
        )


def _provider_base_url_invalid_error(
    message: str,
    suggested_fix: str,
) -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code="provider_base_url_invalid",
            message=message,
            phase="spec",
            denied_rule="valid_provider_config_required",
            suggested_fix=suggested_fix,
        )
    )


def _provider_timeout_invalid_error() -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code="provider_timeout_invalid",
            message="Provider timeout must be a positive integer.",
            phase="spec",
            denied_rule="valid_provider_config_required",
            suggested_fix="Set provider_timeout_seconds to a positive integer.",
        )
    )


def _provider_retry_config_invalid_error() -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code="provider_retry_config_invalid",
            message="Provider retry count must be a non-negative integer.",
            phase="spec",
            denied_rule="valid_provider_config_required",
            suggested_fix="Set provider_max_retries to a non-negative integer.",
        )
    )


def _provider_output_limit_invalid_error() -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code="provider_output_limit_invalid",
            message="Provider output limits must be positive integers.",
            phase="spec",
            denied_rule="valid_provider_config_required",
            suggested_fix=(
                "Set provider_max_output_tokens and "
                "provider_max_response_bytes to positive integers."
            ),
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
        normalized_name not in _PROVIDER_FIELD_EXEMPTIONS
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
