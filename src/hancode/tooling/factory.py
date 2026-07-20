"""Default deterministic tool registration for a configured workspace."""

from __future__ import annotations

from collections.abc import Callable
from functools import partial

from hancode.core.config import HanCodeConfig
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


def build_default_tool_catalog(
    config: HanCodeConfig,
) -> tuple[ToolDescriptor, ...]:
    """Return the shared tool descriptors for provider prompts."""
    return (
        ToolDescriptor(
            name="read_file",
            description="Read a file inside the allowed workspace.",
            args_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        ),
        ToolDescriptor(
            name="list_files",
            description="List files in the project workspace.",
            args_schema={"type": "object"},
        ),
        ToolDescriptor(
            name="search_text",
            description="Search text content in the workspace.",
            args_schema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        ),
        ToolDescriptor(
            name="write_file",
            description="Write a file inside the allowed workspace.",
            args_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        ),
        ToolDescriptor(
            name="edit_file",
            description="Edit a file by replacing a string.",
            args_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_string": {"type": "string"},
                    "new_string": {"type": "string"},
                },
                "required": ["path", "old_string", "new_string"],
            },
        ),
        ToolDescriptor(
            name="run_tests",
            description="Run the configured test command.",
            args_schema={"type": "object", "maxProperties": 0},
        ),
        ToolDescriptor(
            name="rollback_last_checkpoint",
            description="Rollback to the last checkpoint.",
            args_schema={"type": "object", "maxProperties": 0},
        ),
    )
