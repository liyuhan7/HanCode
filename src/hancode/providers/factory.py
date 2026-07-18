from __future__ import annotations

from hancode.core.config import HanCodeConfig
from hancode.providers.base import LLMClient
from hancode.providers.mock import MockLLM


def create_provider_adapter(config: HanCodeConfig) -> LLMClient:
    """Create the only provider supported by the offline P0 runtime."""
    if config.llm_provider == "mock":
        return MockLLM([])
    raise NotImplementedError(
        f"Provider {config.llm_provider} is configured but not implemented yet."
    )
