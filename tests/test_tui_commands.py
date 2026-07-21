"""S4-T4: CommandParser and plain-text semantics (Textual-independent)."""

from __future__ import annotations

from hancode.interfaces.tui.commands import (
    PlainTextIntent,
    TuiCommand,
    TuiCommandError,
    classify_plain_text,
    parse_command,
)


def test_parse_task_command_with_goal() -> None:
    result = parse_command("/task Build a CSV grade report CLI")

    assert isinstance(result, TuiCommand)
    assert result.name == "task"
    assert result.args == ("Build a CSV grade report CLI",)


def test_parse_use_command() -> None:
    result = parse_command("/use task-003")

    assert isinstance(result, TuiCommand)
    assert result.name == "use"
    assert result.args == ("task-003",)


def test_parse_bare_command_without_args() -> None:
    result = parse_command("/run")

    assert isinstance(result, TuiCommand)
    assert result.name == "run"
    assert result.args == ()


def test_unknown_command_returns_structured_error() -> None:
    result = parse_command("/frobnicate")

    assert isinstance(result, TuiCommandError)
    assert result.error_code == "unknown_tui_command"


def test_task_command_without_goal_is_error() -> None:
    result = parse_command("/task")

    assert isinstance(result, TuiCommandError)
    assert result.error_code == "tui_goal_required"


def test_use_command_without_task_id_is_error() -> None:
    result = parse_command("/use")

    assert isinstance(result, TuiCommandError)
    assert result.error_code == "tui_task_id_required"


def test_empty_input_is_error() -> None:
    result = parse_command("   ")

    assert isinstance(result, TuiCommandError)
    assert result.error_code == "tui_empty_input"


def test_quoted_goal_is_preserved_as_single_arg() -> None:
    result = parse_command('/task "import CSV, export report"')

    assert isinstance(result, TuiCommand)
    assert result.args == ("import CSV, export report",)


# ---------------------------------------------------------------------------
# Plain-text semantics
# ---------------------------------------------------------------------------


def test_plain_text_creates_task_when_no_active_task() -> None:
    intent = classify_plain_text(
        "Implement a student grade statistics CLI",
        has_active_task=False,
        waiting_input=False,
    )

    assert intent is PlainTextIntent.CREATE_TASK


def test_plain_text_answers_when_waiting_input() -> None:
    intent = classify_plain_text(
        "Use FastAPI.",
        has_active_task=True,
        waiting_input=True,
    )

    assert intent is PlainTextIntent.ANSWER


def test_plain_text_is_rejected_during_normal_idle() -> None:
    intent = classify_plain_text(
        "just chatting",
        has_active_task=True,
        waiting_input=False,
    )

    assert intent is PlainTextIntent.REJECT
