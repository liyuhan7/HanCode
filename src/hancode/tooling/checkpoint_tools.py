"""Checkpoint tools — list_checkpoints (S4-R4)."""

from __future__ import annotations

from pathlib import Path

from hancode.storage.checkpoint_queries import CheckpointQueryRepository
from hancode.tooling.registry import ToolResult


def list_checkpoints(project_root: Path, task_root: Path) -> ToolResult:
    """List checkpoints for the current task as safe public summaries."""
    task_root = task_root.resolve()
    repo = CheckpointQueryRepository()

    try:
        manifests = repo.list(task_root)
    except Exception as exc:
        return ToolResult(
            success=False,
            action_name="list_checkpoints",
            error_summary=f"Cannot list checkpoints: {exc}",
        )

    summaries: list[dict[str, object]] = []
    for m in manifests:
        summaries.append({
            "checkpoint_id": m.checkpoint_id,
            "phase": m.phase.value,
            "reason": m.reason,
            "created_at": m.created_at.isoformat(),
            "status": m.status,
            "files": [f.path for f in m.files],
            "rollback_available": m.rollback_available,
        })

    return ToolResult(
        success=True,
        action_name="list_checkpoints",
        output={
            "task_id": task_root.name,
            "checkpoints": summaries,
        },
    )
