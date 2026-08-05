"""Provider capability negotiation.

The OpenAI-compatible ecosystem does not expose a single linear ladder of
"modes"; each provider supports an independent *combination* of request
capabilities (native tools, ``function.strict``, ``tool_choice=required``,
``parallel_tool_calls``, ``response_format`` and its ``json_schema`` variant).

This module models the action-output form as a
:class:`ProviderCapabilityProfile` and provides a *monotonic capability
removal* state machine: every transition strictly drops one capability
requirement, guaranteeing finite convergence between OpenAI, DeepSeek and
self-hosted OpenAI-compatible services.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Literal

from hancode.providers.base import ProviderActionMode
from hancode.providers.transport import ProviderResponse

__all__ = [
    "ActionEncoding",
    "CapabilityFailure",
    "ProviderCapabilityProfile",
    "classify_capability_failure",
    "initial_profile",
    "next_encoding_on_protocol_failure",
    "next_profile_for_feature",
    "profile_label",
    "ENCODING_RETRYABLE_ERROR_CODES",
]

ActionEncoding = Literal["native_tools", "json_schema", "json_object", "prompt_json"]

# --- Capability features a provider may reject -----------------------------

STRICT_TOOLS = "strict_tools"
PARALLEL_TOOL_CALLS = "parallel_tool_calls"
TOOL_CHOICE = "tool_choice"
NATIVE_TOOLS = "native_tools"
STRICT_JSON_SCHEMA = "strict_json_schema"
JSON_SCHEMA_TYPE = "json_schema_type"
RESPONSE_FORMAT = "response_format"


# Response protocol failures (HTTP 200 but the payload cannot be decoded into a
# valid action) that justify moving to the next action encoding. Terminal
# conditions such as refusals, content filtering, truncation, auth and rate
# limiting are intentionally excluded: retrying a different encoding will not
# help those.
ENCODING_RETRYABLE_ERROR_CODES = frozenset(
    {
        "provider_tool_call_missing",
        "provider_tool_call_count_invalid",
        "provider_choice_count_invalid",
        "provider_tool_arguments_invalid",
        "provider_tool_schema_invalid",
        "provider_empty_response",
        "provider_invalid_response",
        "provider_action_schema_invalid",
    }
)


@dataclass(frozen=True, slots=True)
class ProviderCapabilityProfile:
    """The exact request form used to elicit a structured action."""

    action_encoding: ActionEncoding
    strict_tools: bool = False
    tool_choice_required: bool = False
    disable_parallel_tool_calls: bool = False
    strict_json_schema: bool = False


@dataclass(frozen=True, slots=True)
class CapabilityFailure:
    feature: str
    confidence: Literal["exact", "strong"]
    reason_code: str


def initial_profile(mode: ProviderActionMode) -> ProviderCapabilityProfile:
    """Map a configured action mode to its starting capability profile."""
    if mode in {"auto", "native_tools_strict"}:
        return ProviderCapabilityProfile(
            action_encoding="native_tools",
            strict_tools=True,
            tool_choice_required=True,
            disable_parallel_tool_calls=True,
        )
    if mode == "native_tools":
        return ProviderCapabilityProfile(
            action_encoding="native_tools",
            strict_tools=False,
            tool_choice_required=True,
            disable_parallel_tool_calls=True,
        )
    if mode == "json_schema":
        return ProviderCapabilityProfile(
            action_encoding="json_schema",
            strict_json_schema=True,
        )
    if mode == "json_object":
        return ProviderCapabilityProfile(action_encoding="json_object")
    # Defensive default; config validation restricts mode to the set above.
    return ProviderCapabilityProfile(action_encoding="json_object")


def profile_label(profile: ProviderCapabilityProfile) -> str:
    """Stable, human-readable label for trace/fallback events."""
    if profile.action_encoding == "native_tools":
        if profile.strict_tools:
            return "native_tools_strict"
        if not profile.tool_choice_required:
            return "native_tools_basic"
        if not profile.disable_parallel_tool_calls:
            return "native_tools_no_parallel"
        return "native_tools"
    if profile.action_encoding == "json_schema":
        return "json_schema" if profile.strict_json_schema else "json_schema_relaxed"
    return profile.action_encoding


# --- Error classification --------------------------------------------------

_ACCEPTED_ERROR_CODES = frozenset(
    {
        "unsupported_parameter",
        "unsupported_value",
        "invalid_request_error",
        "unsupported_feature",
        "not_supported",
        "invalid_parameter",
        "invalid_function_parameters",
        "schema_validation_error",
    }
)


def _normalize_param(param: str) -> str:
    """Normalize array indices so ``tools[3].function.strict`` and
    ``tools.3.function.strict`` both collapse to ``tools.*.function.strict``."""
    normalized = re.sub(r"\[\s*\d+\s*\]", ".*", param)
    normalized = re.sub(r"(?<=\.)\d+(?=\.|$)", "*", normalized)
    normalized = re.sub(r"^\d+(?=\.|$)", "*", normalized)
    return normalized.strip()


def _feature_from_param(param: str) -> str | None:
    p = _normalize_param(param).lower()
    if not p:
        return None
    if "strict" in p and ("json_schema" in p or "response_format" in p):
        return STRICT_JSON_SCHEMA
    if "parallel_tool_calls" in p:
        return PARALLEL_TOOL_CALLS
    if "tool_choice" in p:
        return TOOL_CHOICE
    if "strict" in p and ("tool" in p or "function" in p):
        return STRICT_TOOLS
    if p == "strict":
        return STRICT_TOOLS
    if "response_format.type" in p or "response_format.json_schema" in p or p == "json_schema":
        return JSON_SCHEMA_TYPE
    if p == "response_format" or p.startswith("response_format"):
        return RESPONSE_FORMAT
    if p == "tools" or p.startswith("tools"):
        return NATIVE_TOOLS
    return None


def _feature_from_message(message: str) -> str | None:
    m = message.lower()
    if not m:
        return None
    if "parallel_tool_calls" in m or "parallel tool call" in m:
        return PARALLEL_TOOL_CALLS
    if "tool_choice" in m or "tool choice" in m:
        return TOOL_CHOICE
    if "strict" in m and ("json schema" in m or "json_schema" in m or "response_format" in m):
        return STRICT_JSON_SCHEMA
    if "strict" in m and ("function" in m or "tool" in m):
        return STRICT_TOOLS
    if "json schema" in m or "json_schema" in m:
        return JSON_SCHEMA_TYPE
    if "response_format" in m or "response format" in m:
        return RESPONSE_FORMAT
    if "function calling" in m or "tool call" in m or "tools" in m:
        return NATIVE_TOOLS
    return None


def classify_capability_failure(response: ProviderResponse) -> CapabilityFailure | None:
    """Classify a rejection into a capability feature.

    Only ``exact`` (param-derived) and ``strong`` (message-derived) results
    are returned; anything unrecognized yields ``None`` so callers can
    fail-closed instead of guessing.
    """
    body = response.json_body
    error: dict[str, object] = {}
    if isinstance(body, dict):
        raw_error = body.get("error")
        if isinstance(raw_error, dict):
            error = raw_error

    code = error.get("code")
    err_type = error.get("type")
    param = error.get("param")
    message = error.get("message")

    code_str = str(code).lower() if isinstance(code, str) else ""
    type_str = str(err_type).lower() if isinstance(err_type, str) else ""
    recognized_code = (
        code_str in _ACCEPTED_ERROR_CODES
        or type_str in _ACCEPTED_ERROR_CODES
        or response.status_code == 422
    )

    if isinstance(param, str) and param.strip():
        feature = _feature_from_param(param)
        if feature is not None and (recognized_code or response.status_code == 400):
            return CapabilityFailure(feature=feature, confidence="exact", reason_code=code_str or type_str or "capability_unsupported")

    if isinstance(message, str) and message.strip() and (recognized_code or response.status_code in (400, 422)):
        feature = _feature_from_message(message)
        if feature is not None:
            return CapabilityFailure(feature=feature, confidence="strong", reason_code=code_str or type_str or "capability_unsupported")

    return None


# --- State-machine transitions ---------------------------------------------

_JSON_SCHEMA_STRICT = ProviderCapabilityProfile(
    action_encoding="json_schema", strict_json_schema=True
)
_JSON_OBJECT = ProviderCapabilityProfile(action_encoding="json_object")
_PROMPT_JSON = ProviderCapabilityProfile(action_encoding="prompt_json")


def next_profile_for_feature(
    profile: ProviderCapabilityProfile, feature: str
) -> ProviderCapabilityProfile | None:
    """Return the next profile after a capability rejection, or ``None`` to
    fail-closed when the rejected feature is not applicable to the current
    request form. Each transition removes exactly one capability requirement."""
    enc = profile.action_encoding

    if enc == "native_tools":
        if feature == STRICT_TOOLS and profile.strict_tools:
            return replace(profile, strict_tools=False)
        if feature == PARALLEL_TOOL_CALLS and profile.disable_parallel_tool_calls:
            return replace(profile, disable_parallel_tool_calls=False)
        if feature == TOOL_CHOICE and profile.tool_choice_required:
            return replace(profile, tool_choice_required=False)
        if feature == NATIVE_TOOLS:
            # A coarse "tools" rejection on a strict request may only mean the
            # strict tool definition was refused; try non-strict native first
            # before abandoning the native family entirely (P0-6).
            if profile.strict_tools:
                return replace(profile, strict_tools=False)
            return _JSON_SCHEMA_STRICT
        return None

    if enc == "json_schema":
        if feature == STRICT_JSON_SCHEMA and profile.strict_json_schema:
            return replace(profile, strict_json_schema=False)
        if feature == JSON_SCHEMA_TYPE:
            return _JSON_OBJECT
        if feature == RESPONSE_FORMAT:
            return _JSON_OBJECT
        return None

    if enc == "json_object":
        if feature in (RESPONSE_FORMAT, JSON_SCHEMA_TYPE):
            return _PROMPT_JSON
        return None

    # prompt_json is terminal: it sends no capability-bearing parameters.
    return None


def next_encoding_on_protocol_failure(
    profile: ProviderCapabilityProfile,
) -> ProviderCapabilityProfile | None:
    """Advance to the next action encoding after a decode/protocol failure on
    an accepted (HTTP 200) response."""
    enc = profile.action_encoding
    if enc == "native_tools":
        return _JSON_SCHEMA_STRICT
    if enc == "json_schema":
        return _JSON_OBJECT
    if enc == "json_object":
        return _PROMPT_JSON
    return None
