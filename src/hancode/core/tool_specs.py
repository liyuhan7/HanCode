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
                    "pattern": "\\S",
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
            "Use it to discover project structure before reading relevant files."
        ),
        args_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "minLength": 1,
                    "pattern": "\\S",
                    "description": (
                        "Optional project-relative directory. "
                        "Omit it to list from the project root."
                    ),
                },
            },
            "additionalProperties": False,
        },
        allowed_phases=frozenset(
            {Phase.SPEC, Phase.PLAN, Phase.CODE, Phase.TEST, Phase.REVIEW}
        ),
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
            "properties": {
                "query": {"type": "string", "minLength": 1, "pattern": "\\S"}
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        allowed_phases=frozenset(
            {Phase.SPEC, Phase.PLAN, Phase.CODE, Phase.TEST, Phase.REVIEW}
        ),
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
                "path": {"type": "string", "minLength": 1, "pattern": "\\S"},
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
                "path": {"type": "string", "minLength": 1, "pattern": "\\S"},
                "old_string": {"type": "string", "minLength": 1, "pattern": "\\S"},
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
        description=(
            "Run one explicit project validation command selected by the Agent. "
            "The command must actually execute behavioral tests rather than only "
            "compile source code. Shell syntax is not supported."
        ),
        args_schema={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "minLength": 1,
                    "pattern": "\\S",
                    "description": (
                        "Explicit single-command argv input, such as "
                        "'python -m pytest -q', 'npm test', or 'make test'. "
                        "Shell operators and chained commands are not supported."
                    ),
                },
            },
            "required": ["command"],
            "additionalProperties": False,
        },
        allowed_phases=frozenset({Phase.TEST}),
        read_only=False,
    ),
    ToolSpec(
        name="record_test_strategy",
        description=(
            "Bind the task to one executable behavioral test command and the "
            "project test files that implement its requirement coverage. "
            "Create or update the test files before recording this strategy."
        ),
        args_schema={
            "type": "object",
            "properties": {
                "command": {"type": "string", "minLength": 1, "pattern": "\\S"},
                "framework": {"type": "string", "minLength": 1, "pattern": "\\S"},
                "test_files": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"type": "string", "minLength": 1, "pattern": "\\S"},
                },
                "coverage": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "properties": {
                            "requirement": {
                                "type": "string",
                                "minLength": 1,
                                "pattern": "\\S",
                            },
                            "verification": {
                                "type": "string",
                                "minLength": 1,
                                "pattern": "\\S",
                            },
                        },
                        "required": ["requirement", "verification"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["command", "framework", "test_files", "coverage"],
            "additionalProperties": False,
        },
        allowed_phases=frozenset({Phase.CODE}),
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
                "path": {"type": "string", "pattern": "\\S"},
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
                    "minLength": 1,
                    "pattern": "\\S",
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
                        "required": ["requirement_id", "status", "evidence"],
                        "properties": {
                            "requirement_id": {"type": "string", "minLength": 1},
                            "status": {
                                "type": "string",
                                "enum": [
                                    "covered",
                                    "partial",
                                    "not_covered",
                                    "missing",
                                    "untested",
                                ],
                            },
                            "evidence": {"type": "string"},
                            "risk": {
                                "oneOf": [
                                    {"type": "string"},
                                    {"type": "null"},
                                ],
                            },
                            "is_core": {
                                "type": "boolean",
                            },
                        },
                        "additionalProperties": False,
                    },
                },
                "risks": {
                    "type": "array",
                    "items": {"type": "string"},
                },
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
                        "required": ["category", "summary", "detail"],
                        "properties": {
                            "category": {
                                "type": "string",
                                "enum": [
                                    "requirement_understanding",
                                    "design_decision",
                                    "testing_experience",
                                    "error_fix",
                                    "reusable_pattern",
                                    "bug_fix",
                                    "test_insight",
                                    "process_improvement",
                                    "other",
                                ],
                            },
                            "summary": {"type": "string", "minLength": 1},
                            "detail": {"type": "string", "minLength": 1},
                            "source_trace_id": {
                                "oneOf": [
                                    {"type": "string"},
                                    {"type": "null"},
                                ],
                            },
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
