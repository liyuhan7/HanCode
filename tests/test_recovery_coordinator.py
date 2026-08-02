from __future__ import annotations

from hancode.core.actions import Action, ActionType, ParseError
from hancode.core.failures import FailureCategory, RecoveryMode
from hancode.core.models import Phase, TaskStatus
from hancode.core.state import TaskState
from hancode.policy.path_policy import PathZone
from hancode.policy.tool_policy import PolicyDecision
from hancode.runtime.recovery import RecoveryCoordinator
from hancode.tooling.registry import ToolResult


def _state() -> TaskState:
    return TaskState(
        schema_version=1,
        task_id="task-001",
        goal="implement",
        status=TaskStatus.RUNNING,
        current_phase=Phase.CODE,
        files_changed=(),
        latest_checkpoint=None,
        checkpoint_seq=0,
        tests_run=(),
        latest_test_status="none",
        test_status_consumed=False,
        retry_budget_remaining=2,
        inconsistent=False,
        source_edits_this_phase=0,
        rollback_required=False,
        rollback_done=False,
        phase_completed={phase.value: False for phase in Phase},
        artifacts={
            name: False
            for name in (
                "SPEC.md",
                "PLAN.md",
                "TEST_REPORT.md",
                "REVIEW.md",
                "KNOWLEDGE.md",
                "DELIVERABLES.md",
            )
        },
    )


def _read_action(path: str = "src/main.py") -> Action:
    return Action(
        type=ActionType.TOOL_CALL,
        phase=Phase.CODE,
        tool_name="read_file",
        args={"path": path},
        reason=None,
    )


def _write_action(path: str = "src/main.py", reason: str = "change") -> Action:
    return Action(
        type=ActionType.TOOL_CALL,
        phase=Phase.CODE,
        tool_name="write_file",
        args={"path": path, "content": "new"},
        reason=reason,
    )


def test_parse_failure_escalates_and_observation_is_bounded() -> None:
    coordinator = RecoveryCoordinator()
    error = ParseError(
        error_code="invalid_action_args",
        message="invalid arguments",
        phase=Phase.CODE.value,
        denied_rule=None,
        suggested_fix="fix arguments",
    )
    raw = {
        "type": "tool_call",
        "phase": "code",
        "tool_name": "read_file",
        "args": {},
        "reason": "first wording",
    }

    first = coordinator.record_parse_failure(
        state=_state(), raw_action=raw, parse_error=error, phase=Phase.CODE
    )
    second = coordinator.record_parse_failure(
        state=first.state, raw_action=raw, parse_error=error, phase=Phase.CODE
    )
    third = coordinator.record_parse_failure(
        state=second.state, raw_action=raw, parse_error=error, phase=Phase.CODE
    )

    assert first.state.active_failure is not None
    assert first.state.active_failure.repeat_count == 1
    assert second.state.active_failure is not None
    assert second.state.active_failure.recovery_mode is RecoveryMode.CHANGE_ACTION
    assert third.should_block is True
    assert third.state.status is TaskStatus.BLOCKED
    assert third.observation.details["failure_id"] == third.state.active_failure.failure_id


def test_action_digest_excludes_reason_and_guard_blocks_third_submission() -> None:
    coordinator = RecoveryCoordinator()
    decision = PolicyDecision(
        allowed=False,
        reason="protected",
        phase=Phase.CODE,
        denied_rule="protected_path",
        suggested_fix="choose source",
        target_zone=PathZone.PROTECTED,
    )
    action_a = _write_action(reason="reason A")
    action_b = _write_action(reason="reason B")

    first = coordinator.record_policy_failure(
        state=_state(), action=action_a, decision=decision, phase=Phase.CODE
    )
    guarded = coordinator.guard_action(state=first.state, action=action_b)
    assert guarded is not None
    assert guarded.state.active_failure is not None
    assert guarded.state.active_failure.repeat_count == 2
    blocked = coordinator.guard_action(state=guarded.state, action=action_a)
    assert blocked is not None
    assert blocked.should_block is True
    assert blocked.state.status is TaskStatus.BLOCKED


def test_different_failure_fingerprint_starts_new_round() -> None:
    coordinator = RecoveryCoordinator()
    error = ParseError(
        error_code="invalid_action_args",
        message="invalid arguments",
        phase=Phase.CODE.value,
        denied_rule=None,
        suggested_fix="fix",
    )
    first = coordinator.record_parse_failure(
        state=_state(),
        raw_action={"type": "bad", "phase": "code", "tool_name": None, "args": {}},
        parse_error=error,
        phase=Phase.CODE,
    )
    second = coordinator.record_parse_failure(
        state=first.state,
        raw_action={"type": "bad", "phase": "code", "tool_name": None, "args": {"x": 1}},
        parse_error=error,
        phase=Phase.CODE,
    )
    assert first.state.active_failure is not None
    assert second.state.active_failure is not None
    assert second.state.active_failure.fingerprint != first.state.active_failure.fingerprint
    assert second.state.active_failure.repeat_count == 1


def test_file_failure_and_conservative_success_cleanup() -> None:
    coordinator = RecoveryCoordinator()
    action = _read_action("missing.py")
    failure = coordinator.record_tool_failure(
        state=_state(),
        action=action,
        result=ToolResult(
            success=False,
            action_name="read_file",
            error_summary="File does not exist.",
            error_code="file_not_found",
        ),
        phase=Phase.CODE,
    )
    assert failure.state.active_failure is not None
    assert failure.state.active_failure.category is FailureCategory.TOOL_FAILED
    assert coordinator.resolve_after_success(state=failure.state, action=_read_action("other.py")).active_failure is None
    assert coordinator.resolve_after_success(state=failure.state, action=_write_action()).active_failure is not None


def test_unrelated_read_does_not_clear_write_failure() -> None:
    coordinator = RecoveryCoordinator()
    action = _write_action("src/main.py")
    failure = coordinator.record_tool_failure(
        state=_state(),
        action=action,
        result=ToolResult(
            success=False,
            action_name="write_file",
            error_summary="Path is not a file.",
            error_code="not_a_file",
            mutation_applied=False,
        ),
        phase=Phase.CODE,
    )
    cleared = coordinator.resolve_after_success(
        state=failure.state,
        action=_read_action("src/main.py"),
    )
    assert cleared.active_failure is not None
