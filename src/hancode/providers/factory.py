from __future__ import annotations

import time
from typing import cast

from hancode.core.config import HanCodeConfig
from hancode.core.errors import HanCodeError, StructuredError
from hancode.providers.base import LLMClient
from hancode.providers.mock import MockLLM
from hancode.providers.openai_compatible import OpenAICompatibleProvider
from hancode.providers.prompt_builder import PromptBuilder
from hancode.providers.transport import HttpxProviderTransport, ProviderTransport, Sleeper
from hancode.tooling.factory import build_default_tool_catalog


def create_provider_adapter(
    config: HanCodeConfig,
    *,
    credential: str | None = None,
    transport: ProviderTransport | None = None,
    sleeper: Sleeper | None = None,
) -> LLMClient:
    """Create the provider adapter for the configured provider."""
    if config.llm_provider == "mock":
        return MockLLM([])

    if config.llm_provider == "openai_compatible":
        if not credential or not credential.strip():
            raise HanCodeError(
                StructuredError(
                    error_code="provider_credential_missing",
                    message="The configured provider credential is missing.",
                    phase="spec",
                    denied_rule="provider_credential_required",
                    suggested_fix="Configure the provider credential and retry the task.",
                )
            )
        return OpenAICompatibleProvider(
            model_name=config.model_name or "",
            base_url=config.provider_base_url or "",
            credential=credential,
            timeout_seconds=config.provider_timeout_seconds,
            max_retries=config.provider_max_retries,
            max_output_tokens=config.provider_max_output_tokens,
            max_response_bytes=config.provider_max_response_bytes,
            prompt_builder=PromptBuilder(),
            transport=transport or HttpxProviderTransport(),
            sleeper=sleeper or cast(Sleeper, time.sleep),
            tool_catalog=build_default_tool_catalog(config),
        )

    raise HanCodeError(
        StructuredError(
            error_code="provider_not_implemented",
            message=f"Provider is not implemented: {config.llm_provider}.",
            phase="spec",
            denied_rule="implemented_provider_required",
            suggested_fix=(
                "Use the mock provider until the configured adapter is implemented."
            ),
        )
    )
