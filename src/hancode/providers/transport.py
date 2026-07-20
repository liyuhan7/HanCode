"""HTTP transport abstraction for provider requests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol

__all__ = [
    "FakeTransport",
    "HttpxProviderTransport",
    "ProviderRequest",
    "ProviderResponse",
    "ProviderTransport",
    "Sleeper",
]


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    method: str
    url: str
    headers: Mapping[str, str]
    json_body: Mapping[str, object]
    timeout_seconds: int


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    status_code: int
    headers: Mapping[str, str]
    json_body: object
    body_size: int


class ProviderTransport(Protocol):
    """Boundary for sending HTTP requests to a model provider."""

    def send(self, request: ProviderRequest) -> ProviderResponse: ...


class Sleeper(Protocol):
    """Injectable sleep callable for retry backoff."""

    def __call__(self, seconds: float) -> None: ...


class FakeTransport:
    """Deterministic transport for offline testing."""

    def __init__(self, responses: list[ProviderResponse]) -> None:
        self._responses = list(responses)
        self.requests: list[ProviderRequest] = []

    def send(self, request: ProviderRequest) -> ProviderResponse:
        self.requests.append(request)
        return self._responses.pop(0)


class HttpxProviderTransport:
    """Default HTTP transport backed by httpx."""

    def send(self, request: ProviderRequest) -> ProviderResponse:
        import httpx

        with httpx.Client(
            timeout=request.timeout_seconds,
            follow_redirects=False,
            verify=True,
        ) as client:
            response = client.request(
                method=request.method,
                url=request.url,
                headers=dict(request.headers),
                json=dict(request.json_body),
            )

        try:
            json_body: object = response.json()
        except Exception:
            json_body = None

        return ProviderResponse(
            status_code=response.status_code,
            headers=dict(response.headers),
            json_body=json_body,
            body_size=len(response.content),
        )
