from __future__ import annotations

from dataclasses import dataclass

from hancode.core.models import Phase, TaskStatus
from hancode.core.state import TaskState


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    phase: Phase
    reason: str
    rollback_required: bool = False
    blocked: bool = False
    completed: bool = False


def select_next_phase(state: TaskState) -> RoutingDecision:
    if state.inconsistent or state.status is TaskStatus.INCONSISTENT:
        if state.rollback_required and state.latest_checkpoint is not None:
            return RoutingDecision(
                Phase.REVIEW, "rollback_required", rollback_required=True
            )
        return RoutingDecision(
            state.current_phase, "state_inconsistent", blocked=True
        )
    if state.status is TaskStatus.COMPLETED:
        if not state.artifacts["KNOWLEDGE.md"]:
            return RoutingDecision(Phase.DELIVER, "knowledge_missing", blocked=True)
        if not state.artifacts["DELIVERABLES.md"]:
            return RoutingDecision(Phase.DELIVER, "deliverables_missing", blocked=True)
        return RoutingDecision(state.current_phase, "task_completed", completed=True)
    if state.status is TaskStatus.BLOCKED:
        return RoutingDecision(state.current_phase, "task_blocked", blocked=True)
    if state.status is TaskStatus.FAILED:
        return RoutingDecision(state.current_phase, "task_failed", blocked=True)
    if state.rollback_required and not state.rollback_done:
        return RoutingDecision(Phase.REVIEW, "rollback_required", rollback_required=True)
    if not state.artifacts["SPEC.md"]:
        return RoutingDecision(Phase.SPEC, "spec_missing")
    if not state.artifacts["PLAN.md"]:
        return RoutingDecision(Phase.PLAN, "plan_missing")
    if state.latest_test_status == "failed" and not state.test_status_consumed:
        if state.retry_budget_remaining <= 0:
            if state.latest_checkpoint is not None:
                return RoutingDecision(
                    Phase.REVIEW,
                    "retry_budget_exhausted",
                    rollback_required=True,
                )
            return RoutingDecision(
                Phase.REVIEW,
                "retry_budget_exhausted_no_checkpoint",
                blocked=True,
            )
        return RoutingDecision(Phase.REVIEW, "test_failed")
    if not state.phase_completed["code"]:
        return RoutingDecision(Phase.CODE, "code_incomplete")
    if state.latest_test_status == "none" or not state.phase_completed["test"]:
        return RoutingDecision(Phase.TEST, "test_required")
    if not state.phase_completed["review"]:
        return RoutingDecision(Phase.REVIEW, "review_required")
    if not state.artifacts["KNOWLEDGE.md"]:
        return RoutingDecision(Phase.DELIVER, "knowledge_missing")
    if not state.artifacts["DELIVERABLES.md"]:
        return RoutingDecision(Phase.DELIVER, "deliverables_missing")
    return RoutingDecision(Phase.DELIVER, "all_done", completed=True)
