from __future__ import annotations

import pytest

from hancode.core.models import Phase
from hancode.providers.base import ToolDescriptor
from hancode.providers.errors import ProviderError
from hancode.providers.openai_compatible import OpenAICompatibleProvider
from hancode.providers.prompt_builder import PromptBuilder
from hancode.providers.transport import (
    ProviderRequest,
    ProviderResponse,
    ProviderTransportNetworkError,
    ProviderTransportResponseTooLarge,
    ProviderTransportTimeout,
)


class _ScriptedTransport:
    """Transport that returns pre-scripted responses or raises exceptions."""

    def __init__(self, behaviors: list[object]) -> None:
        self._behaviors = list(behaviors)
        self.requests: list[ProviderRequest] = []

    def send(self, request: ProviderRequest) -> ProviderResponse:
        self.requests.append(request)
        behavior = self._behaviors.pop(0)
        if isinstance(behavior, Exception):
            raise behavior
        if isinstance(behavior, ProviderResponse):
            return behavior
        raise TypeError(f"Unexpected behavior type: {type(behavior)}")


class _RecordingEventSink:
    def __init__(self) -> None:
        self.events: list[object] = []

    def emit(self, event: object) -> None:
        self.events.append(event)


def _make_catalog() -> tuple[ToolDescriptor, ...]:
    return (
        ToolDescriptor(
            name="read_file",
            description="Read a file.",
            args_schema={"type": "object"},
        ),
    )


def _make_context(phase: Phase = Phase.SPEC) -> dict[str, object]:
    return {
        "task_id": "task-001",
        "phase": phase.value,
        "goal": "Generate SPEC.md.",
        "sections": {},
        "context_risks": [],
        "truncation": {"applied": False, "omitted_sections": [], "truncated_sections": []},
    }


def _ok_response(action: dict[str, object] | None = None) -> ProviderResponse:
    if action is None:
        action = {"type": "finish_phase", "phase": "spec", "tool_name": None, "args": {}, "reason": "Done."}
    return ProviderResponse(
        status_code=200,
        headers={"content-type": "application/json"},
        json_body={"choices": [{"message": {"content": __import__("json").dumps(action)}}]},
        body_size=100,
    )


def _error_response(status_code: int) -> ProviderResponse:
    return ProviderResponse(
        status_code=status_code,
        headers={"content-type": "application/json"},
        json_body={"error": {"message": "server error"}},
        body_size=50,
    )


def _make_provider(
    *,
    transport: _ScriptedTransport,
    sleeper: object = None,
    max_retries: int = 2,
    interaction_enabled: bool = False,
    response_mode: str = "json_object",
    event_sink: object | None = None,
) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        model_name="test-model",
        base_url="https://example.invalid/v1",
        credential="test-key",
        timeout_seconds=60,
        max_retries=max_retries,
        max_output_tokens=2048,
        max_response_bytes=1048576,
        response_mode=response_mode,  # type: ignore[arg-type]
        prompt_builder=PromptBuilder(),
        transport=transport,
        sleeper=sleeper if sleeper is not None else (lambda _: None),
        tool_catalog=_make_catalog(),
        interaction_enabled=interaction_enabled,
        event_sink=event_sink,  # type: ignore[arg-type]
    )


def test_provider_returns_action_on_success() -> None:
    transport = _ScriptedTransport([_ok_response()])
    provider = _make_provider(transport=transport)

    action = provider.next_action(_make_context())

    assert action["type"] == "finish_phase"
    assert len(transport.requests) == 1


def test_provider_retries_on_429() -> None:
    sleep_calls: list[float] = []
    transport = _ScriptedTransport([_error_response(429), _ok_response()])
    provider = _make_provider(transport=transport, sleeper=sleep_calls.append)

    action = provider.next_action(_make_context())

    assert action["type"] == "finish_phase"
    assert len(transport.requests) == 2
    assert sleep_calls == [1.0]


