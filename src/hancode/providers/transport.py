"""HTTP transport abstraction for provider requests."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Mapping, Protocol

__all__ = [
    "FakeTransport",
    "HttpxProviderTransport",
    "ProviderRequest",
    "ProviderResponse",
    "ProviderTransport",
    "ProviderTransportError",
    "ProviderTransportNetworkError",
    "ProviderTransportResponseTooLarge",
    "ProviderTransportTimeout",
    "Sleeper",
]


class ProviderTransportError(Exception):
    """Base class for expected transport failures."""


class ProviderTransportTimeout(ProviderTransportError):
    """The transport timed out before completing the request."""


class ProviderTransportNetworkError(ProviderTransportError):
    """The transport could not connect or complete the network operation."""


class ProviderTransportResponseTooLarge(ProviderTransportError):
    """The response exceeded the configured byte limit while being read."""


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    method: str
    url: str
    headers: Mapping[str, str]
    json_body: Mapping[str, object]
    timeout_seconds: int
    max_response_bytes: int | None = None


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

        try:
            with httpx.Client(
                timeout=request.timeout_seconds,
                follow_redirects=False,
                verify=True,
            ) as client:
                with client.stream(
                    method=request.method,
                    url=request.url,
                    headers=dict(request.headers),
                    json=dict(request.json_body),
                ) as response:
                    limit = request.max_response_bytes
                    content_length = response.headers.get("content-length")
                    if limit is not None and content_length is not None:
                        try:
                            declared_size = int(content_length)
                        except ValueError:
                            declared_size = None
                        if declared_size is not None and declared_size > limit:
                            raise ProviderTransportResponseTooLarge

                    chunks: list[bytes] = []
                    total_size = 0
                    for chunk in response.iter_bytes():
                        total_size += len(chunk)
                        if limit is not None and total_size > limit:
                            raise ProviderTransportResponseTooLarge
                        chunks.append(chunk)
                    raw_body = b"".join(chunks)
                    try:
                        json_text = raw_body.decode("utf-8")
                        json_body: object = json.loads(json_text)
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        json_body = None
                    return ProviderResponse(
                        status_code=response.status_code,
                        headers=dict(response.headers),
                        json_body=json_body,
                        body_size=total_size,
                    )
        except ProviderTransportError:
            raise
        except httpx.TimeoutException:
            raise ProviderTransportTimeout from None
        except httpx.TransportError:
            raise ProviderTransportNetworkError from None
