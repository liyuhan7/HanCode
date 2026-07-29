"""Canonical project.json shape and defaults.

This module deliberately has no storage or interface dependencies so workspace
initialization, configuration loading, and interactive editors can share one
ordered source of truth without creating import cycles.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType


PROJECT_METADATA_KEYS = (
    "workspace_version",
    "project_id",
    "course_name",
    "assignment_name",
    "project_root",
)

PROJECT_CONFIG_DEFAULT_ITEMS: tuple[tuple[str, object], ...] = (
    ("llm_provider", "mock"),
    ("model_name", None),
    ("credential_source", None),
    ("provider_base_url", None),
    ("provider_timeout_seconds", 60),
    ("provider_max_retries", 2),
    ("provider_protocol_retries", 2),
    ("provider_max_output_tokens", 2048),
    ("provider_max_response_bytes", 1_048_576),
    ("provider_action_mode", "auto"),
    ("test_command", None),
    ("build_command", None),
    ("max_steps", 30),
    ("retry_budget", 2),
    ("max_checkpoints_per_task", 5),
    ("max_observation_bytes", 8_192),
    ("max_context_chars", 24_000),
    ("max_trace_events", 1000),
    ("writable_roots", ("src", "tests")),
    ("protected_patterns", ()),
    ("interaction_mode", "disabled"),
    ("max_interactions_per_phase", 8),
    ("max_interaction_question_chars", 2_048),
    ("max_interaction_answer_chars", 8_192),
    ("approval_mode", "disabled"),
    ("confirm_agent_rollback", True),
    ("confirm_agent_build", True),
    ("max_approvals_per_phase", 20),
    ("max_approval_payload_bytes", 262_144),
    ("max_approval_preview_chars", 12_000),
    ("max_rejection_reason_chars", 1_024),
    ("max_diff_files", 100),
    ("max_diff_chars", 30_000),
    ("max_diff_file_bytes", 524_288),
    ("diff_context_lines", 3),
)

PROJECT_CONFIG_KEYS = tuple(key for key, _value in PROJECT_CONFIG_DEFAULT_ITEMS)
PROJECT_CONFIG_DEFAULTS = MappingProxyType(dict(PROJECT_CONFIG_DEFAULT_ITEMS))


def build_project_config(
    *,
    project_id: str,
    course_name: str,
    assignment_name: str,
) -> dict[str, object]:
    """Return a fresh, fully expanded project configuration document."""
    metadata: dict[str, object] = {
        "workspace_version": 1,
        "project_id": project_id,
        "course_name": course_name,
        "assignment_name": assignment_name,
        "project_root": ".",
    }
    return complete_project_config(metadata)


def complete_project_config(
    values: Mapping[str, object],
    *,
    fallback_project_root: Path | None = None,
) -> dict[str, object]:
    """Normalize a valid legacy/minimal mapping into canonical key order."""
    root_name = fallback_project_root.name if fallback_project_root is not None else ""
    complete: dict[str, object] = {
        "workspace_version": values.get("workspace_version", 1),
        "project_id": values.get("project_id", root_name or "hancode-project"),
        "course_name": values.get("course_name", "unspecified-course"),
        "assignment_name": values.get("assignment_name", "unspecified-assignment"),
        "project_root": values.get("project_root", "."),
    }
    defaults = fresh_project_defaults()
    for key in PROJECT_CONFIG_KEYS:
        complete[key] = values.get(key, defaults[key])

    if "provider_response_mode" in values and "provider_action_mode" not in values:
        complete["provider_action_mode"] = values["provider_response_mode"]
    return complete


def fresh_project_defaults() -> dict[str, object]:
    """Return defaults with independent mutable list values."""
    defaults: dict[str, object] = {}
    for key, value in PROJECT_CONFIG_DEFAULT_ITEMS:
        defaults[key] = list(value) if isinstance(value, tuple) else value
    return defaults


__all__ = [
    "PROJECT_CONFIG_DEFAULTS",
    "PROJECT_CONFIG_DEFAULT_ITEMS",
    "PROJECT_CONFIG_KEYS",
    "PROJECT_METADATA_KEYS",
    "build_project_config",
    "complete_project_config",
    "fresh_project_defaults",
]
