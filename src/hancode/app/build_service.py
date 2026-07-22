"""BuildService — application-level build execution (S4-R2)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from hancode.core.config import load_config
from hancode.core.errors import HanCodeError, StructuredError
from hancode.tooling.build_tools import run_build


@dataclass(frozen=True, slots=True)
class BuildSummary:
    command: str
    status: Literal["passed", "failed", "timed_out"]
    exit_code: int | None
    stdout: str | None
    stderr: str | None
    timed_out: bool


class BuildService:
    """Execute the configured build command for a task."""

    def run(self, project_root: Path, task_id: str) -> BuildSummary:
        config = load_config(project_root, task_id)
        if not config.build_command:
            raise HanCodeError(
                StructuredError(
                    error_code="build_command_missing",
                    message="No build command configured for this project.",
                    phase="test",
                    denied_rule="build_command_required",
                    suggested_fix="Set build_command in .hancode/project.json.",
                )
            )
        result = run_build(project_root, config.build_command)
        status: Literal["passed", "failed", "timed_out"]
        if result.timed_out:
            status = "timed_out"
        elif result.success:
            status = "passed"
        else:
            status = "failed"

        return BuildSummary(
            command=result.command or config.build_command,
            status=status,
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            timed_out=result.timed_out,
        )
