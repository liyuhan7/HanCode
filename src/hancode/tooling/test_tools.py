"""Deterministic adapter for the configured project test command."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import shlex
import subprocess

from hancode.tooling.file_tools import redact_text
from hancode.tooling.registry import ToolResult


TestRunner = Callable[..., subprocess.CompletedProcess[str]]
_SHELL_OPERATOR_CHARS = frozenset("&|;<>$`\r\n")


def run_tests(
    project_root: Path,
    command: str | None,
    *,
    runner: TestRunner | None = None,
    timeout_seconds: float = 120.0,
) -> ToolResult:
    if not isinstance(command, str) or not command.strip():
        return _failed("No configured test command.")
    if any(character in command for character in _SHELL_OPERATOR_CHARS):
        return _failed("Shell syntax is not supported for test commands.")
    try:
        argv = shlex.split(command)
    except ValueError:
        return _failed("Configured test command is invalid.")
    if not argv:
        return _failed("No configured test command.")

    redacted_command = redact_text(command)
    selected_runner = subprocess.run if runner is None else runner
    try:
        completed = selected_runner(
            argv,
            cwd=project_root,
            text=True,
            capture_output=True,
            check=False,
            shell=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        return ToolResult(
            success=False,
            action_name="run_tests",
            error_summary="Test command timed out.",
            stdout=_redacted_output(exc.output),
            stderr=_redacted_output(exc.stderr),
            timed_out=True,
            command=redacted_command,
        )
    except OSError as exc:
        return ToolResult(
            success=False,
            action_name="run_tests",
            error_summary=f"Test command could not be started: {type(exc).__name__}.",
            command=redacted_command,
        )

    return ToolResult(
        success=completed.returncode == 0,
        action_name="run_tests",
        error_summary=None if completed.returncode == 0 else "Test command failed.",
        exit_code=completed.returncode,
        stdout=_redacted_output(completed.stdout),
        stderr=_redacted_output(completed.stderr),
        command=redacted_command,
    )


def _failed(error_summary: str) -> ToolResult:
    return ToolResult(
        success=False,
        action_name="run_tests",
        error_summary=error_summary,
        command=None,
    )


def _text_output(value: str | bytes | None) -> str | None:
    if isinstance(value, str) or value is None:
        return value
    return value.decode("utf-8", errors="replace")


def _redacted_output(value: str | bytes | None) -> str | None:
    output = _text_output(value)
    return None if output is None else redact_text(output)
