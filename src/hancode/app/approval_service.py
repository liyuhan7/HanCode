"""Approval service: application-layer facade for human approval decisions.

Provides approve/reject/get_pending operations with proper locking,
idempotency, and conflict detection.
"""

from __future__ import annotations

from pathlib import Path

from hancode.app.task_models import TaskSummary
from hancode.core.approvals import ApprovalStatus, is_valid_approval_id
from hancode.core.errors import HanCodeError, StructuredError
from hancode.core.state import load_state
from hancode.storage.approvals import ApprovalStore
from hancode.storage.task_lock import FilesystemTaskMutationGuard
from hancode.storage.workspace import task_path


class ApprovalService:
    """Manages the lifecycle of approval requests: view, approve, reject."""

    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root.resolve()
        self._project_id = self._resolve_project_id()

    def _resolve_project_id(self) -> str:
        try:
            from hancode.storage.workspace import load_project_metadata
            metadata = load_project_metadata(
                self._project_root / ".hancode" / "project.json"
            )
            return str(metadata.get("project_id", "unknown"))
        except Exception:
            return "unknown"

    def _store(self) -> ApprovalStore:
        return ApprovalStore(self._project_root, self._project_id)

    def get_pending(
        self,
        task_id: str,
    ) -> dict[str, object] | None:
        """Get the pending approval for a task, if any."""
        state = load_state(task_path(self._project_root, task_id))
        if state.pending_approval_id is None:
            return None

        approval_id = state.pending_approval_id
        try:
            record = self._store().load_pending(task_id, approval_id)
        except HanCodeError:
            return {
                "approval_id": approval_id,
                "status": "unknown",
                "error": "Could not load approval record.",
            }

        return {
            "approval_id": record.approval_id,
            "phase": record.phase.value,
            "category": record.category.value,
            "tool_name": record.action.tool_name,
            "targets": [t.path for t in record.targets],
            "reason": record.action.reason,
            "status": record.status.value,
            "preview": record.preview.to_dict() if record.preview else None,
        }

    def approve(
        self,
        task_id: str,
        *,
        approval_id: str | None = None,
    ) -> TaskSummary:
        """Approve a pending approval request.

        Idempotent: if already approved, returns success.
        Conflicts: if already rejected/expired/consumed, raises error.
        """
        return self._decide(task_id, approved=True, approval_id=approval_id)

    def reject(
        self,
        task_id: str,
        *,
        approval_id: str | None = None,
        reason: str | None = None,
    ) -> TaskSummary:
        """Reject a pending approval request.

        Idempotent: if already rejected, returns success.
        Conflicts: if already approved/expired/consumed, raises error.
        """
        return self._decide(
            task_id,
            approved=False,
            approval_id=approval_id,
            reason=reason,
        )

    def _decide(
        self,
        task_id: str,
        *,
        approved: bool,
        approval_id: str | None = None,
        reason: str | None = None,
    ) -> TaskSummary:
        task_root = task_path(self._project_root, task_id)
        guard = FilesystemTaskMutationGuard(
            self._project_root,
            task_path_resolver=lambda root, tid: task_path(root, tid),
        )

        with guard.acquire(task_id, None):  # type: ignore[arg-type]
            state = load_state(task_root)

            if approval_id is None:
                approval_id = state.pending_approval_id

            if approval_id is None or not is_valid_approval_id(approval_id):
                raise HanCodeError(
                    StructuredError(
                        error_code="approval_id_mismatch",
                        message="No valid pending approval to decide.",
                        phase=state.current_phase.value,
                        denied_rule="approval_id_required",
                        suggested_fix="Verify the task has a pending approval.",
                    )
                )

            store = self._store()

            try:
                record = store.load_pending(task_id, approval_id)
            except HanCodeError as exc:
                raise HanCodeError(
                    StructuredError(
                        error_code="approval_not_found",
                        message=f"Approval {approval_id} not found.",
                        phase=state.current_phase.value,
                        denied_rule="approval_not_found",
                        suggested_fix="Verify the approval ID.",
                    )
                ) from exc

            # Check for conflicts
            if record.status is ApprovalStatus.APPROVED and not approved:
                raise HanCodeError(
                    StructuredError(
                        error_code="approval_decision_conflict",
                        message=f"Approval {approval_id} is already approved; cannot reject.",
                        phase=record.phase.value,
                        denied_rule="approval_decision_conflict",
                        suggested_fix="The approval has already been approved.",
                    )
                )

            if record.status is ApprovalStatus.REJECTED and approved:
                raise HanCodeError(
                    StructuredError(
                        error_code="approval_decision_conflict",
                        message=f"Approval {approval_id} is already rejected; cannot approve.",
                        phase=record.phase.value,
                        denied_rule="approval_decision_conflict",
                        suggested_fix="The approval has already been rejected.",
                    )
                )

            # Idempotency: re-issuing the SAME decision is a no-op success. The
            # underlying store only transitions from PENDING, so short-circuit
            # here to honour the documented idempotent contract without a
            # second (illegal) transition or overwriting the original reason.
            if record.status is ApprovalStatus.APPROVED and approved:
                return TaskSummary.from_state(state)
            if record.status is ApprovalStatus.REJECTED and not approved:
                return TaskSummary.from_state(state)

            if record.status in {ApprovalStatus.EXECUTING, ApprovalStatus.CONSUMED}:
                raise HanCodeError(
                    StructuredError(
                        error_code="approval_already_consumed",
                        message=f"Approval {approval_id} has already been {record.status.value}.",
                        phase=record.phase.value,
                        denied_rule="approval_already_consumed",
                        suggested_fix="Create a new task to generate a new approval request.",
                    )
                )

            if record.status is ApprovalStatus.EXPIRED:
                raise HanCodeError(
                    StructuredError(
                        error_code="approval_expired",
                        message=f"Approval {approval_id} has expired.",
                        phase=record.phase.value,
                        denied_rule="approval_expired",
                        suggested_fix="Run the task again to generate a new approval request.",
                    )
                )

            # Perform the decision
            store.decide(
                task_id,
                approved,
                approval_id=approval_id,
                reason=reason,
            )

            # Reload state
            state = load_state(task_root)
            return TaskSummary.from_state(state)
