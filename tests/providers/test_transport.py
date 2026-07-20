from __future__ import annotations

import pytest

from hancode.providers.transport import (
    FakeTransport,
    ProviderRequest,
    ProviderResponse,
)


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
