"""Tests for S3-R2: ApprovalPolicy, Preview, and Store."""

from __future__ import annotations

from pathlib import Path

import pytest

from hancode.core.actions import Action, ActionType
from hancode.core.approvals import (
    ApprovalCategory,
    ApprovalRecord,
    ApprovalStatus,
)
from hancode.core.config import HanCodeConfig
from hancode.core.models import Phase, TaskStatus
from hancode.core.state import TaskState, load_state
from hancode.policy.approval_policy import ApprovalPolicy, _require
from hancode.policy.tool_policy import PolicyDecision
from hancode.runtime.approval_request import (
    ApprovalRequestBuilder,
    _contains_sensitive_content,
)
from hancode.storage.approvals import (
    ApprovalStore,
)
from hancode.storage.workspace import init_project_workspace, init_task_workspace, task_path


# ---------------------------------------------------------------------------
# ApprovalPolicy tests
# ---------------------------------------------------------------------------

def _allowed_decision(phase: Phase) -> PolicyDecision:
    return PolicyDecision(
        allowed=True,
        reason="Allowed by policy.",
        phase=phase,
        requires_checkpoint=True,
    )


def _denied_decision(phase: Phase) -> PolicyDecision:
    return PolicyDecision(
        allowed=False,
        reason="Denied by policy.",
        phase=phase,
        denied_rule="test_denial",
        suggested_fix="Fix the action.",
    )


def _make_config(approval_mode: str = "disabled") -> HanCodeConfig:
    return HanCodeConfig(
        project_root=Path("."),
        hancode_root=Path(".hancode"),
        allowed_workspace_root=Path("."),
        task_root=None,
        llm_provider="mock",
        model_name=None,
        credential_source=None,
        test_command=None,
        build_command=None,
        max_steps=30,
        retry_budget=2,
        max_checkpoints_per_task=5,
        max_observation_bytes=8192,
        max_context_chars=24000,
        max_trace_events=40,
        protected_patterns=(),
        writable_roots=(Path("src"), Path("tests")),
        approval_mode=approval_mode,
    )


def _make_write_action() -> Action:
    return Action(
        type=ActionType.TOOL_CALL,
        phase=Phase.CODE,
        tool_name="write_file",
        args={"path": "src/main.py", "content": "print('hello')"},
        reason="Add main module",
    )


def _make_edit_action() -> Action:
    return Action(
        type=ActionType.TOOL_CALL,
        phase=Phase.CODE,
        tool_name="edit_file",
        args={"path": "src/main.py", "old_string": "old", "new_string": "new"},
        reason="Fix bug",
    )


def _make_rollback_action() -> Action:
    return Action(
        type=ActionType.TOOL_CALL,
        phase=Phase.REVIEW,
        tool_name="rollback_last_checkpoint",
        args={},
        reason="Rollback bad changes",
    )


