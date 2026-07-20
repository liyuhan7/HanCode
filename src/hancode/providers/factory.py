from __future__ import annotations

from hancode.core.config import HanCodeConfig
from hancode.core.errors import HanCodeError, StructuredError
from hancode.providers.base import LLMClient
from hancode.providers.mock import MockLLM


def create_provider_adapter(config: HanCodeConfig) -> LLMClient:
    """Create the only provider supported by the offline P0 runtime."""
    if config.llm_provider == "mock":
        return MockLLM([])
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
