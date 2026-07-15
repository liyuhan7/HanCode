from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Mapping, cast

from hancode.actions import Action
from hancode.agent_loop import AgentLoop, CheckpointManager, Policy
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
    def __init__(self, *, requires_checkpoint: bool = False) -> None:
        self._requires_checkpoint = requires_checkpoint

    def evaluate(
        self, *, action: Action, phase: Phase, state: TaskState
    ) -> AllowedDecision:
        assert action.phase is phase
        assert state.current_phase is phase
        return AllowedDecision(
            requires_checkpoint=(
                self._requires_checkpoint
                and action.tool_name in {"write_file", "edit_file"}
            )
        )


class ScriptedTools:
    def __init__(
        self,
        *,
        events: list[str] | None = None,
        write_success: bool = True,
    ) -> None:
        self.actions: list[Action] = []
        self.events = events
        self.write_success = write_success

    def dispatch(self, action: Action) -> ToolResult:
        if self.events is not None:
            self.events.append("dispatch")
        self.actions.append(action)
        if action.tool_name == "run_tests":
            return ToolResult(
                success=False,
                action_name="run_tests",
                exit_code=1,
                stderr="E   AssertionError: expected retry\n1 failed",
            )
        if action.tool_name == "write_file" and not self.write_success:
            return ToolResult(
                success=False,
                action_name="write_file",
                error_summary="Source write failed.",
            )
        return ToolResult(success=True, action_name=action.tool_name or "unknown")


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


class RecordingCheckpointManager:
    def __init__(
        self,
        events: list[str],
        *,
        create_error: HanCodeError | None = None,
        commit_error: HanCodeError | None = None,
    ) -> None:
        self.events = events
        self.create_error = create_error
        self.commit_error = commit_error
        self.files: list[Path] | None = None
        self.reason: str | None = None

    def create(self, task_id: str, files: list[Path], reason: str) -> CheckpointManifest:
        self.events.append("create")
        self.files = files
        self.reason = reason
        if self.create_error is not None:
            raise self.create_error
        return _checkpoint_manifest(task_id)

    def commit(self, task_id: str, checkpoint_id: str) -> CheckpointManifest:
        self.events.append("commit")
        assert checkpoint_id == "ckpt-001"
        if self.commit_error is not None:
            raise self.commit_error
        return _checkpoint_manifest(task_id, status="committed", rollback_available=True)


class NoopRollbackManager:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def rollback_last(self, task_id: str) -> RollbackResult:
        self.calls.append(task_id)
        raise AssertionError("Task 2 must not roll back checkpoints.")


class RecordingContextBuilder:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def build(self, *, task_id: str, phase: Phase, state: TaskState) -> dict[str, object]:
        context: dict[str, object] = {"task_id": task_id, "phase": phase.value}
        self.calls.append(context)
        return context


def test_source_write_checkpoint_orders_create_dispatch_then_commit() -> None:
    events: list[str] = []
    checkpoints = RecordingCheckpointManager(events)
    loop = _loop(
        llm=MockLLM([_retry_write_action()]),
        state_store=MemoryStateStore(_retry_code_state()),
        context_builder=RecordingContextBuilder(),
        feedback=RecordingFeedback(),
        policy=AllowedPolicy(requires_checkpoint=True),
        tools=ScriptedTools(events=events),
        checkpoint_manager=checkpoints,
        max_steps=1,
    )

    loop.run("task-001")

    assert events == ["create", "dispatch", "commit"]
    assert checkpoints.files == [Path("src/main.py")]
    assert checkpoints.reason == "Fix the failed assertion."


