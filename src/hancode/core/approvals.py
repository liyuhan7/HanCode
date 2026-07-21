"""Domain model for human approval protocol.

Approval is a separate mechanism from ASK_USER interactions:
- ASK_USER: the model lacks information and needs user content.
- APPROVAL: the model has proposed a complete Action and needs the user to
  approve or reject execution.

Approval records are persisted under .hancode/tasks/<task-id>/approvals/.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import hashlib
import json
import re
from types import MappingProxyType
from typing import Mapping

from hancode.core.actions import ActionType
from hancode.core.models import Phase

_APPROVAL_ID_PATTERN = re.compile(r"^apr-\d{6}$")


class ApprovalStatus(str, Enum):
    """Lifecycle of an approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTING = "executing"
    CONSUMED = "consumed"
    EXPIRED = "expired"


class ApprovalCategory(str, Enum):
    """Why the approval was requested."""

    SOURCE_WRITE = "source_write"
    SOURCE_OVERWRITE = "source_overwrite"
    MULTI_FILE_WRITE = "multi_file_write"
    RUN_TESTS = "run_tests"
    RUN_BUILD = "run_build"
    ROLLBACK = "rollback"


@dataclass(frozen=True, slots=True)
class ApprovalTarget:
    """Describes a file that will be affected by the proposed action."""

    path: str
    exists: bool
    before_sha256: str | None
    size_bytes: int | None

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "exists": self.exists,
            "before_sha256": self.before_sha256,
            "size_bytes": self.size_bytes,
        }


