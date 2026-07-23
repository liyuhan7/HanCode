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


def test_parse_approve_command() -> None:
    result = parse_command("/approve")

    assert isinstance(result, TuiCommand)
    assert result.name == "approve"
    assert result.args == ()


def test_parse_reject_command_with_reason() -> None:
    result = parse_command("/reject not this approach")

    assert isinstance(result, TuiCommand)
    assert result.name == "reject"
    assert result.args == ("not", "this", "approach")


def test_parse_reject_command_without_reason() -> None:
    result = parse_command("/reject")

    assert isinstance(result, TuiCommand)
    assert result.name == "reject"
    assert result.args == ()


def test_plain_text_while_waiting_approval_requires_command() -> None:
    # A pending approval must never be decided by stray plain text.
    intent = classify_plain_text(
        "yes go ahead",
        has_active_task=True,
        waiting_input=False,
        waiting_approval=True,
    )

    assert intent is PlainTextIntent.APPROVAL_REQUIRES_COMMAND


def test_waiting_approval_takes_precedence_over_waiting_input() -> None:
    intent = classify_plain_text(
        "text",
        has_active_task=True,
        waiting_input=True,
        waiting_approval=True,
    )

    assert intent is PlainTextIntent.APPROVAL_REQUIRES_COMMAND


def test_parse_inspection_commands_and_diff_arguments() -> None:
    assert parse_command("/diff latest src/main.py") == TuiCommand(
        name="diff", args=("latest", "src/main.py")
    )
    assert parse_command("/test") == TuiCommand(name="test", args=())
    assert parse_command("/checkpoints") == TuiCommand(name="checkpoints", args=())
    assert parse_command("/delivery") == TuiCommand(name="delivery", args=())
    assert parse_command("/trace evt-000001") == TuiCommand(
        name="trace", args=("evt-000001",)
    )


def test_parse_inspection_commands_reject_invalid_arguments() -> None:
    diff = parse_command("/diff src/main.py")
    artifact = parse_command("/open source.py")

    assert isinstance(diff, TuiCommandError)
    assert diff.error_code == "tui_diff_scope_invalid"
    assert isinstance(artifact, TuiCommandError)
    assert artifact.error_code == "tui_artifact_name_invalid"


def test_parse_export_requires_one_directory() -> None:
    result = parse_command("/export C:/tmp/delivery")

    assert result == TuiCommand(name="export", args=("C:/tmp/delivery",))
    missing = parse_command("/export")
    assert isinstance(missing, TuiCommandError)
    assert missing.error_code == "tui_export_directory_required"


def test_parse_build_command() -> None:
    assert parse_command("/build") == TuiCommand(name="build", args=())
