"""Default deterministic tool registration for a configured workspace."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from functools import partial
from pathlib import Path
from typing import Any, cast

from hancode.core.config import HanCodeConfig
from hancode.core.tool_specs import ALL_TOOL_SPECS
from hancode.tooling.build_tools import run_build
from hancode.tooling.checkpoint_tools import list_checkpoints
from hancode.tooling.delivery_tools import record_knowledge, record_review, read_test_report
from hancode.tooling.diff_tools import get_diff
from hancode.tooling.file_tools import (
    edit_file,
    list_files,
    read_file,
    redact_text,
    search_text,
    write_file,
)
from hancode.tooling.test_tools import run_tests
from hancode.tooling.registry import ToolRegistry, ToolResult
from hancode.providers.base import ToolDescriptor


RunTestsTool = Callable[[str | None], ToolResult]


def _resolve_test_command(
    fallback_command: str | None, **kwargs: object
) -> tuple[str | None, dict[str, object]]:
    """Select one explicit command or the configured test-command fallback."""
    raw_command = kwargs.pop("command", fallback_command)
    command = raw_command if isinstance(raw_command, str) or raw_command is None else fallback_command
    return command, kwargs


def _run_tests_dispatch(
    project_root: Path,
    fallback_command: str | None,
    run_tests_tool: RunTestsTool | None = None,
    **kwargs: object,
) -> ToolResult:
    command, remaining = _resolve_test_command(fallback_command, **kwargs)
    if run_tests_tool is not None:
        if remaining:
            return ToolResult(
                success=False,
                action_name="run_tests",
                error_summary="Unexpected run_tests arguments.",
            )
        return _redact_test_result(run_tests_tool(command))
    return run_tests(project_root, command, **cast(dict[str, Any], remaining))


def _redact_test_result(result: ToolResult) -> ToolResult:
    """Keep injected test adapters under the same output redaction contract."""
    return replace(
        result,
        output=redact_text(result.output) if isinstance(result.output, str) else result.output,
        error_summary=(
            redact_text(result.error_summary)
            if result.error_summary is not None
            else None
        ),
        stdout=redact_text(result.stdout) if result.stdout is not None else None,
        stderr=redact_text(result.stderr) if result.stderr is not None else None,
        command=redact_text(result.command) if result.command is not None else None,
    )


def build_default_tool_registry(
    config: HanCodeConfig,
    *,
    run_tests_tool: RunTestsTool | None = None,
) -> ToolRegistry:
    registry = ToolRegistry()
    project_root = config.project_root
    task_root = config.task_root

    registry.register("read_file", partial(read_file, project_root))
    registry.register("list_files", partial(list_files, project_root))
    registry.register("search_text", partial(search_text, project_root))
    registry.register("write_file", partial(write_file, project_root))
    registry.register("edit_file", partial(edit_file, project_root))
    registry.register(
        "run_tests",
        partial(
            _run_tests_dispatch,
            project_root,
            config.test_command,
            run_tests_tool,
        ),
    )

    # S4 tools
    if task_root is not None:
        registry.register(
            "get_diff",
            partial(get_diff, project_root, task_root),
        )
        registry.register(
            "read_test_report",
            partial(read_test_report, project_root, task_root),
        )
        registry.register(
            "list_checkpoints",
            partial(list_checkpoints, project_root, task_root),
        )
        registry.register(
            "record_review",
            partial(record_review, project_root, task_root.name),
        )
        registry.register(
            "record_knowledge",
            partial(record_knowledge, project_root, task_root.name),
        )
    registry.register(
        "run_build",
        partial(run_build, project_root, config.build_command),
    )

    return registry


def build_default_tool_catalog(
    config: HanCodeConfig,
) -> tuple[ToolDescriptor, ...]:
    """Return the shared tool descriptors for provider prompts."""
    return tuple(
        ToolDescriptor(
            name=spec.name,
            description=spec.description,
            args_schema=spec.args_schema,
        )
        for spec in ALL_TOOL_SPECS
    )
