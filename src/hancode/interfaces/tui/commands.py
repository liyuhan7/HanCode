"""Textual-independent command parsing and plain-text semantics (S4-T4).

CommandParser turns raw composer input into a :class:`TuiCommand` or a
:class:`TuiCommandError`. It performs no business action — the controller maps
commands to application services. Plain text (no leading ``/``) is classified by
:func:`classify_plain_text` into create-task / answer / reject, so HanCode never
becomes an unbounded free-chat agent.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from enum import Enum


_MAX_INPUT_CHARS = 8192

# command name -> (min_args, max_args or None for unbounded, missing-arg error)
_COMMANDS: dict[str, tuple[int, int | None, str]] = {
    "help": (0, 0, ""),
    "task": (1, None, "tui_goal_required"),
    "tasks": (0, 0, ""),
    "use": (1, 1, "tui_task_id_required"),
    "run": (0, 0, ""),
    "resume": (0, 0, ""),
    "approve": (0, 0, ""),
    "reject": (0, None, ""),
    "status": (0, 0, ""),
    "trace": (0, 0, ""),
    "artifacts": (0, 0, ""),
    "open": (1, 1, "tui_artifact_name_required"),
    "rollback": (0, 1, ""),
    "clear": (0, 0, ""),
    "quit": (0, 0, ""),
}


@dataclass(frozen=True, slots=True)
class TuiCommand:
    name: str
    args: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TuiCommandError:
    error_code: str
    message: str
    suggested_fix: str


class PlainTextIntent(Enum):
    CREATE_TASK = "create_task"
    ANSWER = "answer"
    REJECT = "reject"
    # When a task is paused for approval, plain text is intentionally inert:
    # approve/reject are irreversible outward decisions and must be explicit
    # (/approve, /reject <reason>), never inferred from stray keystrokes.
    APPROVAL_REQUIRES_COMMAND = "approval_requires_command"


def parse_command(raw: str) -> TuiCommand | TuiCommandError:
    """Parse composer input beginning with ``/`` into a command."""
    if not isinstance(raw, str) or not raw.strip():
        return TuiCommandError(
            "tui_empty_input",
            "No command was entered.",
            "Type /help to see available commands.",
        )
    if len(raw) > _MAX_INPUT_CHARS:
        return TuiCommandError(
            "tui_input_too_long",
            "The command input exceeds the length limit.",
            "Shorten the input before submitting.",
        )

    text = raw.strip()
    if not text.startswith("/"):
        return TuiCommandError(
            "tui_not_a_command",
            "Commands must start with '/'.",
            "Prefix commands with '/', or type plain text where allowed.",
        )

    body = text[1:]
    try:
        tokens = shlex.split(body)
    except ValueError:
        return TuiCommandError(
            "tui_command_unparseable",
            "The command could not be parsed (check quoting).",
            "Balance quotes and retry.",
        )
    if not tokens:
        return TuiCommandError(
            "tui_empty_input",
            "No command was entered.",
            "Type /help to see available commands.",
        )

    name = tokens[0].lower()
    args = tuple(tokens[1:])
    spec = _COMMANDS.get(name)
    if spec is None:
        return TuiCommandError(
            "unknown_tui_command",
            f"Unknown command: /{name}.",
            "Type /help to see available commands.",
        )

    min_args, max_args, missing_error = spec
    if len(args) < min_args:
        return TuiCommandError(
            missing_error,
            f"/{name} requires more arguments.",
            "Provide the required argument for this command.",
        )
    if max_args is not None and len(args) > max_args:
        return TuiCommandError(
            "tui_too_many_arguments",
            f"/{name} received too many arguments.",
            "Remove the extra arguments.",
        )
    if name == "task":
        # Preserve the whole goal (possibly multi-word) as one argument.
        goal = body[len("task") :].strip()
        if (goal.startswith('"') and goal.endswith('"')) or (
            goal.startswith("'") and goal.endswith("'")
        ):
            goal = goal[1:-1]
        return TuiCommand(name="task", args=(goal,))

    return TuiCommand(name=name, args=args)


def classify_plain_text(
    text: str,
    *,
    has_active_task: bool,
    waiting_input: bool,
    waiting_approval: bool = False,
) -> PlainTextIntent:
    """Decide what plain (non-command) composer text means for the current state."""
    if waiting_approval:
        # A pending approval takes precedence: never let plain text implicitly
        # decide it. The user must type /approve or /reject <reason>.
        return PlainTextIntent.APPROVAL_REQUIRES_COMMAND
    if waiting_input:
        return PlainTextIntent.ANSWER
    if not has_active_task:
        return PlainTextIntent.CREATE_TASK
    return PlainTextIntent.REJECT


__all__ = [
    "TuiCommand",
    "TuiCommandError",
    "PlainTextIntent",
    "parse_command",
    "classify_plain_text",
]
