from __future__ import annotations

from dataclasses import replace

import pytest

from hancode.core.interactions import InteractionRecord, InteractionStatus
from hancode.core.models import Phase, TaskStatus
from hancode.core.router import RoutingDecision, select_next_phase
from hancode.core.state import TaskState


def test_missing_spec_routes_to_spec() -> None:
    decision = select_next_phase(_state(artifacts={"SPEC.md": False}))

    assert decision == RoutingDecision(Phase.SPEC, "spec_missing")


def test_missing_plan_routes_to_plan() -> None:
    decision = select_next_phase(_state(artifacts={"PLAN.md": False}))

    assert decision == RoutingDecision(Phase.PLAN, "plan_missing")


def test_missing_spec_precedes_missing_plan() -> None:
    decision = select_next_phase(
        _state(artifacts={"SPEC.md": False, "PLAN.md": False})
    )

    assert decision == RoutingDecision(Phase.SPEC, "spec_missing")


@pytest.mark.parametrize(
    ("artifact_name", "phase", "reason"),
    [
        ("SPEC.md", Phase.SPEC, "spec_missing"),
        ("PLAN.md", Phase.PLAN, "plan_missing"),
    ],
)
def test_missing_spec_or_plan_precedes_unconsumed_failed_test(
    artifact_name: str, phase: Phase, reason: str
) -> None:
    decision = select_next_phase(
        _state(artifacts={artifact_name: False}, latest_test_status="failed")
    )

    assert decision == RoutingDecision(phase, reason)


@pytest.mark.parametrize(
    ("inconsistent", "status"),
    [(True, TaskStatus.RUNNING), (False, TaskStatus.INCONSISTENT)],
)
def test_inconsistent_state_blocks_routing(
    inconsistent: bool, status: TaskStatus
) -> None:
    decision = select_next_phase(
        _state(
            inconsistent=inconsistent,
            status=status,
            current_phase=Phase.TEST,
            artifacts={"SPEC.md": False},
        )
    )

    assert decision == RoutingDecision(Phase.TEST, "state_inconsistent", blocked=True)


@pytest.mark.parametrize(
    ("status", "reason"),
    [(TaskStatus.BLOCKED, "task_blocked"), (TaskStatus.FAILED, "task_failed")],
)
def test_blocked_or_failed_state_blocks_routing(status: TaskStatus, reason: str) -> None:
    decision = select_next_phase(
        _state(status=status, current_phase=Phase.PLAN, artifacts={"SPEC.md": False})
    )

    assert decision == RoutingDecision(Phase.PLAN, reason, blocked=True)


def test_waiting_input_routes_to_answer_required() -> None:
    interaction = InteractionRecord(
        interaction_id="ask-000001",
        phase=Phase.CODE,
        question="Continue?",
        answer=None,
        status=InteractionStatus.WAITING,
    )
    state = replace(
        _state(),
        status=TaskStatus.WAITING_INPUT,
        interaction_seq=1,
        interactions=(interaction,),
        pending_interaction_id=interaction.interaction_id,
    )

    assert select_next_phase(state) == RoutingDecision(
        Phase.CODE,
        "interaction_answer_required",
        blocked=True,
    )


def test_failed_test_routes_to_review() -> None:
    decision = select_next_phase(_state(latest_test_status="failed"))

    assert decision == RoutingDecision(Phase.REVIEW, "test_failed")


def test_retry_budget_exhausted_requires_rollback() -> None:
    decision = select_next_phase(
        _state(
            latest_test_status="failed",
            retry_budget_remaining=0,
            latest_checkpoint="checkpoint-001",
        )
    )

    assert decision == RoutingDecision(
        Phase.REVIEW,
        "retry_budget_exhausted",
        rollback_required=True,
    )


def test_retry_budget_exhausted_without_checkpoint_blocks() -> None:
    decision = select_next_phase(
        _state(latest_test_status="failed", retry_budget_remaining=0)
    )

    assert decision == RoutingDecision(
        Phase.REVIEW,
        "retry_budget_exhausted_no_checkpoint",
        blocked=True,
    )


def test_consumed_test_failure_does_not_re_route_to_review() -> None:
    decision = select_next_phase(
        _state(latest_test_status="failed", test_status_consumed=True)
    )

    assert decision == RoutingDecision(Phase.CODE, "code_incomplete")


def test_spec_and_plan_complete_routes_to_code() -> None:
    decision = select_next_phase(_state())

    assert decision == RoutingDecision(Phase.CODE, "code_incomplete")