def test_provider_retries_on_500() -> None:
    sleep_calls: list[float] = []
    transport = _ScriptedTransport([_error_response(500), _ok_response()])
    provider = _make_provider(transport=transport, sleeper=sleep_calls.append)

    action = provider.next_action(_make_context())

    assert action["type"] == "finish_phase"
    assert len(transport.requests) == 2
    assert sleep_calls == [1.0]


def test_provider_retries_on_408_timeout() -> None:
    sleep_calls: list[float] = []
    transport = _ScriptedTransport([_error_response(408), _ok_response()])
    provider = _make_provider(transport=transport, sleeper=sleep_calls.append)

    action = provider.next_action(_make_context())

    assert action["type"] == "finish_phase"
    assert len(transport.requests) == 2
    assert sleep_calls == [1.0]


def test_provider_retries_on_network_error() -> None:
    sleep_calls: list[float] = []
    transport = _ScriptedTransport(
        [ProviderTransportNetworkError(), _ok_response()]
    )
    provider = _make_provider(transport=transport, sleeper=sleep_calls.append)

    action = provider.next_action(_make_context())

    assert action["type"] == "finish_phase"
    assert len(transport.requests) == 2
    assert sleep_calls == [1.0]


def test_provider_retries_transport_timeout_as_provider_timeout() -> None:
    sleep_calls: list[float] = []
    transport = _ScriptedTransport([ProviderTransportTimeout(), _ok_response()])
    provider = _make_provider(transport=transport, sleeper=sleep_calls.append)

    action = provider.next_action(_make_context())

    assert action["type"] == "finish_phase"
    assert sleep_calls == [1.0]


def test_provider_timeout_error_code_after_retry_budget() -> None:
    transport = _ScriptedTransport(
        [ProviderTransportTimeout(), ProviderTransportTimeout()]
    )
    provider = _make_provider(transport=transport, max_retries=1)

    with pytest.raises(ProviderError) as exc_info:
        provider.next_action(_make_context())

    assert exc_info.value.structured_error.error_code == "provider_timeout"


def test_provider_does_not_mask_programming_errors() -> None:
    transport = _ScriptedTransport([IndexError("script exhausted")])
    provider = _make_provider(transport=transport)

    with pytest.raises(IndexError, match="script exhausted"):
        provider.next_action(_make_context())


def test_provider_maps_transport_response_too_large() -> None:
    transport = _ScriptedTransport([ProviderTransportResponseTooLarge()])
    provider = _make_provider(transport=transport)

    with pytest.raises(ProviderError) as exc_info:
        provider.next_action(_make_context())

    assert exc_info.value.structured_error.error_code == "provider_response_too_large"


def test_provider_stops_after_max_retries() -> None:
    sleep_calls: list[float] = []
    transport = _ScriptedTransport([
        _error_response(500),
        _error_response(500),
        _error_response(500),
    ])
    provider = _make_provider(transport=transport, sleeper=sleep_calls.append, max_retries=2)

    with pytest.raises(ProviderError) as exc_info:
        provider.next_action(_make_context())

    assert exc_info.value.structured_error.error_code == "provider_server_error"
    assert not exc_info.value.protocol_retryable
    assert len(transport.requests) == 3
    assert sleep_calls == [1.0, 2.0]


def test_provider_does_not_retry_400() -> None:
    sleep_calls: list[float] = []
    transport = _ScriptedTransport([_error_response(400)])
    provider = _make_provider(transport=transport, sleeper=sleep_calls.append)

    with pytest.raises(ProviderError) as exc_info:
        provider.next_action(_make_context())

    assert exc_info.value.structured_error.error_code == "provider_request_rejected"
    assert not exc_info.value.protocol_retryable
    assert len(transport.requests) == 1
    assert sleep_calls == []


def test_provider_does_not_retry_401() -> None:
    sleep_calls: list[float] = []
    transport = _ScriptedTransport([_error_response(401)])
    provider = _make_provider(transport=transport, sleeper=sleep_calls.append)

    with pytest.raises(ProviderError) as exc_info:
        provider.next_action(_make_context())

    assert exc_info.value.structured_error.error_code == "provider_auth_failed"
    assert not exc_info.value.protocol_retryable
    assert len(transport.requests) == 1
    assert sleep_calls == []


