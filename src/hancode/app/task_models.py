"""Application-layer data models for task lifecycle presentation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from hancode.core.models import Phase, TaskStatus
from hancode.core.state import TaskState
from hancode.runtime.agent_loop import AgentRunResult


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

    @classmethod
    def from_state(cls, state: TaskState) -> TaskSummary:
        resumable = (
            state.status is TaskStatus.BLOCKED and not state.inconsistent
        ) or (
            state.status is TaskStatus.INCONSISTENT
            and state.rollback_required
            and state.latest_checkpoint is not None
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
