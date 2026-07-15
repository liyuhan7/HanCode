from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from hancode.actions import Action
from hancode.agent_loop import AgentLoop
from hancode.checkpoints import CheckpointManifest, RollbackResult
from hancode.errors import HanCodeError, StructuredError
from hancode.llm import MockLLM
from hancode.models import Phase, TaskStatus
from hancode.state import TaskState
from hancode.tools import ToolResult
from hancode.trace import TraceEvent


@dataclass(frozen=True)
class AllowedDecision:
    allowed: bool = True
    reason: str = "Action is allowed."
    requires_checkpoint: bool = False
    denied_rule: str | None = None
    suggested_fix: str = "Continue."


class MemoryStateStore:
    def __init__(self, state: TaskState) -> None:
        self.state = state
        self.saves: list[TaskState] = []

    def load(self, task_id: str) -> TaskState:
        assert task_id == self.state.task_id
        return self.state

    def save(self, task_id: str, state: TaskState) -> None:
        assert task_id == state.task_id
        self.state = state
        self.saves.append(state)


class AllowedPolicy:
    def evaluate(
        self, *, action: Action, phase: Phase, state: TaskState
    ) -> AllowedDecision:
        assert action.phase is phase
        assert state.current_phase is phase
        return AllowedDecision()


class ScriptedTools:
    def dispatch(self, action: Action) -> ToolResult:
        if action.tool_name == "run_tests":
            return ToolResult(
                success=False,
                action_name="run_tests",
                exit_code=1,
                stderr="E   AssertionError: expected retry\n1 failed",
            )
        assert action.tool_name == "write_file"
        return ToolResult(success=True, action_name="write_file")


class RecordingFeedback:
    def from_parse_error(self, error: object) -> object:
        return {"kind": "parse"}

    def from_policy_denial(self, decision: object) -> object:
        return {"kind": "policy"}

    def from_tool_result(self, result: ToolResult, *, phase: Phase) -> object:
        return {"kind": "test_failure", "phase": phase.value, "result": result}

    def from_checkpoint_manifest(self, manifest: CheckpointManifest) -> object:
        return {"kind": "checkpoint"}

    def from_rollback_result(self, result: RollbackResult, *, phase: Phase) -> object:
        return {"kind": "rollback"}


class FailingFeedback(RecordingFeedback):
    def from_tool_result(self, result: ToolResult, *, phase: Phase) -> object:
        raise HanCodeError(
            StructuredError(
                error_code="feedback_input_invalid",
                message="Feedback cannot be built.",
                phase=phase.value,
                denied_rule="feedback_test_double",
                suggested_fix="Repair the feedback builder.",
            )
        )


class NoopTraceAppender:
    def append(
        self,
        task_id: str,
        *,
        event_type: str,
        phase: Phase,
        status: str,
        action: Mapping[str, object] | None = None,
        observation: Mapping[str, object] | None = None,
        error_summary: str | None = None,
        state_transition: Mapping[str, object] | None = None,
    ) -> TraceEvent:
        raise AssertionError("Task 2 must not append trace events.")


class NoopCheckpointManager:
    def create(self, task_id: str, files: list[object], reason: str) -> CheckpointManifest:
        raise AssertionError("Task 2 must not create checkpoints.")

    def commit(self, task_id: str, checkpoint_id: str) -> CheckpointManifest:
        raise AssertionError("Task 2 must not commit checkpoints.")


class NoopRollbackManager:
    def rollback_last(self, task_id: str) -> RollbackResult:
        raise AssertionError("Task 2 must not roll back checkpoints.")


class RecordingContextBuilder:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def build(self, *, task_id: str, phase: Phase, state: TaskState) -> dict[str, object]:
        context = {"task_id": task_id, "phase": phase.value}
        self.calls.append(context)
        return context