def test_provider_error_uses_current_code_phase() -> None:
    transport = _ScriptedTransport([_error_response(401)])
    provider = _make_provider(transport=transport)

    with pytest.raises(ProviderError) as exc_info:
        provider.next_action(_make_context(Phase.CODE))

    assert exc_info.value.structured_error.phase == Phase.CODE.value


def test_provider_does_not_retry_403() -> None:
    transport = _ScriptedTransport([_error_response(403)])
    provider = _make_provider(transport=transport)

    with pytest.raises(ProviderError) as exc_info:
        provider.next_action(_make_context())

    assert exc_info.value.structured_error.error_code == "provider_auth_failed"
    assert not exc_info.value.protocol_retryable


def test_provider_does_not_retry_404() -> None:
    transport = _ScriptedTransport([_error_response(404)])
    provider = _make_provider(transport=transport)

    with pytest.raises(ProviderError) as exc_info:
        provider.next_action(_make_context())

    assert exc_info.value.structured_error.error_code == "provider_endpoint_not_found"
    assert not exc_info.value.protocol_retryable


def test_provider_does_not_retry_invalid_response() -> None:
    transport = _ScriptedTransport([
        ProviderResponse(
            status_code=200,
            headers={},
            json_body={"choices": [{"message": {"content": "plain text"}}]},
            body_size=50,
        )
    ])
    provider = _make_provider(transport=transport)

    with pytest.raises(ProviderError) as exc_info:
        provider.next_action(_make_context())

    assert exc_info.value.structured_error.error_code == "provider_invalid_response"
    assert exc_info.value.protocol_retryable


def test_provider_marks_empty_response_as_protocol_retryable() -> None:
    transport = _ScriptedTransport([
        ProviderResponse(
            status_code=200,
            headers={},
            json_body={"choices": [{"message": {"content": ""}}]},
            body_size=50,
        )
    ])
    provider = _make_provider(transport=transport)

    with pytest.raises(ProviderError) as exc_info:
        provider.next_action(_make_context())

    assert exc_info.value.structured_error.error_code == "provider_empty_response"
    assert exc_info.value.protocol_retryable


def test_provider_uses_injected_sleeper() -> None:
    sleep_calls: list[float] = []
    transport = _ScriptedTransport([
        _error_response(429),
        _error_response(429),
        _ok_response(),
    ])
    provider = _make_provider(transport=transport, sleeper=sleep_calls.append, max_retries=2)

    provider.next_action(_make_context())

    assert sleep_calls == [1.0, 2.0]


def test_provider_request_contains_authorization_header() -> None:
    transport = _ScriptedTransport([_ok_response()])
    provider = _make_provider(transport=transport)

    provider.next_action(_make_context())

    request = transport.requests[0]
    assert request.headers["Authorization"] == "Bearer test-key"
    assert request.headers["Content-Type"] == "application/json"
    assert "User-Agent" in request.headers


def test_provider_can_enable_ask_user_schema() -> None:
    transport = _ScriptedTransport([_ok_response()])
    provider = _make_provider(transport=transport, interaction_enabled=True)

    provider.next_action(_make_context())

    user_message = transport.requests[0].json_body["messages"][1]["content"]
    assert "ask_user" in user_message


def test_provider_credential_not_in_request_body() -> None:
    transport = _ScriptedTransport([_ok_response()])
    provider = _make_provider(transport=transport)

    provider.next_action(_make_context())

    request = transport.requests[0]
    body_str = __import__("json").dumps(request.json_body)
    assert "test-key" not in body_str


def test_provider_credential_not_in_error() -> None:
    transport = _ScriptedTransport([_error_response(401)])
    provider = _make_provider(transport=transport)

    with pytest.raises(ProviderError) as exc_info:
        provider.next_action(_make_context())

    error_str = str(exc_info.value)
    assert "test-key" not in error_str


