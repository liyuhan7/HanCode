from __future__ import annotations

import pytest

from hancode.providers.errors import ProviderError
from hancode.providers.openai_compatible import decode_response
from hancode.providers.transport import ProviderResponse


def _make_response(
    json_body: object,
    *,
    body_size: int = 100,
    status_code: int = 200,
) -> ProviderResponse:
    return ProviderResponse(
        status_code=status_code,
        headers={"content-type": "application/json"},
        json_body=json_body,
        body_size=body_size,
    )


def test_decoder_reads_message_parsed() -> None:
    response = _make_response(
        {"choices": [{"message": {"parsed": {"type": "tool_call", "phase": "spec"}}}]}
    )
    action = decode_response(response, max_response_bytes=1048576)
    assert action == {"type": "tool_call", "phase": "spec"}


def test_decoder_reads_message_content_json() -> None:
    response = _make_response(
        {"choices": [{"message": {"content": '{"type": "finish_phase", "phase": "plan"}'}}]}
    )
    action = decode_response(response, max_response_bytes=1048576)
    assert action == {"type": "finish_phase", "phase": "plan"}


def test_decoder_accepts_single_json_code_fence() -> None:
    content = '```json\n{"type": "final", "phase": "deliver"}\n```'
    response = _make_response({"choices": [{"message": {"content": content}}]})
    action = decode_response(response, max_response_bytes=1048576)
    assert action == {"type": "final", "phase": "deliver"}


def test_decoder_rejects_plain_text() -> None:
    response = _make_response(
        {"choices": [{"message": {"content": "I think you should read the file first."}}]}
    )
    with pytest.raises(ProviderError) as exc_info:
        decode_response(response, max_response_bytes=1048576)
    assert exc_info.value.structured_error.error_code == "provider_invalid_response"


def test_decoder_rejects_json_array() -> None:
    response = _make_response(
        {"choices": [{"message": {"content": "[1, 2, 3]"}}]}
    )
    with pytest.raises(ProviderError) as exc_info:
        decode_response(response, max_response_bytes=1048576)
    assert exc_info.value.structured_error.error_code == "provider_invalid_response"


def test_decoder_rejects_missing_choices() -> None:
    response = _make_response({"error": "something"})
    with pytest.raises(ProviderError) as exc_info:
        decode_response(response, max_response_bytes=1048576)
    assert exc_info.value.structured_error.error_code == "provider_invalid_response"


def test_decoder_rejects_empty_content() -> None:
    response = _make_response({"choices": [{"message": {"content": ""}}]})
    with pytest.raises(ProviderError) as exc_info:
        decode_response(response, max_response_bytes=1048576)
    assert exc_info.value.structured_error.error_code == "provider_invalid_response"


def test_decoder_rejects_oversized_response() -> None:
    response = _make_response(
        {"choices": [{"message": {"content": '{"type": "tool_call"}'}}]},
        body_size=2_000_000,
    )
    with pytest.raises(ProviderError) as exc_info:
        decode_response(response, max_response_bytes=1_048_576)
    assert exc_info.value.structured_error.error_code == "provider_response_too_large"


def test_decoder_does_not_include_raw_body_in_error() -> None:
    secret_content = "plain text with secret sk-abc123def"
    response = _make_response(
        {"choices": [{"message": {"content": secret_content}}]}
    )
    with pytest.raises(ProviderError) as exc_info:
        decode_response(response, max_response_bytes=1048576)
    error_str = str(exc_info.value)
    assert "sk-abc123def" not in error_str
    assert secret_content not in error_str


def test_decoder_rejects_non_dict_parsed() -> None:
    response = _make_response(
        {"choices": [{"message": {"parsed": [1, 2, 3]}}]}
    )
    with pytest.raises(ProviderError) as exc_info:
        decode_response(response, max_response_bytes=1048576)
    assert exc_info.value.structured_error.error_code == "provider_invalid_response"
