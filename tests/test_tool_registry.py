from __future__ import annotations

import pytest

from hancode.actions import Action, ActionType
from hancode.models import Phase
from hancode.tools import ToolRegistry, ToolResult


def test_register_and_dispatch_tool() -> None:
    received: list[str] = []

    def read_file(*, path: str) -> ToolResult:
        received.append(path)
        return ToolResult(success=True, action_name="read_file", output="contents")

    registry = ToolRegistry()
    registry.register("read_file", read_file)

    result = registry.dispatch(_tool_action("read_file", {"path": "src/main.py"}))

    assert received == ["src/main.py"]
    assert result == ToolResult(success=True, action_name="read_file", output="contents")


def test_unknown_tool_returns_structured_error() -> None:
    called: list[str] = []

    def list_files() -> ToolResult:
        called.append("list_files")
        return ToolResult(success=True, action_name="list_files")

    registry = ToolRegistry()
    registry.register("list_files", list_files)

    result = registry.dispatch(_tool_action("read_file", {"path": "src/main.py"}))

    assert result == ToolResult(
        success=False,
        action_name="read_file",
        error_summary="Tool is not registered.",
    )
    assert called == []


def test_tool_exception_returns_failed_result_without_exception_message() -> None:
    def read_file(*, path: str) -> ToolResult:
        raise ValueError("OPENAI_API_KEY=secret-value")

    registry = ToolRegistry()
    registry.register("read_file", read_file)

    result = registry.dispatch(_tool_action("read_file", {"path": "src/main.py"}))

    assert result == ToolResult(
        success=False,
        action_name="read_file",
        error_summary="Tool execution failed: ValueError.",
    )
    assert "secret-value" not in (result.error_summary or "")


def test_tool_result_contains_action_name_success_and_error_summary() -> None:
    result = ToolResult(
        success=False,
        action_name="run_tests",
        error_summary="Test command failed.",
        exit_code=1,
        stdout="failed",
        stderr="assertion error",
    )

    assert result.success is False
    assert result.action_name == "run_tests"
    assert result.error_summary == "Test command failed."
    assert result.exit_code == 1
    assert result.stdout == "failed"
    assert result.stderr == "assertion error"
    assert result.timed_out is False


def test_tool_result_can_mark_a_timeout_explicitly() -> None:
    result = ToolResult(
        success=False,
        action_name="run_tests",
        timed_out=True,
    )

    assert result.timed_out is True


def test_duplicate_registration_is_rejected() -> None:
    registry = ToolRegistry()
    registry.register("read_file", _successful_tool)

    with pytest.raises(ValueError, match="tool is already registered"):
        registry.register("read_file", _successful_tool)


@pytest.mark.parametrize("name", ["", "   "])
def test_register_rejects_empty_tool_name(name: str) -> None:
    with pytest.raises(ValueError, match="tool name must be non-empty"):
        ToolRegistry().register(name, _successful_tool)


def test_register_rejects_non_callable_tool() -> None:
    with pytest.raises(ValueError, match="tool must be callable"):
        ToolRegistry().register("read_file", object())  # type: ignore[arg-type]


def test_dispatch_rejects_non_tool_action() -> None:
    action = Action(
        type=ActionType.FINISH_PHASE,
        phase=Phase.CODE,
        tool_name=None,
        args={},
        reason=None,
    )

    result = ToolRegistry().dispatch(action)

    assert result == ToolResult(
        success=False,
        action_name="finish_phase",
        error_summary="Action is not a tool call.",
    )


def test_dispatch_converts_invalid_tool_return_to_failed_result() -> None:
    def invalid_tool(*, path: str) -> ToolResult:
        return "not a tool result"  # type: ignore[return-value]

    registry = ToolRegistry()
    registry.register("read_file", invalid_tool)

    result = registry.dispatch(_tool_action("read_file", {"path": "src/main.py"}))

    assert result == ToolResult(
        success=False,
        action_name="read_file",
        error_summary="Tool returned an invalid result.",
    )


def test_dispatch_rejects_result_for_a_different_action() -> None:
    def wrong_action_tool(*, path: str) -> ToolResult:
        return ToolResult(success=True, action_name="write_file", output=path)

    registry = ToolRegistry()
    registry.register("read_file", wrong_action_tool)

    result = registry.dispatch(_tool_action("read_file", {"path": "src/main.py"}))

    assert result == ToolResult(
        success=False,
        action_name="read_file",
        error_summary="Tool returned a result for a different action.",
    )


def _successful_tool(*, path: str) -> ToolResult:
    return ToolResult(success=True, action_name="read_file", output=path)


def _tool_action(name: str, args: dict[str, object]) -> Action:
    return Action(
        type=ActionType.TOOL_CALL,
        phase=Phase.CODE,
        tool_name=name,
        args=args,
        reason=None,
    )
