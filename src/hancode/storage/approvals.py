"""Approval manifest persistence and lifecycle management.

Approval manifests are stored under:
    .hancode/tasks/<task-id>/approvals/<approval-id>.json

All writes use atomic temp-file + os.replace to avoid corruption.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from tempfile import mkstemp
from typing import Mapping

from hancode.core.approvals import (
    ApprovalRecord,
    ApprovalStatus,
    is_valid_approval_id,
)
from hancode.core.errors import HanCodeError, StructuredError
from hancode.core.models import TaskStatus
from dataclasses import replace as state_replace

from hancode.core.state import TaskState, save_state
from hancode.storage.workspace import task_path


def _approvals_dir(project_root: Path, task_id: str) -> Path:
    return task_path(project_root, task_id) / "approvals"


def _approval_path(project_root: Path, task_id: str, approval_id: str) -> Path:
    return _approvals_dir(project_root, task_id) / f"{approval_id}.json"


def _atomic_write_json(path: Path, data: Mapping[str, object]) -> None:
    """Write JSON atomically using temp file + os.replace."""
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = mkstemp(dir=str(parent), prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, str(path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def save_approval_manifest(
    project_root: Path, task_id: str, record: ApprovalRecord
) -> None:
    """Persist an approval manifest atomically."""
    if not is_valid_approval_id(record.approval_id):
        raise HanCodeError(
            StructuredError(
                error_code="approval_manifest_invalid",
                message=f"Invalid approval ID: {record.approval_id!r}.",
                phase=record.phase.value,
                denied_rule="approval_id_format",
                suggested_fix="Use format_approval_id() to generate valid IDs.",
            )
        )
    target = _approval_path(project_root, task_id, record.approval_id)
    _atomic_write_json(target, record.to_dict())


def load_approval_manifest(
    project_root: Path, task_id: str, approval_id: str
) -> ApprovalRecord:
    """Load a persisted approval manifest."""
    if not is_valid_approval_id(approval_id):
        raise HanCodeError(
            StructuredError(
                error_code="approval_manifest_invalid",
                message=f"Invalid approval ID: {approval_id!r}.",
                phase="unknown",
                denied_rule="approval_id_format",
                suggested_fix="Use a valid apr-XXXXXX format.",
            )
        )
    target = _approval_path(project_root, task_id, approval_id)
    if not target.is_file():
        raise HanCodeError(
            StructuredError(
                error_code="approval_not_found",
                message=f"Approval manifest not found: {approval_id}.",
                phase="unknown",
                denied_rule="approval_manifest_missing",
                suggested_fix="Verify the approval ID is correct.",
            )
        )
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Not a JSON object")
        return ApprovalRecord.from_dict(data)
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        raise HanCodeError(
            StructuredError(
                error_code="approval_manifest_invalid",
                message=f"Cannot parse approval manifest: {approval_id}.",
                phase="unknown",
                denied_rule="approval_manifest_corrupt",
                suggested_fix="Delete the corrupt manifest and retry.",
            )
        ) from exc


class ApprovalStore:
    """Manages approval lifecycle: create, load, update, and validate."""

    def __init__(self, project_root: Path, project_id: str) -> None:
        self._project_root = project_root.resolve()
        self._project_id = project_id

    def create(
        self,
        task_id: str,
        state: TaskState,
        record: ApprovalRecord,
    ) -> tuple[TaskState, ApprovalRecord]:
        """Persist a pending approval and update task state.

        Returns the updated TaskState and the persisted ApprovalRecord.
        Transaction order:
        1. Write pending approval manifest
        2. Update and save TaskState (WAITING_APPROVAL)
        On failure: try to clean up the manifest.
        """
        if record.status is not ApprovalStatus.PENDING:
            raise HanCodeError(
                StructuredError(
                    error_code="approval_not_pending",
                    message="Only pending approvals can be created.",
                    phase=record.phase.value,
                    denied_rule="approval_must_be_pending",
                    suggested_fix="Create the record with PENDING status.",
                )
            )

        # 1. Write the approval manifest
        try:
            save_approval_manifest(self._project_root, task_id, record)
        except HanCodeError:
            raise
        except Exception as exc:
            raise HanCodeError(
                StructuredError(
                    error_code="approval_persistence_inconsistent",
                    message=f"Failed to write approval manifest: {exc}.",
                    phase=record.phase.value,
                    denied_rule="approval_persistence_failed",
                    suggested_fix="Check disk space and permissions.",
                )
            ) from exc

        # 2. Update task state
        updated_state = state_replace(
            state,
            status=TaskStatus.WAITING_APPROVAL,
            approval_seq=state.approval_seq + 1,
            pending_approval_id=record.approval_id,
        )

        try:
            save_state(task_path(self._project_root, task_id), updated_state)
        except HanCodeError:
            # Compensation: delete the manifest
            try:
                manifest_path = _approval_path(
                    self._project_root, task_id, record.approval_id
                )
                if manifest_path.is_file():
                    manifest_path.unlink()
            except OSError:
                pass
            raise
        except Exception as exc:
            # Compensation: delete the manifest
            try:
                manifest_path = _approval_path(
                    self._project_root, task_id, record.approval_id
                )
                if manifest_path.is_file():
                    manifest_path.unlink()
            except OSError:
                pass
            raise HanCodeError(
                StructuredError(
                    error_code="approval_persistence_inconsistent",
                    message=f"Failed to save task state after approval create: {exc}.",
                    phase=record.phase.value,
                    denied_rule="approval_state_persistence_failed",
                    suggested_fix="Check disk space and permissions.",
                )
            ) from exc

        return updated_state, record

    def load_pending(
        self, task_id: str, approval_id: str
    ) -> ApprovalRecord:
        """Load a pending approval manifest."""
        if not is_valid_approval_id(approval_id):
            raise HanCodeError(
                StructuredError(
                    error_code="approval_id_mismatch",
                    message=f"Invalid approval ID: {approval_id!r}.",
                    phase="unknown",
                    denied_rule="approval_id_format",
                    suggested_fix="Use a valid apr-XXXXXX format.",
                )
            )
        return load_approval_manifest(self._project_root, task_id, approval_id)

    def decide(
        self,
        task_id: str,
        approved: bool,
        *,
        approval_id: str,
        reason: str | None = None,
    ) -> ApprovalRecord:
        """Approve or reject a pending approval.

        Returns the updated record. The task state is NOT modified here;
        the AgentLoop will consume the decision on resume.
        """
        record = load_approval_manifest(self._project_root, task_id, approval_id)

        if record.status is not ApprovalStatus.PENDING:
            raise HanCodeError(
                StructuredError(
                    error_code="approval_not_pending",
                    message=f"Approval {approval_id} is already {record.status.value}.",
                    phase=record.phase.value,
                    denied_rule="approval_not_pending",
                    suggested_fix="The approval has already been decided or expired.",
                )
            )

        new_status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
        decided_at = datetime.now(timezone.utc).isoformat()

        updated = record.with_status(
            new_status,
            decided_at=decided_at,
            rejection_reason=reason if not approved else None,
        )

        save_approval_manifest(self._project_root, task_id, updated)
        return updated

    def mark_executing(
        self,
        task_id: str,
        approval_id: str,
        *,
        expected_checkpoint_id: str,
    ) -> ApprovalRecord:
        """Mark an approved record as executing."""
        record = load_approval_manifest(self._project_root, task_id, approval_id)

        if record.status is not ApprovalStatus.APPROVED:
            raise HanCodeError(
                StructuredError(
                    error_code="approval_not_approved",
                    message=f"Approval {approval_id} is {record.status.value}, not approved.",
                    phase=record.phase.value,
                    denied_rule="approval_not_approved",
                    suggested_fix="Only approved approvals can be marked as executing.",
                )
            )

        updated = record.with_executing(
            expected_checkpoint_id=expected_checkpoint_id,
            executed_at=datetime.now(timezone.utc).isoformat(),
        )
        save_approval_manifest(self._project_root, task_id, updated)
        return updated

    def mark_consumed(
        self,
        task_id: str,
        approval_id: str,
        *,
        execution_checkpoint_id: str | None = None,
    ) -> ApprovalRecord:
        """Mark an executing/approved record as consumed."""
        record = load_approval_manifest(self._project_root, task_id, approval_id)
        updated = record.with_consumed(
            execution_checkpoint_id=execution_checkpoint_id
        )
        save_approval_manifest(self._project_root, task_id, updated)
        return updated

    def mark_expired(
        self, task_id: str, approval_id: str
    ) -> ApprovalRecord:
        """Mark an approval as expired (stale)."""
        record = load_approval_manifest(self._project_root, task_id, approval_id)
        updated = record.with_expired()
        save_approval_manifest(self._project_root, task_id, updated)
        return updated
