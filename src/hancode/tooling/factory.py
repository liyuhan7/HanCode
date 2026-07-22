"""Default deterministic tool registration for a configured workspace."""

from __future__ import annotations

from collections.abc import Callable
from functools import partial

from hancode.core.config import HanCodeConfig
from hancode.core.tool_specs import ALL_TOOL_SPECS
from hancode.tooling.build_tools import run_build
from hancode.tooling.checkpoint_tools import list_checkpoints
from hancode.tooling.delivery_tools import record_knowledge, record_review, read_test_report
from hancode.tooling.diff_tools import get_diff
from hancode.tooling.file_tools import edit_file, list_files, read_file, search_text, write_file
from hancode.tooling.test_tools import run_tests
from hancode.tooling.registry import ToolRegistry, ToolResult
from hancode.providers.base import ToolDescriptor


RunTestsTool = Callable[[], ToolResult]


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
        run_tests_tool
        or partial(run_tests, project_root, config.test_command),
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
