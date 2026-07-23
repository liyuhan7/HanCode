"""Stage 1+2: Provider factory boundary tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from hancode.core.config import HanCodeConfig
from hancode.core.errors import HanCodeError
from hancode.providers.factory import create_provider_adapter
from hancode.providers.mock import MockLLM
from hancode.providers.openai_compatible import OpenAICompatibleProvider
from hancode.providers.transport import FakeTransport


def _make_config(
    provider: str,
    tmp_path: Path | None = None,
    *,
    base_url: str | None = "https://example.invalid/v1",
) -> HanCodeConfig:
    root = tmp_path or Path(".")
    return HanCodeConfig(
        project_root=root,
        hancode_root=root / ".hancode",
        allowed_workspace_root=root,
        task_root=None,
        llm_provider=provider,
        model_name="test-model",
        credential_source="keyring",
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
        provider_base_url=base_url,
        provider_timeout_seconds=60,
        provider_max_retries=2,
        provider_max_output_tokens=2048,
        provider_max_response_bytes=1048576,
    )


def test_provider_factory_returns_mock_for_mock_provider(tmp_path: Path) -> None:
    config = _make_config("mock", tmp_path)
    provider = create_provider_adapter(config)

    assert isinstance(provider, MockLLM)


def test_provider_factory_requires_credential_for_openai_compatible(
    tmp_path: Path,
) -> None:
    config = _make_config("openai_compatible", tmp_path)

    with pytest.raises(HanCodeError) as exc_info:
        create_provider_adapter(config)

    assert exc_info.value.structured_error.error_code == "provider_credential_missing"
    assert exc_info.value.structured_error.denied_rule == "provider_credential_required"


def test_provider_factory_creates_openai_compatible_with_credential(
    tmp_path: Path,
) -> None:
    config = _make_config("openai_compatible", tmp_path)
    transport = FakeTransport([])

    provider = create_provider_adapter(
        config,
        credential="test-key",
        transport=transport,
    )

    assert isinstance(provider, OpenAICompatibleProvider)


def test_factory_passes_provider_response_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = _make_config("openai_compatible", tmp_path)
    config = _make_config_with_response_mode(tmp_path, "json_schema")
    captured: dict[str, object] = {}

    class StubProvider:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(
        "hancode.providers.factory.OpenAICompatibleProvider",
        StubProvider,
    )

    create_provider_adapter(config, credential="test-credential")

    assert captured["response_mode"] == "json_schema"


def _make_config_with_response_mode(
    tmp_path: Path, response_mode: str
) -> HanCodeConfig:
    config = _make_config("openai_compatible", tmp_path)
    from dataclasses import replace

    return replace(config, provider_response_mode=response_mode)  # type: ignore[arg-type]


def test_provider_factory_raises_structured_error_for_anthropic(
    tmp_path: Path,
) -> None:
    config = _make_config("anthropic", tmp_path)

    with pytest.raises(HanCodeError) as exc_info:
        create_provider_adapter(config, credential="test-key")

    assert exc_info.value.structured_error.error_code == "provider_not_implemented"
    assert exc_info.value.structured_error.denied_rule == "implemented_provider_required"
    assert "anthropic" in exc_info.value.structured_error.message


def test_provider_factory_error_does_not_leak_secret_like_values(
    tmp_path: Path,
) -> None:
    config = _make_config("anthropic", tmp_path)

    with pytest.raises(HanCodeError) as exc_info:
        create_provider_adapter(config, credential="sk-secret-value")

    error_dict = exc_info.value.to_dict()
    error_text = str(error_dict)
    assert "sk-secret-value" not in error_text
    assert "sk-" not in error_text