@pytest.mark.parametrize(
    ("latest_test_status", "phase_completed"),
    [
        ("none", {"code": True, "test": True}),
        ("passed", {"code": True, "test": False}),
    ],
)
def test_completed_code_routes_to_test_until_tests_complete(
    latest_test_status: str, phase_completed: dict[str, bool]
) -> None:
    decision = select_next_phase(
        _state(
            latest_test_status=latest_test_status,
            phase_completed=phase_completed,
        )
    )

    assert decision == RoutingDecision(Phase.TEST, "test_required")


def test_completed_tests_route_to_review_until_review_is_complete() -> None:
    decision = select_next_phase(
        _state(
            latest_test_status="passed",
            phase_completed={"code": True, "test": True, "review": False},
        )
    )

    assert decision == RoutingDecision(Phase.REVIEW, "review_required")


@pytest.mark.parametrize(
    ("artifact_name", "reason"),
    [
        ("KNOWLEDGE.md", "knowledge_missing"),
        ("DELIVERABLES.md", "deliverables_missing"),
    ],
)
def test_missing_deliver_artifact_routes_to_deliver(
    artifact_name: str, reason: str
) -> None:
    decision = select_next_phase(
        _state(
            artifacts={
                "KNOWLEDGE.md": artifact_name != "KNOWLEDGE.md",
                "DELIVERABLES.md": artifact_name != "DELIVERABLES.md",
            },
            latest_test_status="passed",
            phase_completed={"code": True, "test": True, "review": True},
        )
    )

    assert decision == RoutingDecision(Phase.DELIVER, reason)


def test_missing_knowledge_precedes_missing_deliverables() -> None:
    decision = select_next_phase(
        _state(
            artifacts={"KNOWLEDGE.md": False, "DELIVERABLES.md": False},
            latest_test_status="passed",
            phase_completed={"code": True, "test": True, "review": True},
        )
    )

    assert decision == RoutingDecision(Phase.DELIVER, "knowledge_missing")


def test_full_completion_returns_completed_deliver_decision() -> None:
    decision = select_next_phase(
        _state(
            artifacts={"KNOWLEDGE.md": True, "DELIVERABLES.md": True},
            latest_test_status="passed",
            phase_completed={"code": True, "test": True, "review": True},
        )
    )

    assert decision == RoutingDecision(Phase.DELIVER, "all_done", completed=True)


def test_persisted_completed_status_blocks_when_deliverables_are_missing() -> None:
    decision = select_next_phase(
        _state(
            status=TaskStatus.COMPLETED,
            current_phase=Phase.DELIVER,
            artifacts={"KNOWLEDGE.md": False, "DELIVERABLES.md": False},
        )
    )

    assert decision == RoutingDecision(Phase.DELIVER, "knowledge_missing", blocked=True)


def test_router_is_pure_and_does_not_write_state() -> None:
    state = _state()
    original_artifacts = dict(state.artifacts)
    original_phase_completed = dict(state.phase_completed)

    decision = select_next_phase(state)

    assert decision == RoutingDecision(Phase.CODE, "code_incomplete")
    assert dict(state.artifacts) == original_artifacts
    assert dict(state.phase_completed) == original_phase_completed


def _state(
    *,
    artifacts: dict[str, bool] | None = None,
    phase_completed: dict[str, bool] | None = None,
    status: TaskStatus = TaskStatus.RUNNING,
    current_phase: Phase = Phase.CODE,
    latest_test_status: str = "none",
    test_status_consumed: bool = False,
    retry_budget_remaining: int = 1,
    latest_checkpoint: str | None = None,
    inconsistent: bool = False,
) -> TaskState:
    all_artifacts = {
        "SPEC.md": True,
        "PLAN.md": True,
        "TEST_REPORT.md": False,
        "REVIEW.md": False,
        "KNOWLEDGE.md": False,
        "DELIVERABLES.md": False,
    }
    if artifacts is not None:
        all_artifacts.update(artifacts)
    all_phase_completed = {
        "spec": True,
        "plan": True,
        "code": False,
        "test": False,
        "review": False,
        "deliver": False,
    }
    if phase_completed is not None:
        all_phase_completed.update(phase_completed)
    return TaskState(
        schema_version=1,
        task_id="router-test",
        goal=None,
        status=status,
        current_phase=current_phase,
        files_changed=(),
        latest_checkpoint=latest_checkpoint,
        checkpoint_seq=0,
        tests_run=(),
        latest_test_status=latest_test_status,
        test_status_consumed=test_status_consumed,
        retry_budget_remaining=retry_budget_remaining,
        inconsistent=inconsistent,
        source_edits_this_phase=0,
        rollback_required=False,
        rollback_done=False,
        phase_completed=all_phase_completed,
        artifacts=all_artifacts,
    )
