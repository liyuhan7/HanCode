"""Deterministic prompt construction for provider requests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Mapping

from hancode.core.models import Phase
from hancode.policy.tool_policy import allowed_tools_for_phase
from hancode.providers.action_schema import build_action_schema
from hancode.providers.base import ToolDescriptor

__all__ = ["ChatMessage", "PromptBuilder", "ProviderPrompt", "build_prompt"]


def build_prompt(context: Mapping[str, object]) -> str:
    """Serialize structured runtime context without invoking a provider."""
    return json.dumps(context, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


_SYSTEM_PROMPT = """\
You are the action-selection component of HanCode.

Return exactly one structured Action.
Do not execute tools yourself.
Do not claim that a file was changed unless a tool result confirms it.
Use only the supplied tools.
Respect the current phase.
Never reveal credentials.
Never modify protected course files.
Do not wrap the response in Markdown.
Do not return explanations outside the Action object."""

_PHASE_INSTRUCTIONS: dict[Phase, str] = {
    Phase.SPEC: "Understand the assignment and produce SPEC.md. Do not modify source code.",
    Phase.PLAN: "Use SPEC.md to produce PLAN.md. Do not modify source code.",
    Phase.CODE: "Implement only what is required by SPEC.md and PLAN.md. Source writes require the normal tool and policy path.",
    Phase.TEST: "Run the configured test command. Do not edit protected tests to manufacture a pass.",
    Phase.REVIEW: "Review requirement coverage, test results and rollback risk.",
    Phase.DELIVER: "Produce the required review, knowledge and delivery artifacts.",
}


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: str
    content: str


@dataclass(frozen=True, slots=True)
class ProviderPrompt:
    messages: tuple[ChatMessage, ...]
    action_schema: Mapping[str, object]


class PromptBuilder:
    """Build deterministic system/user messages from runtime context."""

    def build(
        self,
        *,
        context: Mapping[str, object],
        tool_catalog: tuple[ToolDescriptor, ...],
        interaction_enabled: bool = False,
    ) -> ProviderPrompt:
        phase = _require_phase(context)
        phase_catalog = _phase_tool_catalog(phase, tool_catalog)

        system_content = _build_system_message(phase)
        user_content = _build_user_message(
            context=context,
            tool_catalog=phase_catalog,
            phase=phase,
            interaction_enabled=interaction_enabled,
        )

        action_schema = build_action_schema(
            phase=phase,
            tool_catalog=phase_catalog,
            interaction_enabled=interaction_enabled,
        )

        return ProviderPrompt(
            messages=(
                ChatMessage(role="system", content=system_content),
                ChatMessage(role="user", content=user_content),
            ),
            action_schema=action_schema,
        )


def _require_phase(context: Mapping[str, object]) -> Phase:
    raw_phase = context.get("phase")
    if not isinstance(raw_phase, str):
        raise ValueError("Context must contain a string 'phase' field.")
    try:
        return Phase(raw_phase)
    except ValueError as exc:
        raise ValueError(f"Unsupported phase: {raw_phase}") from exc


def _build_system_message(phase: Phase) -> str:
    instruction = _PHASE_INSTRUCTIONS.get(phase, "")
    return f"{_SYSTEM_PROMPT}\n\nCurrent phase: {phase.value}\n{instruction}"


def _build_user_message(
    *,
    context: Mapping[str, object],
    tool_catalog: tuple[ToolDescriptor, ...],
    phase: Phase,
    interaction_enabled: bool,
) -> str:
    safe_context = _sanitize_context(context)
    action_schema = build_action_schema(
        phase=phase,
        tool_catalog=tool_catalog,
        interaction_enabled=interaction_enabled,
    )
    payload: dict[str, object] = {
        "instruction": "Select the next single action.",
        "context": safe_context,
        "available_tools": [
            {
                "name": tool.name,
                "description": tool.description,
                "args_schema": dict(tool.args_schema),
            }
            for tool in tool_catalog
        ],
        "output_contract": action_schema,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _phase_tool_catalog(
    phase: Phase,
    tool_catalog: tuple[ToolDescriptor, ...],
) -> tuple[ToolDescriptor, ...]:
    allowed_names = set(allowed_tools_for_phase(phase))
    return tuple(tool for tool in tool_catalog if tool.name in allowed_names)


_SENSITIVE_CONTEXT_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "token",
        "secret",
        "password",
        "authorization",
        "credential",
        "private_key",
    }
)


def _sanitize_context(context: Mapping[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in context.items()
        if not _is_sensitive_key(str(key))
    }


def _is_sensitive_key(key: str) -> bool:
    normalized = "".join(c for c in key.lower() if c.isalnum())
    return any(marker in normalized for marker in _SENSITIVE_CONTEXT_KEYS)