def test_json_object_mode_uses_json_object_response_format() -> None:
    transport = _ScriptedTransport([_ok_response()])
    provider = _make_provider(transport=transport, response_mode="json_object")

    provider.next_action(_make_context())

    body = transport.requests[0].json_body
    assert body["response_format"] == {
        "type": "json_object",
    }


def test_json_schema_mode_uses_strict_action_schema() -> None:
    transport = _ScriptedTransport([_ok_response()])
    provider = _make_provider(transport=transport, response_mode="json_schema")

    provider.next_action(_make_context())

    body = transport.requests[0].json_body
    response_format = body["response_format"]

    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["name"] == "hancode_action"
    assert response_format["json_schema"]["strict"] is True
    assert "oneOf" in response_format["json_schema"]["schema"]


def test_json_schema_mode_does_not_embed_full_schema_in_user_message() -> None:
    transport = _ScriptedTransport([_ok_response()])
    provider = _make_provider(transport=transport, response_mode="json_schema")

    provider.next_action(_make_context())

    body = transport.requests[0].json_body
    user_message = body["messages"][1]["content"]
    payload = __import__("json").loads(user_message)

    assert "output_contract" not in payload


def test_json_schema_mode_normalizes_synthetic_optional_nulls() -> None:
    catalog = (
        ToolDescriptor(
            name="list_files",
            description="List files.",
            args_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "additionalProperties": False,
            },
        ),
    )
    action = {
        "type": "tool_call",
        "phase": "spec",
        "tool_name": "list_files",
        "args": {"path": None},
        "reason": None,
    }
    transport = _ScriptedTransport([_ok_response(action)])
    provider = OpenAICompatibleProvider(
        model_name="test-model",
        base_url="https://example.invalid/v1",
        credential="test-key",
        timeout_seconds=60,
        max_retries=2,
        max_output_tokens=2048,
        max_response_bytes=1048576,
        response_mode="json_schema",
        prompt_builder=PromptBuilder(),
        transport=transport,
        sleeper=lambda _: None,
        tool_catalog=catalog,
    )

    normalized = provider.next_action(_make_context())

    assert normalized["args"] == {}
    response_format = transport.requests[0].json_body["response_format"]
    branch = next(
        item
        for item in response_format["json_schema"]["schema"]["oneOf"]
        if item["properties"]["tool_name"].get("const") == "list_files"
    )
    assert branch["properties"]["args"]["required"] == ["path"]


def test_json_object_mode_embeds_action_contract_in_prompt() -> None:
    transport = _ScriptedTransport([_ok_response()])
    provider = _make_provider(transport=transport, response_mode="json_object")

    provider.next_action(_make_context())

    body = transport.requests[0].json_body
    user_message = body["messages"][1]["content"]
    payload = __import__("json").loads(user_message)

    assert "output_contract" in payload


def test_native_tools_strict_sends_tool_schema_and_decodes_one_call() -> None:
    catalog = (
        ToolDescriptor(
            name="list_files",
            description="List files.",
            args_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "additionalProperties": False,
            },
        ),
    )
    response = ProviderResponse(
        status_code=200,
        headers={},
        json_body={
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "content": "ignored",
                        "tool_calls": [
                            {
                                "type": "function",
                                "function": {
                                    "name": "list_files",
                                    "arguments": '{"path": null, "reason": null}',
                                },
                            }
                        ],
                    },
                }
            ]
        },
        body_size=100,
    )
    transport = _ScriptedTransport([response])
    provider = OpenAICompatibleProvider(
        model_name="test-model",
        base_url="https://example.invalid/v1",
        credential="test-key",
        timeout_seconds=60,
        max_retries=2,
        max_output_tokens=2048,
        max_response_bytes=1048576,
        response_mode="native_tools_strict",
        prompt_builder=PromptBuilder(),
        transport=transport,
        sleeper=lambda _: None,
        tool_catalog=catalog,
    )

    action = provider.next_action(_make_context())

    assert action == {
        "type": "tool_call",
        "phase": "spec",
        "tool_name": "list_files",
        "args": {},
        "reason": None,
    }
    request = transport.requests[0].json_body
    assert request["tool_choice"] == "required"
    assert request["parallel_tool_calls"] is False
    assert "response_format" not in request
    parameters = request["tools"][0]["function"]["parameters"]
    assert parameters["properties"]["reason"]["oneOf"][1] == {"type": "null"}
    assert parameters["required"] == ["path", "reason"]
    assert parameters["additionalProperties"] is False


