"""Deterministic prompt construction for provider requests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Mapping

from hancode.core.models import Phase
from hancode.policy.tool_policy import allowed_tools_for_phase
from hancode.providers.action_schema import build_action_schema
from hancode.providers.base import ToolDescriptor
from hancode.providers.prompt_contract import (
    BASE_SYSTEM_CONTRACT,
    INTERACTION_CONTRACT,
    PHASE_CONTRACTS,
)

__all__ = ["ChatMessage", "PromptBuilder", "ProviderPrompt", "build_prompt"]

_PROMPT_VERSION = "hancode-action-v2"
_ACTION_SCHEMA_ID = "hancode.action.v2"


def build_prompt(context: Mapping[str, object]) -> str:
    """Serialize structured runtime context without invoking a provider."""
    return json.dumps(context, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: str
    content: str


@dataclass(frozen=True, slots=True)
class ProviderPrompt:
    prompt_version: str
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
        embed_action_schema: bool = True,
    ) -> ProviderPrompt:
        phase = _require_phase(context)
        phase_catalog = _phase_tool_catalog(phase, tool_catalog)

        system_content = _build_system_message(
            phase,
            interaction_enabled=interaction_enabled,
        )
        action_schema = build_action_schema(
            phase=phase,
            tool_catalog=phase_catalog,
            interaction_enabled=interaction_enabled,
        )
        user_content = _build_user_message(
            context=context,
            tool_catalog=phase_catalog,
            phase=phase,
            interaction_enabled=interaction_enabled,
            embed_action_schema=embed_action_schema,
            action_schema=action_schema,
        )

        return ProviderPrompt(
            prompt_version=_PROMPT_VERSION,
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


def _build_system_message(
    phase: Phase,
    *,
    interaction_enabled: bool,
) -> str:
    parts = [BASE_SYSTEM_CONTRACT]

    if interaction_enabled:
        parts.append(INTERACTION_CONTRACT)

    parts.append(
        f"CURRENT PHASE\n\n"
        f"Phase: {phase.value}\n"
        f"{PHASE_CONTRACTS[phase]}"
    )

    return "\n\n".join(parts)


def _build_user_message(
    *,
    context: Mapping[str, object],
    tool_catalog: tuple[ToolDescriptor, ...],
    phase: Phase,
    interaction_enabled: bool,
    embed_action_schema: bool,
    action_schema: Mapping[str, object],
) -> str:
    safe_context = _sanitize_context(context)

    payload: dict[str, object] = {
        "prompt_version": _PROMPT_VERSION,
        "request": {
            "kind": "select_next_action",
            "phase": phase.value,
        },
        "task_context": safe_context,
        "available_tools": [
            {
                "name": tool.name,
                "description": tool.description,
                "args_schema": dict(tool.args_schema),
            }
            for tool in tool_catalog
        ],
        "response_contract": {
            "schema_id": _ACTION_SCHEMA_ID,
            "strict": not embed_action_schema,
        },
    }

    if embed_action_schema:
        payload["output_contract"] = dict(action_schema)

    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


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
        key: _sanitize_value(value)
        for key, value in context.items()
        if not _is_sensitive_key(str(key))
    }


def _sanitize_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            key: _sanitize_value(nested)
            for key, nested in value.items()
            if not _is_sensitive_key(str(key))
        }
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    return value


def _is_sensitive_key(key: str) -> bool:
    normalized = "".join(c for c in key.lower() if c.isalnum())
    return any(marker in normalized for marker in _SENSITIVE_CONTEXT_KEYS)