def test_checkpoint_create_failure_blocks_before_source_write_dispatch() -> None:
    events: list[str] = []
    tools = ScriptedTools(events=events)
    checkpoints = RecordingCheckpointManager(
        events,
        create_error=HanCodeError(
            StructuredError(
                error_code="checkpoint_snapshot_failed",
                message="Checkpoint could not be created.",
                phase=Phase.CODE.value,
                denied_rule="checkpoint_persistence_required",
                suggested_fix="Restore checkpoint storage.",
            )
        ),
    )
    loop = _loop(
        llm=MockLLM([_retry_write_action()]),
        state_store=MemoryStateStore(_retry_code_state()),
        context_builder=RecordingContextBuilder(),
        feedback=RecordingFeedback(),
        policy=AllowedPolicy(requires_checkpoint=True),
        tools=tools,
        checkpoint_manager=checkpoints,
        max_steps=1,
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.BLOCKED
    assert result.error is not None
    assert result.error.error_code == "checkpoint_snapshot_failed"
    assert events == ["create"]
    assert tools.actions == []


def test_checkpointed_source_write_failure_marks_state_inconsistent_and_stops() -> None:
    events: list[str] = []
    state_store = MemoryStateStore(_retry_code_state())
    loop = _loop(
        llm=MockLLM([_retry_write_action()]),
        state_store=state_store,
        context_builder=RecordingContextBuilder(),
        feedback=RecordingFeedback(),
        policy=AllowedPolicy(requires_checkpoint=True),
        tools=ScriptedTools(events=events, write_success=False),
        checkpoint_manager=RecordingCheckpointManager(events),
        max_steps=1,
    )

    result = loop.run("task-001")

    assert events == ["create", "dispatch"]
    assert result.status is TaskStatus.INCONSISTENT
    assert result.error is not None
    assert result.error.error_code == "checkpointed_write_failed"
    assert result.final_state.inconsistent is True
    assert state_store.state.status is TaskStatus.INCONSISTENT
    assert result.risks[0].level == "high"


def test_checkpoint_commit_failure_marks_state_inconsistent_and_stops() -> None:
    events: list[str] = []
    state_store = MemoryStateStore(_retry_code_state())
    loop = _loop(
        llm=MockLLM([_retry_write_action()]),
        state_store=state_store,
        context_builder=RecordingContextBuilder(),
        feedback=RecordingFeedback(),
        policy=AllowedPolicy(requires_checkpoint=True),
        tools=ScriptedTools(events=events),
        checkpoint_manager=RecordingCheckpointManager(
            events,
            commit_error=HanCodeError(
                StructuredError(
                    error_code="checkpoint_commit_failed",
                    message="Checkpoint could not be committed.",
                    phase=Phase.CODE.value,
                    denied_rule="checkpoint_commit_required",
                    suggested_fix="Reconcile the source file.",
                )
            ),
        ),
        max_steps=1,
    )

    result = loop.run("task-001")

    assert events == ["create", "dispatch", "commit"]
    assert result.status is TaskStatus.INCONSISTENT
    assert result.error is not None
    assert result.error.error_code == "checkpoint_commit_failed"
    assert result.final_state.inconsistent is True
    assert state_store.state.status is TaskStatus.INCONSISTENT
    assert result.risks[0].level == "high"


def test_failed_test_retries_through_review_then_decrements_once_on_retry_write() -> None:
    state_store = MemoryStateStore(_state())
    context_builder = RecordingContextBuilder()
    llm = MockLLM(
        [
            _run_tests_action(),
            _finish_review_action(),
            _retry_write_action(),
            _retry_write_action(),
        ]
    )
    loop = _loop(
        llm=llm,
        state_store=state_store,
        context_builder=context_builder,
        feedback=RecordingFeedback(),
        policy=AllowedPolicy(requires_checkpoint=True),
        checkpoint_manager=RecordingCheckpointManager([]),
        max_steps=4,
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
    assert result.final_state.source_edits_this_phase == 2
    assert result.status is not TaskStatus.COMPLETED


def test_successful_retry_write_without_checkpoint_requirement_keeps_budget() -> None:
    state = _retry_code_state()
    loop = _loop(
        llm=MockLLM([_retry_write_action()]),
        state_store=MemoryStateStore(state),
        context_builder=RecordingContextBuilder(),
        feedback=RecordingFeedback(),
        policy=AllowedPolicy(requires_checkpoint=False),
        max_steps=1,
    )

    result = loop.run("task-001")

    assert result.retry_budget_remaining == 2
    assert result.final_state.source_edits_this_phase == 1


def test_rollback_tool_is_blocked_without_dispatch_or_rollback_call() -> None:
    tools = ScriptedTools()
    rollback_manager = NoopRollbackManager()
    loop = _loop(
        llm=MockLLM([_rollback_action()]),
        state_store=MemoryStateStore(_review_state()),
        context_builder=RecordingContextBuilder(),
        feedback=RecordingFeedback(),
        tools=tools,
        rollback_manager=rollback_manager,
        max_steps=1,
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.BLOCKED
    assert result.error is not None
    assert result.error.error_code == "rollback_deferred_to_task_4"
    assert tools.actions == []
    assert rollback_manager.calls == []


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
    policy: AllowedPolicy | None = None,
    tools: ScriptedTools | None = None,
    checkpoint_manager: RecordingCheckpointManager | None = None,
    rollback_manager: NoopRollbackManager | None = None,
    max_steps: int,
) -> AgentLoop:
    return AgentLoop(
        llm=llm,
        context_builder=context_builder,
        policy=cast(Policy, policy or AllowedPolicy()),
        tool_registry=tools or ScriptedTools(),
        feedback_builder=feedback,
        state_store=state_store,
        trace_appender=NoopTraceAppender(),
        checkpoint_manager=cast(
            CheckpointManager,
            checkpoint_manager or NoopCheckpointManager(),
        ),
        rollback_manager=rollback_manager or NoopRollbackManager(),
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


def _retry_code_state() -> TaskState:
    state = _state()
    phase_completed = dict(state.phase_completed)
    phase_completed[Phase.CODE.value] = False
    phase_completed[Phase.TEST.value] = False
    return replace(
        state,
        current_phase=Phase.CODE,
        latest_test_status="failed",
        test_status_consumed=True,
        phase_completed=phase_completed,
    )


def _review_state() -> TaskState:
    state = _state()
    phase_completed = dict(state.phase_completed)
    phase_completed[Phase.TEST.value] = True
    phase_completed[Phase.REVIEW.value] = False
    return replace(
        state,
        current_phase=Phase.REVIEW,
        latest_test_status="passed",
        phase_completed=phase_completed,
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


def _rollback_action() -> dict[str, object]:
    return {
        "type": "tool_call",
        "phase": Phase.REVIEW.value,
        "tool_name": "rollback_last_checkpoint",
        "args": {},
        "reason": None,
    }


def _checkpoint_manifest(
    task_id: str,
    *,
    status: Literal["pending", "committed", "rolled_back"] = "pending",
    rollback_available: bool = False,
) -> CheckpointManifest:
    return CheckpointManifest(
        schema_version=1,
        project_id="project-001",
        checkpoint_id="ckpt-001",
        task_id=task_id,
        phase=Phase.CODE,
        reason="Fix the failed assertion.",
        created_at=datetime.now(UTC),
        status=status,
        files=(),
        rollback_available=rollback_available,
    )
