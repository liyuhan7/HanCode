"""S17-R4 RED tests for Approval run/revision binding."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from hancode.core.actions import Action, ActionType
from hancode.core.approvals import (
    ApprovalActionSnapshot,
    ApprovalCategory,
    ApprovalPreview,
    ApprovalRecord,
    ApprovalStatus,
)
from hancode.core.config import load_config
from hancode.core.models import Phase
from hancode.core.models import TaskStatus
from hancode.core.interventions import ActionCommitResult, ActionCommitStatus
from hancode.core.state import load_state, save_state
from hancode.policy.approval_policy import ApprovalRequirement
from hancode.runtime.approval_request import ApprovalRequestBuilder
from hancode.runtime.engine import create_agent_loop
from hancode.storage.approvals import ApprovalStore, save_approval_manifest
from hancode.storage.approvals import load_approval_manifest
from hancode.storage.workspace import init_project_workspace, init_task_workspace, task_path


def _record(*, run_id: str | None = "run-a", revision: int | None = 3) -> ApprovalRecord:
    action = ApprovalActionSnapshot.from_action(
        action_type=ActionType.TOOL_CALL,
        phase=Phase.CODE,
        tool_name="write_file",
        args={"path": "src/main.py", "content": "x"},
        reason="write source",
    )
    return ApprovalRecord(
        schema_version=1,
        project_id="project-001",
        task_id="task-001",
        approval_id="apr-000001",
        phase=Phase.CODE,
        category=ApprovalCategory.SOURCE_WRITE,
        status=ApprovalStatus.PENDING,
        action=action,
        targets=(),
        preview=ApprovalPreview(
            summary="write source",
            unified_diff=None,
            truncated=False,
            redacted=False,
        ),
        checkpoint_seq_at_request=0,
        latest_checkpoint_at_request=None,
        expected_checkpoint_id=None,
        created_at="2026-01-01T00:00:00Z",
        decided_at=None,
        executed_at=None,
        rejection_reason=None,
        execution_checkpoint_id=None,
        run_id=run_id,
        steering_revision_at_request=revision,
    )


def test_approval_binding_round_trips_through_manifest_dict() -> None:
    record = _record()

    restored = ApprovalRecord.from_dict(record.to_dict())

    assert restored.run_id == "run-a"
    assert restored.steering_revision_at_request == 3


def test_legacy_manifest_is_explicitly_unbound() -> None:
    data = _record().to_dict()
    data.pop("run_id")
    data.pop("steering_revision_at_request")

    restored = ApprovalRecord.from_dict(data)

    assert restored.run_id is None
    assert restored.steering_revision_at_request is None


def test_binding_requires_revision_when_run_id_is_present() -> None:
    with pytest.raises(ValueError):
        _record(run_id="run-a", revision=None)


def test_binding_revision_must_be_nonnegative() -> None:
    with pytest.raises(ValueError):
        _record(run_id="run-a", revision=-1)


def test_approval_request_builder_persists_binding(tmp_path: Path) -> None:
    init_project_workspace(tmp_path, "project-001", "Course", "Assignment")
    init_task_workspace(tmp_path, "task-001", goal="g")
    config = load_config(tmp_path, "task-001")
    state = replace(load_state(task_path(tmp_path, "task-001")), active_run_id="run-a")
    action = Action(
        type=ActionType.TOOL_CALL,
        phase=state.current_phase,
        tool_name="write_file",
        args={"path": "src/main.py", "content": "x"},
        reason="write source",
    )
    requirement = ApprovalRequirement(
        required=True,
        category=ApprovalCategory.SOURCE_WRITE,
        reason="source write",
        risk_level="high",
        targets=("src/main.py",),
    )

    record = ApprovalRequestBuilder(config).build(
        project_id="project-001",
        task_id="task-001",
        state=state,
        action=action,
        requirement=requirement,
        project_root=tmp_path,
        run_id="run-a",
        steering_revision_at_request=7,
    )

    assert record.run_id == "run-a"
    assert record.steering_revision_at_request == 7


def _persist_record(tmp_path: Path, record: ApprovalRecord) -> ApprovalStore:
    init_project_workspace(tmp_path, "project-001", "Course", "Assignment")
    init_task_workspace(tmp_path, "task-001", goal="g")
    save_approval_manifest(tmp_path, "task-001", record)
    return ApprovalStore(tmp_path, "project-001")


def test_pending_approval_cannot_be_consumed_directly(tmp_path: Path) -> None:
    store = _persist_record(tmp_path, _record())

    with pytest.raises(Exception, match="approved|executing"):
        store.mark_consumed("task-001", "apr-000001")


@pytest.mark.parametrize("status", [ApprovalStatus.EXECUTING, ApprovalStatus.CONSUMED])
def test_executing_or_consumed_approval_cannot_expire(
    tmp_path: Path, status: ApprovalStatus
) -> None:
    store = _persist_record(tmp_path, replace(_record(), status=status))

    with pytest.raises(Exception, match="expire|executing|consumed"):
        store.mark_expired("task-001", "apr-000001")


@pytest.mark.parametrize("status", [ApprovalStatus.EXPIRED, ApprovalStatus.REJECTED])
def test_terminal_approval_cleanup_is_idempotent(
    tmp_path: Path, status: ApprovalStatus
) -> None:
    store = _persist_record(tmp_path, replace(_record(), status=status))

    result = store.mark_expired("task-001", "apr-000001")

    assert result.status is status


@pytest.mark.parametrize(
    ("field", "expected"),
    [("project_id", "project-002"), ("task_id", "task-002")],
)
def test_manifest_identity_mismatch_is_rejected(
    tmp_path: Path, field: str, expected: str
) -> None:
    store = _persist_record(tmp_path, replace(_record(), **{field: expected}))

    with pytest.raises(Exception, match="identity|mismatch"):
        store.load_pending("task-001", "apr-000001")


def _prepare_waiting_loop(tmp_path: Path, record: ApprovalRecord):
    init_project_workspace(tmp_path, "project-001", "Course", "Assignment")
    task_root = init_task_workspace(tmp_path, "task-001", goal="g")
    state = replace(
        load_state(task_root),
        status=TaskStatus.WAITING_APPROVAL,
        current_phase=Phase.CODE,
        pending_approval_id=record.approval_id,
        active_run_id="run-a",
    )
    save_state(task_root, state)
    save_approval_manifest(tmp_path, "task-001", record)
    return create_agent_loop(tmp_path, "task-001")


@pytest.mark.parametrize(
    "record",
    [
        _record(run_id=None, revision=None),
        replace(_record(), run_id="run-b"),
        replace(_record(), steering_revision_at_request=4),
    ],
)
def test_pending_binding_drift_expires_and_replans(
    tmp_path: Path, record: ApprovalRecord
) -> None:
    loop = _prepare_waiting_loop(tmp_path, record)
    state = load_state(task_path(tmp_path, "task-001"))

    result = loop._handle_approval_resume("task-001", state, [])

    assert result is None
    assert load_state(task_path(tmp_path, "task-001")).status is TaskStatus.RUNNING
    assert load_state(task_path(tmp_path, "task-001")).pending_approval_id is None
    assert load_approval_manifest(tmp_path, "task-001", "apr-000001").status is ApprovalStatus.EXPIRED


def test_consumed_binding_drift_fails_closed(tmp_path: Path) -> None:
    record = replace(_record(), status=ApprovalStatus.CONSUMED, run_id="run-b")
    loop = _prepare_waiting_loop(tmp_path, record)
    state = load_state(task_path(tmp_path, "task-001"))

    result = loop._handle_approval_resume("task-001", state, [])

    assert result is not None
    assert result.status is TaskStatus.INCONSISTENT
    assert result.tool_calls == ()


def test_approved_resume_uses_independent_approval_commit_key(tmp_path: Path) -> None:
    record = replace(_record(revision=0), status=ApprovalStatus.APPROVED)
    loop = _prepare_waiting_loop(tmp_path, record)
    state = load_state(task_path(tmp_path, "task-001"))

    result = loop._handle_approval_resume("task-001", state, [])

    assert isinstance(result, Action)
    ledger = (task_path(tmp_path, "task-001") / "action_commits.jsonl").read_text(
        encoding="utf-8"
    )
    assert "approval:apr-000001:" in ledger
    assert "step-" not in ledger


class _ApprovalGateReplanStore:
    def current_revision(self, task_id: str) -> int:
        return 0

    def commit_action(
        self,
        task_id: str,
        run_id: str,
        expected_revision: int,
        delivery_sequences: tuple[int, ...],
        action_digest: str,
        commit_key: str,
        acknowledge: bool,
    ) -> ActionCommitResult:
        return ActionCommitResult(
            status=ActionCommitStatus.REPLAN,
            current_revision=1,
        )


def test_approval_commit_replan_expires_without_returning_action(tmp_path: Path) -> None:
    record = replace(_record(revision=0), status=ApprovalStatus.APPROVED)
    loop = _prepare_waiting_loop(tmp_path, record)
    loop._intervention_store = _ApprovalGateReplanStore()  # type: ignore[assignment]
    state = load_state(task_path(tmp_path, "task-001"))

    result = loop._handle_approval_resume("task-001", state, [])

    assert result is None
    assert load_approval_manifest(tmp_path, "task-001", "apr-000001").status is ApprovalStatus.EXPIRED
    assert load_state(task_path(tmp_path, "task-001")).status is TaskStatus.RUNNING
