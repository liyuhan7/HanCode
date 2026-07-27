"""Provider-facing action JSON Schema builder."""

from __future__ import annotations

from hancode.core.actions import Action, ActionType, ParseError, parse_action
from hancode.core.models import Phase
from hancode.providers.base import ToolDescriptor

__all__ = [
    "Action",
    "ActionType",
    "ParseError",
    "build_action_schema",
    "parse_action",
]


_WRITE_TOOLS = frozenset({"write_file", "edit_file"})


def build_action_schema(
    *,
    phase: Phase,
    tool_catalog: tuple[ToolDescriptor, ...],
    interaction_enabled: bool = False,
) -> dict[str, object]:
    """Build a JSON Schema describing the actions a model may return."""
    branches: list[dict[str, object]] = []

    branches.extend(_tool_call_branch(phase, tool) for tool in tool_catalog)
    branches.append(_control_branch(phase, "finish_phase"))

    if interaction_enabled:
        branches.append(_ask_user_branch(phase))

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "oneOf": branches,
    }


def _tool_call_branch(
    phase: Phase,
    tool: ToolDescriptor,
) -> dict[str, object]:
    required = ["type", "phase", "tool_name", "args", "reason"]

    if tool.name in _WRITE_TOOLS:
        reason_schema: dict[str, object] = {
            "type": "string",
            "minLength": 1,
            "maxLength": 1024,
        }
    else:
        reason_schema = {
            "oneOf": [
                {"type": "string", "minLength": 1, "maxLength": 1024},
                {"type": "null"},
            ]
        }

    return {
        "type": "object",
        "required": required,
        "properties": {
            "type": {"const": "tool_call"},
            "phase": {"const": phase.value},
            "reason": reason_schema,
            "tool_name": {"const": tool.name},
            "args": _provider_args_schema(phase, tool),
        },
        "additionalProperties": False,
    }


def _provider_args_schema(
    phase: Phase,
    tool: ToolDescriptor,
) -> dict[str, object]:
    schema = dict(tool.args_schema)

    # Real Agents must show the exact TEST command that will be approved.
    if phase is Phase.TEST and tool.name == "run_tests":
        raw_required = schema.get("required", ())
        if isinstance(raw_required, (list, tuple)):
            required = [item for item in raw_required if isinstance(item, str)]
        else:
            required = []
        if "command" not in required:
            required.append("command")
        schema["required"] = required

    return schema


_REASON_ONE_OF = {
    "oneOf": [
        {"type": "string", "minLength": 1, "maxLength": 1024},
        {"type": "null"},
    ]
}


def _control_branch(phase: Phase, action_type: str) -> dict[str, object]:
    return {
        "type": "object",
        "required": ["type", "phase", "tool_name", "args", "reason"],
        "properties": {
            "type": {"const": action_type},
            "phase": {"const": phase.value},
            "reason": dict(_REASON_ONE_OF),
            "tool_name": {"type": "null"},
            "args": {"type": "object", "maxProperties": 0},
        },
        "additionalProperties": False,
    }


def _ask_user_branch(phase: Phase) -> dict[str, object]:
    return {
        "type": "object",
        "required": ["type", "phase", "tool_name", "args", "reason"],
        "properties": {
            "type": {"const": "ask_user"},
            "phase": {"const": phase.value},
            "reason": dict(_REASON_ONE_OF),
            "tool_name": {"type": "null"},
            "args": {
                "type": "object",
                "required": ["question"],
                "properties": {
                    "question": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 2048,
                    }
                },
                "additionalProperties": False,
            },
        },
        "additionalProperties": False,
    }
