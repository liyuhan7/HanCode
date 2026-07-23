from __future__ import annotations

from collections.abc import Mapping

import pytest

import hancode.core.actions as actions
from hancode.core.actions import Action, ActionType, ParseError
from hancode.core.models import Phase


def test_tool_call_preserves_valid_fields() -> None:
    action = Action.from_values(
        type=ActionType.TOOL_CALL,
        phase=Phase.CODE,
        tool_name="read_file",
        args={"path": "src/main.py"},
        reason=None,
    )

    assert action == Action(
        type=ActionType.TOOL_CALL,
        phase=Phase.CODE,
        tool_name="read_file",
        args={"path": "src/main.py"},
        reason=None,
    )


def test_action_requires_tool_name() -> None:
    result = Action.from_values(
        type=ActionType.TOOL_CALL,
        phase=Phase.CODE,
        tool_name=None,
        args={"path": "src/main.py"},
        reason=None,
    )

    assert isinstance(result, ParseError)
    assert result.error_code == "missing_tool_name"
    assert result.phase == "code"
    assert result.denied_rule is None


def test_action_requires_phase() -> None:
    result = Action.from_values(
        type=ActionType.TOOL_CALL,
        phase=None,
        tool_name="read_file",
        args={"path": "src/main.py"},
        reason=None,
    )

    assert isinstance(result, ParseError)
    assert result.error_code == "invalid_phase"
    assert result.phase == "unknown"


def test_unknown_action_type_is_invalid() -> None:
    result = Action.from_values(
        type="unknown",
        phase=Phase.CODE,
        tool_name="read_file",
        args={"path": "src/main.py"},
        reason=None,
    )

    assert isinstance(result, ParseError)
    assert result.error_code == "invalid_action_type"


def test_write_action_requires_reason_field() -> None:
    result = Action.from_values(
        type=ActionType.TOOL_CALL,
        phase=Phase.CODE,
        tool_name="write_file",
        args={"path": "src/main.py", "content": "print('ok')\n"},
        reason=None,
    )

    assert isinstance(result, ParseError)
    assert result.error_code == "missing_reason"


def test_run_tests_accepts_optional_command() -> None:
    """The LLM may supply an explicit command; it is no longer rejected."""
    result = Action.from_values(
        type=ActionType.TOOL_CALL,
        phase=Phase.TEST,
        tool_name="run_tests",
        args={"command": "gcc hello.c"},
        reason="compile the C hello world",
    )

    assert isinstance(result, Action)
    assert result.args["command"] == "gcc hello.c"


def test_run_tests_rejects_non_string_command() -> None:
    result = Action.from_values(
        type=ActionType.TOOL_CALL,
        phase=Phase.TEST,
        tool_name="run_tests",
        args={"command": ["pytest", "-q"]},
        reason=None,
    )

    assert isinstance(result, ParseError)
    assert result.error_code == "invalid_action_args"


def test_finish_action_has_no_tool_side_effect() -> None:
    result = Action.from_values(
        type=ActionType.FINISH_PHASE,
        phase=Phase.CODE,
        tool_name="write_file",
        args={},
        reason=None,
    )

    assert isinstance(result, ParseError)
    assert result.error_code == "unexpected_tool_name"


@pytest.mark.parametrize(
    ("tool_name", "args", "reason"),
    [
        ("read_file", {"path": "README.md"}, None),
        ("list_files", {}, None),
        ("list_files", {"path": "src"}, None),
        ("search_text", {"query": "Action"}, None),
        ("write_file", {"path": "docs/PLAN.md", "content": "# Plan\n"}, "record plan"),
        (
            "edit_file",
            {"path": "src/main.py", "old_string": "old", "new_string": "new"},
            "fix implementation",
        ),
        ("run_tests", {}, None),
        ("run_tests", {"command": "gcc hello.c"}, "test C program"),
        ("rollback_last_checkpoint", {}, None),
    ],
)
def test_known_tools_accept_their_fixed_argument_schema(
    tool_name: str, args: dict[str, str], reason: str | None
) -> None:
    result = Action.from_values(
        type=ActionType.TOOL_CALL,
        phase=Phase.CODE,
        tool_name=tool_name,
        args=args,
        reason=reason,
    )

    assert isinstance(result, Action)
    assert result.tool_name == tool_name
    assert dict(result.args) == args


