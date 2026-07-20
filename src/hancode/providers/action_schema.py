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


def build_action_schema(
    *,
    phase: Phase,
    tool_catalog: tuple[ToolDescriptor, ...],
    interaction_enabled: bool = False,
) -> dict[str, object]:
    """Build a JSON Schema describing the actions a model may return."""
    tool_names = [tool.name for tool in tool_catalog]
    branches: list[dict[str, object]] = []

    branches.append(
        _tool_call_branch(phase, tool_names)
    )
    branches.append(
        _control_branch(phase, "finish_phase")
    )
    branches.append(
        _control_branch(phase, "final")
    )
    if interaction_enabled:
        branches.append(_ask_user_branch(phase))

    return {"oneOf": branches, "$schema": "https://json-schema.org/draft/2020-12/schema"}


def _tool_call_branch(
    phase: Phase, tool_names: list[str]
) -> dict[str, object]:
    return {
        "type": "object",
        "required": ["type", "phase", "reason", "tool_name", "args"],
        "properties": {
            "type": {"const": "tool_call"},
            "phase": {"const": phase.value},
            "reason": {"type": "string", "minLength": 1},
            "tool_name": {"enum": tool_names},
            "args": {"type": "object"},
        },
        "additionalProperties": False,
    }


def _control_branch(phase: Phase, action_type: str) -> dict[str, object]:
    return {
        "type": "object",
        "required": ["type", "phase", "reason", "tool_name", "args"],
        "properties": {
            "type": {"const": action_type},
            "phase": {"const": phase.value},
            "reason": {"type": "string", "minLength": 1},
            "tool_name": {"type": "null"},
            "args": {"type": "object", "maxProperties": 0},
        },
        "additionalProperties": False,
    }


def _ask_user_branch(phase: Phase) -> dict[str, object]:
    return {
        "type": "object",
        "required": ["type", "phase", "reason", "tool_name", "args"],
        "properties": {
            "type": {"const": "ask_user"},
            "phase": {"const": phase.value},
            "reason": {"type": "string", "minLength": 1},
            "tool_name": {"type": "null"},
            "args": {
                "type": "object",
                "required": ["question"],
                "properties": {"question": {"type": "string", "minLength": 1}},
                "additionalProperties": False,
            },
        },
        "additionalProperties": False,
    }
