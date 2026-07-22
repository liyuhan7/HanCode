"""CheckpointInspectionService — application-level checkpoint listing (S4-R4)."""

from __future__ import annotations

from pathlib import Path

from hancode.core.change_models import CheckpointSummary
from hancode.storage.checkpoint_queries import CheckpointQueryRepository
from hancode.storage.workspace import task_path


class CheckpointInspectionService:
    """List checkpoints for a task as safe public summaries."""

    def list_checkpoints(self, project_root: Path, task_id: str) -> tuple[CheckpointSummary, ...]:
        task_root = task_path(project_root, task_id)
        repo = CheckpointQueryRepository()
        manifests = repo.list(task_root)
        return tuple(
            CheckpointSummary(
                checkpoint_id=m.checkpoint_id,
                phase=m.phase,
                reason=m.reason,
                created_at=m.created_at.isoformat(),
                status=m.status,
                files=tuple(f.path for f in m.files),
                rollback_available=m.rollback_available,
            )
            for m in manifests
        )
