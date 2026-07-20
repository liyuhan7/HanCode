"""Stage 1: Provider factory boundary tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from hancode.core.config import HanCodeConfig
from hancode.core.errors import HanCodeError
from hancode.providers.factory import create_provider_adapter


def _make_config(provider: str, tmp_path: Path | None = None) -> HanCodeConfig:
    root = tmp_path or Path(".")
    return HanCodeConfig(
        project_root=root,
        hancode_root=root / ".hancode",
        allowed_workspace_root=root,
        task_root=None,
        llm_provider=provider,
        model_name=None,
        credential_source="missing",
        test_command="pytest",
        build_command=None,
        max_steps=30,
        retry_budget=2,
        max_checkpoints_per_task=5,
        max_observation_bytes=8192,
        max_context_chars=24000,
        max_trace_events=40,
        protected_patterns=(),
        writable_roots=(Path("src"),),
    )


def test_provider_factory_returns_mock_for_mock_provider(tmp_path: Path) -> None:
    from hancode.providers.mock import MockLLM

    config = _make_config("mock", tmp_path)
    provider = create_provider_adapter(config)

    assert isinstance(provider, MockLLM)


def test_provider_factory_raises_structured_error_for_unimplemented_provider(
    tmp_path: Path,
) -> None:
    config = _make_config("openai_compatible", tmp_path)

    with pytest.raises(HanCodeError) as exc_info:
        create_provider_adapter(config)

    assert exc_info.value.structured_error.error_code == "provider_not_implemented"
    assert exc_info.value.structured_error.denied_rule == "implemented_provider_required"
    assert "openai_compatible" in exc_info.value.structured_error.message


def test_provider_factory_error_does_not_leak_secret_like_values(tmp_path: Path) -> None:
    config = _make_config("anthropic", tmp_path)

    with pytest.raises(HanCodeError) as exc_info:
        create_provider_adapter(config)

    error_dict = exc_info.value.to_dict()
    error_text = str(error_dict)
    assert "sk-" not in error_text
