"""run_build tool — S4-R2.

The build command is ALWAYS read from config.build_command. The model cannot
supply an arbitrary command.  Reuses the shared command_runner for shell=False,
fixed cwd, timeout, and output redaction.
"""

from __future__ import annotations

from pathlib import Path

from hancode.tooling.command_runner import CommandRunner, run_configured_command
from hancode.tooling.registry import ToolResult


def run_build(
    project_root: Path,
    command: str | None,
    *,
    runner: CommandRunner | None = None,
    timeout_seconds: float = 300.0,
    max_output_chars: int = 20_000,
) -> ToolResult:
    return run_configured_command(
        action_name="run_build",
        project_root=project_root,
        command=command,
        timeout_seconds=timeout_seconds,
        max_output_chars=max_output_chars,
        runner=runner,
    )
