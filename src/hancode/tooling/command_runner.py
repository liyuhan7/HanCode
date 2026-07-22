from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from typing import Any, Callable

from hancode.tooling.file_tools import redact_text
from hancode.tooling.registry import ToolResult


_RunnerType = Callable[..., subprocess.CompletedProcess[str]]


class CommandRunner:
    def __init__(self, delegate: _RunnerType | None = None) -> None:
        self._delegate: _RunnerType = delegate or subprocess.run

    def run(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return self._delegate(argv, **kwargs)


def run_configured_command(
    *,
    action_name: str,
    project_root: Path,
    command: str | None,
    timeout_seconds: float = 120.0,
    max_output_chars: int = 10_000,
    runner: CommandRunner | None = None,
) -> ToolResult:
    if not isinstance(command, str) or not command.strip():
        return ToolResult(
            success=False,
            action_name=action_name,
            error_summary=f"No configured {action_name} command.",
        )

    try:
        argv = shlex.split(command)
    except ValueError:
        return ToolResult(
            success=False,
            action_name=action_name,
            error_summary=f"Configured {action_name} command is invalid.",
        )

    if not argv:
        return ToolResult(
            success=False,
            action_name=action_name,
            error_summary=f"No configured {action_name} command.",
        )

    selected_runner = runner or CommandRunner()

    try:
        completed = selected_runner.run(
            argv,
            cwd=str(project_root),
            text=True,
            capture_output=True,
            check=False,
            shell=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        return ToolResult(
            success=False,
            action_name=action_name,
            error_summary=f"{action_name} timed out.",
            stdout=_redact_and_truncate(_text_output(exc.output), max_output_chars),
            stderr=_redact_and_truncate(_text_output(exc.stderr), max_output_chars),
            timed_out=True,
            command=redact_text(command),
        )
    except OSError as exc:
        return ToolResult(
            success=False,
            action_name=action_name,
            error_summary=f"{action_name} could not be started: {type(exc).__name__}.",
            command=redact_text(command),
        )

    stdout = _redact_and_truncate(_text_output(completed.stdout), max_output_chars)
    stderr = _redact_and_truncate(_text_output(completed.stderr), max_output_chars)

    return ToolResult(
        success=completed.returncode == 0,
        action_name=action_name,
        error_summary=None if completed.returncode == 0 else f"{action_name} failed.",
        exit_code=completed.returncode,
        stdout=stdout,
        stderr=stderr,
        command=redact_text(command),
    )


def _text_output(value: str | bytes | None) -> str | None:
    if isinstance(value, str) or value is None:
        return value
    return value.decode("utf-8", errors="replace")


def _redact_and_truncate(value: str | None, max_chars: int) -> str | None:
    if value is None:
        return None
    redacted = redact_text(value)
    if len(redacted) > max_chars:
        return redacted[:max_chars]
    return redacted