def test_native_tools_omits_strict_flag() -> None:
    response = ProviderResponse(
        status_code=200,
        headers={},
        json_body={
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "type": "function",
                                "function": {
                                    "name": "read_file",
                                    "arguments": '{"path": "README.md", "reason": null}',
                                },
                            }
                        ]
                    }
                }
            ]
        },
        body_size=100,
    )
    transport = _ScriptedTransport([response])
    provider = _make_provider(transport=transport, response_mode="native_tools")

    provider.next_action(_make_context())

    function = transport.requests[0].json_body["tools"][0]["function"]
    assert "strict" not in function


def test_native_tools_expose_and_decode_finish_phase_control() -> None:
    response = ProviderResponse(
        status_code=200,
        headers={},
        json_body={
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "type": "function",
                                "function": {
                                    "name": "finish_phase",
                                    "arguments": '{"reason":"Specification is complete."}',
                                },
                            }
                        ]
                    }
                }
            ]
        },
        body_size=100,
    )
    transport = _ScriptedTransport([response])
    provider = _make_provider(transport=transport, response_mode="native_tools")

    action = provider.next_action(_make_context())

    assert action == {
        "type": "finish_phase",
        "phase": "spec",
        "tool_name": None,
        "args": {},
        "reason": "Specification is complete.",
    }
    names = {
        tool["function"]["name"] for tool in transport.requests[0].json_body["tools"]
    }
    assert "finish_phase" in names
    assert "final" not in names


@pytest.mark.parametrize(
    ("choice", "retryable"),
    [
        ({"finish_reason": "length", "message": {"tool_calls": []}}, False),
        ({"message": {"refusal": "Cannot comply.", "tool_calls": []}}, False),
        ({"message": {"tool_calls": []}}, True),
        ({"message": {"tool_calls": [{}, {}]}}, True),
    ],
    ids=["length", "refusal", "zero_calls", "multiple_calls"],
)
def test_native_tools_terminal_responses_are_not_protocol_retryable(
    choice: dict[str, object],
    retryable: bool,
) -> None:
    transport = _ScriptedTransport([
        ProviderResponse(
            status_code=200,
            headers={},
            json_body={"choices": [choice]},
            body_size=100,
        )
    ])
    provider = _make_provider(transport=transport, response_mode="native_tools")

    with pytest.raises(ProviderError) as exc_info:
        provider.next_action(_make_context())

    assert exc_info.value.protocol_retryable is retryable


def test_auto_downgrades_strict_to_native_tools_without_second_agent_call() -> None:
    unsupported_strict = ProviderResponse(
        status_code=400,
        headers={},
        json_body={
            "error": {
                "code": "unsupported_parameter",
                "param": "tools[0].function.strict",
            }
        },
        body_size=100,
    )
    native_success = ProviderResponse(
        status_code=200,
        headers={},
        json_body={
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "type": "function",
                                "function": {
                                    "name": "read_file",
                                    "arguments": '{"path": "README.md", "reason": null}',
                                },
                            }
                        ]
                    }
                }
            ]
        },
        body_size=100,
    )
    transport = _ScriptedTransport([unsupported_strict, native_success])
    provider = _make_provider(transport=transport, response_mode="auto")

    action = provider.next_action(_make_context())

    assert action["tool_name"] == "read_file"
    assert len(transport.requests) == 2
    assert transport.requests[0].json_body["tools"][0]["function"]["strict"] is True
    assert "strict" not in transport.requests[1].json_body["tools"][0]["function"]


