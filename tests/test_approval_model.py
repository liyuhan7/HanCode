"""Tests for S3-R1: Approval domain model, state, and config."""

from __future__ import annotations

import pytest

from hancode.core.approvals import (
    ApprovalActionSnapshot,
    ApprovalCategory,
    ApprovalPreview,
    ApprovalRecord,
    ApprovalStatus,
    ApprovalTarget,
    compute_action_digest,
    format_approval_id,
    is_valid_approval_id,
)
from hancode.core.actions import ActionType
from hancode.core.interactions import InteractionRecord, InteractionStatus
from hancode.core.models import Phase, TaskStatus
from hancode.core.state import TaskState


# ---------------------------------------------------------------------------
# Approval ID format
# ---------------------------------------------------------------------------

def test_approval_id_format_matches_pattern() -> None:
    assert is_valid_approval_id("apr-000001")
    assert is_valid_approval_id("apr-999999")
    assert not is_valid_approval_id("apr-1")
    assert not is_valid_approval_id("ask-000001")
    assert not is_valid_approval_id("")
    assert not is_valid_approval_id("APR-000001")


def test_format_approval_id_produces_valid_ids() -> None:
    assert format_approval_id(1) == "apr-000001"
    assert format_approval_id(999999) == "apr-999999"
    assert is_valid_approval_id(format_approval_id(42))


def test_format_approval_id_rejects_invalid_seq() -> None:
    with pytest.raises(ValueError):
        format_approval_id(0)
    with pytest.raises(ValueError):
        format_approval_id(-1)
    with pytest.raises(ValueError):
        format_approval_id(1_000_000)


# ---------------------------------------------------------------------------
# Approval action digest is deterministic
# ---------------------------------------------------------------------------

def test_approval_action_digest_is_deterministic() -> None:
    args1 = {"path": "src/main.py", "content": "print('hello')"}
    snapshot1 = ApprovalActionSnapshot.from_action(
        action_type=ActionType.TOOL_CALL,
        phase=Phase.CODE,
        tool_name="write_file",
        args=args1,
        reason="Add hello world",
    )
    snapshot2 = ApprovalActionSnapshot.from_action(
        action_type=ActionType.TOOL_CALL,
        phase=Phase.CODE,
        tool_name="write_file",
        args=args1,
        reason="Add hello world",
    )
    assert snapshot1.sha256 == snapshot2.sha256
    assert snapshot1.digest_matches(snapshot2)


def test_approval_action_digest_changes_with_different_args() -> None:
    s1 = ApprovalActionSnapshot.from_action(
        action_type=ActionType.TOOL_CALL,
        phase=Phase.CODE,
        tool_name="write_file",
        args={"path": "src/a.py", "content": "x"},
        reason="Add x",
    )
    s2 = ApprovalActionSnapshot.from_action(
        action_type=ActionType.TOOL_CALL,
        phase=Phase.CODE,
        tool_name="write_file",
        args={"path": "src/b.py", "content": "x"},
        reason="Add x",
    )
    assert s1.sha256 != s2.sha256


def test_compute_action_digest_matches_snapshot() -> None:
    args = {"path": "src/main.py", "content": "print('hi')"}
    digest = compute_action_digest(
        action_type=ActionType.TOOL_CALL,
        phase=Phase.CODE,
        tool_name="edit_file",
        args=args,
        reason="Edit file",
    )
    snapshot = ApprovalActionSnapshot.from_action(
        action_type=ActionType.TOOL_CALL,
        phase=Phase.CODE,
        tool_name="edit_file",
        args=args,
        reason="Edit file",
    )
    assert digest == snapshot.sha256


# ---------------------------------------------------------------------------
# WAITING_APPROVAL state invariants
# ---------------------------------------------------------------------------

