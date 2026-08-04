from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Mapping

import pytest

from hancode.app.approval_service import ApprovalService
from hancode.core.actions import Action, ActionType
from hancode.core.state import TaskState, load_state, save_state
from hancode.core.test_strategy import TestCoverageItem
from hancode.runtime.agent_loop import (
    AgentLoop,
    InMemoryMutationGuard,
    _state_after_tool,
)
from hancode.runtime.engine import create_agent_loop
from hancode.runtime.pause import PauseToken
from hancode.storage.checkpoints import (
    CheckpointManifest,
    RollbackResult,
    commit_checkpoint,
    create_checkpoint,
)
from hancode.storage.workspace import init_project_workspace, init_task_workspace
from hancode.core.config import HanCodeConfig, load_config
from hancode.core.errors import HanCodeError, StructuredError
from hancode.core.failures import (
    FailureCategory,
    FailureRecord,
    FailureSource,
    RecoveryMode,
)
from hancode.core.interactions import InteractionRecord, InteractionStatus
from hancode.core.memory import MemoryBlob, MemoryKind, MemoryRecordDraft
from hancode.delivery_support.result import RequirementCoverage, RequirementStatus
from hancode.runtime.delivery_pipeline import DeliveryPipeline
from hancode.runtime.feedback import (
    FailureCategory as FeedbackFailureCategory,
    FeedbackBuilder,
    FeedbackReport,
)
from hancode.providers.mock import MockLLM
from hancode.core.models import Phase, TaskStatus
from hancode.policy.path_policy import PathZone
from hancode.policy.tool_policy import PolicyDecision, ToolPolicy
from hancode.tooling.factory import build_default_tool_registry
from hancode.tooling.registry import ToolResult
from hancode.storage.trace import TraceEvent
from hancode.storage.test_strategies import TestStrategyStore
from hancode.storage.memory import FilesystemMemoryStore


@dataclass(frozen=True)
class StubPolicyDecision:
    allowed: bool
    reason: str = "Action is allowed."
    requires_checkpoint: bool = False
    denied_rule: str | None = None
    suggested_fix: str = "Use an allowed action."
    target_zone: PathZone | None = None


def test_successful_strategy_record_updates_task_digest() -> None:
    action = Action(
        type=ActionType.TOOL_CALL,
        phase=Phase.CODE,
        tool_name="record_test_strategy",
        args={
            "command": "python -m pytest -q",
            "framework": "pytest",
            "test_files": ["tests/test_app.py"],
            "coverage": [
                {
                    "requirement": "REQ-001",
                    "verification": "test_app",
                }
            ],
        },
        reason=None,
    )
    result = ToolResult(
        success=True,
        action_name="record_test_strategy",
        output={"test_strategy_digest": "a" * 64},
        mutation_applied=True,
    )

    updated = _state_after_tool(
        _task_state(),
        action,
        result,
        False,
        source_write=False,
    )

    assert updated.test_strategy_digest == "a" * 64


def test_strategy_preflight_failure_clears_digest_without_recording_test() -> None:
    action = Action(
        type=ActionType.TOOL_CALL,
        phase=Phase.TEST,
        tool_name="run_tests",
        args={"command": "python -m pytest -q"},
        reason=None,
    )
    state = replace(_task_state(), test_strategy_digest="a" * 64)
    result = ToolResult(
        success=False,
        action_name="run_tests",
        output={"strategy_error": "test_strategy_stale"},
        error_summary="A registered test file changed.",
    )

    updated = _state_after_tool(
        state,
        action,
        result,
        False,
        source_write=False,
    )

    assert updated.test_strategy_digest is None
    assert updated.tests_run == ()
    assert updated.latest_test_status == "none"


def test_zero_tests_is_recorded_as_failed_evidence() -> None:
    action = Action(
        type=ActionType.TOOL_CALL,
        phase=Phase.TEST,
        tool_name="run_tests",
        args={"command": "python -m pytest -q"},
        reason=None,
    )
    result = ToolResult(
        success=True,
        action_name="run_tests",
        stdout="no tests ran in 0.01s",
        exit_code=0,
        command="python -m pytest -q",
    )

    updated = _state_after_tool(
        _task_state(),
        action,
        result,
        False,
        source_write=False,
    )

    assert updated.latest_test_status == "failed"


class StubStateStore:
    def __init__(self, state: TaskState) -> None:
        self.state = state
        self.task_ids: list[str] = []

    def load(self, task_id: str) -> TaskState:
        self.task_ids.append(task_id)
        return self.state

    def save(self, task_id: str, state: TaskState) -> None:
        assert task_id == state.task_id
        self.task_ids.append(task_id)
        self.state = state


class ReconcileStateStore(StubStateStore):
    def __init__(self, state: TaskState) -> None:
        super().__init__(state)
        self.recover_pending: list[bool] = []

    def reconcile(self, task_id: str, *, recover_pending: bool) -> TaskState:
        self.recover_pending.append(recover_pending)
        return self.state


class SpyTraceAppender:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.events: list[TraceEvent] = []

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
        self.calls.append(task_id)
        event = TraceEvent(
            event_id=f"evt-{len(self.events) + 1:06d}",
            seq=len(self.events) + 1,
            event_type=event_type,
            task_id=task_id,
            phase=phase,
            timestamp=datetime.now(UTC),
            status=status,
            action=action,
            observation=observation,
            error_summary=error_summary,
            state_transition=state_transition,
        )
        self.events.append(event)
        return event


class GappedTraceAppender(SpyTraceAppender):
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
        event = super().append(
            task_id,
            event_type=event_type,
            phase=phase,
            status=status,
            action=action,
            observation=observation,
            error_summary=error_summary,
            state_transition=state_transition,
        )
        if len(self.events) == 3:
            event = replace(
                event,
                event_id="evt-000004",
                seq=4,
            )
            self.events[-1] = event
        return event


class FailingTraceAppender(SpyTraceAppender):
    def __init__(self, *, fail_on: str | None = None) -> None:
        super().__init__()
        self._fail_on = fail_on

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
        if self._fail_on is None or event_type == self._fail_on:
            raise HanCodeError(
                StructuredError(
                    error_code="trace_write_error",
                    message="Trace storage is unavailable.",
                    phase=phase.value,
                    denied_rule="trace_write_required",
                    suggested_fix="Restore trace storage.",
                )
            )
        return super().append(
            task_id,
            event_type=event_type,
            phase=phase,
            status=status,
            action=action,
            observation=observation,
            error_summary=error_summary,
            state_transition=state_transition,
        )


class StubCheckpointManager:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def create(
        self, task_id: str, files: list[Path], reason: str
    ) -> CheckpointManifest:
        self.calls.append(task_id)
        raise AssertionError("T21 Task 1 must not create checkpoints.")

    def commit(self, task_id: str, checkpoint_id: str) -> CheckpointManifest:
        self.calls.append(task_id)
        raise AssertionError("T21 Task 1 must not commit checkpoints.")


class StubRollbackManager:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def rollback_last(self, task_id: str) -> RollbackResult:
        self.calls.append(task_id)
        raise AssertionError("T21 Task 1 must not roll back checkpoints.")


class StubDeliveryResult:
    def __init__(self, *, status: TaskStatus, blockers: tuple[str, ...]) -> None:
        self.status = status
        self.blockers = blockers