def test_auto_uses_the_conservative_full_downgrade_chain_and_emits_modes() -> None:
    responses = [
        ProviderResponse(
            status_code=400,
            headers={},
            json_body={"error": {"code": "unsupported_parameter", "param": "strict"}},
            body_size=100,
        ),
        ProviderResponse(
            status_code=400,
            headers={},
            json_body={"error": {"code": "unsupported_parameter", "param": "tools"}},
            body_size=100,
        ),
        ProviderResponse(
            status_code=400,
            headers={},
            json_body={
                "error": {"code": "unsupported_value", "param": "response_format.type"}
            },
            body_size=100,
        ),
        _ok_response(),
    ]
    transport = _ScriptedTransport(responses)
    sink = _RecordingEventSink()
    provider = _make_provider(
        transport=transport,
        response_mode="auto",
        event_sink=sink,
    )

    action = provider.next_action(_make_context())

    assert action["type"] == "finish_phase"
    assert len(transport.requests) == 4
    assert "tools" in transport.requests[0].json_body
    assert "tools" in transport.requests[1].json_body
    assert transport.requests[2].json_body["response_format"]["type"] == "json_schema"
    assert transport.requests[3].json_body["response_format"] == {"type": "json_object"}
    assert [(event.from_mode, event.to_mode) for event in sink.events] == [
        ("native_tools_strict", "native_tools"),
        ("native_tools", "json_schema"),
        ("json_schema", "json_object"),
    ]
    assert all("arguments" not in str(event) for event in sink.events)


def test_auto_reuses_last_accepted_effective_mode_across_calls() -> None:
    unsupported_strict = ProviderResponse(
        status_code=400,
        headers={},
        json_body={"error": {"code": "unsupported_parameter", "param": "strict"}},
        body_size=100,
    )
    native_success = ProviderResponse(
        status_code=200,
        headers={},
        json_body={
            "choices": [{"message": {"tool_calls": [{"type": "function", "function": {"name": "read_file", "arguments": '{"path":"README.md","reason":null}'}}]}}]
        },
        body_size=100,
    )
    transport = _ScriptedTransport([unsupported_strict, native_success, native_success])
    sink = _RecordingEventSink()
    provider = _make_provider(transport=transport, response_mode="auto", event_sink=sink)

    provider.next_action(_make_context())
    provider.next_action(_make_context())

    assert len(transport.requests) == 3
    assert "strict" not in transport.requests[2].json_body["tools"][0]["function"]
    assert [(event.from_mode, event.to_mode) for event in sink.events] == [
        ("native_tools_strict", "native_tools")
    ]


def test_auto_fallback_sink_failure_is_not_wrapped_as_provider_error() -> None:
    class _FailingSink:
        def emit(self, event: object) -> None:
            raise RuntimeError("trace persistence failed")

    transport = _ScriptedTransport([
        ProviderResponse(
            status_code=400,
            headers={},
            json_body={"error": {"code": "unsupported_parameter", "param": "strict"}},
            body_size=100,
        )
    ])
    provider = _make_provider(
        transport=transport,
        response_mode="auto",
        event_sink=_FailingSink(),
    )

    with pytest.raises(RuntimeError, match="trace persistence failed"):
        provider.next_action(_make_context())


def test_auto_fails_closed_for_an_unrecognized_capability_error() -> None:
    transport = _ScriptedTransport([
        ProviderResponse(
            status_code=400,
            headers={},
            json_body={
                "error": {
                    "code": "unsupported_parameter",
                    "param": "response_format",
                }
            },
            body_size=100,
        )
    ])
    provider = _make_provider(transport=transport, response_mode="auto")

    with pytest.raises(ProviderError) as exc_info:
        provider.next_action(_make_context())

    assert exc_info.value.structured_error.error_code == "provider_request_rejected"
    assert len(transport.requests) == 1