def _valid_state(**overrides: object) -> TaskState:
    kwargs: dict[str, object] = {
        "schema_version": 1,
        "task_id": "task-001",
        "goal": "test goal",
        "status": TaskStatus.CREATED,
        "current_phase": Phase.CODE,
        "files_changed": (),
        "latest_checkpoint": None,
        "checkpoint_seq": 0,
        "tests_run": (),
        "latest_test_status": "none",
        "test_status_consumed": False,
        "retry_budget_remaining": 2,
        "inconsistent": False,
        "source_edits_this_phase": 0,
        "rollback_required": False,
        "rollback_done": False,
        "phase_completed": {p.value: False for p in Phase},
        "artifacts": {
            "SPEC.md": True,
            "PLAN.md": True,
            "TEST_REPORT.md": False,
            "REVIEW.md": False,
            "KNOWLEDGE.md": False,
            "DELIVERABLES.md": False,
        },
    }
    kwargs.update(overrides)
    return TaskState(**kwargs)


def test_waiting_approval_requires_pending_id() -> None:
    with pytest.raises(ValueError, match="pending_approval_id"):
        _valid_state(
            status=TaskStatus.WAITING_APPROVAL,
            pending_approval_id=None,
        )


def test_waiting_approval_with_valid_pending_id() -> None:
    state = _valid_state(
        status=TaskStatus.WAITING_APPROVAL,
        approval_seq=1,
        pending_approval_id="apr-000001",
    )
    assert state.status is TaskStatus.WAITING_APPROVAL
    assert state.pending_approval_id == "apr-000001"
    assert state.approval_seq == 1


def test_interaction_and_approval_cannot_both_be_pending() -> None:
    with pytest.raises(ValueError):
        _valid_state(
            status=TaskStatus.WAITING_APPROVAL,
            approval_seq=1,
            pending_approval_id="apr-000001",
            pending_interaction_id="ask-000001",
        )


def test_waiting_input_cannot_have_pending_approval() -> None:
    with pytest.raises(ValueError):
        _valid_state(
            status=TaskStatus.WAITING_INPUT,
            current_phase=Phase.SPEC,
            interactions=(
                InteractionRecord(
                    interaction_id="ask-000001",
                    phase=Phase.SPEC,
                    question="Which framework?",
                    answer=None,
                    status=InteractionStatus.WAITING,
                ),
            ),
            interaction_seq=1,
            pending_interaction_id="ask-000001",
            pending_approval_id="apr-000001",
        )


def test_non_waiting_approval_cannot_have_pending_approval_id() -> None:
    with pytest.raises(ValueError, match="pending_approval_id"):
        _valid_state(
            status=TaskStatus.RUNNING,
            pending_approval_id="apr-000001",
        )


def test_old_state_loads_with_empty_approval_fields() -> None:
    """Old state.json without approval fields should default to 0/None."""
    state = _valid_state()
    assert state.approval_seq == 0
    assert state.pending_approval_id is None


def test_approval_seq_must_be_nonnegative() -> None:
    with pytest.raises(ValueError, match="approval_seq"):
        _valid_state(approval_seq=-1)


def test_pending_approval_id_must_be_valid_format() -> None:
    with pytest.raises(ValueError, match="pending_approval_id"):
        _valid_state(
            status=TaskStatus.WAITING_APPROVAL,
            approval_seq=1,
            pending_approval_id="bad-format",
        )


# ---------------------------------------------------------------------------
# ApprovalStatus enum
# ---------------------------------------------------------------------------

def test_approval_status_values() -> None:
    assert ApprovalStatus.PENDING.value == "pending"
    assert ApprovalStatus.APPROVED.value == "approved"
    assert ApprovalStatus.REJECTED.value == "rejected"
    assert ApprovalStatus.EXECUTING.value == "executing"
    assert ApprovalStatus.CONSUMED.value == "consumed"
    assert ApprovalStatus.EXPIRED.value == "expired"


# ---------------------------------------------------------------------------
# ApprovalCategory enum
# ---------------------------------------------------------------------------

