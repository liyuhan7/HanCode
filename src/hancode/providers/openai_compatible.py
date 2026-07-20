"""OpenAI-Compatible provider adapter."""

from __future__ import annotations

import json
import re
from typing import Mapping

from hancode.core.errors import StructuredError
from hancode.providers.base import ToolDescriptor
from hancode.providers.errors import ProviderError
from hancode.providers.prompt_builder import PromptBuilder, ProviderPrompt
from hancode.providers.transport import (
    ProviderRequest,
    ProviderResponse,
    ProviderTransport,
    Sleeper,
)

__all__ = ["OpenAICompatibleProvider", "decode_response"]


_CODE_FENCE_RE = re.compile(
    r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", re.DOTALL
)

_USER_AGENT = "hancode/0.1.0"


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
        prompt_builder: PromptBuilder,
        transport: ProviderTransport,
        sleeper: Sleeper,
        tool_catalog: tuple[ToolDescriptor, ...],
    ) -> None:
        self._model_name = model_name
        self._base_url = base_url.rstrip("/")
        self._credential = credential
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._max_output_tokens = max_output_tokens
        self._max_response_bytes = max_response_bytes
        self._prompt_builder = prompt_builder
        self._transport = transport
        self._sleeper = sleeper
        self._tool_catalog = tool_catalog

    def next_action(self, context: Mapping[str, object]) -> dict[str, object]:
        prompt = self._prompt_builder.build(
            context=context,
            tool_catalog=self._tool_catalog,
            interaction_enabled=False,
        )
        request = self._build_request(prompt)

        response = self._send_with_retry(request)

        return decode_response(
            response, max_response_bytes=self._max_response_bytes
        )

    def _build_request(self, prompt: ProviderPrompt) -> ProviderRequest:
        messages = [
            {"role": msg.role, "content": msg.content}
            for msg in prompt.messages
        ]
        body: dict[str, object] = {
            "model": self._model_name,
            "messages": messages,
            "temperature": 0,
            "max_tokens": self._max_output_tokens,
            "response_format": {"type": "json_object"},
        }
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
        )

    def _send_with_retry(self, request: ProviderRequest) -> ProviderResponse:
        last_error: ProviderError | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._transport.send(request)
            except Exception:
                error = _network_error()
                last_error = error
                if attempt < self._max_retries:
                    self._sleeper(2 ** attempt)
                    continue
                raise error from None

            if response.status_code < 400:
                return response

            error = _classify_http_error(response.status_code)
            last_error = error
            if not error.retryable or attempt >= self._max_retries:
                raise error from None
            self._sleeper(2 ** attempt)

        assert last_error is not None
        raise last_error


def _classify_http_error(status_code: int) -> ProviderError:
    if status_code == 400:
        return _provider_error(
            "provider_request_rejected",
            "The provider rejected the request.",
            retryable=False,
        )
    if status_code in (401, 403):
        return _provider_error(
            "provider_auth_failed",
            "Provider authentication failed.",
            retryable=False,
        )
    if status_code == 404:
        return _provider_error(
            "provider_endpoint_not_found",
            "The provider endpoint was not found.",
            retryable=False,
        )
    if status_code == 408:
        return _provider_error(
            "provider_timeout",
            "The provider request timed out.",
            retryable=True,
        )
    if status_code == 429:
        return _provider_error(
            "provider_rate_limited",
            "The provider rate limited the request.",
            retryable=True,
        )
    if 500 <= status_code < 600:
        return _provider_error(
            "provider_server_error",
            "The provider returned a server error.",
            retryable=True,
        )
    return _provider_error(
        "provider_request_rejected",
        f"The provider returned an unexpected status: {status_code}.",
        retryable=False,
    )


def _network_error() -> ProviderError:
    return _provider_error(
        "provider_network_error",
        "A network error occurred while contacting the provider.",
        retryable=True,
    )


def _provider_error(
    error_code: str,
    message: str,
    *,
    retryable: bool,
) -> ProviderError:
    return ProviderError(
        StructuredError(
            error_code=error_code,
            message=message,
            phase="spec",
            denied_rule="provider_available",
            suggested_fix="Check provider configuration and retry.",
        ),
        retryable=retryable,
    )


def decode_response(
    response: ProviderResponse,
    *,
    max_response_bytes: int,
) -> dict[str, object]:
    """Extract an Action dict from an OpenAI-compatible HTTP response."""
    if response.body_size > max_response_bytes:
        raise ProviderError(
            StructuredError(
                error_code="provider_response_too_large",
                message="Provider response exceeded the configured size limit.",
                phase="spec",
                denied_rule="provider_response_size_limit",
                suggested_fix="Reduce the response size or increase provider_max_response_bytes.",
            ),
            retryable=False,
        )

    body = response.json_body
    if not isinstance(body, dict):
        raise _invalid_response("Provider response body is not a JSON object.")

    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise _invalid_response("Provider response has no choices.")

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise _invalid_response("Provider response choice is not an object.")

    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise _invalid_response("Provider response has no message.")

    parsed = message.get("parsed")
    if parsed is not None:
        if isinstance(parsed, dict):
            return parsed
        raise _invalid_response("Provider response message.parsed is not an object.")

    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise _invalid_response("Provider response message.content is empty.")

    return _parse_content(content)


def _parse_content(content: str) -> dict[str, object]:
    stripped = content.strip()
    fence_match = _CODE_FENCE_RE.match(stripped)
    if fence_match is not None:
        stripped = fence_match.group(1).strip()

    try:
        decoded = json.loads(stripped)
    except json.JSONDecodeError:
        raise _invalid_response("Provider response content is not valid JSON.") from None

    if not isinstance(decoded, dict):
        raise _invalid_response("Provider response content is not a JSON object.")

    return decoded


def _invalid_response(message: str) -> ProviderError:
    return ProviderError(
        StructuredError(
            error_code="provider_invalid_response",
            message=message,
            phase="spec",
            denied_rule="provider_response_valid",
            suggested_fix="Check the provider model configuration and response format.",
        ),
        retryable=False,
    )