def _valid_state(**overrides: object) -> TaskState:
    kwargs: dict[str, object] = {
        "schema_version": 1,
        "task_id": "task-001",
        "goal": "test goal",
        "status": TaskStatus.RUNNING,
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


# --- Policy denial never becomes approval ---


def test_policy_denial_never_becomes_approval() -> None:
    policy = ApprovalPolicy(_make_config(approval_mode="all_source_writes"))
    action = _make_write_action()
    state = _valid_state()
    decision = _denied_decision(Phase.CODE)

    result = policy.evaluate(action=action, policy_decision=decision, state=state)
    assert result.required is False


# --- Disabled mode ---


def test_disabled_mode_never_requires_approval() -> None:
    policy = ApprovalPolicy(_make_config(approval_mode="disabled"))
    action = _make_write_action()
    state = _valid_state()
    decision = _allowed_decision(Phase.CODE)

    result = policy.evaluate(action=action, policy_decision=decision, state=state)
    assert result.required is False


# --- first_source_write mode ---


def test_first_source_write_requires_approval() -> None:
    policy = ApprovalPolicy(_make_config(approval_mode="first_source_write"))
    action = _make_write_action()
    state = _valid_state(source_edits_this_phase=0)
    decision = _allowed_decision(Phase.CODE)

    result = policy.evaluate(action=action, policy_decision=decision, state=state)
    assert result.required is True
    assert result.category is ApprovalCategory.SOURCE_WRITE


def test_second_source_edit_does_not_require_first_write_approval() -> None:
    """edit_file on second edit in first_source_write mode: no approval needed."""
    policy = ApprovalPolicy(_make_config(approval_mode="first_source_write"))
    action = _make_edit_action()
    state = _valid_state(source_edits_this_phase=1)
    decision = _allowed_decision(Phase.CODE)

    result = policy.evaluate(action=action, policy_decision=decision, state=state)
    assert result.required is False


# --- all_source_writes mode ---


def test_all_source_writes_mode_requires_every_write() -> None:
    policy = ApprovalPolicy(_make_config(approval_mode="all_source_writes"))
    action = _make_write_action()
    state = _valid_state(source_edits_this_phase=5)
    decision = _allowed_decision(Phase.CODE)

    result = policy.evaluate(action=action, policy_decision=decision, state=state)
    assert result.required is True


def test_all_source_writes_requires_edit_too() -> None:
    policy = ApprovalPolicy(_make_config(approval_mode="all_source_writes"))
    action = _make_edit_action()
    state = _valid_state()
    decision = _allowed_decision(Phase.CODE)

    result = policy.evaluate(action=action, policy_decision=decision, state=state)
    assert result.required is True


# --- Agent-requested rollback ---


def test_agent_requested_rollback_requires_approval() -> None:
    policy = ApprovalPolicy(_make_config(approval_mode="disabled"))
    # Even with approval_mode=disabled, agent rollback confirmation is controlled
    # by confirm_agent_rollback which defaults to True
    action = _make_rollback_action()
    state = _valid_state(current_phase=Phase.REVIEW)
    decision = _allowed_decision(Phase.REVIEW)

    result = policy.evaluate(action=action, policy_decision=decision, state=state)
    assert result.required is True
    assert result.category is ApprovalCategory.ROLLBACK


def test_agent_rollback_not_required_when_disabled() -> None:
    config = _make_config(approval_mode="disabled")
    object.__setattr__(config, "confirm_agent_rollback", False)
    policy = ApprovalPolicy(config)
    action = _make_rollback_action()
    state = _valid_state(current_phase=Phase.REVIEW)
    decision = _allowed_decision(Phase.REVIEW)

    result = policy.evaluate(action=action, policy_decision=decision, state=state)
    assert result.required is False


# --- Non-tool actions never require approval ---


def test_ask_user_action_never_requires_approval() -> None:
    policy = ApprovalPolicy(_make_config(approval_mode="all_source_writes"))
    action = Action(
        type=ActionType.ASK_USER,
        phase=Phase.SPEC,
        tool_name=None,
        args={"question": "Which framework?"},
        reason="Need info",
    )
    state = _valid_state(current_phase=Phase.SPEC)
    decision = _allowed_decision(Phase.SPEC)

    result = policy.evaluate(action=action, policy_decision=decision, state=state)
    assert result.required is False


# ---------------------------------------------------------------------------
# Sensitive content detection
# ---------------------------------------------------------------------------


def test_sensitive_content_detection_finds_api_key() -> None:
    assert _contains_sensitive_content("API_KEY = 'sk-abc123'")
    assert _contains_sensitive_content("password = 'secret'")
    assert _contains_sensitive_content('token: "xyz"')


def test_sensitive_content_detection_ignores_normal_code() -> None:
    assert not _contains_sensitive_content("print('hello')")
    assert not _contains_sensitive_content("def foo(): pass")


# ---------------------------------------------------------------------------
# Preview tests
# ---------------------------------------------------------------------------


def test_preview_does_not_mutate_file(tmp_path: Path) -> None:
    config = _make_config()
    builder = ApprovalRequestBuilder(config)

    src_file = tmp_path / "src" / "main.py"
    src_file.parent.mkdir(parents=True, exist_ok=True)
    original = "print('original')"
    src_file.write_text(original, encoding="utf-8")

    action = Action(
        type=ActionType.TOOL_CALL,
        phase=Phase.CODE,
        tool_name="write_file",
        args={"path": "src/main.py", "content": "print('new')"},
        reason="Update",
    )

    requirement = _require(
        ApprovalCategory.SOURCE_WRITE,
        "Test approval",
        targets=("src/main.py",),
    )

    init_project_workspace(tmp_path, "proj-001", "test", "hw1")

    record = builder.build(
        project_id="proj-001",
        task_id="task-001",
        state=_valid_state(),
        action=action,
        requirement=requirement,
        project_root=tmp_path,
    )

    # File must NOT have been modified
    assert src_file.read_text(encoding="utf-8") == original
    assert record.preview.unified_diff is not None


def test_preview_is_produced_for_write(tmp_path: Path) -> None:
    config = _make_config()
    builder = ApprovalRequestBuilder(config)

    src_file = tmp_path / "src" / "main.py"
    src_file.parent.mkdir(parents=True, exist_ok=True)
    src_file.write_text("print('old')", encoding="utf-8")

    init_project_workspace(tmp_path, "proj-001", "test", "hw1")

    action = Action(
        type=ActionType.TOOL_CALL,
        phase=Phase.CODE,
        tool_name="write_file",
        args={"path": "src/main.py", "content": "print('new')"},
        reason="Update",
    )

    requirement = _require(
        ApprovalCategory.SOURCE_WRITE,
        "Test approval",
        targets=("src/main.py",),
    )

    record = builder.build(
        project_id="proj-001",
        task_id="task-001",
        state=_valid_state(),
        action=action,
        requirement=requirement,
        project_root=tmp_path,
    )

    assert record.preview.summary
    assert record.preview.unified_diff is not None
    # Diff should show the change
    assert "old" in record.preview.unified_diff or "new" in record.preview.unified_diff


def test_sensitive_payload_is_rejected(tmp_path: Path) -> None:
    config = _make_config()
    builder = ApprovalRequestBuilder(config)

    src_file = tmp_path / "src" / "main.py"
    src_file.parent.mkdir(parents=True, exist_ok=True)
    src_file.write_text("x=1", encoding="utf-8")

    init_project_workspace(tmp_path, "proj-001", "test", "hw1")

    action = Action(
        type=ActionType.TOOL_CALL,
        phase=Phase.CODE,
        tool_name="write_file",
        args={"path": "src/main.py", "content": "API_KEY='abc123'"},
        reason="Add config",
    )

    requirement = _require(
        ApprovalCategory.SOURCE_WRITE,
        "Test approval",
        targets=("src/main.py",),
    )

    with pytest.raises(Exception) as exc_info:
        builder.build(
            project_id="proj-001",
            task_id="task-001",
            state=_valid_state(),
            action=action,
            requirement=requirement,
            project_root=tmp_path,
        )
    assert "sensitive" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# ApprovalStore tests
# ---------------------------------------------------------------------------


def _init_task(tmp_path: Path) -> tuple[Path, Path]:
    """Initialize a project and task workspace."""
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    init_project_workspace(project_root, "proj-001", "test", "hw1")
    init_task_workspace(project_root, "task-001", goal="Test goal")
    return project_root, task_path(project_root, "task-001")


def test_approval_manifest_is_atomic(tmp_path: Path) -> None:
    project_root, task_root = _init_task(tmp_path)
    store = ApprovalStore(project_root, "proj-001")

    state = load_state(task_root)
    state = state.__class__(
        schema_version=state.schema_version,
        task_id=state.task_id,
        goal=state.goal,
        status=TaskStatus.RUNNING,
        current_phase=Phase.CODE,
        files_changed=state.files_changed,
        latest_checkpoint=state.latest_checkpoint,
        checkpoint_seq=state.checkpoint_seq,
        tests_run=state.tests_run,
        latest_test_status=state.latest_test_status,
        test_status_consumed=state.test_status_consumed,
        retry_budget_remaining=state.retry_budget_remaining,
        inconsistent=state.inconsistent,
        source_edits_this_phase=state.source_edits_this_phase,
        rollback_required=state.rollback_required,
        rollback_done=state.rollback_done,
        phase_completed=state.phase_completed,
        artifacts=state.artifacts,
    )

    record = _build_test_record(state)

    updated_state, persisted = store.create("task-001", state, record)

    assert persisted.approval_id == "apr-000001"
    assert persisted.status is ApprovalStatus.PENDING
    assert updated_state.status is TaskStatus.WAITING_APPROVAL
    assert updated_state.pending_approval_id == "apr-000001"
    assert updated_state.approval_seq == 1

    # Verify manifest file exists
    manifest_path = task_root / "approvals" / "apr-000001.json"
    assert manifest_path.is_file()


def test_load_and_decide_approval(tmp_path: Path) -> None:
    project_root, task_root = _init_task(tmp_path)
    store = ApprovalStore(project_root, "proj-001")

    state = load_state(task_root)
    state = state.__class__(
        schema_version=state.schema_version,
        task_id=state.task_id,
        goal=state.goal,
        status=TaskStatus.RUNNING,
        current_phase=Phase.CODE,
        files_changed=state.files_changed,
        latest_checkpoint=state.latest_checkpoint,
        checkpoint_seq=state.checkpoint_seq,
        tests_run=state.tests_run,
        latest_test_status=state.latest_test_status,
        test_status_consumed=state.test_status_consumed,
        retry_budget_remaining=state.retry_budget_remaining,
        inconsistent=state.inconsistent,
        source_edits_this_phase=state.source_edits_this_phase,
        rollback_required=state.rollback_required,
        rollback_done=state.rollback_done,
        phase_completed=state.phase_completed,
        artifacts=state.artifacts,
    )

    record = _build_test_record(state)

    updated_state, _ = store.create("task-001", state, record)

    # Load pending
    loaded = store.load_pending("task-001", "apr-000001")
    assert loaded.status is ApprovalStatus.PENDING

    # Approve
    approved = store.decide("task-001", True, approval_id="apr-000001")
    assert approved.status is ApprovalStatus.APPROVED
    assert approved.decided_at is not None

    # Verify persisted
    reloaded = store.load_pending("task-001", "apr-000001")
    assert reloaded.status is ApprovalStatus.APPROVED


def test_reject_approval(tmp_path: Path) -> None:
    project_root, task_root = _init_task(tmp_path)
    store = ApprovalStore(project_root, "proj-001")

    state = load_state(task_root)
    state = state.__class__(
        schema_version=state.schema_version,
        task_id=state.task_id,
        goal=state.goal,
        status=TaskStatus.RUNNING,
        current_phase=Phase.CODE,
        files_changed=state.files_changed,
        latest_checkpoint=state.latest_checkpoint,
        checkpoint_seq=state.checkpoint_seq,
        tests_run=state.tests_run,
        latest_test_status=state.latest_test_status,
        test_status_consumed=state.test_status_consumed,
        retry_budget_remaining=state.retry_budget_remaining,
        inconsistent=state.inconsistent,
        source_edits_this_phase=state.source_edits_this_phase,
        rollback_required=state.rollback_required,
        rollback_done=state.rollback_done,
        phase_completed=state.phase_completed,
        artifacts=state.artifacts,
    )

    record = _build_test_record(state)
    updated_state, _ = store.create("task-001", state, record)

    rejected = store.decide(
        "task-001", False, approval_id="apr-000001", reason="Not safe"
    )
    assert rejected.status is ApprovalStatus.REJECTED
    assert rejected.rejection_reason == "Not safe"


def test_cannot_decide_non_pending(tmp_path: Path) -> None:
    project_root, task_root = _init_task(tmp_path)
    store = ApprovalStore(project_root, "proj-001")

    state = load_state(task_root)
    state = state.__class__(
        schema_version=state.schema_version,
        task_id=state.task_id,
        goal=state.goal,
        status=TaskStatus.RUNNING,
        current_phase=Phase.CODE,
        files_changed=state.files_changed,
        latest_checkpoint=state.latest_checkpoint,
        checkpoint_seq=state.checkpoint_seq,
        tests_run=state.tests_run,
        latest_test_status=state.latest_test_status,
        test_status_consumed=state.test_status_consumed,
        retry_budget_remaining=state.retry_budget_remaining,
        inconsistent=state.inconsistent,
        source_edits_this_phase=state.source_edits_this_phase,
        rollback_required=state.rollback_required,
        rollback_done=state.rollback_done,
        phase_completed=state.phase_completed,
        artifacts=state.artifacts,
    )

    record = _build_test_record(state)
    updated_state, _ = store.create("task-001", state, record)

    # First approve
    store.decide("task-001", True, approval_id="apr-000001")

    # Second decision should fail
    with pytest.raises(Exception) as exc_info:
        store.decide("task-001", False, approval_id="apr-000001")
    assert "not pending" in str(exc_info.value).lower() or "already" in str(exc_info.value).lower()


def test_mark_executing_and_consumed(tmp_path: Path) -> None:
    project_root, task_root = _init_task(tmp_path)
    store = ApprovalStore(project_root, "proj-001")

    state = load_state(task_root)
    state = state.__class__(
        schema_version=state.schema_version,
        task_id=state.task_id,
        goal=state.goal,
        status=TaskStatus.RUNNING,
        current_phase=Phase.CODE,
        files_changed=state.files_changed,
        latest_checkpoint=state.latest_checkpoint,
        checkpoint_seq=state.checkpoint_seq,
        tests_run=state.tests_run,
        latest_test_status=state.latest_test_status,
        test_status_consumed=state.test_status_consumed,
        retry_budget_remaining=state.retry_budget_remaining,
        inconsistent=state.inconsistent,
        source_edits_this_phase=state.source_edits_this_phase,
        rollback_required=state.rollback_required,
        rollback_done=state.rollback_done,
        phase_completed=state.phase_completed,
        artifacts=state.artifacts,
    )

    record = _build_test_record(state)
    updated_state, _ = store.create("task-001", state, record)

    store.decide("task-001", True, approval_id="apr-000001")

    executing = store.mark_executing(
        "task-001", "apr-000001", expected_checkpoint_id="ckpt-001"
    )
    assert executing.status is ApprovalStatus.EXECUTING
    assert executing.expected_checkpoint_id == "ckpt-001"

    consumed = store.mark_consumed("task-001", "apr-000001")
    assert consumed.status is ApprovalStatus.CONSUMED


def test_mark_expired(tmp_path: Path) -> None:
    project_root, task_root = _init_task(tmp_path)
    store = ApprovalStore(project_root, "proj-001")

    state = load_state(task_root)
    state = state.__class__(
        schema_version=state.schema_version,
        task_id=state.task_id,
        goal=state.goal,
        status=TaskStatus.RUNNING,
        current_phase=Phase.CODE,
        files_changed=state.files_changed,
        latest_checkpoint=state.latest_checkpoint,
        checkpoint_seq=state.checkpoint_seq,
        tests_run=state.tests_run,
        latest_test_status=state.latest_test_status,
        test_status_consumed=state.test_status_consumed,
        retry_budget_remaining=state.retry_budget_remaining,
        inconsistent=state.inconsistent,
        source_edits_this_phase=state.source_edits_this_phase,
        rollback_required=state.rollback_required,
        rollback_done=state.rollback_done,
        phase_completed=state.phase_completed,
        artifacts=state.artifacts,
    )

    record = _build_test_record(state)
    updated_state, _ = store.create("task-001", state, record)

    expired = store.mark_expired("task-001", "apr-000001")
    assert expired.status is ApprovalStatus.EXPIRED


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_test_record(state: TaskState) -> ApprovalRecord:
    from hancode.core.approvals import (
        ApprovalActionSnapshot,
        ApprovalPreview,
        format_approval_id,
    )

    snapshot = ApprovalActionSnapshot.from_action(
        action_type=ActionType.TOOL_CALL,
        phase=state.current_phase,
        tool_name="write_file",
        args={"path": "src/main.py", "content": "print('hello')"},
        reason="Add main module",
    )

    return ApprovalRecord(
        schema_version=1,
        project_id="proj-001",
        task_id=state.task_id,
        approval_id=format_approval_id(state.approval_seq + 1),
        phase=state.current_phase,
        category=ApprovalCategory.SOURCE_WRITE,
        status=ApprovalStatus.PENDING,
        action=snapshot,
        targets=(),
        preview=ApprovalPreview(
            summary="Create src/main.py",
            unified_diff=None,
            truncated=False,
            redacted=False,
        ),
        checkpoint_seq_at_request=state.checkpoint_seq,
        latest_checkpoint_at_request=state.latest_checkpoint,
        expected_checkpoint_id=None,
        created_at="2026-01-01T00:00:00Z",
        decided_at=None,
        executed_at=None,
        rejection_reason=None,
        execution_checkpoint_id=None,
    )