def test_approval_category_values() -> None:
    assert ApprovalCategory.SOURCE_WRITE.value == "source_write"
    assert ApprovalCategory.SOURCE_OVERWRITE.value == "source_overwrite"
    assert ApprovalCategory.ROLLBACK.value == "rollback"


# ---------------------------------------------------------------------------
# TaskStatus WAITING_APPROVAL
# ---------------------------------------------------------------------------

def test_waiting_approval_status_exists() -> None:
    assert TaskStatus.WAITING_APPROVAL.value == "waiting_approval"


# ---------------------------------------------------------------------------
# ApprovalRecord validation
# ---------------------------------------------------------------------------

def _valid_record(**overrides: object) -> ApprovalRecord:
    kwargs: dict[str, object] = {
        "schema_version": 1,
        "project_id": "proj-001",
        "task_id": "task-001",
        "approval_id": "apr-000001",
        "phase": Phase.CODE,
        "category": ApprovalCategory.SOURCE_WRITE,
        "status": ApprovalStatus.PENDING,
        "action": ApprovalActionSnapshot.from_action(
            action_type=ActionType.TOOL_CALL,
            phase=Phase.CODE,
            tool_name="write_file",
            args={"path": "src/main.py", "content": "print('hello')"},
            reason="Add main module",
        ),
        "targets": (),
        "preview": ApprovalPreview(
            summary="Create src/main.py",
            unified_diff=None,
            truncated=False,
            redacted=False,
        ),
        "checkpoint_seq_at_request": 0,
        "latest_checkpoint_at_request": None,
        "expected_checkpoint_id": None,
        "created_at": "2026-01-01T00:00:00Z",
        "decided_at": None,
        "executed_at": None,
        "rejection_reason": None,
        "execution_checkpoint_id": None,
    }
    kwargs.update(overrides)
    return ApprovalRecord(**kwargs)


def test_record_is_valid_with_minimal_data() -> None:
    record = _valid_record()
    assert record.approval_id == "apr-000001"
    assert record.status is ApprovalStatus.PENDING


def test_record_rejects_bad_approval_id() -> None:
    with pytest.raises(ValueError, match="approval_id"):
        _valid_record(approval_id="bad")


def test_with_status_returns_new_record() -> None:
    record = _valid_record()
    updated = record.with_status(ApprovalStatus.APPROVED, decided_at="2026-01-02T00:00:00Z")
    assert updated.status is ApprovalStatus.APPROVED
    assert updated.decided_at == "2026-01-02T00:00:00Z"
    assert record.status is ApprovalStatus.PENDING  # original unchanged


def test_with_executing_transitions() -> None:
    record = _valid_record()
    updated = record.with_executing(
        expected_checkpoint_id="ckpt-001", executed_at="2026-01-03T00:00:00Z"
    )
    assert updated.status is ApprovalStatus.EXECUTING
    assert updated.expected_checkpoint_id == "ckpt-001"


def test_with_consumed_transitions() -> None:
    record = _valid_record()
    updated = record.with_consumed()
    assert updated.status is ApprovalStatus.CONSUMED


def test_with_expired_transitions() -> None:
    record = _valid_record()
    updated = record.with_expired()
    assert updated.status is ApprovalStatus.EXPIRED


# ---------------------------------------------------------------------------
# ApprovalRecord round-trip
# ---------------------------------------------------------------------------

def test_record_to_dict_and_back() -> None:
    original = _valid_record(
        targets=(
            ApprovalTarget(
                path="src/main.py",
                exists=False,
                before_sha256=None,
                size_bytes=None,
            ),
        ),
    )
    data = original.to_dict()
    restored = ApprovalRecord.from_dict(data)
    assert restored.approval_id == original.approval_id
    assert restored.action.sha256 == original.action.sha256
    assert restored.status == original.status
    assert len(restored.targets) == 1
    assert restored.targets[0].path == "src/main.py"
