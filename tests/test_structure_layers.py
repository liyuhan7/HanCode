from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from hancode.core.config import HanCodeConfig
from hancode.demo_support import runner as demo
from hancode.demo_support.runner import _run_stage
from hancode.providers.mock import MockLLM
from hancode.runtime.agent_loop import FilesystemAgentLoopPorts
from hancode.tooling.registry import ToolRegistry
from hancode.storage.workspace import init_project_workspace, init_task_workspace


def test_layered_modules_are_importable() -> None:
    from hancode.core import actions, config, errors, models, phases, router, state
    from hancode.policy import path_policy, tool_policy
    from hancode.providers import action_schema, base, factory, mock, prompt_builder
    from hancode.runtime import agent_loop, context, engine, feedback
    from hancode.storage import checkpoints, export, trace, workspace
    from hancode.tooling import factory as tooling_factory
    from hancode.tooling import file_tools, registry, test_tools
    from hancode.interfaces import cli

    assert actions.Action
    assert config.HanCodeConfig
    assert errors.StructuredError
    assert models.Phase
    assert phases.can_write_artifact
    assert router.select_next_phase
    assert state.TaskState
    assert path_policy.PathClassifier
    assert tool_policy.ToolPolicy
    assert base.LLMClient
    assert factory.create_provider_adapter
    assert mock.MockLLM
    assert action_schema.Action
    assert prompt_builder.build_prompt
    assert agent_loop.AgentLoop
    assert context.ContextBuilder
    assert engine.create_agent_loop
    assert feedback.FeedbackBuilder
    assert checkpoints.CheckpointManifest
    assert export.ExportResult
    assert trace.TraceEvent
    assert workspace.init_project_workspace
    assert tooling_factory.build_default_tool_registry
    assert file_tools.read_file
    assert registry.ToolRegistry
    assert test_tools.run_tests
    assert cli.app


def test_package_root_contains_only_allowed_entries() -> None:
    package_root = Path(__file__).resolve().parents[1] / "src" / "hancode"
    allowed_entries = {
        "__init__.py",
        "README.md",
        "cli.py",
        "_demo_fixture",
        "app",
        "core",
        "delivery_support",
        "demo_support",
        "interfaces",
        "policy",
        "providers",
        "runtime",
        "storage",
        "tooling",
    }

    actual_entries = {
        child.name for child in package_root.iterdir() if child.name != "__pycache__"
    }

    assert actual_entries == allowed_entries


def test_provider_factory_supports_only_mock() -> None:
    from hancode.providers.factory import create_provider_adapter

    mock_config = cast(HanCodeConfig, SimpleNamespace(llm_provider="mock"))
    provider = create_provider_adapter(mock_config)
    assert isinstance(provider, MockLLM)

    unsupported_config = cast(
        HanCodeConfig, SimpleNamespace(llm_provider="openai_compatible")
    )
    with pytest.raises(NotImplementedError, match="not implemented"):
        create_provider_adapter(unsupported_config)


def test_engine_accepts_injected_provider(tmp_path: Path) -> None:
    from hancode.runtime.engine import create_agent_loop

    project_root = tmp_path / "project"
    project_root.mkdir()
    init_project_workspace(project_root, "project-001", "Course", "Assignment")
    init_task_workspace(project_root, "task-001")
    provider = MockLLM([])

    loop = create_agent_loop(project_root, "task-001", provider=provider)

    assert loop._llm is provider


def test_cli_entry_proxy_exports_app() -> None:
    from hancode import cli as entrypoint
    from hancode.interfaces.cli import app

    assert entrypoint.app is app


def test_demo_uses_engine_factory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    sentinel = object()

    class FakeLoop:
        def run(self, task_id: str, *, resume: bool) -> object:
            captured["run"] = (task_id, resume)
            return sentinel

    def fake_create_agent_loop(
        project_root: Path,
        task_id: str,
        *,
        provider: object,
        tool_registry: object,
        trace_appender: object,
        max_steps: int,
    ) -> FakeLoop:
        captured.update(
            {
                "project_root": project_root,
                "task_id": task_id,
                "provider": provider,
                "tool_registry": tool_registry,
                "trace_appender": trace_appender,
                "max_steps": max_steps,
            }
        )
        return FakeLoop()

    monkeypatch.setattr(demo, "create_agent_loop", fake_create_agent_loop)
    config = cast(HanCodeConfig, object())
    ports = cast(FilesystemAgentLoopPorts, SimpleNamespace(trace_appender=object()))
    registry = cast(ToolRegistry, object())
    actions = ({"type": "final"},)

    result = _run_stage(
        tmp_path,
        config,
        ports,
        registry,
        actions,
        resume=True,
    )

    assert result is sentinel
    assert isinstance(captured["provider"], MockLLM)
    assert captured["tool_registry"] is registry
    assert captured["max_steps"] == 1
    assert captured["run"] == (demo.TASK_ID, True)