@pytest.mark.parametrize(
    ("tool_name", "args", "reason"),
    [
        ("read_file", {}, None),
        ("read_file", {"path": "README.md", "target_kind": "source"}, None),
        ("list_files", {"query": "Action"}, None),
        ("search_text", {"query": "Action", "path": "src"}, None),
        ("write_file", {"path": "src/main.py"}, "add file"),
        (
            "edit_file",
            {"path": "src/main.py", "old_string": "", "new_string": "new"},
            "fix implementation",
        ),
        ("rollback_last_checkpoint", {"checkpoint": "checkpoint-1"}, None),
    ],
)
def test_tools_reject_missing_or_unexpected_arguments(
    tool_name: str, args: dict[str, str], reason: str | None
) -> None:
    result = Action.from_values(
        type=ActionType.TOOL_CALL,
        phase=Phase.CODE,
        tool_name=tool_name,
        args=args,
        reason=reason,
    )

    assert isinstance(result, ParseError)
    assert result.error_code == "invalid_action_args"


def test_ask_user_requires_nonempty_question() -> None:
    result = Action.from_values(
        type=ActionType.ASK_USER,
        phase=Phase.SPEC,
        tool_name=None,
        args={},
        reason=None,
    )

    assert isinstance(result, ParseError)
    assert result.error_code == "invalid_action_args"


def test_ask_user_rejects_question_over_schema_limit() -> None:
    result = Action.from_values(
        type=ActionType.ASK_USER,
        phase=Phase.SPEC,
        tool_name=None,
        args={"question": "x" * 2049},
        reason=None,
    )

    assert isinstance(result, ParseError)
    assert result.error_code == "invalid_action_args"


def test_final_rejects_arguments() -> None:
    result = Action.from_values(
        type=ActionType.FINAL,
        phase=Phase.DELIVER,
        tool_name=None,
        args={"result": "done"},
        reason=None,
    )

    assert isinstance(result, ParseError)
    assert result.error_code == "invalid_action_args"


def test_direct_construction_rejects_invalid_schema() -> None:
    with pytest.raises(ValueError, match="invalid Action schema"):
        Action(
            type=ActionType.TOOL_CALL,
            phase=Phase.TEST,
            tool_name="run_tests",
            args={"invalid_extra_arg": "garbage"},
            reason=None,
        )


def test_action_arguments_are_immutable() -> None:
    args = {"path": "README.md"}
    result = Action.from_values(
        type=ActionType.TOOL_CALL,
        phase=Phase.CODE,
        tool_name="read_file",
        args=args,
        reason=None,
    )
    assert isinstance(result, Action)
    assert isinstance(result.args, Mapping)

    args["path"] = "changed.md"

    assert dict(result.args) == {"path": "README.md"}
    with pytest.raises(TypeError):
        result.args["path"] = "other.md"  # type: ignore[index]


@pytest.mark.parametrize(
    ("action_type", "phase", "args"),
    [
        (ActionType.FINISH_PHASE, Phase.CODE, {}),
        (ActionType.ASK_USER, Phase.SPEC, {"question": "Which requirement applies?"}),
        (ActionType.FINAL, Phase.DELIVER, {}),
    ],
)
def test_control_actions_accept_their_fixed_schema(
    action_type: ActionType, phase: Phase, args: dict[str, str]
) -> None:
    result = Action.from_values(
        type=action_type,
        phase=phase,
        tool_name=None,
        args=args,
        reason=None,
    )

    assert isinstance(result, Action)
    assert result.type is action_type
    assert result.tool_name is None


def test_unknown_tool_returns_structured_error_without_echoing_candidate_value() -> None:
    result = Action.from_values(
        type=ActionType.TOOL_CALL,
        phase=Phase.CODE,
        tool_name="secret-tool-name",
        args={},
        reason=None,
    )

    assert isinstance(result, ParseError)
    assert result.to_dict() == {
        "error_code": "unknown_tool",
        "message": "Use a registered tool.",
        "phase": "code",
        "denied_rule": None,
        "suggested_fix": "Provide a valid action schema.",
    }


def test_registered_tool_without_schema_is_rejected_even_with_no_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(actions, "_TOOL_NAMES", actions._TOOL_NAMES | {"future_tool"})

    result = Action.from_values(
        type=ActionType.TOOL_CALL,
        phase=Phase.CODE,
        tool_name="future_tool",
        args={},
        reason=None,
    )

    assert isinstance(result, ParseError)
    assert result.error_code == "invalid_action_args"
