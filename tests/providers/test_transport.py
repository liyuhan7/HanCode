from __future__ import annotations

import pytest

from hancode.providers.transport import (
    FakeTransport,
    ProviderRequest,
    ProviderResponse,
    ProviderTransportResponseTooLarge,
    HttpxProviderTransport,
)
from hancode.providers.openai_compatible import decode_response
from hancode.providers.errors import ProviderError


def _make_request(**overrides: object) -> ProviderRequest:
    defaults: dict[str, object] = {
        "method": "POST",
        "url": "https://example.invalid/v1/chat/completions",
        "headers": {"Authorization": "Bearer test-key", "Content-Type": "application/json"},
        "json_body": {"model": "test-model", "messages": []},
        "timeout_seconds": 60,
    }
    defaults.update(overrides)
    return ProviderRequest(**defaults)  # type: ignore[arg-type]


def _make_response(**overrides: object) -> ProviderResponse:
    defaults: dict[str, object] = {
        "status_code": 200,
        "headers": {"content-type": "application/json"},
        "json_body": {"choices": []},
        "body_size": 100,
    }
    defaults.update(overrides)
    return ProviderResponse(**defaults)  # type: ignore[arg-type]


def test_provider_request_is_frozen() -> None:
    request = _make_request()
    with pytest.raises(Exception):
        request.method = "GET"  # type: ignore[misc]


def test_provider_response_is_frozen() -> None:
    response = _make_response()
    with pytest.raises(Exception):
        response.status_code = 500  # type: ignore[misc]


def test_fake_transport_returns_preconfigured_responses() -> None:
    responses = [_make_response(status_code=200), _make_response(status_code=429)]
    transport = FakeTransport(responses)
    r1 = transport.send(_make_request())
    r2 = transport.send(_make_request())
    assert r1.status_code == 200
    assert r2.status_code == 429


def test_fake_transport_records_requests() -> None:
    transport = FakeTransport([_make_response()])
    request = _make_request(url="https://custom.invalid/v1")
    transport.send(request)
    assert len(transport.requests) == 1
    assert transport.requests[0].url == "https://custom.invalid/v1"


def test_fake_transport_raises_when_exhausted() -> None:
    transport = FakeTransport([_make_response()])
    transport.send(_make_request())
    with pytest.raises(IndexError):
        transport.send(_make_request())


def test_fake_transport_request_headers_contain_authorization() -> None:
    transport = FakeTransport([_make_response()])
    transport.send(_make_request())
    recorded = transport.requests[0]
    assert "Authorization" in recorded.headers
    assert recorded.headers["Authorization"] == "Bearer test-key"


class _FakeStreamResponse:
    status_code = 200
    headers: dict[str, str] = {"content-type": "application/json"}

    def __init__(self, chunks: list[bytes], *, content_length: str | None = None) -> None:
        self._chunks = chunks
        if content_length is not None:
            self.headers["content-length"] = content_length

    def __enter__(self) -> "_FakeStreamResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def iter_bytes(self):
        yield from self._chunks


class _FakeHttpxClient:
    def __init__(self, response: _FakeStreamResponse) -> None:
        self.response = response

    def __enter__(self) -> "_FakeHttpxClient":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def stream(self, *args: object, **kwargs: object) -> _FakeStreamResponse:
        return self.response


def test_httpx_transport_rejects_content_length_before_reading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    response = _FakeStreamResponse([b"ignored"], content_length="10")
    client = _FakeHttpxClient(response)
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: client)

    with pytest.raises(ProviderTransportResponseTooLarge):
        HttpxProviderTransport().send(
            _make_request(max_response_bytes=5)
        )


def test_httpx_transport_rejects_stream_after_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    response = _FakeStreamResponse([b"123", b"456"])
    client = _FakeHttpxClient(response)
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: client)

    with pytest.raises(ProviderTransportResponseTooLarge):
        HttpxProviderTransport().send(
            _make_request(max_response_bytes=5)
        )


def test_httpx_transport_invalid_utf8_becomes_invalid_provider_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    response = _FakeStreamResponse([b'{"choices":\xff'])
    client = _FakeHttpxClient(response)
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: client)

    transport_response = HttpxProviderTransport().send(
        _make_request(max_response_bytes=1024)
    )
    assert transport_response.json_body is None
    with pytest.raises(ProviderError) as exc_info:
        decode_response(transport_response, max_response_bytes=1024)
    assert exc_info.value.structured_error.error_code == "provider_invalid_response"
