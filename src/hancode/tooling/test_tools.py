"""Deterministic adapter for the configured project test command."""

from __future__ import annotations

from collections.abc import Callable
import locale
from pathlib import Path
import shlex
import subprocess

from hancode.tooling.file_tools import redact_text
from hancode.tooling.registry import ToolResult


TestRunner = Callable[
    ...,
    subprocess.CompletedProcess[str] | subprocess.CompletedProcess[bytes],
]
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
            text=False,
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
        stable_fields = [
            f"errno={exc.errno}" if exc.errno is not None else None,
            (
                f"winerror={exc.winerror}"
                if getattr(exc, "winerror", None) is not None
                else None
            ),
        ]
        metadata = ", ".join(field for field in stable_fields if field is not None)
        return ToolResult(
            success=False,
            action_name="run_tests",
            error_summary=(
                f"Test command could not be started: {type(exc).__name__}"
                f"{f' ({metadata})' if metadata else ''}."
            ),
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
    if value.startswith((b"\xff\xfe", b"\xfe\xff")):
        return value.decode("utf-16", errors="replace")
    if b"\x00" in value:
        even_nulls = value[0::2].count(0)
        odd_nulls = value[1::2].count(0)
        encoding = "utf-16-le" if odd_nulls >= even_nulls else "utf-16-be"
        try:
            return value.decode(encoding)
        except UnicodeDecodeError:
            pass
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError:
        return value.decode(locale.getpreferredencoding(False), errors="replace")


def _redacted_output(value: str | bytes | None) -> str | None:
    output = _text_output(value)
    return None if output is None else redact_text(output)
