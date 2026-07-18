"""Default deterministic tool registration for a configured workspace."""

from __future__ import annotations

from collections.abc import Callable
from functools import partial

from hancode.core.config import HanCodeConfig
from hancode.tooling.file_tools import edit_file, list_files, read_file, search_text, write_file
from hancode.tooling.test_tools import run_tests
from hancode.tooling.registry import ToolRegistry, ToolResult


RunTestsTool = Callable[[], ToolResult]


def build_default_tool_registry(
    config: HanCodeConfig,
    *,
    run_tests_tool: RunTestsTool | None = None,
) -> ToolRegistry:
    registry = ToolRegistry()
    project_root = config.project_root
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
    return registry
