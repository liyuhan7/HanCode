"""OpenAI-Compatible provider adapter."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Mapping

from hancode.core.actions import Action, ParseError
from hancode.core.errors import StructuredError
from hancode.core.models import Phase
from hancode.providers.base import (
    ProviderActionMode,
    ProviderEvent,
    ProviderEventSink,
    ProviderToolDefinition,
    ToolDescriptor,
    build_provider_tool_definitions,
)
from hancode.providers.capability import (
    ENCODING_RETRYABLE_ERROR_CODES,
    ProviderCapabilityProfile,
    classify_capability_failure,
    initial_profile,
    next_encoding_on_protocol_failure,
    next_profile_for_feature,
    profile_label,
)
from hancode.providers.errors import ProviderError
from hancode.providers.prompt_builder import PromptBuilder, ProviderPrompt
from hancode.providers.strict_schema import (
    StrictSchemaProjection,
    StrictSchemaValidationError,
)
from hancode.core.schema_validator import (
    SchemaValidationError,
    SchemaViolation,
    validate_instance,
)
from hancode.providers.action_normalizer import normalize_provider_arguments
from hancode.policy.tool_policy import allowed_tools_for_phase
from hancode.providers.transport import (
    ProviderRequest,
    ProviderResponse,
    ProviderTransport,
    ProviderTransportNetworkError,
    ProviderTransportResponseTooLarge,
    ProviderTransportTimeout,
    Sleeper,
)

__all__ = ["OpenAICompatibleProvider", "decode_response"]


_CODE_FENCE_RE = re.compile(
    r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", re.DOTALL
)

_USER_AGENT = "hancode/0.1.1"


@dataclass(frozen=True, slots=True)
class _TransportFailure:
    error_code: str
    message: str
    retryable: bool


@dataclass(frozen=True, slots=True)
class _ProfileDowngrade(Exception):
    """Raised internally to request a monotonic capability-profile transition."""

    next_profile: ProviderCapabilityProfile
    reason_code: str


class OpenAICompatibleProvider:
    """Provider adapter that converts context to HTTP requests and responses to Actions."""

    def __init__(
        self,
        *,
        model_name: str,
        base_url: str,
        credential: str,
        timeout_seconds: int,
        max_retries: int,
        max_output_tokens: int,
        max_response_bytes: int,
        response_mode: ProviderActionMode,
        prompt_builder: PromptBuilder,
        transport: ProviderTransport,
        sleeper: Sleeper,
        tool_catalog: tuple[ToolDescriptor, ...],
        interaction_enabled: bool = False,
        event_sink: ProviderEventSink | None = None,
    ) -> None:
        self._model_name = model_name
        self._base_url = base_url.rstrip("/")
        self._credential = credential
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._max_output_tokens = max_output_tokens
        self._max_response_bytes = max_response_bytes
        self._response_mode = response_mode
        self._prompt_builder = prompt_builder
        self._transport = transport
        self._sleeper = sleeper
        self._tool_catalog = tool_catalog
        self._tool_definitions = build_provider_tool_definitions(
            tool_catalog, interaction_enabled=interaction_enabled
        )
        self._interaction_enabled = interaction_enabled
        self._event_sink = event_sink
        self._auto = self._response_mode == "auto"
        self._effective_profile: ProviderCapabilityProfile | None = None
        self._emitted_fallbacks: set[tuple[str, str]] = set()
        # Bound the negotiation so a misbehaving provider cannot loop forever.
        self._max_transitions = 12

    def next_action(self, context: Mapping[str, object]) -> dict[str, object]:
        phase = _context_phase(context)
        profile = self._effective_profile or initial_profile(self._response_mode)
        visited: set[str] = set()
        # Per-encoding protocol retry budget (HTTP 200 but undecodable action).
        encoding_attempts = 0
        transitions = 0
        while True:
            try:
                action = self._request_action(context, phase, profile)
                self._effective_profile = profile
                return action
            except _ProfileDowngrade as downgrade:
                transitions += 1
                if transitions > self._max_transitions:
                    raise
                self._emit_fallback(phase, profile, downgrade)
                profile = downgrade.next_profile
                encoding_attempts = 0
            except ProviderError as exc:
                # HTTP 200 protocol failures drive encoding transitions in auto
                # mode: retry the same encoding once, then advance (P0-4).
                if not (
                    self._auto
                    and exc.structured_error.error_code in ENCODING_RETRYABLE_ERROR_CODES
                ):
                    raise
                if encoding_attempts < 1:
                    encoding_attempts += 1
                    continue
                next_profile = next_encoding_on_protocol_failure(profile)
                if next_profile is None:
                    raise
                label = profile_label(profile)
                if label in visited:
                    raise
                visited.add(label)
                transitions += 1
                if transitions > self._max_transitions:
                    raise
                self._emit_fallback(
                    phase,
                    profile,
                    _ProfileDowngrade(
                        next_profile=next_profile,
                        reason_code=exc.structured_error.error_code,
                    ),
                )
                profile = next_profile
                encoding_attempts = 0

    def _request_action(
        self,
        context: Mapping[str, object],
        phase: Phase,
        profile: ProviderCapabilityProfile,
    ) -> dict[str, object]:
        encoding = profile.action_encoding
        is_native = encoding == "native_tools"
        # json_object and prompt_json both rely on an embedded action contract
        # in the user message; prompt_json additionally sends no response_format.
        embed_action_schema = encoding in {"json_object", "prompt_json"}
        prompt = self._prompt_builder.build(
            context=context,
            tool_catalog=self._tool_catalog,
            interaction_enabled=self._interaction_enabled,
            embed_action_schema=embed_action_schema,
            native_tool_calling=is_native,
        )
        strict_projection = (
            StrictSchemaProjection.project(prompt.action_schema)
            if encoding == "json_schema" and profile.strict_json_schema
            else None
        )
        tool_definitions = self._tool_definitions_for_phase(phase)
        strict_tool_projections = (
            {
                definition.name: definition.projection
                for definition in tool_definitions
            }
            if is_native and profile.strict_tools
            else {}
        )
        request = self._build_request(
            prompt,
            profile=profile,
            strict_projection=strict_projection,
            strict_tool_projections=strict_tool_projections,
            tool_definitions=tool_definitions,
        )
        response = self._send_with_retry(
            request,
            phase,
            allow_auto_capability_error=self._auto,
        )
        if response.status_code >= 400:
            if self._auto:
                failure = classify_capability_failure(response)
                if failure is not None:
                    next_profile = next_profile_for_feature(profile, failure.feature)
                    if next_profile is not None:
                        raise _ProfileDowngrade(
                            next_profile=next_profile,
                            reason_code=failure.reason_code,
                        )
            raise _transport_failure_error(
                _classify_transport_failure(response.status_code), phase.value
            )
        if is_native:
            return _decode_native_tool_call(
                response,
                phase=phase,
                max_response_bytes=self._max_response_bytes,
                tool_definitions=tool_definitions,
                strict_tool_projections=strict_tool_projections,
            )
        raw_action = decode_response(
            response,
            max_response_bytes=self._max_response_bytes,
            phase=phase.value,
        )
        if strict_projection is not None:
            try:
                raw_action = strict_projection.normalize(raw_action)
            except StrictSchemaValidationError:
                raise _provider_error(
                    "provider_action_schema_invalid",
                    "Provider action does not match the expected schema.",
                    phase=phase.value,
                    protocol_retryable=True,
                ) from None
        violations = validate_instance(raw_action, prompt.action_schema)
        if violations:
            raise _provider_error(
                "provider_action_schema_invalid",
                _schema_violation_message(violations),
                phase=phase.value,
                protocol_retryable=True,
            )
        return raw_action

    def _tool_definitions_for_phase(
        self, phase: Phase
    ) -> tuple[ProviderToolDefinition, ...]:
        allowed = set(allowed_tools_for_phase(phase)) | {"finish_phase"}
        if self._interaction_enabled:
            allowed.add("ask_user")
        return tuple(
            definition for definition in self._tool_definitions if definition.name in allowed
        )

    def _build_request(
        self,
        prompt: ProviderPrompt,
        *,
        profile: ProviderCapabilityProfile,
        strict_projection: StrictSchemaProjection | None = None,
        strict_tool_projections: Mapping[str, StrictSchemaProjection] | None = None,
        tool_definitions: tuple[ProviderToolDefinition, ...] | None = None,
    ) -> ProviderRequest:
        messages = [
            {"role": msg.role, "content": msg.content}
            for msg in prompt.messages
        ]
        encoding = profile.action_encoding

        if encoding == "json_schema":
            json_schema: dict[str, object] = {
                "name": "hancode_action",
                "schema": dict(
                    strict_projection.provider_schema
                    if strict_projection is not None
                    else prompt.action_schema
                ),
            }
            if profile.strict_json_schema:
                json_schema["strict"] = True
            response_format: dict[str, object] | None = {
                "type": "json_schema",
                "json_schema": json_schema,
            }
        elif encoding == "json_object":
            response_format = {
                "type": "json_object",
            }
        else:
            # native_tools and prompt_json send no response_format.
            response_format = None

        body: dict[str, object] = {
            "model": self._model_name,
            "messages": messages,
            "temperature": 0,
            "max_tokens": self._max_output_tokens,
        }
        if response_format is not None:
            body["response_format"] = response_format
        if encoding == "native_tools":
            body["tools"] = [
                _native_tool_definition(
                    definition,
                    strict=profile.strict_tools,
                    strict_projection=(strict_tool_projections or {}).get(definition.name),
                )
                for definition in (tool_definitions or self._tool_definitions)
            ]
            if profile.tool_choice_required:
                body["tool_choice"] = "required"
            if profile.disable_parallel_tool_calls:
                body["parallel_tool_calls"] = False
        headers = {
            "Authorization": f"Bearer {self._credential}",
            "Content-Type": "application/json",
            "User-Agent": _USER_AGENT,
        }
        return ProviderRequest(
            method="POST",
            url=f"{self._base_url}/chat/completions",
            headers=headers,
            json_body=body,
            timeout_seconds=self._timeout_seconds,
            max_response_bytes=self._max_response_bytes,
        )

    def _emit_fallback(
        self,
        phase: Phase,
        from_profile: ProviderCapabilityProfile,
        downgrade: _ProfileDowngrade,
    ) -> None:
        from_label = profile_label(from_profile)
        to_label = profile_label(downgrade.next_profile)
        if self._event_sink is None:
            return
        key = (from_label, to_label)
        if key in self._emitted_fallbacks:
            return
        # Trace emission is best-effort: a failing sink must not abort an
        # otherwise successful capability negotiation (P1-3).
        try:
            self._event_sink.emit(ProviderEvent(
                kind="mode_fallback",
                phase=phase,
                from_mode=from_label,
                to_mode=to_label,
                reason_code=downgrade.reason_code,
            ))
        except Exception:
            return
        self._emitted_fallbacks.add(key)

    def _send_with_retry(
        self,
        request: ProviderRequest,
        phase: Phase,
        *,
        allow_auto_capability_error: bool = False,
    ) -> ProviderResponse:
        last_failure: _TransportFailure | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._transport.send(request)
            except ProviderTransportTimeout:
                failure = _TransportFailure(
                    "provider_timeout",
                    "The provider request timed out.",
                    retryable=True,
                )
                last_failure = failure
                if attempt < self._max_retries:
                    self._sleeper(2 ** attempt)
                    continue
                raise _transport_failure_error(failure, phase.value) from None
            except ProviderTransportNetworkError:
                failure = _network_failure()
                last_failure = failure
                if attempt < self._max_retries:
                    self._sleeper(2 ** attempt)
                    continue
                raise _transport_failure_error(failure, phase.value) from None
            except ProviderTransportResponseTooLarge:
                raise _provider_error(
                    "provider_response_too_large",
                    "Provider response exceeded the configured size limit.",
                    phase=phase.value,
                ) from None

            if response.status_code < 400:
                return response
            if allow_auto_capability_error and response.status_code == 400:
                return response

            failure = _classify_transport_failure(response.status_code)
            last_failure = failure
            if not failure.retryable or attempt >= self._max_retries:
                raise _transport_failure_error(failure, phase.value) from None
            self._sleeper(2 ** attempt)

        assert last_failure is not None
        raise _transport_failure_error(last_failure, phase.value)


def _classify_transport_failure(status_code: int) -> _TransportFailure:
    if status_code == 400:
        return _TransportFailure(
            "provider_request_rejected",
            "The provider rejected the request.",
            retryable=False,
        )
    if status_code in (401, 403):
        return _TransportFailure(
            "provider_auth_failed",
            "Provider authentication failed.",
            retryable=False,
        )
    if status_code == 404:
        return _TransportFailure(
            "provider_endpoint_not_found",
            "The provider endpoint was not found.",
            retryable=False,
        )
    if status_code == 408:
        return _TransportFailure(
            "provider_timeout",
            "The provider request timed out.",
            retryable=True,
        )
    if status_code == 429:
        return _TransportFailure(
            "provider_rate_limited",
            "The provider rate limited the request.",
            retryable=True,
        )
    if 500 <= status_code < 600:
        return _TransportFailure(
            "provider_server_error",
            "The provider returned a server error.",
            retryable=True,
        )
    return _TransportFailure(
        "provider_request_rejected",
        f"The provider returned an unexpected status: {status_code}.",
        retryable=False,
    )


def _network_failure() -> _TransportFailure:
    return _TransportFailure(
        "provider_network_error",
        "A network error occurred while contacting the provider.",
        retryable=True,
    )


def _provider_error(
    error_code: str,
    message: str,
    *,
    phase: str = "spec",
    protocol_retryable: bool = False,
) -> ProviderError:
    return ProviderError(
        StructuredError(
            error_code=error_code,
            message=message,
            phase=phase,
            denied_rule="provider_available",
            suggested_fix="Check provider configuration and retry.",
        ),
        protocol_retryable=protocol_retryable,
    )


def _schema_violation_message(violations: tuple[SchemaViolation, ...]) -> str:
    """Return bounded schema diagnostics without echoing provider-supplied values."""
    summaries: list[str] = []
    for violation in violations[:3]:
        path = ".".join(str(part) for part in violation.path) or "$"
        summaries.append(f"{path} ({violation.validator})")
    diagnostic = "; ".join(summaries)
    if len(violations) > len(summaries):
        diagnostic += "; additional violations omitted"
    return (
        "Provider action does not match the expected schema. "
        f"Safe validation details: {diagnostic}."
    )


def _transport_failure_error(failure: _TransportFailure, phase: str) -> ProviderError:
    return _provider_error(failure.error_code, failure.message, phase=phase)


def decode_response(
    response: ProviderResponse,
    *,
    max_response_bytes: int,
    phase: str = "spec",
) -> dict[str, object]:
    """Extract an Action dict from an OpenAI-compatible HTTP response."""
    if response.body_size > max_response_bytes:
        raise ProviderError(
            StructuredError(
                error_code="provider_response_too_large",
                message="Provider response exceeded the configured size limit.",
                phase=phase,
                denied_rule="provider_response_size_limit",
                suggested_fix="Reduce the response size or increase provider_max_response_bytes.",
            ),
        )

    body = response.json_body
    if not isinstance(body, dict):
        raise _invalid_response("Provider response body is not a JSON object.", phase)

    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise _invalid_response("Provider response has no choices.", phase)

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise _invalid_response("Provider response choice is not an object.", phase)

    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise _invalid_response("Provider response has no message.", phase)

    parsed = message.get("parsed")
    if parsed is not None:
        if isinstance(parsed, dict):
            return parsed
        raise _invalid_response(
            "Provider response message.parsed is not an object.", phase
        )

    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise _empty_response("Provider response message.content is empty.", phase)

    return _parse_content(content, phase)


def _parse_content(content: str, phase: str) -> dict[str, object]:
    stripped = content.strip()
    fence_match = _CODE_FENCE_RE.match(stripped)
    if fence_match is not None:
        stripped = fence_match.group(1).strip()

    try:
        decoded = json.loads(stripped)
    except json.JSONDecodeError:
        raise _invalid_response(
            "Provider response content is not valid JSON.", phase
        ) from None

    if not isinstance(decoded, dict):
        raise _invalid_response("Provider response content is not a JSON object.", phase)

    return decoded


def _invalid_response(message: str, phase: str = "spec") -> ProviderError:
    return ProviderError(
        StructuredError(
            error_code="provider_invalid_response",
            message=message,
            phase=phase,
            denied_rule="provider_response_valid",
            suggested_fix="Check the provider model configuration and response format.",
        ),
        protocol_retryable=True,
    )


def _empty_response(message: str, phase: str = "spec") -> ProviderError:
    return ProviderError(
        StructuredError(
            error_code="provider_empty_response",
            message=message,
            phase=phase,
            denied_rule="provider_response_valid",
            suggested_fix="Check the provider model configuration and response format.",
        ),
        protocol_retryable=True,
    )


def _native_tool_definition(
    definition: ProviderToolDefinition,
    *,
    strict: bool,
    strict_projection: StrictSchemaProjection | None,
) -> dict[str, object]:
    function: dict[str, object] = {
        "name": definition.name,
        "description": definition.description,
        "parameters": dict(
            strict_projection.provider_schema
            if strict_projection is not None
            else definition.request_schema
        ),
    }
    if strict:
        function["strict"] = True
    return {"type": "function", "function": function}


def _decode_native_tool_call(
    response: ProviderResponse,
    *,
    phase: Phase,
    max_response_bytes: int,
    tool_definitions: tuple[ProviderToolDefinition, ...],
    strict_tool_projections: Mapping[str, StrictSchemaProjection],
) -> dict[str, object]:
    if response.body_size > max_response_bytes:
        raise _provider_error(
            "provider_response_too_large",
            "Provider response exceeded the configured size limit.",
            phase=phase.value,
        )
    body = response.json_body
    if not isinstance(body, dict):
        raise _native_protocol_error(
            "provider_tool_call_missing", "Provider response body is not an object.", phase.value
        )
    choices = body.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        raise _native_protocol_error(
            "provider_choice_count_invalid", "Provider response must contain exactly one choice.", phase.value
        )
    choice = choices[0]
    finish_reason = choice.get("finish_reason")
    if finish_reason == "content_filter":
        raise _provider_error(
            "provider_content_filtered",
            "Provider response was filtered.",
            phase=phase.value,
        )
    if finish_reason == "length":
        raise _provider_error(
            "provider_output_truncated",
            "Provider response was truncated.",
            phase=phase.value,
        )
    message = choice.get("message")
    if not isinstance(message, dict):
        raise _native_protocol_error(
            "provider_tool_call_missing", "Provider response has no message.", phase.value
        )
    refusal = message.get("refusal")
    if isinstance(refusal, str) and refusal.strip():
        raise _provider_error(
            "provider_refusal",
            "Provider refused the requested tool call.",
            phase=phase.value,
        )
    tool_calls = message.get("tool_calls")
    if not isinstance(tool_calls, list):
        raise _native_protocol_error(
            "provider_tool_call_missing", "Provider response has no tool calls.", phase.value
        )
    if len(tool_calls) != 1:
        raise _native_protocol_error(
            "provider_tool_call_count_invalid", "Provider response must contain exactly one tool call.", phase.value
        )
    tool_call = tool_calls[0]
    if not isinstance(tool_call, dict) or tool_call.get("type") != "function":
        raise _native_protocol_error(
            "provider_tool_call_count_invalid", "Provider tool call is invalid.", phase.value
        )
    function = tool_call.get("function")
    if not isinstance(function, dict):
        raise _native_protocol_error(
            "provider_tool_call_arguments_invalid", "Provider tool call has no function.", phase.value
        )
    name = function.get("name")
    known_names = {definition.name for definition in tool_definitions}
    if not isinstance(name, str) or name not in known_names:
        raise _provider_error("provider_tool_name_invalid", "Provider returned an unknown tool.", phase=phase.value)
    encoded_arguments = function.get("arguments")
    if not isinstance(encoded_arguments, str):
        raise _native_protocol_error(
            "provider_tool_arguments_invalid", "Provider tool arguments are not JSON text.", phase.value
        )
    try:
        decoded_arguments = json.loads(encoded_arguments)
    except json.JSONDecodeError:
        raise _native_protocol_error(
            "provider_tool_arguments_invalid", "Provider tool arguments are invalid JSON.", phase.value
        ) from None
    if not isinstance(decoded_arguments, dict):
        raise _native_protocol_error(
            "provider_tool_arguments_invalid", "Provider tool arguments are not an object.", phase.value
        )
    definition = next(item for item in tool_definitions if item.name == name)
    try:
        decoded_arguments = normalize_provider_arguments(
            decoded_arguments,
            definition.request_schema,
            strict_tool_projections.get(name),
        )
    except (SchemaValidationError, StrictSchemaValidationError):
        raise _native_protocol_error(
            "provider_tool_schema_invalid", "Provider tool arguments do not match the function schema.", phase.value
        ) from None
    reason = decoded_arguments.pop("reason", None)
    if reason is not None and not isinstance(reason, str):
        raise _native_protocol_error(
            "provider_tool_arguments_invalid", "Provider tool reason is invalid.", phase.value
        )
    action_type = "tool_call"
    action_args: Mapping[str, object] = decoded_arguments
    if name == "finish_phase":
        action_type = "finish_phase"
        action_args = {}
    elif name == "ask_user":
        action_type = "ask_user"
    action = Action.from_values(
        type=action_type,
        phase=phase,
        tool_name=None if action_type != "tool_call" else name,
        args=action_args,
        reason=reason,
    )
    if isinstance(action, ParseError):
        raise _native_protocol_error(
            "provider_tool_schema_invalid", "Provider tool arguments do not match the action schema.", phase.value
        )
    return {
        "type": action.type.value,
        "phase": phase.value,
        "tool_name": action.tool_name,
        "args": dict(action.args),
        "reason": action.reason,
    }


def _native_protocol_error(error_code: str, message: str, phase: str) -> ProviderError:
    return _provider_error(error_code, message, phase=phase, protocol_retryable=True)


def _context_phase(context: Mapping[str, object]) -> Phase:
    raw_phase = context.get("phase")
    try:
        return Phase(raw_phase)
    except (TypeError, ValueError):
        raise ValueError("Provider context must contain a supported phase.") from None
