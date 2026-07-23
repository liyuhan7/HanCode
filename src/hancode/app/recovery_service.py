"""Application service for controlled checkpoint rollback (S4-T7).

The TUI never calls the storage RollbackManager directly. RecoveryService:
- previews the affected files strictly from the checkpoint manifest (never a
  guess), so the confirmation dialog is truthful;
- performs the rollback under the shared task mutation lock and reconciles state.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from hancode.core.errors import HanCodeError, StructuredError
from hancode.core.models import OperationStatus
from hancode.core.state import load_state, reconcile_state
from hancode.storage.checkpoints import rollback_last_checkpoint
from hancode.storage.task_lock import FilesystemTaskMutationGuard
from hancode.storage.workspace import task_path


@dataclass(frozen=True, slots=True)
class RollbackPreview:
    checkpoint_id: str | None
    available: bool
    files: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RecoverySummary:
    checkpoint_id: str | None
    restored_files: tuple[str, ...]
    failed_files: tuple[str, ...]


class RecoveryService:
    """Preview and perform controlled rollback of the latest checkpoint."""

    def preview_last(self, project_root: Path, task_id: str) -> RollbackPreview:
        task_root = task_path(project_root, task_id)
        state = reconcile_state(task_root, load_state(task_root))
        checkpoint_id = state.latest_checkpoint
        if checkpoint_id is None:
            return RollbackPreview(checkpoint_id=None, available=False, files=())

        from hancode.storage.checkpoint_queries import CheckpointQueryRepository
        repo = CheckpointQueryRepository()
        try:
            manifest = repo.get(task_root, checkpoint_id)
        except Exception:
            return RollbackPreview(
                checkpoint_id=checkpoint_id, available=False, files=(),
            )

        return RollbackPreview(
            checkpoint_id=checkpoint_id,
            available=manifest.rollback_available,
            files=tuple(f.path for f in manifest.files),
        )

    def rollback_last(
        self,
        project_root: Path,
        task_id: str,
        *,
        expected_checkpoint_id: str | None = None,
    ) -> RecoverySummary:
        task_root = task_path(project_root, task_id)
        state = reconcile_state(task_root, load_state(task_root))
        if state.latest_checkpoint is None:
            raise _recovery_error(
                "recovery_checkpoint_required",
                "The task has no checkpoint to roll back to.",
                "Run the task until it creates a checkpoint before rolling back.",
            )

        guard = FilesystemTaskMutationGuard(project_root)
        with guard.acquire(task_id, state.current_phase):
            locked_state = reconcile_state(task_root, load_state(task_root))
            if (
                expected_checkpoint_id is not None
                and locked_state.latest_checkpoint != expected_checkpoint_id
            ):
                raise _recovery_error(
                    "rollback_preview_stale",
                    "The rollback preview is stale because the latest checkpoint changed.",
                    "Preview rollback again and confirm the current latest checkpoint.",
                )
            result = rollback_last_checkpoint(task_root)
        if result.status is not OperationStatus.SUCCEEDED:
            raise HanCodeError(
                result.error
                or StructuredError(
                    error_code="recovery_failed",
                    message="The rollback did not succeed.",
                    phase=state.current_phase.value,
                    denied_rule="recovery_failed",
                    suggested_fix="Inspect the task state and trace before retrying.",
                )
            )
        return RecoverySummary(
            checkpoint_id=result.checkpoint_id,
            restored_files=result.restored_files,
            failed_files=result.failed_files,
        )


def _is_link(path: Path) -> bool:
    try:
        junction_probe = getattr(path, "is_junction", None)
        return path.is_symlink() or (
            bool(junction_probe()) if callable(junction_probe) else False
        )
    except (AttributeError, OSError, RuntimeError):
        return True


def _recovery_error(
    error_code: str, message: str, suggested_fix: str
) -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code=error_code,
            message=message,
            phase="review",
            denied_rule=error_code,
            suggested_fix=suggested_fix,
        )
    )


__all__ = ["RecoveryService", "RollbackPreview", "RecoverySummary"]
