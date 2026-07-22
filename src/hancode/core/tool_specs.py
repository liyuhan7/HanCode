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
        description="Read a file inside the allowed workspace.",
        args_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        allowed_phases=frozenset(Phase),
        read_only=True,
    ),
    ToolSpec(
        name="list_files",
        description="List files in the project workspace.",
        args_schema={"type": "object"},
        allowed_phases=frozenset({Phase.SPEC, Phase.PLAN, Phase.CODE, Phase.REVIEW}),
        read_only=True,
    ),
    ToolSpec(
        name="search_text",
        description="Search text content in the workspace.",
        args_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        allowed_phases=frozenset({Phase.SPEC, Phase.PLAN, Phase.CODE, Phase.REVIEW}),
        read_only=True,
    ),
    ToolSpec(
        name="write_file",
        description="Write a file inside the allowed workspace.",
        args_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
        allowed_phases=frozenset(Phase),
        read_only=False,
    ),
    ToolSpec(
        name="edit_file",
        description="Edit a file by replacing a string.",
        args_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_string": {"type": "string"},
                "new_string": {"type": "string"},
            },
            "required": ["path", "old_string", "new_string"],
        },
        allowed_phases=frozenset({Phase.CODE}),
        read_only=False,
    ),
    ToolSpec(
        name="run_tests",
        description="Run the configured test command.",
        args_schema={"type": "object", "maxProperties": 0},
        allowed_phases=frozenset({Phase.CODE, Phase.TEST, Phase.REVIEW}),
        read_only=False,
    ),
    ToolSpec(
        name="rollback_last_checkpoint",
        description="Rollback to the last checkpoint.",
        args_schema={"type": "object", "maxProperties": 0},
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
        },
        allowed_phases=frozenset({Phase.CODE, Phase.TEST, Phase.REVIEW, Phase.DELIVER}),
        read_only=True,
    ),
    ToolSpec(
        name="run_build",
        description="Run the configured build command.",
        args_schema={"type": "object", "maxProperties": 0},
        allowed_phases=frozenset({Phase.TEST, Phase.REVIEW}),
        read_only=False,
    ),
    ToolSpec(
        name="read_test_report",
        description="Read the test report for the current task.",
        args_schema={"type": "object", "maxProperties": 0},
        allowed_phases=frozenset({Phase.TEST, Phase.REVIEW, Phase.DELIVER}),
        read_only=True,
    ),
    ToolSpec(
        name="list_checkpoints",
        description="List all checkpoints for the current task.",
        args_schema={"type": "object", "maxProperties": 0},
        allowed_phases=frozenset({Phase.CODE, Phase.TEST, Phase.REVIEW, Phase.DELIVER}),
        read_only=True,
    ),
    ToolSpec(
        name="record_review",
        description="Record structured review evidence.",
        args_schema={
            "type": "object",
            "properties": {
                "requirements": {"type": "array"},
                "risks": {"type": "array"},
            },
            "required": ["requirements"],
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
                "items": {"type": "array"},
            },
            "required": ["items"],
        },
        allowed_phases=frozenset({Phase.DELIVER}),
        read_only=False,
    ),
)

TOOL_SPEC_BY_NAME: dict[str, ToolSpec] = {spec.name: spec for spec in ALL_TOOL_SPECS}
ALL_TOOL_NAMES: frozenset[str] = frozenset(TOOL_SPEC_BY_NAME)