class StubDeliveryPipeline:
    """Simulate DeliveryPipeline.finalize() writing state behind the loop's back.

    Mirrors result.py ``_write_artifact``: the persisted state is updated
    (DELIVERABLES.md present, coverage digest, status) through the shared
    state store, so the AgentLoop's in-memory ``state`` becomes stale after
    finalize() returns.
    """

    def __init__(
        self,
        state_store: StubStateStore,
        *,
        status: TaskStatus,
        blockers: tuple[str, ...] = (),
    ) -> None:
        self._state_store = state_store
        self.status = status
        self.blockers = blockers
        self.finalized = False

    def record_test(self, task_root: Path, report: object, command: str) -> object:
        return None

    def record_build(self, task_root: Path, task_id: str, status: str) -> None:
        return None

    def record_diff(
        self,
        task_root: Path,
        task_id: str,
        digest: str | None,
        *,
        drifted: bool = False,
    ) -> None:
        return None

    def finalize(self, task_root: Path, task_id: str) -> StubDeliveryResult:
        self.finalized = True
        state = self._state_store.load(task_id)
        updated = replace(
            state,
            status=self.status,
            delivery_coverage_digest="d" * 64,
            artifacts={**state.artifacts, "DELIVERABLES.md": True},
        )
        self._state_store.save(task_id, updated)
        return StubDeliveryResult(status=self.status, blockers=self.blockers)


class SpyContextBuilder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Phase, TaskState]] = []

    def build(self, *, task_id: str, phase: Phase, state: TaskState, observation: object | None = None) -> dict[str, object]:
        self.calls.append((task_id, phase, state))
        context: dict[str, object] = {"task_id": task_id, "phase": phase.value}
        if observation is not None:
            to_dict = getattr(observation, "to_dict", None)
            context["observation"] = to_dict() if callable(to_dict) else observation
        return context


class FailingContextBuilder:
    def __init__(self, error: HanCodeError) -> None:
        self.error = error

    def build(self, *, task_id: str, phase: Phase, state: TaskState, observation: object | None = None) -> dict[str, object]:
        raise self.error


class SpyPolicy:
    def __init__(self, decision: StubPolicyDecision, events: list[str]) -> None:
        self.decision = decision
        self.events = events
        self.actions: list[Action] = []

    def evaluate(
        self, *, action: Action, phase: Phase, state: TaskState
    ) -> StubPolicyDecision:
        assert state.current_phase is phase
        self.events.append("policy")
        self.actions.append(action)
        return self.decision


class SpyToolRegistry:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.actions: list[Action] = []

    def dispatch(self, action: Action) -> ToolResult:
        self.events.append("tool")
        self.actions.append(action)
        return ToolResult(success=True, action_name=action.tool_name or "unknown")


class PauseAfterFirstActionLLM(MockLLM):
    def __init__(self, actions: list[dict[str, object]], token: PauseToken) -> None:
        super().__init__(actions)
        self._token = token

    def next_action(self, context: dict[str, object]) -> dict[str, object]:
        action = super().next_action(context)
        self._token.request()
        return action


class PauseAfterToolRegistry(SpyToolRegistry):
    def __init__(self, events: list[str], token: PauseToken) -> None:
        super().__init__(events)
        self._token = token

    def dispatch(self, action: Action) -> ToolResult:
        result = super().dispatch(action)
        self._token.request()
        return result


class FailingToolRegistry(SpyToolRegistry):
    def dispatch(self, action: Action) -> ToolResult:
        self.events.append("tool")
        self.actions.append(action)
        return ToolResult(
            success=False,
            action_name=action.tool_name or "unknown",
            error_summary="File does not exist.",
            error_code="file_not_found",
        )


class SpyFeedbackBuilder:
    def __init__(self) -> None:
        self.parse_errors: list[object] = []
        self.policy_denials: list[object] = []
        self.tool_results: list[object] = []
        self.tool_result_phases: list[Phase] = []

    def from_parse_error(self, error: object) -> object:
        self.parse_errors.append(error)
        return {"kind": "parse_error"}

    def from_policy_denial(self, decision: object) -> object:
        self.policy_denials.append(decision)
        return {"kind": "policy_denial"}

    def from_tool_result(self, result: object, *, phase: Phase) -> object:
        self.tool_results.append(result)
        self.tool_result_phases.append(phase)
        return {"kind": "tool_result", "result": result}

    def from_checkpoint_manifest(self, manifest: CheckpointManifest) -> object:
        return {"kind": "checkpoint", "manifest": manifest}

    def from_rollback_result(self, result: RollbackResult, *, phase: Phase) -> object:
        return {"kind": "rollback", "result": result, "phase": phase}


@dataclass(frozen=True, slots=True)
class _MemoryRecord:
    memory_id: str = "mem-000001"
    blob_ref: str | None = None
    content_sha256: str | None = None
    blob_bytes: int | None = None
    workspace_generation: int = 0
    kind: str = "tool_result"


class SpyMemoryStore:
    def __init__(self) -> None:
        self.tool_records: list[tuple[Action, ToolResult]] = []

    def ensure_capacity(self, task_id: str, *, reserved_bytes: int) -> None:
        return None

    def record_tool_result(
        self,
        task_id: str,
        *,
        phase: Phase,
        action: Action,
        result: ToolResult,
        observation: object,
        state: TaskState,
    ) -> _MemoryRecord:
        self.tool_records.append((action, result))
        return _MemoryRecord()

    def record_rollback(
        self,
        task_id: str,
        *,
        phase: Phase,
        result: RollbackResult,
        observation: object,
        state: TaskState,
    ) -> _MemoryRecord:
        return _MemoryRecord(memory_id="mem-rollback", kind="rollback")


class FailingMemoryStore(SpyMemoryStore):
    def record_tool_result(
        self,
        task_id: str,
        *,
        phase: Phase,
        action: Action,
        result: ToolResult,
        observation: object,
        state: TaskState,
    ) -> _MemoryRecord:
        raise HanCodeError(
            StructuredError(
                error_code="memory_write_error",
                message="Task runtime memory could not be persisted.",
                phase=phase.value,
                denied_rule="memory_persistence_required",
                suggested_fix="Restore task memory storage before continuing.",
            )
        )


class CorruptMemoryToolRegistry(SpyToolRegistry):
    def __init__(self, events: list[str], error_code: str) -> None:
        super().__init__(events)
        self.error_code = error_code

    def dispatch(self, action: Action) -> ToolResult:
        self.events.append("tool")
        self.actions.append(action)
        raise HanCodeError(
            StructuredError(
                error_code=self.error_code,
                message="Task runtime memory cannot be trusted.",
                phase=action.phase.value,
                denied_rule="valid_runtime_memory_required",
                suggested_fix="Repair task runtime memory before continuing.",
            )
        )


def test_finish_action_routes_to_the_next_phase_with_context() -> None:
    loop, llm, context_builder, _, _, _ = _build_loop([_finish_action()])

    result = loop.run("task-001")

    assert result.status is TaskStatus.BLOCKED
    assert context_builder.calls[0][0:2] == ("task-001", Phase.CODE)
    assert llm.contexts == (
        {"task_id": "task-001", "phase": "code"},
        {"task_id": "task-001", "phase": "test"},
    )


def test_agent_loop_parses_action_before_policy() -> None:
    loop, _, _, policy, _, _ = _build_loop([_finish_action()])

    loop.run("task-001")

    assert policy.actions[0].type.value == "finish_phase"


def test_agent_loop_calls_policy_before_tool() -> None:
    events: list[str] = []
    loop, _, _, _, _, _ = _build_loop([_read_file_action(), _finish_action()], events=events)

    loop.run("task-001")

    assert events == ["policy", "tool", "policy"]


def test_agent_loop_persists_tool_feedback_before_completion_trace() -> None:
    memory_store = SpyMemoryStore()
    trace = SpyTraceAppender()
    loop, _, _, _, _, _ = _build_loop(
        [_read_file_action(), _finish_action()],
        memory_store=memory_store,
        trace_appender=trace,
    )

    result = loop.run("task-001")

    assert memory_store.tool_records[0][0].tool_name == "read_file"
    assert result.final_observation == {"kind": "tool_result", "result": memory_store.tool_records[0][1], "memory_ref": {"memory_id": "mem-000001", "persisted": True, "has_content": False, "workspace_generation": 0}}
    completed = next(event for event in trace.events if event.event_type == "tool_completed")
    assert completed.observation is not None
    assert completed.observation["memory_id"] == "mem-000001"