def test_failed_test_retries_through_review_then_decrements_once_on_retry_write() -> None:
    state_store = MemoryStateStore(_state())
    context_builder = RecordingContextBuilder()
    llm = MockLLM([_run_tests_action(), _finish_review_action(), _retry_write_action()])
    loop = _loop(
        llm=llm,
        state_store=state_store,
        context_builder=context_builder,
        feedback=RecordingFeedback(),
        max_steps=3,
    )

    result = loop.run("task-001")

    failed_test_state = next(
        saved
        for saved in state_store.saves
        if saved.latest_test_status == "failed" and not saved.test_status_consumed
    )
    review_state = next(
        saved
        for saved in state_store.saves
        if saved.phase_completed[Phase.REVIEW.value]
    )

    assert failed_test_state.phase_completed[Phase.TEST.value] is False
    assert failed_test_state.retry_budget_remaining == 2
    assert review_state.test_status_consumed is True
    assert review_state.phase_completed[Phase.CODE.value] is False
    assert llm.contexts[2]["phase"] == Phase.CODE.value
    assert llm.contexts[2]["observation"] == {
        "kind": "test_failure",
        "phase": Phase.TEST.value,
        "result": ToolResult(
            success=False,
            action_name="run_tests",
            exit_code=1,
            stderr="E   AssertionError: expected retry\n1 failed",
        ),
    }
    assert result.retry_budget_remaining == 1
    assert result.status is not TaskStatus.COMPLETED


def test_final_action_after_failed_test_cannot_bypass_router_completion() -> None:
    state_store = MemoryStateStore(_state())
    loop = _loop(
        llm=MockLLM([_run_tests_action(), _final_review_action()]),
        state_store=state_store,
        context_builder=RecordingContextBuilder(),
        feedback=RecordingFeedback(),
        max_steps=2,
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.BLOCKED
    assert result.status is not TaskStatus.COMPLETED
    assert result.error is not None
    assert result.error.error_code == "final_requires_router_completion"


def test_feedback_construction_failure_blocks_with_its_structured_error() -> None:
    loop = _loop(
        llm=MockLLM([_run_tests_action()]),
        state_store=MemoryStateStore(_state()),
        context_builder=RecordingContextBuilder(),
        feedback=FailingFeedback(),
        max_steps=1,
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.BLOCKED
    assert result.error is not None
    assert result.error.error_code == "feedback_input_invalid"
    assert result.error.denied_rule == "feedback_test_double"


def _loop(
    *,
    llm: MockLLM,
    state_store: MemoryStateStore,
    context_builder: RecordingContextBuilder,
    feedback: RecordingFeedback,
    max_steps: int,
) -> AgentLoop:
    return AgentLoop(
        llm=llm,
        context_builder=context_builder,
        policy=AllowedPolicy(),
        tool_registry=ScriptedTools(),
        feedback_builder=feedback,
        state_store=state_store,
        trace_appender=NoopTraceAppender(),
        checkpoint_manager=NoopCheckpointManager(),
        rollback_manager=NoopRollbackManager(),
        max_steps=max_steps,
    )


def _state() -> TaskState:
    return TaskState(
        schema_version=1,
        task_id="task-001",
        goal="Retry a failed test.",
        status=TaskStatus.CREATED,
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
        phase_completed={
            Phase.SPEC.value: True,
            Phase.PLAN.value: True,
            Phase.CODE.value: True,
            Phase.TEST.value: False,
            Phase.REVIEW.value: False,
            Phase.DELIVER.value: False,
        },
        artifacts={
            "SPEC.md": True,
            "PLAN.md": True,
            "TEST_REPORT.md": False,
            "REVIEW.md": False,
            "KNOWLEDGE.md": False,
            "DELIVERABLES.md": False,
        },
    )


def _run_tests_action() -> dict[str, object]:
    return {
        "type": "tool_call",
        "phase": Phase.TEST.value,
        "tool_name": "run_tests",
        "args": {},
        "reason": None,
    }


def _finish_review_action() -> dict[str, object]:
    return {
        "type": "finish_phase",
        "phase": Phase.REVIEW.value,
        "tool_name": None,
        "args": {},
        "reason": None,
    }


def _final_review_action() -> dict[str, object]:
    return {
        "type": "final",
        "phase": Phase.REVIEW.value,
        "tool_name": None,
        "args": {},
        "reason": None,
    }


def _retry_write_action() -> dict[str, object]:
    return {
        "type": "tool_call",
        "phase": Phase.CODE.value,
        "tool_name": "write_file",
        "args": {"path": "src/main.py", "content": "fixed\n"},
        "reason": "Fix the failed assertion.",
    }
