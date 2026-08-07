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
            "available in the supplied context. When the same path was already "
            "read, search task runtime memory first; repeat the read only when "
            "the evidence is stale, incomplete, or the workspace may have changed. "
            "Do not use it for protected credentials."
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
        name="memory_read",
        description=(
            "Read a line range from one persisted memory blob in the current task. "
            "Use a memory_id returned by memory_search. Stale history is readable "
            "but explicitly non-authoritative; do not repeat the same memory_id and "
            "line range unless the previous output was incomplete."
        ),
        args_schema={
            "type": "object",
            "properties": {
                "memory_id": {
                    "type": "string",
                    "pattern": "^mem-[0-9]{6,}$",
                },
                "start_line": {"type": "integer", "minimum": 1, "default": 1},
                "end_line": {"type": "integer", "minimum": 1, "default": 200},
                "start_byte_offset": {
                    "type": "integer",
                    "minimum": 0,
                    "default": 0,
                },
            },
            "required": ["memory_id"],
            "additionalProperties": False,
        },
        allowed_phases=frozenset(Phase),
        read_only=True,
    ),
    ToolSpec(
        name="memory_search",
        description=(
            "Search tool-call summaries, recorded file paths, and verified "
            "file-content blobs in task runtime memory. Internal decisions such "
            "as test_remediation or test_failure are NOT stored here; read them "
            "via read_file at .hancode/tasks/<task>/test_remediation.json. The "
            "query argument is required; use path only as an optional filter."
        ),
        args_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1, "pattern": "\\S"},
                "path": {
                    "type": "string",
                    "minLength": 1,
                    "pattern": "^(?!/)(?!.*\\\\)(?!.*(?:^|/)\\.{1,2}(?:/|$))(?!.*//).+$",
                },
                "phase": {"type": "string", "enum": [phase.value for phase in Phase]},
                "include_stale": {"type": "boolean", "default": False},
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 20,
                    "default": 5,
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        allowed_phases=frozenset(Phase),
        read_only=True,
    ),
    ToolSpec(
        name="list_files",
        description=(
            "List project files visible to the current workspace policy. "
            "Use it to discover project structure only when no sufficient listing "
            "for the path is available in the supplied context. If the path was "
            "already listed, search task runtime memory first; repeat it only when "
            "the listing may be stale or a narrower scope is needed."
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
        name="record_requirements",
        description=(
            "Record structured requirement understanding and render SPEC.md. "
            "Each requirement carries the original source text, the student's "
            "own understanding, acceptance evidence, priority, and whether it "
            "is a core requirement."
        ),
        args_schema={
            "type": "object",
            "properties": {
                "goal": {"type": "string", "minLength": 1},
                "requirements": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": [
                            "source_text",
                            "student_understanding",
                            "acceptance_evidence",
                        ],
                        "properties": {
                            "source_text": {"type": "string", "minLength": 1},
                            "student_understanding": {"type": "string", "minLength": 1},
                            "acceptance_evidence": {"type": "string"},
                            "priority": {"type": "string"},
                            "is_core": {"type": "boolean"},
                        },
                        "additionalProperties": False,
                    },
                },
                "boundaries": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "constraints": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "assumptions": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["goal", "requirements"],
            "additionalProperties": False,
        },
        allowed_phases=frozenset({Phase.SPEC}),
        read_only=False,
    ),
    ToolSpec(
        name="record_plan",
        description=(
            "Record structured plan evidence (alternatives, the final choice "
            "with reasons, and concrete plan steps) and render PLAN.md."
        ),
        args_schema={
            "type": "object",
            "properties": {
                "decisions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["chosen_option", "rationale"],
                        "properties": {
                            "chosen_option": {"type": "string", "minLength": 1},
                            "rationale": {"type": "string", "minLength": 1},
                            "rejected_options": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "requirement_refs": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "additionalProperties": False,
                    },
                },
                "plan_steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["description"],
                        "properties": {
                            "description": {"type": "string", "minLength": 1},
                            "verification": {"type": "string"},
                            "requirement_refs": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "planned_paths": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["decisions", "plan_steps"],
            "additionalProperties": False,
        },
        allowed_phases=frozenset({Phase.PLAN}),
        read_only=False,
    ),
    ToolSpec(
        name="record_review",
        description=(
            "Record structured review evidence. For tasks with structured "
            "learning evidence, use requirement_reviews and "
            "delivery_recommendation; legacy tasks use requirements and risks."
        ),
        args_schema={
            "oneOf": [
                {
                    "type": "object",
                    "properties": {
                        "requirements": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["requirement_id", "status", "evidence"],
                                "properties": {
                                    "requirement_id": {
                                        "type": "string",
                                        "minLength": 1,
                                    },
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
                                    "is_core": {"type": "boolean"},
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
                {
                    "type": "object",
                    "properties": {
                        "requirement_reviews": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": [
                                    "requirement_id",
                                    "change_refs",
                                    "test_refs",
                                    "status",
                                    "risk",
                                ],
                                "properties": {
                                    "requirement_id": {
                                        "type": "string",
                                        "minLength": 1,
                                    },
                                    "change_refs": {
                                        "type": "array",
                                        "items": {
                                            "type": "string",
                                            "pattern": "^C-[0-9]+$",
                                            "description": (
                                                "Existing change evidence ID from "
                                                "sections.learning_evidence.changes; "
                                                "never a file path or memory ID."
                                            ),
                                        },
                                    },
                                    "test_refs": {
                                        "type": "array",
                                        "items": {
                                            "type": "string",
                                            "pattern": "^T-[0-9]+$",
                                            "description": (
                                                "Existing test attempt ID from "
                                                "sections.learning_evidence.test_attempts; "
                                                "never a command, path, or memory ID."
                                            ),
                                        },
                                    },
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
                                    "risk": {
                                        "oneOf": [
                                            {"type": "string"},
                                            {"type": "null"},
                                        ],
                                    },
                                },
                                "additionalProperties": False,
                            },
                        },
                        "quality_findings": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "untested_risks": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "plan_deviations": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "delivery_recommendation": {
                            "type": "string",
                            "minLength": 1,
                        },
                    },
                    "required": ["requirement_reviews", "delivery_recommendation"],
                    "additionalProperties": False,
                },
            ],
        },
        allowed_phases=frozenset({Phase.REVIEW}),
        read_only=False,
    ),
    ToolSpec(
        name="record_remediation",
        description=(
            "Record one structured response to the latest active test failure. "
            "The failure digest must match exactly; test commands are registered "
            "separately with record_test_strategy."
        ),
        args_schema={
            "type": "object",
            "properties": {
                "failure_digest": {
                    "type": "string",
                    "pattern": "^[0-9a-f]{64}$",
                },
                "kind": {
                    "type": "string",
                    "enum": [
                        "modify_source",
                        "modify_test",
                        "replace_test_strategy",
                        "rerun_for_diagnosis",
                        "request_input",
                        "rollback",
                    ],
                },
                "diagnosis": {"type": "string", "minLength": 1, "pattern": "\\S"},
                "planned_paths": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1, "pattern": "\\S"},
                },
                "question": {
                    "oneOf": [
                        {"type": "string", "minLength": 1, "maxLength": 1000, "pattern": "\\S"},
                        {"type": "null"},
                    ]
                },
            },
            "required": [
                "failure_digest",
                "kind",
                "diagnosis",
                "planned_paths",
                "question",
            ],
            "additionalProperties": False,
        },
        # CODE is allowed so an agent can re-declare remediation scope (planned
        # paths) when a cross-file fix becomes necessary, instead of being
        # locked out by remediation_planned_path_required.
        allowed_phases=frozenset({Phase.REVIEW, Phase.CODE}),
        read_only=False,
    ),
    ToolSpec(
        name="record_knowledge",
        description=(
            "Record structured knowledge items. Legacy tasks use items; tasks "
            "with structured learning evidence use grounded knowledge cards."
        ),
        args_schema={
            "oneOf": [
                {
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
                {
                    "type": "object",
                    "properties": {
                        "cards": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": [
                                    "category",
                                    "problem",
                                    "context",
                                    "principle",
                                    "solution",
                                    "evidence_refs",
                                    "applicable_when",
                                    "not_applicable_when",
                                    "common_mistake",
                                    "transfer_example",
                                ],
                                "properties": {
                                    "category": {"type": "string", "minLength": 1},
                                    "problem": {"type": "string", "minLength": 1},
                                    "context": {"type": "string", "minLength": 1},
                                    "principle": {"type": "string", "minLength": 1},
                                    "solution": {"type": "string", "minLength": 1},
                                    "evidence_refs": {
                                        "type": "array",
                                        "minItems": 1,
                                        "items": {
                                            "type": "string",
                                            "pattern": "^(R|D|P|C|T|F|REC)-[0-9]+$",
                                            "description": (
                                                "Existing ID from sections.learning_evidence; "
                                                "never a file path, hash, trace event, or "
                                                "memory ID."
                                            ),
                                        },
                                    },
                                    "applicable_when": {
                                        "type": "string",
                                        "minLength": 1,
                                    },
                                    "not_applicable_when": {
                                        "type": "string",
                                        "minLength": 1,
                                    },
                                    "common_mistake": {
                                        "type": "string",
                                        "minLength": 1,
                                    },
                                    "transfer_example": {
                                        "type": "string",
                                        "minLength": 1,
                                    },
                                },
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["cards"],
                    "additionalProperties": False,
                },
            ],
        },
        allowed_phases=frozenset({Phase.DELIVER}),
        read_only=False,
    ),
)

TOOL_SPEC_BY_NAME: dict[str, ToolSpec] = {spec.name: spec for spec in ALL_TOOL_SPECS}
ALL_TOOL_NAMES: frozenset[str] = frozenset(TOOL_SPEC_BY_NAME)
