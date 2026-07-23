"""ToolSpec — single source of truth for tool metadata (S4-R6).

All tool names, descriptions, arg schemas, allowed phases, and read-only flags
are defined here.  Action.from_values, Provider Tool Catalog, ToolPolicy,
ToolRegistry tests, and README generation all consume these specs.
"""

from __future__ import annotations

from dataclasses import dataclass

from hancode.core.models import Phase


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    args_schema: dict[str, object]
    allowed_phases: frozenset[Phase]
    read_only: bool


ALL_TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="read_file",
        description=(
            "Read one UTF-8 file inside the allowed workspace. "
            "Use this before editing when the current file content is not already "
            "available in the supplied context. "
            "Do not use it for paths outside the workspace or protected credentials."
        ),
        args_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "minLength": 1,
                    "description": (
                        "Clean project-relative file path without '.' or '..' segments."
                    ),
                }
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        allowed_phases=frozenset(Phase),
        read_only=True,
    ),
    ToolSpec(
        name="list_files",
        description=(
            "List project files visible to the current workspace policy. "
            "Use it to discover file names before read_file or search_text. "
            "Do not infer file contents from the listing."
        ),
        args_schema={
            "type": "object",
            "additionalProperties": False,
        },
        allowed_phases=frozenset({Phase.SPEC, Phase.PLAN, Phase.CODE, Phase.REVIEW}),
        read_only=True,
    ),
    ToolSpec(
        name="search_text",
        description=(
            "Search workspace text for an exact query. "
            "Use it to locate symbols, requirements, or references before reading "
            "or editing a file. Do not use it as proof that absent text does not "
            "exist in binary or excluded files."
        ),
        args_schema={
            "type": "object",
            "properties": {"query": {"type": "string", "minLength": 1}},
            "required": ["query"],
            "additionalProperties": False,
        },
        allowed_phases=frozenset({Phase.SPEC, Phase.PLAN, Phase.CODE, Phase.REVIEW}),
        read_only=True,
    ),
    ToolSpec(
        name="write_file",
        description=(
            "Write complete UTF-8 content to one allowed file path. "
            "Use it to create a new artifact or when the complete target content "
            "is intentionally known. It may replace existing content. "
            "Prefer edit_file for a small confirmed change to an existing source file."
        ),
        args_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "minLength": 1},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
            "additionalProperties": False,
        },
        allowed_phases=frozenset(Phase),
        read_only=False,
    ),
    ToolSpec(
        name="edit_file",
        description=(
            "Replace one exact existing text fragment in a UTF-8 file. "
            "Use only after current content has been confirmed through context or "
            "read_file. old_string must match the current file exactly. "
            "Do not use it to create a new file or replace an unknown whole file."
        ),
        args_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "minLength": 1},
                "old_string": {"type": "string"},
                "new_string": {"type": "string"},
            },
            "required": ["path", "old_string", "new_string"],
            "additionalProperties": False,
        },
        allowed_phases=frozenset({Phase.CODE}),
        read_only=False,
    ),
    ToolSpec(
        name="run_tests",
        description="Run one test command. If command is omitted, the project's configured test command is used. Shell syntax is not supported.",
        args_schema={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Explicit single-command argv input (e.g. 'gcc hello.c'). "
                                   "When omitted the project-level test_command is used; shell operators are rejected.",
                },
            },
            "additionalProperties": False,
        },
        allowed_phases=frozenset({Phase.CODE, Phase.TEST, Phase.REVIEW}),
        read_only=False,
    ),
    ToolSpec(
        name="rollback_last_checkpoint",
        description="Rollback to the last checkpoint.",
        args_schema={"type": "object", "maxProperties": 0, "additionalProperties": False},
        allowed_phases=frozenset({Phase.REVIEW, Phase.DELIVER}),
        read_only=False,
    ),
    # --- S4 new tools ---
    ToolSpec(
        name="get_diff",
        description="Get the diff of changed files since the task baseline.",
        args_schema={
            "type": "object",
            "properties": {
                "scope": {"type": "string", "enum": ["task", "latest"]},
                "path": {"type": "string"},
            },
            "additionalProperties": False,
        },
        allowed_phases=frozenset({Phase.CODE, Phase.TEST, Phase.REVIEW, Phase.DELIVER}),
        read_only=True,
    ),
    ToolSpec(
        name="run_build",
        description="Run a build command. If command is omitted, the project's configured build_command is used.",
        args_schema={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Explicit build command to run (e.g. 'gcc hello.c -o hello'). "
                                   "When omitted the project-level build_command is used.",
                },
            },
            "additionalProperties": False,
        },
        allowed_phases=frozenset({Phase.TEST, Phase.REVIEW}),
        read_only=False,
    ),
    ToolSpec(
        name="read_test_report",
        description="Read the test report for the current task.",
        args_schema={"type": "object", "maxProperties": 0, "additionalProperties": False},
        allowed_phases=frozenset({Phase.TEST, Phase.REVIEW, Phase.DELIVER}),
        read_only=True,
    ),
    ToolSpec(
        name="list_checkpoints",
        description="List all checkpoints for the current task.",
        args_schema={"type": "object", "maxProperties": 0, "additionalProperties": False},
        allowed_phases=frozenset({Phase.CODE, Phase.TEST, Phase.REVIEW, Phase.DELIVER}),
        read_only=True,
    ),
    ToolSpec(
        name="record_review",
        description="Record structured review evidence.",
        args_schema={
            "type": "object",
            "properties": {
                "requirements": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["requirement", "status", "evidence"],
                        "properties": {
                            "requirement": {"type": "string", "minLength": 1},
                            "status": {
                                "type": "string",
                                "enum": ["covered", "partial", "missing"],
                            },
                            "evidence": {"type": "string"},
                        },
                        "additionalProperties": False,
                    },
                },
                "risks": {"type": "array"},
            },
            "required": ["requirements"],
            "additionalProperties": False,
        },
        allowed_phases=frozenset({Phase.REVIEW}),
        read_only=False,
    ),
    ToolSpec(
        name="record_knowledge",
        description="Record structured knowledge items.",
        args_schema={
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["topic", "summary"],
                        "properties": {
                            "topic": {"type": "string", "minLength": 1},
                            "summary": {"type": "string", "minLength": 1},
                            "evidence": {"type": "string"},
                        },
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["items"],
            "additionalProperties": False,
        },
        allowed_phases=frozenset({Phase.DELIVER}),
        read_only=False,
    ),
)

TOOL_SPEC_BY_NAME: dict[str, ToolSpec] = {spec.name: spec for spec in ALL_TOOL_SPECS}
ALL_TOOL_NAMES: frozenset[str] = frozenset(TOOL_SPEC_BY_NAME)
