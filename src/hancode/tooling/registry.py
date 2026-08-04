from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from hancode.core.actions import Action, ActionType
from hancode.core.errors import HanCodeError


_MEMORY_INTEGRITY_ERRORS = frozenset(
    {
        "memory_corrupt",
        "memory_task_identity_mismatch",
        "memory_path_link_not_allowed",
        "memory_write_error",
    }
)


@dataclass(frozen=True, slots=True)
class ToolResult:
    success: bool
    action_name: str
    output: object | None = None
    error_summary: str | None = None
    exit_code: int | None = None
    stdout: str | None = None
    stderr: str | None = None
    timed_out: bool = False
    command: str | None = None
    mutation_applied: bool | None = None
    error_code: str | None = None


Tool = Callable[..., ToolResult]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, name: str, tool: Tool) -> None:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("tool name must be non-empty")
        if not callable(tool):
            raise ValueError("tool must be callable")
        if name in self._tools:
            raise ValueError("tool is already registered")
        self._tools[name] = tool

    def dispatch(self, action: Action) -> ToolResult:
        if action.type is not ActionType.TOOL_CALL:
            return _failed_result(
                action.type.value,
                "Action is not a tool call.",
                error_code="tool_not_registered",
            )

        assert action.tool_name is not None
        tool = self._tools.get(action.tool_name)
        if tool is None:
            return _failed_result(
                action.tool_name,
                "Tool is not registered.",
                error_code="tool_not_registered",
            )

        try:
            result = tool(**action.args)
        except HanCodeError as exc:
            if (
                action.tool_name in {"memory_read", "memory_search"}
                and exc.structured_error.error_code in _MEMORY_INTEGRITY_ERRORS
            ):
                raise
            return _failed_result(
                action.tool_name,
                f"Tool execution failed: {type(exc).__name__}.",
                error_code="tool_execution_exception",
            )
        except Exception as exc:
            return _failed_result(
                action.tool_name,
                f"Tool execution failed: {type(exc).__name__}.",
                error_code="tool_execution_exception",
            )

        if not isinstance(result, ToolResult):
            return _failed_result(
                action.tool_name,
                "Tool returned an invalid result.",
                error_code="tool_result_invalid",
            )
        if result.action_name != action.tool_name:
            return _failed_result(
                action.tool_name,
                "Tool returned a result for a different action.",
                error_code="tool_result_action_mismatch",
            )
        return result


def _failed_result(
    action_name: str, error_summary: str, *, error_code: str
) -> ToolResult:
    return ToolResult(
        success=False,
        action_name=action_name,
        error_summary=error_summary,
        error_code=error_code,
    )