def test_read_memory_failure_blocks_without_a_second_provider_call() -> None:
    loop, llm, _, _, tools, _ = _build_loop(
        [_read_file_action(), _finish_action()],
        memory_store=FailingMemoryStore(),
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.BLOCKED
    assert result.error is not None
    assert result.error.error_code == "memory_write_error"
    assert len(tools.actions) == 1
    assert len(llm.contexts) == 1


@pytest.mark.parametrize(
    "error_code",
    [
        "memory_corrupt",
        "memory_task_identity_mismatch",
        "memory_path_link_not_allowed",
        "memory_write_error",
    ],
)
def test_memory_tool_integrity_failure_blocks_without_record_or_second_provider(
    error_code: str,
) -> None:
    events: list[str] = []
    tools = CorruptMemoryToolRegistry(events, error_code)
    memory_store = SpyMemoryStore()
    loop, llm, _, _, _, feedback = _build_loop(
        [
            {
                "type": "tool_call",
                "phase": "code",
                "tool_name": "memory_search",
                "args": {"query": "needle"},
                "reason": None,
            },
            _finish_action(),
        ],
        events=events,
        tool_registry=tools,
        memory_store=memory_store,
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.BLOCKED
    assert result.error is not None
    assert result.error.error_code == error_code
    assert len(llm.contexts) == 1
    assert memory_store.tool_records == []
    assert feedback.tool_results == []


def test_memory_search_then_read_recovers_history_across_agent_loop_instances(
    tmp_path: Path,
) -> None:
    init_project_workspace(tmp_path, "project-001", "Course", "Assignment")
    init_task_workspace(tmp_path, "task-001", goal="Recover historical evidence.")
    store = FilesystemMemoryStore(tmp_path)
    historical = store.append(
        "task-001",
        MemoryRecordDraft(
            phase=Phase.SPEC,
            kind=MemoryKind.TOOL_RESULT,
            tool_name="get_diff",
            success=True,
            summary="Captured recovery needle.",
            blob=MemoryBlob.text("historical evidence body\n"),
        ),
    ).record
    config = load_config(tmp_path, "task-001")

    search_loop = create_agent_loop(
        tmp_path,
        "task-001",
        provider=MockLLM(
            [
                {
                    "type": "tool_call",
                    "phase": "spec",
                    "tool_name": "memory_search",
                    "args": {"query": "recovery needle"},
                    "reason": None,
                }
            ]
        ),
        tool_registry=build_default_tool_registry(config),
        max_steps=1,
    )
    searched = search_loop.run("task-001")
    save_state(
        config.task_root,
        replace(load_state(config.task_root), status=TaskStatus.CREATED),
    )

    read_loop = create_agent_loop(
        tmp_path,
        "task-001",
        provider=MockLLM(
            [
                {
                    "type": "tool_call",
                    "phase": "spec",
                    "tool_name": "memory_read",
                    "args": {"memory_id": historical.memory_id},
                    "reason": None,
                }
            ]
        ),
        tool_registry=build_default_tool_registry(config),
        max_steps=1,
    )
    read = read_loop.run("task-001")

    snapshot = store.load("task-001").snapshot
    access_records = [
        record for record in snapshot.records if record.kind is MemoryKind.MEMORY_ACCESS
    ]
    assert searched.tool_calls == ("memory_search",)
    assert read.tool_calls == ("memory_read",)
    assert [record.tool_name for record in access_records] == [
        "memory_search",
        "memory_read",
    ]
    assert all(record.blob_ref is None for record in access_records)
    assert read.final_observation is not None
    assert "historical evidence body" in read.final_observation.to_dict()["summary"]


def test_policy_denial_does_not_execute_tool() -> None:
    events: list[str] = []
    loop, _, _, policy, tools, feedback = _build_loop(
        [_read_file_action()],
        decision=StubPolicyDecision(
            allowed=False,
            reason="Source files are protected.",
            denied_rule="protected_file",
            suggested_fix="Choose an allowed file.",
        ),
        events=events,
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.BLOCKED
    assert result.error is not None
    assert result.error.to_dict() == {
        "error_code": "policy_denied",
        "message": "Source files are protected.",
        "phase": "code",
        "denied_rule": "protected_file",
        "suggested_fix": "Choose an allowed file.",
    }
    assert events == ["policy"]
    assert not tools.actions
    assert feedback.policy_denials == [policy.decision]


def test_policy_denial_keeps_primary_error_when_trace_write_fails() -> None:
    events: list[str] = []
    loop, _, _, _, tools, _ = _build_loop(
        [_read_file_action()],
        decision=StubPolicyDecision(
            allowed=False,
            reason="Source files are protected.",
            denied_rule="protected_file",
            suggested_fix="Choose an allowed file.",
        ),
        events=events,
        trace_appender=FailingTraceAppender(fail_on="policy_denied"),
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.BLOCKED
    assert result.error is not None
    assert result.error.error_code == "policy_denied"
    assert result.error.denied_rule == "protected_file"
    assert [risk.level for risk in result.risks] == ["medium"]
    assert result.risks[0].message.startswith("The audit trace")
    assert not tools.actions


def test_real_tool_policy_denial_does_not_execute_tool(tmp_path: Path) -> None:
    events: list[str] = []
    llm = MockLLM(
        [
            {
                "type": "tool_call",
                "phase": "code",
                "tool_name": "write_file",
                "args": {"path": "assignment.md", "content": "changed\n"},
                "reason": "Change assignment.",
            }
        ]
    )
    tools = SpyToolRegistry(events)
    feedback = SpyFeedbackBuilder()
    loop = AgentLoop(
        llm=llm,
        context_builder=SpyContextBuilder(),
        policy=ToolPolicy(_policy_config(tmp_path)),
        tool_registry=tools,
        feedback_builder=feedback,
        state_store=StubStateStore(_task_state()),
        trace_appender=SpyTraceAppender(),
            checkpoint_manager=StubCheckpointManager(),
            rollback_manager=StubRollbackManager(),
            memory_store=SpyMemoryStore(),
            max_steps=1,
        mutation_guard=InMemoryMutationGuard(),
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.BLOCKED
    assert result.error is not None
    assert result.error.to_dict() == {
        "error_code": "policy_denied",
        "message": "Target path is a protected course or credential file.",
        "phase": "code",
        "denied_rule": "protected_path",
        "suggested_fix": "Modify allowed source code instead; do not change course evaluation or credential files.",
    }
    assert not tools.actions
    assert len(feedback.policy_denials) == 1
    decision = feedback.policy_denials[0]
    assert isinstance(decision, PolicyDecision)
    assert decision.denied_rule == "protected_path"


def test_out_of_scope_task_file_is_policy_denied_without_inconsistent_state(
    tmp_path: Path,
) -> None:
    events: list[str] = []
    llm = MockLLM(
        [
            {
                "type": "tool_call",
                "phase": "code",
                "tool_name": "write_file",
                "args": {
                    "path": ".hancode/tasks/task-001/index.html",
                    "content": "<!doctype html>\n",
                },
                "reason": "Create the requested page.",
            }
        ]
    )
    tools = SpyToolRegistry(events)
    feedback = SpyFeedbackBuilder()
    trace = SpyTraceAppender()
    loop = AgentLoop(
        llm=llm,
        context_builder=SpyContextBuilder(),
        policy=ToolPolicy(_policy_config(tmp_path)),
        tool_registry=tools,
        feedback_builder=feedback,
        state_store=StubStateStore(_task_state()),
        trace_appender=trace,
            checkpoint_manager=StubCheckpointManager(),
            rollback_manager=StubRollbackManager(),
            memory_store=SpyMemoryStore(),
            max_steps=1,
        mutation_guard=InMemoryMutationGuard(),
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.BLOCKED
    assert result.final_state.inconsistent is False
    assert result.error is not None
    assert result.error.error_code == "policy_denied"
    assert result.error.denied_rule == "path_out_of_scope"
    assert not tools.actions
    assert len(feedback.policy_denials) == 1
    assert any(event.event_type == "policy_denied" for event in trace.events)


def test_max_steps_prevents_infinite_loop() -> None:
    trace = SpyTraceAppender()
    loop, llm, _, _, tools, _ = _build_loop(
        [_read_file_action(), _read_file_action(), _read_file_action()],
        max_steps=2,
        trace_appender=trace,
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.BLOCKED
    assert result.steps == 2
    assert result.error is not None
    assert result.error.error_code == "max_steps_exceeded"
    assert len(llm.contexts) == 2
    assert [action.tool_name for action in tools.actions] == ["read_file", "read_file"]
    assert trace.events[-1].event_type == "run_blocked"
    assert trace.events[-1].observation == {"error_code": "max_steps_exceeded"}


@pytest.mark.parametrize("interaction_enabled", [False, True])
def test_legacy_test_phase_without_strategy_reopens_code(
    interaction_enabled: bool,
) -> None:
    trace = SpyTraceAppender()
    state = replace(
        _task_state(),
        status=TaskStatus.RUNNING,
        current_phase=Phase.TEST,
        phase_completed={
            Phase.SPEC.value: True,
            Phase.PLAN.value: True,
            Phase.CODE.value: True,
            Phase.TEST.value: False,
            Phase.REVIEW.value: False,
            Phase.DELIVER.value: False,
        },
    )
    loop, llm, _, _, tools, _ = _build_loop(
        [_read_file_action()],
        max_steps=1,
        state=state,
        trace_appender=trace,
        interaction_enabled=interaction_enabled,
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.BLOCKED
    assert llm.contexts[0]["phase"] == Phase.CODE.value
    assert [action.tool_name for action in tools.actions] == ["read_file"]
    assert any(event.event_type == "test_strategy_missing" for event in trace.events)


def test_trace_sequence_skip_is_accepted_other_components_may_write_trace_events() -> None:
    """A seq jump forward is legitimate when other components (e.g. checkpoint
    manager) write trace events directly to disk.  The in-memory list lags."""
    loop, _, _, _, _, _ = _build_loop(
        [_read_file_action()],
        trace_appender=GappedTraceAppender(),
    )

    result = loop.run("task-001")

    # The skip is tolerated; only a *regressing* seq (< expected_seq) is fatal.
    assert result.status is TaskStatus.BLOCKED


def test_finish_action_does_not_stop_before_router_selects_next_phase() -> None:
    loop, _, _, _, tools, _ = _build_loop([_finish_action(), _read_file_action()])

    result = loop.run("task-001")

    assert result.status is TaskStatus.BLOCKED
    assert result.steps == 3
    assert result.tool_calls == ()
    assert not tools.actions


def test_agent_loop_result_preserves_non_state_port_boundaries() -> None:
    state = _task_state()
    trace_appender = SpyTraceAppender()
    checkpoint_manager = StubCheckpointManager()
    rollback_manager = StubRollbackManager()
    loop, _, _, _, _, _ = _build_loop(
        [_finish_action()],
        state=state,
        trace_appender=trace_appender,
        checkpoint_manager=checkpoint_manager,
        rollback_manager=rollback_manager,
    )

    result = loop.run("task-001")

    assert result.final_state is not state
    assert result.final_state.current_phase is Phase.TEST
    assert result.final_state.phase_completed[Phase.CODE.value] is True
    assert result.retry_budget_remaining == state.retry_budget_remaining
    assert [event.event_type for event in result.trace_events] == [
        "phase_started",
        "phase_completed",
        "phase_started",
    ]
    assert result.trace_events == tuple(trace_appender.events)
    assert checkpoint_manager.calls == []
    assert rollback_manager.calls == []


def test_model_final_cannot_complete_task() -> None:
    loop, _, _, _, tools, _ = _build_loop([_final_action(), _read_file_action()])

    result = loop.run("task-001")

    assert result.status is TaskStatus.BLOCKED
    assert result.steps == 1
    assert result.tool_calls == ()
    assert not tools.actions
    assert result.error is not None
    assert result.error.error_code == "final_not_model_selectable"


def test_tool_observation_is_fed_into_next_context() -> None:
    loop, llm, _, _, _, feedback = _build_loop([_read_file_action(), _finish_action()])

    loop.run("task-001")

    assert llm.contexts[1] == {
        "task_id": "task-001",
        "phase": "code",
        "observation": {
            "kind": "tool_result",
            "result": ToolResult(success=True, action_name="read_file"),
            "memory_ref": {
                "memory_id": "mem-000001",
                "persisted": True,
                "has_content": False,
                "workspace_generation": 0,
            },
        },
    }
    assert feedback.tool_result_phases == [Phase.CODE]


def test_parse_error_blocks_without_policy_or_tool() -> None:
    events: list[str] = []
    loop, _, _, policy, tools, feedback = _build_loop([{}], events=events)

    result = loop.run("task-001")

    assert result.status is TaskStatus.BLOCKED
    assert result.error is not None
    assert result.error.error_code == "missing_action_fields"
    assert events == []
    assert not policy.actions
    assert not tools.actions
    assert len(feedback.parse_errors) == 1


def test_parse_error_keeps_primary_error_when_trace_write_fails() -> None:
    loop, _, _, _, tools, _ = _build_loop(
        [{}],
        trace_appender=FailingTraceAppender(fail_on="action_parse_failed"),
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.BLOCKED
    assert result.error is not None
    assert result.error.error_code == "missing_action_fields"
    assert [risk.level for risk in result.risks] == ["medium"]
    assert result.risks[0].message.startswith("The audit trace")
    assert not tools.actions


def test_mock_llm_exhaustion_returns_structured_blocked_result() -> None:
    loop, llm, _, _, tools, _ = _build_loop([])

    result = loop.run("task-001")

    assert result.status is TaskStatus.BLOCKED
    assert result.steps == 1
    assert result.error is not None
    assert result.error.to_dict() == {
        "error_code": "mock_llm_exhausted",
        "message": "MockLLM action sequence exhausted.",
        "phase": "code",
        "denied_rule": None,
        "suggested_fix": "Provide another mock action or stop the loop as blocked.",
    }
    assert len(llm.contexts) == 1
    assert not tools.actions


def test_blocked_task_requires_explicit_resume_to_retry() -> None:
    blocked_state = _task_state()
    blocked_state = replace(blocked_state, status=TaskStatus.BLOCKED)
    loop, llm, _, _, tools, _ = _build_loop([_read_file_action()], state=blocked_state, max_steps=1)

    blocked = loop.run("task-001")
    resumed = loop.run("task-001", resume=True)

    assert blocked.status is TaskStatus.BLOCKED
    assert blocked.error is not None
    assert blocked.error.error_code == "task_blocked"
    assert resumed.tool_calls == ("read_file",)


def test_agent_loop_passes_resume_as_explicit_pending_recovery_authorization() -> None:
    state_store = ReconcileStateStore(_task_state())
    first, *_ = _build_loop(
        [_read_file_action()],
        state_store=state_store,
        max_steps=1,
    )

    first_result = first.run("task-001", resume=False)

    assert first_result.status is TaskStatus.BLOCKED
    second, *_ = _build_loop(
        [_read_file_action()],
        state_store=state_store,
        max_steps=1,
    )
    second_result = second.run("task-001", resume=True)

    assert second_result.status is TaskStatus.BLOCKED
    assert state_store.recover_pending == [False, True]


def test_context_builder_hancode_error_is_preserved_as_blocked() -> None:
    state = _task_state()
    context_error = HanCodeError(
        StructuredError(
            error_code="context_required_artifact_missing",
            message="Required artifact is missing.",
            phase="code",
            denied_rule="required_context",
            suggested_fix="Restore PLAN.md before retrying.",
        )
    )
    loop, _, _, _, _, _ = _build_loop([_read_file_action()], state=state)
    loop._context_builder = FailingContextBuilder(context_error)  # type: ignore[attr-defined]

    result = loop.run("task-001")

    assert result.status is TaskStatus.BLOCKED
    assert result.error == context_error.structured_error
    assert result.final_state.status is TaskStatus.BLOCKED


def test_resume_canonicalizes_inconsistent_blocked_state() -> None:
    state = replace(
        _task_state(),
        status=TaskStatus.BLOCKED,
        inconsistent=True,
    )
    loop, _, _, _, _, _ = _build_loop([], state=state)

    result = loop.run("task-001", resume=True)

    assert result.status is TaskStatus.INCONSISTENT
    assert result.final_state.status is TaskStatus.INCONSISTENT
    assert result.final_state.inconsistent is True


def test_real_feedback_observation_is_json_safe_for_mock_llm_context() -> None:
    state = _task_state()
    state = replace(
        state,
        current_phase=Phase.TEST,
        phase_completed={**state.phase_completed, Phase.CODE.value: True},
        test_strategy_digest="a" * 64,
    )
    loop, llm, _, _, _, _ = _build_loop(
        [
            {
                "type": "tool_call",
                "phase": "test",
                "tool_name": "run_tests",
                "args": {"command": "pytest -q"},
                "reason": None,
            },
            {
                "type": "finish_phase",
                "phase": "review",
                "tool_name": None,
                "args": {},
                "reason": None,
            },
        ],
        max_steps=2,
        state=state,
    )
    loop._feedback_builder = FeedbackBuilder()  # type: ignore[attr-defined]

    result = loop.run("task-001")

    assert result.status is TaskStatus.BLOCKED
    assert result.error is not None
    assert result.error.error_code == "phase_mismatch"
    assert isinstance(llm.contexts[1]["observation"], dict)
    assert llm.contexts[1]["observation"]["kind"] == "test_feedback"


def test_step_exhaustion_still_returns_completed_after_final_artifact_write() -> None:
    state = _task_state(
        phase_completed={phase.value: True for phase in Phase},
        latest_test_status="passed",
        artifacts={
            "SPEC.md": True,
            "PLAN.md": True,
            "TEST_REPORT.md": True,
            "REVIEW.md": True,
            "KNOWLEDGE.md": False,
            "DELIVERABLES.md": False,
        },
    )
    actions = [
        {
            "type": "tool_call",
            "phase": "deliver",
            "tool_name": "write_file",
            "args": {"path": "KNOWLEDGE.md", "content": "# Knowledge\n"},
            "reason": "Write knowledge.",
        },
        {
            "type": "tool_call",
            "phase": "deliver",
            "tool_name": "write_file",
            "args": {"path": "DELIVERABLES.md", "content": "# Deliverables\n"},
            "reason": "Write deliverables.",
        },
    ]
    loop, _, _, _, _, _ = _build_loop(
        actions,
        state=state,
        max_steps=2,
        decision=StubPolicyDecision(allowed=True, target_zone=PathZone.ARTIFACT),
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.COMPLETED
    assert result.steps == 2
    assert result.final_state.current_phase is Phase.DELIVER


def test_deliver_finalize_blocked_preserves_persisted_delivery_state() -> None:
    """Blocked delivery must not overwrite state written by finalize().

    Regression: when the delivery gate blocks (e.g. missing latest diff), the
    AgentLoop reused the stale in-memory state in ``_block()``, re-saving
    artifacts["DELIVERABLES.md"]=False and delivery_coverage_digest=None on top
    of the state finalize() had just persisted. That drift later surfaced as
    ``state_inconsistent``.
    """
    store = StubStateStore(
        replace(
            _task_state(),
            current_phase=Phase.DELIVER,
            latest_checkpoint="ckpt-005",
            latest_test_status="passed",
            phase_completed={
                phase.value: phase is not Phase.DELIVER for phase in Phase
            },
            artifacts={
                "SPEC.md": True,
                "PLAN.md": True,
                "TEST_REPORT.md": True,
                "REVIEW.md": True,
                "KNOWLEDGE.md": True,
                "DELIVERABLES.md": False,
            },
        )
    )
    pipeline = StubDeliveryPipeline(
        store,
        status=TaskStatus.BLOCKED,
        blockers=("存在 Checkpoint，但缺少最新 Diff 证据。",),
    )
    loop, _, _, _, _, _ = _build_loop(
        [_finish_deliver_action()],
        max_steps=1,
        state_store=store,
        delivery_pipeline=pipeline,
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.BLOCKED
    assert pipeline.finalized is True
    persisted = store.state
    assert persisted.artifacts["DELIVERABLES.md"] is True
    assert persisted.delivery_coverage_digest == "d" * 64
    assert persisted.status is TaskStatus.BLOCKED


def test_deliver_finish_blocked_without_diff_evidence_keeps_state_consistent(
    tmp_path: Path,
) -> None:
    """Real-pipeline E2E: missing diff evidence must not corrupt state.

    With a committed checkpoint and no latest diff evidence, the DELIVER
    phase gate rejects finish_phase (deliver_finish_requirements) before
    finalize() is reached, so the loop must keep the task consistently
    BLOCKED without persisting DELIVERABLES.md yet.
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    init_project_workspace(project_root, "project-001", "Course", "Assignment")
    task_root = init_task_workspace(project_root, "task-001", goal="Deliver.")
    state = load_state(task_root)
    save_state(
        task_root,
        replace(
            state,
            current_phase=Phase.CODE,
            artifacts={**state.artifacts, "SPEC.md": True, "PLAN.md": True},
        ),
    )
    (task_root / "SPEC.md").write_text("# Spec\n", encoding="utf-8")
    (task_root / "PLAN.md").write_text("# Plan\n", encoding="utf-8")
    (project_root / "src").mkdir()
    (project_root / "src" / "main.py").write_text(
        "def main():\n    pass\n", encoding="utf-8"
    )
    # A committed checkpoint exists, but no diff evidence was recorded yet.
    manifest = create_checkpoint(
        task_root, [Path("src/main.py")], "Before delivery diff."
    )
    commit_checkpoint(task_root, manifest.checkpoint_id)

    pipeline = DeliveryPipeline()
    pipeline.record_test(
        task_root,
        FeedbackReport(
            passed=True,
            failure_category=FeedbackFailureCategory.NONE,
            summary="Tests passed.",
            next_action_hint="Proceed to review.",
            passed_count=1,
            failed_count=0,
            raw_size_bytes=64,
        ),
        "python -m pytest -q",
    )
    pipeline.record_review(
        task_root,
        "task-001",
        [
            RequirementCoverage(
                requirement_id="REQ-001",
                status=RequirementStatus.COVERED,
                evidence="tests/test_app.py",
                risk=None,
                is_core=True,
            )
        ],
        [],
    )
    pipeline.record_knowledge(task_root, "task-001", [])

    state = load_state(task_root)
    save_state(
        task_root,
        replace(
            state,
            current_phase=Phase.DELIVER,
            latest_test_status="passed",
            phase_completed={
                phase.value: phase is not Phase.DELIVER for phase in Phase
            },
        ),
    )

    provider = MockLLM([_finish_deliver_action()])
    loop = create_agent_loop(
        project_root,
        "task-001",
        provider=provider,
        max_steps=1,
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.BLOCKED
    assert result.error is not None
    assert result.error.denied_rule == "deliver_finish_requirements"
    assert "get_diff" in (result.error.suggested_fix or "")
    final_state = load_state(task_root)
    assert final_state.status is TaskStatus.BLOCKED
    assert final_state.inconsistent is False
    assert final_state.phase_completed[Phase.DELIVER.value] is False
    # finalize() was not reached: the phase gate rejects finish without diff
    # evidence, so DELIVERABLES.md is not persisted yet.
    assert final_state.artifacts["DELIVERABLES.md"] is False
    assert not (task_root / "DELIVERABLES.md").is_file()
    # A subsequent reconcile must not flag drift.
    from hancode.core.state import reconcile_state

    assert reconcile_state(task_root, final_state) == final_state


def test_lifecycle_events_bracket_a_finished_phase() -> None:
    trace_appender = SpyTraceAppender()
    loop, _, _, _, _, _ = _build_loop(
        [_finish_action()],
        trace_appender=trace_appender,
    )

    loop.run("task-001")

    types = [event.event_type for event in trace_appender.events]
    assert "phase_started" in types
    assert "phase_completed" in types
    assert types.index("phase_started") < types.index("phase_completed")


def test_run_completed_event_is_emitted_on_router_completion() -> None:
    state = _task_state(
        phase_completed={phase.value: True for phase in Phase},
        artifacts={
            "SPEC.md": True,
            "PLAN.md": True,
            "TEST_REPORT.md": True,
            "REVIEW.md": True,
            "KNOWLEDGE.md": True,
            "DELIVERABLES.md": True,
        },
        latest_test_status="passed",
    )
    trace_appender = SpyTraceAppender()
    loop, _, _, _, _, _ = _build_loop(
        [], state=state, trace_appender=trace_appender
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.COMPLETED
    assert [event.event_type for event in trace_appender.events] == ["run_completed"]


def test_terminal_routing_stops_before_llm() -> None:
    state = _task_state(
        phase_completed={phase.value: True for phase in Phase},
        artifacts={
            "SPEC.md": True,
            "PLAN.md": True,
            "TEST_REPORT.md": True,
            "REVIEW.md": True,
            "KNOWLEDGE.md": True,
            "DELIVERABLES.md": True,
        },
        latest_test_status="passed",
    )
    loop, llm, _, _, _, _ = _build_loop([], state=state)

    result = loop.run("task-001")

    assert result.status is TaskStatus.COMPLETED
    assert result.steps == 0
    assert llm.contexts == ()


def test_ask_user_sets_waiting_input_without_tool_dispatch() -> None:
    loop, _, _, _, tools, _ = _build_loop([_ask_user_action()])

    result = loop.run("task-001")

    assert result.status is TaskStatus.WAITING_INPUT
    assert result.error is None
    assert result.final_state.status is TaskStatus.WAITING_INPUT
    assert result.final_state.current_phase is Phase.CODE
    assert result.final_state.pending_interaction_id == "ask-000001"
    assert result.final_observation == {
        "interaction_id": "ask-000001",
        "question": "Continue?",
    }
    assert not tools.actions


def test_ask_user_persists_question_and_writes_safe_trace() -> None:
    state_store = StubStateStore(_task_state())
    trace_appender = SpyTraceAppender()
    loop, _, _, _, _, _ = _build_loop(
        [_ask_user_action()], state_store=state_store, trace_appender=trace_appender
    )

    result = loop.run("task-001")

    assert len(result.final_state.interactions) == 1
    interaction = result.final_state.interactions[0]
    assert interaction.question == "Continue?"
    assert interaction.status is InteractionStatus.WAITING
    assert [event.event_type for event in trace_appender.events] == [
        "phase_started",
        "interaction_requested",
    ]
    assert trace_appender.events[-1].observation == {
        "interaction_id": "ask-000001",
        "question_length": len("Continue?"),
    }


def test_waiting_input_does_not_call_provider_until_answered() -> None:
    interaction = InteractionRecord(
        interaction_id="ask-000001",
        phase=Phase.CODE,
        question="Continue?",
        answer=None,
        status=InteractionStatus.WAITING,
    )
    waiting_state = replace(
        _task_state(),
        status=TaskStatus.WAITING_INPUT,
        interaction_seq=1,
        interactions=(interaction,),
        pending_interaction_id=interaction.interaction_id,
    )
    state_store = StubStateStore(waiting_state)
    loop, llm, _, _, _, _ = _build_loop(
        [_read_file_action()], state=waiting_state, state_store=state_store
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.WAITING_INPUT
    assert llm.contexts == ()
    assert state_store.state == waiting_state


def test_resume_with_answered_interaction_returns_to_running() -> None:
    interaction = InteractionRecord(
        interaction_id="ask-000001",
        phase=Phase.CODE,
        question="Continue?",
        answer="Yes",
        status=InteractionStatus.ANSWERED,
    )
    answered_state = replace(
        _task_state(),
        status=TaskStatus.WAITING_INPUT,
        interaction_seq=1,
        interactions=(interaction,),
        pending_interaction_id=interaction.interaction_id,
    )
    loop, _, context_builder, _, _, _ = _build_loop(
        [_read_file_action()], state=answered_state
    )

    result = loop.run("task-001", resume=True)

    assert result.status is TaskStatus.BLOCKED
    assert context_builder.calls[0][2].status is TaskStatus.RUNNING
    assert context_builder.calls[0][2].pending_interaction_id is None
    assert context_builder.calls[0][2].interactions[0].answer == "Yes"


def test_ask_user_trace_failure_keeps_valid_waiting_state() -> None:
    trace_appender = FailingTraceAppender(fail_on="interaction_requested")
    loop, _, _, _, _, _ = _build_loop(
        [_ask_user_action()], trace_appender=trace_appender
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.WAITING_INPUT
    assert result.final_state.status is TaskStatus.WAITING_INPUT
    assert result.final_state.pending_interaction_id == "ask-000001"
    assert result.error is not None
    assert result.error.error_code == "trace_write_error"
    assert len(result.trace_events) == 1
    assert result.trace_events[0].event_type == "phase_started"


def test_ask_user_redacts_secret_in_question() -> None:
    action = {
        "type": "ask_user",
        "phase": "code",
        "tool_name": None,
        "args": {"question": "Is sk-abc123 the intended key?"},
        "reason": None,
    }
    loop, _, _, _, _, _ = _build_loop([action])

    result = loop.run("task-001")

    assert result.status is TaskStatus.WAITING_INPUT
    assert len(result.final_state.interactions) == 1
    question = result.final_state.interactions[0].question
    assert "sk-abc123" not in question
    assert "[REDACTED]" in question


def test_ask_user_rejects_secret_only_question() -> None:
    state_store = StubStateStore(_task_state())
    loop, _, _, _, _, _ = _build_loop(
        [
            {
                "type": "ask_user",
                "phase": "code",
                "tool_name": None,
                "args": {"question": "sk-abc123"},
                "reason": None,
            }
        ],
        state_store=state_store,
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.BLOCKED
    assert result.error is not None
    assert (
        result.error.error_code == "interaction_question_contains_only_sensitive_content"
    )
    assert state_store.state.interactions == ()


def test_agent_loop_rejects_non_positive_max_steps() -> None:
    with pytest.raises(ValueError, match="max_steps must be positive"):
        _build_loop([_finish_action()], max_steps=0)


def test_same_parse_failure_blocks_before_max_steps_without_policy_or_tool() -> None:
    loop, llm, _, policy, tools, _ = _build_loop([{}, {}, {}], max_steps=100)

    result = loop.run("task-001")

    assert result.status is TaskStatus.BLOCKED
    assert result.error is not None
    assert result.error.error_code == "recovery_no_progress"
    assert len(llm.contexts) == 3
    assert policy.actions == []
    assert tools.actions == []
    assert result.final_state.active_failure is not None
    assert result.final_state.active_failure.repeat_count == 3
    assert result.final_state.active_failure.recovery_mode is RecoveryMode.BLOCKED


def test_same_policy_action_is_guarded_before_policy_on_second_and_third_attempt() -> None:
    denied = StubPolicyDecision(
        allowed=False,
        reason="protected",
        denied_rule="protected_path",
        suggested_fix="Choose source.",
        target_zone=None,
    )
    action = {
        "type": "tool_call",
        "phase": "code",
        "tool_name": "write_file",
        "args": {"path": "assignment.md", "content": "x"},
        "reason": "change",
    }
    loop, llm, _, policy, tools, _ = _build_loop(
        [action, action, action], max_steps=100, decision=denied
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.BLOCKED
    assert result.error is not None
    assert result.error.error_code == "recovery_no_progress"
    assert len(llm.contexts) == 3
    assert len(policy.actions) == 1
    assert tools.actions == []


def test_same_missing_file_failure_dispatches_once_then_guards() -> None:
    action = _read_file_action()
    tools = FailingToolRegistry([])
    loop, llm, _, policy, _, _ = _build_loop(
        [action, action, action], max_steps=100, tool_registry=tools
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.BLOCKED
    assert result.error is not None
    assert result.error.error_code == "recovery_no_progress"
    assert len(llm.contexts) == 3
    assert len(policy.actions) == 1
    assert len(tools.actions) == 1
    assert result.final_state.active_failure is not None
    assert result.final_state.active_failure.error_code == "file_not_found"


def test_blocked_active_failure_resume_does_not_call_llm() -> None:
    digest = "c" * 64
    failure = FailureRecord(
        failure_id="fail-cccccccccccc",
        source=FailureSource.ACTION_PARSE,
        category=FailureCategory.INVALID_ACTION,
        fingerprint=digest,
        action_digest="d" * 64,
        phase=Phase.CODE,
        tool_name=None,
        target=None,
        error_code="invalid_action_payload",
        safe_message="invalid",
        suggested_fix="fix",
        safe_details={},
        repeat_count=3,
        recovery_mode=RecoveryMode.BLOCKED,
    )
    state_store = StubStateStore(replace(_task_state(), active_failure=failure))
    loop, llm, _, _, _, _ = _build_loop(
        [_finish_action()], state=state_store.state, state_store=state_store
    )

    result = loop.run("task-001", resume=True)

    assert result.status is TaskStatus.BLOCKED
    assert llm.contexts == ()
    assert result.final_state.active_failure == failure


def test_pause_before_provider_call_persists_paused_state() -> None:
    token = PauseToken()
    token.request()
    loop, llm, _, _, tools, _ = _build_loop(
        [_read_file_action()],
        pause_token=token,
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.PAUSED
    assert result.error is None
    assert result.final_state.status is TaskStatus.PAUSED
    assert llm.contexts == ()
    assert tools.actions == []


def test_pause_after_provider_response_does_not_dispatch_action() -> None:
    token = PauseToken()
    llm = PauseAfterFirstActionLLM([_read_file_action()], token)
    loop, _, _, _, tools, _ = _build_loop(
        [],
        llm=llm,
        pause_token=token,
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.PAUSED
    assert len(llm.contexts) == 1
    assert tools.actions == []


def test_pause_requested_by_tool_waits_for_tool_completion() -> None:
    token = PauseToken()
    events: list[str] = []
    tools = PauseAfterToolRegistry(events, token)
    loop, _, _, _, _, _ = _build_loop(
        [_read_file_action()],
        events=events,
        tool_registry=tools,
        pause_token=token,
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.PAUSED
    assert [action.tool_name for action in tools.actions] == ["read_file"]
    assert events == ["policy", "tool"]


def _build_loop(
    actions: list[dict[str, object]],
    *,
    max_steps: int = 3,
    interaction_enabled: bool = False,
    state: TaskState | None = None,
    decision: StubPolicyDecision | None = None,
    events: list[str] | None = None,
    trace_appender: SpyTraceAppender | None = None,
    checkpoint_manager: StubCheckpointManager | None = None,
    rollback_manager: StubRollbackManager | None = None,
    state_store: StubStateStore | None = None,
    tool_registry: SpyToolRegistry | None = None,
    delivery_pipeline: StubDeliveryPipeline | None = None,
    pause_token: PauseToken | None = None,
    llm: MockLLM | None = None,
    memory_store: SpyMemoryStore | FailingMemoryStore | None = None,
) -> tuple[
    AgentLoop,
    MockLLM,
    SpyContextBuilder,
    SpyPolicy,
    SpyToolRegistry,
    SpyFeedbackBuilder,
]:
    recorded_events = events if events is not None else []
    llm = llm or MockLLM(actions)
    context_builder = SpyContextBuilder()
    policy = SpyPolicy(decision or StubPolicyDecision(allowed=True), recorded_events)
    tools = tool_registry or SpyToolRegistry(recorded_events)
    feedback = SpyFeedbackBuilder()
    loop = AgentLoop(
        llm=llm,
        context_builder=context_builder,
        policy=policy,
        tool_registry=tools,
        feedback_builder=feedback,
        state_store=state_store or StubStateStore(state or _task_state()),
        trace_appender=trace_appender or SpyTraceAppender(),
        checkpoint_manager=checkpoint_manager or StubCheckpointManager(),
        rollback_manager=rollback_manager or StubRollbackManager(),
        memory_store=memory_store or SpyMemoryStore(),
        max_steps=max_steps,
        interaction_enabled=interaction_enabled,
        mutation_guard=InMemoryMutationGuard(),
        delivery_pipeline=delivery_pipeline,
        pause_token=pause_token,
    )
    return loop, llm, context_builder, policy, tools, feedback


def _task_state(
    *,
    phase_completed: Mapping[str, bool] | None = None,
    artifacts: Mapping[str, bool] | None = None,
    latest_test_status: str = "none",
) -> TaskState:
    return TaskState(
        schema_version=1,
        task_id="task-001",
        goal="Implement the loop.",
        status=TaskStatus.CREATED,
        current_phase=Phase.CODE,
        files_changed=(),
        latest_checkpoint=None,
        checkpoint_seq=0,
        tests_run=(),
        latest_test_status=latest_test_status,
        test_status_consumed=False,
        retry_budget_remaining=2,
        inconsistent=False,
        source_edits_this_phase=0,
        rollback_required=False,
        rollback_done=False,
        phase_completed=phase_completed
        or {phase.value: phase is not Phase.CODE for phase in Phase},
        artifacts=artifacts
        or {
            "SPEC.md": True,
            "PLAN.md": True,
            "TEST_REPORT.md": False,
            "REVIEW.md": False,
            "KNOWLEDGE.md": False,
            "DELIVERABLES.md": False,
        },
    )


def _policy_config(project_root: Path) -> HanCodeConfig:
    return HanCodeConfig(
        project_root=project_root,
        hancode_root=project_root / ".hancode",
        allowed_workspace_root=project_root,
        task_root=project_root / ".hancode" / "tasks" / "task-001",
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
        max_trace_events=1000,
        protected_patterns=("assignment.md",),
        writable_roots=(project_root / "src",),
    )


def _read_file_action() -> dict[str, object]:
    return {
        "type": "tool_call",
        "phase": "code",
        "tool_name": "read_file",
        "args": {"path": "src/example.py"},
        "reason": None,
    }


def _test_list_files_action() -> dict[str, object]:
    return {
        "type": "tool_call",
        "phase": "test",
        "tool_name": "list_files",
        "args": {"path": ".hancode"},
        "reason": "Find the project test runner.",
    }


def _finish_action() -> dict[str, object]:
    return {
        "type": "finish_phase",
        "phase": "code",
        "tool_name": None,
        "args": {},
        "reason": None,
    }


def _finish_deliver_action() -> dict[str, object]:
    return {
        "type": "finish_phase",
        "phase": "deliver",
        "tool_name": None,
        "args": {},
        "reason": None,
    }


def _final_action() -> dict[str, object]:
    return {
        "type": "final",
        "phase": "code",
        "tool_name": None,
        "args": {},
        "reason": None,
    }


def _ask_user_action() -> dict[str, object]:
    return {
        "type": "ask_user",
        "phase": "code",
        "tool_name": None,
        "args": {"question": "Continue?"},
        "reason": None,
    }


def _prepare_explicit_test_loop(
    tmp_path: Path,
    *,
    passed: bool,
) -> tuple[Path, Path, MockLLM, list[str | None], AgentLoop]:
    project_root = tmp_path / "project"
    project_root.mkdir()
    init_project_workspace(project_root, "project-001", "Course", "Assignment")
    task_root = init_task_workspace(project_root, "task-001", goal="Run the tests.")
    (task_root / "SPEC.md").write_text("# Spec\n", encoding="utf-8")
    (task_root / "PLAN.md").write_text("# Plan\n", encoding="utf-8")
    (project_root / "tests").mkdir()
    (project_root / "tests" / "test_app.py").write_text(
        "def test_app():\n    assert True\n",
        encoding="utf-8",
    )
    strategy = TestStrategyStore(project_root).record(
        "task-001",
        command="python -m pytest -q",
        framework="pytest",
        test_files=("tests/test_app.py",),
        coverage=(
            TestCoverageItem(
                requirement="REQ-001",
                verification="test_app",
            ),
        ),
    )

    state = load_state(task_root)
    save_state(
        task_root,
        replace(
            state,
            current_phase=Phase.TEST,
            phase_completed={
                **state.phase_completed,
                Phase.SPEC.value: True,
                Phase.PLAN.value: True,
                Phase.CODE.value: True,
            },
            artifacts={
                **state.artifacts,
                "SPEC.md": True,
                "PLAN.md": True,
            },
            test_strategy_digest=strategy.digest,
        ),
    )

    calls: list[str | None] = []

    def run_tests_tool(command: str | None) -> ToolResult:
        calls.append(command)
        return ToolResult(
            success=passed,
            action_name="run_tests",
            exit_code=0 if passed else 1,
            stdout="1 passed" if passed else "E   AssertionError: expected 1\n1 failed",
            command=command,
        )

    provider_actions: list[dict[str, object]] = [
        {
            "type": "tool_call",
            "phase": "test",
            "tool_name": "run_tests",
            "args": {"command": "python -m pytest -q"},
            "reason": "Run the project behavioral tests.",
        }
    ]
    if passed:
        provider_actions.append(
            {
                "type": "finish_phase",
                "phase": "test",
                "tool_name": None,
                "args": {},
                "reason": "The approved test command passed.",
            }
        )
    provider = MockLLM(provider_actions)
    from hancode.core.config import load_config

    config = load_config(project_root, "task-001")
    registry = build_default_tool_registry(config, run_tests_tool=run_tests_tool)
    loop = create_agent_loop(
        project_root,
        "task-001",
        provider=provider,
        tool_registry=registry,
        max_steps=2,
    )
    return project_root, task_root, provider, calls, loop


def test_agent_creates_registers_and_runs_project_test_strategy(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    init_project_workspace(project_root, "project-001", "Course", "Assignment")
    project_file = project_root / ".hancode" / "project.json"
    project_data = json.loads(project_file.read_text(encoding="utf-8"))
    project_data["approval_mode"] = "all_source_writes"
    project_file.write_text(json.dumps(project_data), encoding="utf-8")
    task_root = init_task_workspace(
        project_root,
        "task-001",
        goal="Create and verify the requested behavior.",
    )
    (task_root / "SPEC.md").write_text("# Spec\n", encoding="utf-8")
    (task_root / "PLAN.md").write_text("# Plan\n", encoding="utf-8")
    state = load_state(task_root)
    save_state(
        task_root,
        replace(
            state,
            current_phase=Phase.CODE,
            phase_completed={
                **state.phase_completed,
                Phase.SPEC.value: True,
                Phase.PLAN.value: True,
            },
            artifacts={
                **state.artifacts,
                "SPEC.md": True,
                "PLAN.md": True,
            },
        ),
    )
    command = "python -m pytest tests/test_agent_feature.py -q"
    provider = MockLLM(
        [
            {
                "type": "tool_call",
                "phase": "code",
                "tool_name": "write_file",
                "args": {
                    "path": "tests/test_agent_feature.py",
                    "content": "def test_feature():\n    assert True\n",
                },
                "reason": "Create behavioral coverage for the requested feature.",
            },
            {
                "type": "tool_call",
                "phase": "code",
                "tool_name": "record_test_strategy",
                "args": {
                    "command": command,
                    "framework": "pytest",
                    "test_files": ["tests/test_agent_feature.py"],
                    "coverage": [
                        {
                            "requirement": "REQ-001",
                            "verification": "test_feature",
                        }
                    ],
                },
                "reason": None,
            },
            {
                "type": "finish_phase",
                "phase": "code",
                "tool_name": None,
                "args": {},
                "reason": None,
            },
            {
                "type": "tool_call",
                "phase": "test",
                "tool_name": "run_tests",
                "args": {"command": command},
                "reason": "Run the registered behavioral test.",
            },
            {
                "type": "finish_phase",
                "phase": "test",
                "tool_name": None,
                "args": {},
                "reason": None,
            },
        ]
    )
    calls: list[str | None] = []
    registry = build_default_tool_registry(
        load_config(project_root, "task-001"),
        run_tests_tool=lambda selected: (
            calls.append(selected)
            or ToolResult(
                success=True,
                action_name="run_tests",
                stdout="1 passed",
                exit_code=0,
                command=selected,
            )
        ),
    )
    loop = create_agent_loop(
        project_root,
        "task-001",
        provider=provider,
        tool_registry=registry,
        max_steps=6,
    )

    first_approval = loop.run("task-001")
    assert first_approval.status is TaskStatus.WAITING_APPROVAL
    ApprovalService(project_root).approve("task-001")
    second_approval = loop.run("task-001", resume=True)
    assert second_approval.status is TaskStatus.WAITING_APPROVAL
    ApprovalService(project_root).approve("task-001")
    loop.run("task-001", resume=True)

    final_state = load_state(task_root)
    assert (project_root / "tests" / "test_agent_feature.py").is_file()
    assert final_state.test_strategy_digest is not None
    assert final_state.tests_run == (command,)
    assert final_state.latest_test_status == "passed"
    assert final_state.artifacts["TEST_REPORT.md"] is True
    assert calls == [command]


def test_approved_run_tests_resumes_provider_and_persists_passed_state(
    tmp_path: Path,
) -> None:
    project_root, task_root, provider, calls, loop = _prepare_explicit_test_loop(
        tmp_path,
        passed=True,
    )

    waiting = loop.run("task-001")
    assert waiting.status is TaskStatus.WAITING_APPROVAL

    ApprovalService(project_root).approve("task-001")
    result = loop.run("task-001", resume=True)
    state = load_state(task_root)

    assert len(provider.contexts) >= 2
    assert result.final_state.pending_approval_id is None
    assert state.tests_run == ("python -m pytest -q",)
    assert state.latest_test_status == "passed"
    assert state.artifacts["TEST_REPORT.md"] is True
    assert state.phase_completed[Phase.TEST.value] is True
    second_observation = provider.contexts[1].get("observation")
    assert isinstance(second_observation, dict)
    assert second_observation["kind"] == "test_feedback"
    assert result.final_observation is not None
    observation = result.final_observation.to_dict()
    assert observation["kind"] == "test_feedback"
    assert observation["success"] is True
    assert observation["details"]["exit_code"] == 0
    assert calls == ["python -m pytest -q"]


def test_approved_failed_run_tests_routes_to_review_in_same_resume(
    tmp_path: Path,
) -> None:
    project_root, task_root, provider, calls, loop = _prepare_explicit_test_loop(
        tmp_path,
        passed=False,
    )

    waiting = loop.run("task-001")
    assert waiting.status is TaskStatus.WAITING_APPROVAL

    ApprovalService(project_root).approve("task-001")
    result = loop.run("task-001", resume=True)
    state = load_state(task_root)

    assert len(provider.contexts) >= 2
    assert result.final_state.pending_approval_id is None
    assert state.tests_run == ("python -m pytest -q",)
    assert state.latest_test_status == "failed"
    assert state.artifacts["TEST_REPORT.md"] is True
    assert state.current_phase is Phase.REVIEW
    assert calls == ["python -m pytest -q"]


def test_approval_manifest_sync_failure_is_reported() -> None:
    class FailingApprovalStore:
        def mark_consumed(
            self,
            task_id: str,
            approval_id: str,
            *,
            execution_checkpoint_id: str | None,
        ) -> None:
            raise RuntimeError("approval manifest unavailable")

    loop, *_ = _build_loop([])
    loop._approval_store = FailingApprovalStore()

    with pytest.raises(HanCodeError) as error:
        loop._consume_and_clear(
            "task-001",
            _task_state(),
            "apr-000001",
            None,
        )

    assert error.value.structured_error.error_code == "approval_state_sync_failed"