@dataclass(frozen=True, slots=True)
class ApprovalActionSnapshot:
    """Canonical, deterministically-hashable snapshot of the Action to approve."""

    type: ActionType
    phase: Phase
    tool_name: str
    args: Mapping[str, object]
    reason: str
    sha256: str

    @classmethod
    def from_action(
        cls,
        *,
        action_type: ActionType,
        phase: Phase,
        tool_name: str | None,
        args: Mapping[str, object],
        reason: str | None,
    ) -> ApprovalActionSnapshot:
        if tool_name is None:
            raise ValueError("approval snapshot requires a tool_name")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("approval snapshot requires a non-empty reason")

        canonical = json.dumps(
            {
                "type": action_type.value,
                "phase": phase.value,
                "tool_name": tool_name,
                "args": dict(args),
                "reason": reason,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

        return cls(
            type=action_type,
            phase=phase,
            tool_name=tool_name,
            args=MappingProxyType(dict(args)),
            reason=reason,
            sha256=digest,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "type": self.type.value,
            "phase": self.phase.value,
            "tool_name": self.tool_name,
            "args": dict(self.args),
            "reason": self.reason,
            "sha256": self.sha256,
        }

    def digest_matches(self, other: ApprovalActionSnapshot) -> bool:
        """Compare two snapshots by sha256 digest."""
        return self.sha256 == other.sha256


@dataclass(frozen=True, slots=True)
class ApprovalPreview:
    """Bounded, redacted diff preview for the user — not the execution authority."""

    summary: str
    unified_diff: str | None
    truncated: bool
    redacted: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "summary": self.summary,
            "unified_diff": self.unified_diff,
            "truncated": self.truncated,
            "redacted": self.redacted,
        }


@dataclass(frozen=True, slots=True)
class ApprovalRecord:
    """Persisted approval manifest for one proposed action."""

    schema_version: int
    project_id: str
    task_id: str
    approval_id: str
    phase: Phase
    category: ApprovalCategory
    status: ApprovalStatus

    action: ApprovalActionSnapshot
    targets: tuple[ApprovalTarget, ...]
    preview: ApprovalPreview

    checkpoint_seq_at_request: int
    latest_checkpoint_at_request: str | None
    expected_checkpoint_id: str | None

    created_at: str
    decided_at: str | None
    executed_at: str | None

    rejection_reason: str | None
    execution_checkpoint_id: str | None

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("approval schema_version must be 1")
        if not isinstance(self.approval_id, str) or not _APPROVAL_ID_PATTERN.fullmatch(
            self.approval_id
        ):
            raise ValueError("approval_id must match apr-XXXXXX")
        if not isinstance(self.phase, Phase):
            raise ValueError("approval phase must be a Phase")
        if not isinstance(self.category, ApprovalCategory):
            raise ValueError("approval category must be an ApprovalCategory")
        if not isinstance(self.status, ApprovalStatus):
            raise ValueError("approval status must be an ApprovalStatus")
        if not isinstance(self.action, ApprovalActionSnapshot):
            raise ValueError("approval action must be an ApprovalActionSnapshot")
        if not isinstance(self.targets, tuple) or any(
            not isinstance(t, ApprovalTarget) for t in self.targets
        ):
            raise ValueError("approval targets must be a tuple of ApprovalTarget")
        if not isinstance(self.preview, ApprovalPreview):
            raise ValueError("approval preview must be an ApprovalPreview")
        if not isinstance(self.checkpoint_seq_at_request, int) or self.checkpoint_seq_at_request < 0:
            raise ValueError("checkpoint_seq_at_request must be non-negative")
        if not isinstance(self.created_at, str) or not self.created_at:
            raise ValueError("created_at must be non-empty")
        if self.rejection_reason is not None and (
            not isinstance(self.rejection_reason, str) or not self.rejection_reason.strip()
        ):
            raise ValueError("rejection_reason must be non-empty if provided")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "task_id": self.task_id,
            "approval_id": self.approval_id,
            "phase": self.phase.value,
            "category": self.category.value,
            "status": self.status.value,
            "action": self.action.to_dict(),
            "targets": [t.to_dict() for t in self.targets],
            "preview": self.preview.to_dict(),
            "checkpoint_seq_at_request": self.checkpoint_seq_at_request,
            "latest_checkpoint_at_request": self.latest_checkpoint_at_request,
            "expected_checkpoint_id": self.expected_checkpoint_id,
            "created_at": self.created_at,
            "decided_at": self.decided_at,
            "executed_at": self.executed_at,
            "rejection_reason": self.rejection_reason,
            "execution_checkpoint_id": self.execution_checkpoint_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ApprovalRecord:
        action_data = data["action"]
        if not isinstance(action_data, Mapping):
            raise ValueError("approval action must be a mapping")
        action = ApprovalActionSnapshot(
            type=ActionType(str(action_data["type"])),
            phase=Phase(str(action_data["phase"])),
            tool_name=str(action_data["tool_name"]),
            args=MappingProxyType(dict(action_data["args"])),
            reason=str(action_data["reason"]),
            sha256=str(action_data["sha256"]),
        )

        targets_raw = data.get("targets", [])
        if not isinstance(targets_raw, (list, tuple)):
            raise ValueError("approval targets must be a list")
        targets = tuple(
            ApprovalTarget(
                path=str(t["path"]),
                exists=bool(t["exists"]),
                before_sha256=str(t["before_sha256"]) if t.get("before_sha256") is not None else None,
                size_bytes=int(t["size_bytes"]) if t.get("size_bytes") is not None else None,
            )
            for t in targets_raw
        )

        preview_data = data["preview"]
        if not isinstance(preview_data, Mapping):
            raise ValueError("approval preview must be a mapping")
        preview = ApprovalPreview(
            summary=str(preview_data["summary"]),
            unified_diff=str(preview_data["unified_diff"]) if preview_data.get("unified_diff") is not None else None,
            truncated=bool(preview_data["truncated"]),
            redacted=bool(preview_data["redacted"]),
        )

        return cls(
            schema_version=int(str(data["schema_version"])),
            project_id=str(data["project_id"]),
            task_id=str(data["task_id"]),
            approval_id=str(data["approval_id"]),
            phase=Phase(str(data["phase"])),
            category=ApprovalCategory(str(data["category"])),
            status=ApprovalStatus(str(data["status"])),
            action=action,
            targets=targets,
            preview=preview,
            checkpoint_seq_at_request=int(str(data["checkpoint_seq_at_request"])),
            latest_checkpoint_at_request=str(data["latest_checkpoint_at_request"])
            if data.get("latest_checkpoint_at_request") is not None
            else None,
            expected_checkpoint_id=str(data["expected_checkpoint_id"])
            if data.get("expected_checkpoint_id") is not None
            else None,
            created_at=str(data["created_at"]),
            decided_at=str(data["decided_at"]) if data.get("decided_at") is not None else None,
            executed_at=str(data["executed_at"]) if data.get("executed_at") is not None else None,
            rejection_reason=str(data["rejection_reason"])
            if data.get("rejection_reason") is not None
            else None,
            execution_checkpoint_id=str(data["execution_checkpoint_id"])
            if data.get("execution_checkpoint_id") is not None
            else None,
        )

    def with_status(
        self,
        status: ApprovalStatus,
        *,
        decided_at: str | None = None,
        rejection_reason: str | None = None,
    ) -> ApprovalRecord:
        """Return a new record with the given status and decision metadata."""
        return replace(
            self,
            status=status,
            decided_at=decided_at if decided_at is not None else self.decided_at,
            rejection_reason=rejection_reason if rejection_reason is not None else self.rejection_reason,
        )

    def with_executing(
        self, *, expected_checkpoint_id: str, executed_at: str
    ) -> ApprovalRecord:
        """Transition to EXECUTING with expected checkpoint."""
        return replace(
            self,
            status=ApprovalStatus.EXECUTING,
            expected_checkpoint_id=expected_checkpoint_id,
            executed_at=executed_at,
        )

    def with_consumed(
        self, *, execution_checkpoint_id: str | None = None
    ) -> ApprovalRecord:
        """Transition to CONSUMED after successful execution.

        Records the checkpoint that guarded the execution so the manifest is a
        complete audit record. Falls back to the expected checkpoint when the
        caller does not supply one explicitly.
        """
        return replace(
            self,
            status=ApprovalStatus.CONSUMED,
            execution_checkpoint_id=(
                execution_checkpoint_id
                if execution_checkpoint_id is not None
                else self.expected_checkpoint_id
            ),
        )

    def with_expired(self) -> ApprovalRecord:
        """Transition to EXPIRED when preconditions change."""
        return replace(self, status=ApprovalStatus.EXPIRED)


def compute_action_digest(
    *,
    action_type: ActionType,
    phase: Phase,
    tool_name: str,
    args: Mapping[str, object],
    reason: str,
) -> str:
    """Compute the canonical sha256 digest for an action (same algorithm as ApprovalActionSnapshot)."""
    canonical = json.dumps(
        {
            "type": action_type.value,
            "phase": phase.value,
            "tool_name": tool_name,
            "args": dict(args),
            "reason": reason,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def format_approval_id(seq: int) -> str:
    """Format an approval sequence number into an approval ID string."""
    if not isinstance(seq, int) or seq < 1 or seq > 999999:
        raise ValueError("approval_seq must be between 1 and 999999")
    return f"apr-{seq:06d}"


def is_valid_approval_id(approval_id: str) -> bool:
    """Check whether a string is a well-formed approval ID."""
    return _APPROVAL_ID_PATTERN.fullmatch(approval_id) is not None
