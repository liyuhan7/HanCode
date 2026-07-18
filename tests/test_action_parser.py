from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy

import pytest

import hancode.core.actions as actions
from hancode.core.actions import Action, ParseError
from hancode.core.models import Phase


@pytest.mark.parametrize(
    ("raw", "current_phase", "tool_name", "args", "reason"),
    [
        (
            {
                "type": "tool_call",
                "phase": "code",
                "tool_name": "read_file",
                "args": {"path": "README.md"},
                "reason": None,
            },
            Phase.CODE,
            "read_file",
            {"path": "README.md"},
            None,
        ),
        (
            {
                "type": "tool_call",
                "phase": "code",
                "tool_name": "edit_file",
                "args": {"path": "src/main.py", "old_string": "old", "new_string": "new"},
                "reason": "fix the implementation",
            },
            Phase.CODE,
            "edit_file",
            {"path": "src/main.py", "old_string": "old", "new_string": "new"},
            "fix the implementation",
        ),
        (
            {
                "type": "tool_call",
                "phase": "test",
                "tool_name": "run_tests",
                "args": {},
                "reason": None,
            },
            Phase.TEST,
            "run_tests",
            {},
            None,
        ),
    ],
)
def test_parse_valid_tool_actions(
    raw: dict[str, object],
    current_phase: Phase,
    tool_name: str,
    args: dict[str, str],
    reason: str | None,
) -> None:
    result = actions.parse_action(raw, current_phase)

    assert result == Action.from_values(
        type="tool_call",
        phase=current_phase,
        tool_name=tool_name,
        args=args,
        reason=reason,
    )


@pytest.mark.parametrize(
    ("raw", "error_code", "message", "suggested_fix"),
    [
        (
            ["not", "an", "object"],
            "invalid_action_payload",
            "Action payload must be an object.",
            "Provide an object with the required action fields.",
        ),
        (
            {"type": "tool_call", "phase": "code", "tool_name": "read_file"},
            "missing_action_fields",
            "Action payload is missing required fields.",
            "Provide all required action fields.",
        ),
        (
            {
                "type": "tool_call",
                "phase": "code",
                "tool_name": "read_file",
                "args": {"path": "README.md"},
                "reason": None,
                "secret": "must not echo",
            },
            "unexpected_action_fields",
            "Action payload contains unexpected fields.",
            "Provide only the required action fields.",
        ),
    ],
)
def test_parse_rejects_invalid_payload_boundary(
    raw: object, error_code: str, message: str, suggested_fix: str
) -> None:
    result = actions.parse_action(raw, Phase.CODE)  # type: ignore[arg-type]

    assert result == ParseError(
        error_code=error_code,
        message=message,
        phase="code",
        denied_rule=None,
        suggested_fix=suggested_fix,
    )
    assert "secret" not in result.message
    assert "secret" not in result.suggested_fix


@pytest.mark.parametrize(
    ("raw", "expected_error"),
    [
        (
            {
                "type": "tool_call",
                "phase": "code",
                "tool_name": "unknown-tool",
                "args": {},
                "reason": None,
            },
            ParseError(
                error_code="unknown_tool",
                message="Use a registered tool.",
                phase="code",
                denied_rule=None,
                suggested_fix="Provide a valid action schema.",
            ),
        ),
        (
            {
                "type": "tool_call",
                "phase": "code",
                "tool_name": "read_file",
                "args": {},
                "reason": None,
            },
            ParseError(
                error_code="invalid_action_args",
                message="Arguments do not match the action schema.",
                phase="code",
                denied_rule=None,
                suggested_fix="Provide a valid action schema.",
            ),
        ),
        (
            {
                "type": "tool_call",
                "phase": "code",
                "tool_name": "write_file",
                "args": {"path": "src/main.py", "content": "print('ok')"},
                "reason": None,
            },
            ParseError(
                error_code="missing_reason",
                message="Write actions require a reason.",
                phase="code",
                denied_rule=None,
                suggested_fix="Provide a valid action schema.",
            ),
        ),
        (
            {
                "type": "tool_call",
                "phase": "invalid-phase",
                "tool_name": "read_file",
                "args": {"path": "README.md"},
                "reason": None,
            },
            ParseError(
                error_code="invalid_phase",
                message="Use a supported phase.",
                phase="unknown",
                denied_rule=None,
                suggested_fix="Provide a valid action schema.",
            ),
        ),
    ],
)
def test_parse_preserves_action_schema_errors(
    raw: dict[str, object], expected_error: ParseError
) -> None:
    result = actions.parse_action(raw, Phase.CODE)

    assert isinstance(result, ParseError)
    assert result == expected_error


def test_parse_rejects_valid_action_for_a_different_phase() -> None:
    result = actions.parse_action(
        {
            "type": "tool_call",
            "phase": "test",
            "tool_name": "run_tests",
            "args": {},
            "reason": None,
        },
        Phase.CODE,
    )

    assert result == ParseError(
        error_code="phase_mismatch",
        message="Action phase does not match the current phase.",
        phase="code",
        denied_rule=None,
        suggested_fix="Use the current phase.",
    )


def test_parse_does_not_mutate_input_or_return_mutable_arguments() -> None:
    raw: dict[str, object] = {
        "type": "tool_call",
        "phase": "code",
        "tool_name": "read_file",
        "args": {"path": "README.md"},
        "reason": None,
    }
    original = deepcopy(raw)

    result = actions.parse_action(raw, Phase.CODE)

    assert raw == original
    assert isinstance(result, Action)
    assert isinstance(result.args, Mapping)
    raw["args"] = {"path": "changed.md"}
    assert dict(result.args) == {"path": "README.md"}
    with pytest.raises(TypeError):
        result.args["path"] = "other.md"  # type: ignore[index]
