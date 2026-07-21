"""Application service for controlled checkpoint rollback (S4-T7).

The TUI never calls the storage RollbackManager directly. RecoveryService:
- previews the affected files strictly from the checkpoint manifest (never a
  guess), so the confirmation dialog is truthful;
- performs the rollback under the shared task mutation lock and reconciles state.
"""

from __future__ import annotations

import json
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

        manifest_path = task_root / "checkpoints" / checkpoint_id / "manifest.json"
        if _is_link(manifest_path) or not manifest_path.is_file():
            return RollbackPreview(
                checkpoint_id=checkpoint_id, available=False, files=()
            )
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return RollbackPreview(
                checkpoint_id=checkpoint_id, available=False, files=()
            )
        if not isinstance(manifest, dict):
            return RollbackPreview(
                checkpoint_id=checkpoint_id, available=False, files=()
            )

        available = bool(manifest.get("rollback_available", False))
        files = tuple(
            str(entry.get("path"))
            for entry in manifest.get("files", [])
            if isinstance(entry, dict) and isinstance(entry.get("path"), str)
        )
        return RollbackPreview(
            checkpoint_id=checkpoint_id, available=available, files=files
        )

    def rollback_last(self, project_root: Path, task_id: str) -> RecoverySummary:
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
