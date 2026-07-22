"""ChangeInspectionService — application-level diff query (S4-R1).

The service mediates between CLI/TUI callers and the low-level get_diff tool,
ensuring proper task workspace resolution and scope handling.
"""

from __future__ import annotations

from pathlib import Path

from hancode.core.change_models import DiffScope, TaskDiff
from hancode.core.errors import HanCodeError, StructuredError
from hancode.storage.workspace import task_path
from hancode.tooling.diff_tools import get_diff


class ChangeInspectionService:
    """Application service for querying task diffs."""

    def get_diff(
        self,
        project_root: Path,
        task_id: str,
        *,
        scope: DiffScope = DiffScope.TASK,
        path: str | None = None,
    ) -> TaskDiff:
        task_root = task_path(project_root, task_id)
        result = get_diff(
            project_root,
            task_root,
            scope=scope.value,
            path=path,
        )
        if not result.success:
            raise HanCodeError(
                StructuredError(
                    error_code="diff_failed",
                    message=result.error_summary or "Diff generation failed.",
                    phase="code",
                    denied_rule="diff_failed",
                    suggested_fix="Verify task checkpoints and workspace integrity.",
                )
            )
        output = result.output
        if not isinstance(output, dict):
            raise HanCodeError(
                StructuredError(
                    error_code="diff_failed",
                    message="Diff returned an invalid result.",
                    phase="code",
                    denied_rule="diff_failed",
                    suggested_fix="Retry the diff operation.",
                )
            )
        # Reconstruct TaskDiff from dict output
        from hancode.core.change_models import ChangeType, FileDiff

        files = tuple(
            FileDiff(
                path=f["path"],
                change_type=ChangeType(f["change_type"]),
                before_sha256=f["before_sha256"],
                current_sha256=f["current_sha256"],
                binary=f["binary"],
                drifted=f["drifted"],
                unified_diff=f["unified_diff"],
                truncated=f["truncated"],
            )
            for f in output["files"]
        )

        return TaskDiff(
            task_id=output["task_id"],
            scope=DiffScope(output["scope"]),
            checkpoint_ids=tuple(output["checkpoint_ids"]),
            files=files,
            truncated=output["truncated"],
            risks=tuple(output["risks"]),
        )
