"""Application-layer data models for task lifecycle presentation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from hancode.core.interactions import InteractionRecord, InteractionStatus
from hancode.core.models import Phase, TaskStatus
from hancode.core.state import TaskState
from hancode.runtime.agent_loop import AgentRunResult
from hancode.tooling.file_tools import redact_text


@dataclass(frozen=True, slots=True)
class TaskSummary:
    task_id: str
    goal: str | None
    status: TaskStatus
    current_phase: Phase
    retry_budget_remaining: int
    latest_test_status: str
    files_changed: tuple[str, ...]
    tests_run: tuple[str, ...]
    latest_checkpoint: str | None
    rollback_required: bool
    inconsistent: bool
    artifacts: Mapping[str, bool]
    resumable: bool
    requires_input: bool = False
    pending_interaction: Mapping[str, object] | None = None
    requires_approval: bool = False
    pending_approval: Mapping[str, object] | None = None

    @classmethod
    def from_state(cls, state: TaskState) -> TaskSummary:
        pending = _pending_interaction(state)
        approval_pending = _pending_approval_for_summary(state)
        requires_input = (
            state.status is TaskStatus.WAITING_INPUT
            and pending is not None
            and pending.status is InteractionStatus.WAITING
        )
        requires_approval = (
            state.status is TaskStatus.WAITING_APPROVAL
            and approval_pending is not None
        )
        resumable = (
            state.status is TaskStatus.BLOCKED and not state.inconsistent
        ) or (
            state.status is TaskStatus.INCONSISTENT
            and state.rollback_required
            and state.latest_checkpoint is not None
        ) or (
            state.status is TaskStatus.WAITING_INPUT
            and pending is not None
            and pending.status is InteractionStatus.ANSWERED
        ) or (
            state.status is TaskStatus.WAITING_APPROVAL
            and approval_pending is not None
            and approval_pending.get("status") in ("approved", "rejected")
        )

        return cls(
            task_id=state.task_id,
            goal=state.goal,
            status=state.status,
            current_phase=state.current_phase,
            retry_budget_remaining=state.retry_budget_remaining,
            latest_test_status=state.latest_test_status,
            files_changed=state.files_changed,
            tests_run=state.tests_run,
            latest_checkpoint=state.latest_checkpoint,
            rollback_required=state.rollback_required,
            inconsistent=state.inconsistent,
            artifacts=state.artifacts,
            resumable=resumable,
            requires_input=requires_input,
            pending_interaction=(
                None
                if pending is None
                else {
                    "interaction_id": pending.interaction_id,
                    "phase": pending.phase.value,
                    "question": redact_text(pending.question),
                    "answer_received": pending.status is InteractionStatus.ANSWERED,
                }
            ),
            requires_approval=requires_approval,
            pending_approval=approval_pending,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "status": self.status.value,
            "current_phase": self.current_phase.value,
            "retry_budget_remaining": self.retry_budget_remaining,
            "latest_test_status": self.latest_test_status,
            "files_changed": list(self.files_changed),
            "tests_run": list(self.tests_run),
            "latest_checkpoint": self.latest_checkpoint,
            "rollback_required": self.rollback_required,
            "inconsistent": self.inconsistent,
            "artifacts": dict(self.artifacts),
            "resumable": self.resumable,
            "requires_input": self.requires_input,
            "pending_interaction": self.pending_interaction,
            "requires_approval": self.requires_approval,
            "pending_approval": self.pending_approval,
        }


def _pending_interaction(state: TaskState) -> InteractionRecord | None:
    if state.pending_interaction_id is None:
        return None
    return next(
        (
            interaction
            for interaction in state.interactions
            if interaction.interaction_id == state.pending_interaction_id
        ),
        None,
    )


def _pending_approval_for_summary(state: TaskState) -> Mapping[str, object] | None:
    if state.pending_approval_id is None:
        return None
    return {
        "approval_id": state.pending_approval_id,
        "status": "pending",
    }


@dataclass(frozen=True, slots=True)
class TaskRunSummary:
    task: TaskSummary
    steps: int
    tool_calls: tuple[str, ...]
    retry_budget_remaining: int
    risks: tuple[dict[str, object], ...]
    error: dict[str, object] | None
    trace_event_count: int

    @classmethod
    def from_result(cls, result: AgentRunResult) -> TaskRunSummary:
        return cls(
            task=TaskSummary.from_state(result.final_state),
            steps=result.steps,
            tool_calls=result.tool_calls,
            retry_budget_remaining=result.retry_budget_remaining,
            risks=tuple(risk.to_dict() for risk in result.risks),
            error=None if result.error is None else result.error.to_dict(),
            trace_event_count=len(result.trace_events),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "task": self.task.to_dict(),
            "steps": self.steps,
            "tool_calls": list(self.tool_calls),
            "retry_budget_remaining": self.retry_budget_remaining,
            "risks": list(self.risks),
            "error": self.error,
            "trace_event_count": self.trace_event_count,
        }
