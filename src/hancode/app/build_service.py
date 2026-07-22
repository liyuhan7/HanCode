"""BuildService — application-level build execution (S4-R2)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from hancode.core.config import load_config
from hancode.core.errors import HanCodeError, StructuredError
from hancode.core.state import load_state, save_state
from hancode.storage.trace import append_trace
from hancode.storage.workspace import task_path
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

        task_root = task_path(project_root, task_id)
        state = load_state(task_root)
        save_state(
            task_root,
            replace(
                state,
                builds_run=(*state.builds_run, result.command or config.build_command),
                latest_build_status=status,
            ),
        )
        append_trace(
            task_root,
            event_type="tool_completed" if result.success else "tool_failed",
            task_id=task_id,
            phase=state.current_phase,
            status="succeeded" if result.success else "failed",
            action={
                "tool_name": "run_build",
                "args": {},
                "reason": "Run configured build.",
                "policy_decision": {
                    "allowed": True,
                    "message": "Configured build command.",
                    "phase": state.current_phase.value,
                    "requires_checkpoint": False,
                    "target_zone": None,
                    "denied_rule": None,
                    "suggested_fix": "",
                },
            },
            observation={
                "exit_code": result.exit_code,
                "timed_out": result.timed_out,
            },
            error_summary=None if result.success else result.error_summary or "Build failed.",
            state_transition={
                "latest_build_status": [state.latest_build_status, status]
            },
        )

        return BuildSummary(
            command=result.command or config.build_command,
            status=status,
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            timed_out=result.timed_out,
        )
