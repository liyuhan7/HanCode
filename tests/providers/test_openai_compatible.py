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
    assert exc_info.value.retryable
    assert len(transport.requests) == 3
    assert sleep_calls == [1.0, 2.0]


def test_provider_does_not_retry_400() -> None:
    sleep_calls: list[float] = []
    transport = _ScriptedTransport([_error_response(400)])
    provider = _make_provider(transport=transport, sleeper=sleep_calls.append)

    with pytest.raises(ProviderError) as exc_info:
        provider.next_action(_make_context())

    assert exc_info.value.structured_error.error_code == "provider_request_rejected"
    assert not exc_info.value.retryable
    assert len(transport.requests) == 1
    assert sleep_calls == []


def test_provider_does_not_retry_401() -> None:
    sleep_calls: list[float] = []
    transport = _ScriptedTransport([_error_response(401)])
    provider = _make_provider(transport=transport, sleeper=sleep_calls.append)

    with pytest.raises(ProviderError) as exc_info:
        provider.next_action(_make_context())

    assert exc_info.value.structured_error.error_code == "provider_auth_failed"
    assert not exc_info.value.retryable
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
    assert not exc_info.value.retryable


def test_provider_does_not_retry_404() -> None:
    transport = _ScriptedTransport([_error_response(404)])
    provider = _make_provider(transport=transport)

    with pytest.raises(ProviderError) as exc_info:
        provider.next_action(_make_context())

    assert exc_info.value.structured_error.error_code == "provider_endpoint_not_found"
    assert not exc_info.value.retryable


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
    assert not exc_info.value.retryable


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


def test_json_object_mode_embeds_action_contract_in_prompt() -> None:
    transport = _ScriptedTransport([_ok_response()])
    provider = _make_provider(transport=transport, response_mode="json_object")

    provider.next_action(_make_context())

    body = transport.requests[0].json_body
    user_message = body["messages"][1]["content"]
    payload = __import__("json").loads(user_message)

    assert "output_contract" in payload
