from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Mapping

import pytest

from hancode.core.actions import Action
from hancode.runtime.agent_loop import AgentLoop, InMemoryMutationGuard
from hancode.storage.checkpoints import CheckpointManifest, RollbackResult
from hancode.core.config import HanCodeConfig
from hancode.core.errors import HanCodeError, StructuredError
from hancode.core.interactions import InteractionRecord, InteractionStatus
from hancode.runtime.feedback import FeedbackBuilder
from hancode.providers.mock import MockLLM
from hancode.core.models import Phase, TaskStatus
from hancode.policy.path_policy import PathZone
from hancode.core.state import TaskState
from hancode.policy.tool_policy import PolicyDecision, ToolPolicy
from hancode.tooling.registry import ToolResult
from hancode.storage.trace import TraceEvent


@dataclass(frozen=True)
class StubPolicyDecision:
    allowed: bool
    reason: str = "Action is allowed."
    requires_checkpoint: bool = False
    denied_rule: str | None = None
    suggested_fix: str = "Use an allowed action."
    target_zone: PathZone | None = None


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


class SpyContextBuilder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Phase, TaskState]] = []

    def build(self, *, task_id: str, phase: Phase, state: TaskState) -> dict[str, object]:
        self.calls.append((task_id, phase, state))
        return {"task_id": task_id, "phase": phase.value}


class FailingContextBuilder:
    def __init__(self, error: HanCodeError) -> None:
        self.error = error

    def build(self, *, task_id: str, phase: Phase, state: TaskState) -> dict[str, object]:
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


def test_max_steps_prevents_infinite_loop() -> None:
    loop, llm, _, _, tools, _ = _build_loop(
        [_read_file_action(), _read_file_action(), _read_file_action()], max_steps=2
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.BLOCKED
    assert result.steps == 2
    assert result.error is not None
    assert result.error.error_code == "max_steps_exceeded"
    assert len(llm.contexts) == 2
    assert [action.tool_name for action in tools.actions] == ["read_file", "read_file"]


def test_trace_sequence_gap_is_rejected_at_agent_loop_boundary() -> None:
    loop, _, _, _, _, _ = _build_loop(
        [_read_file_action()],
        trace_appender=GappedTraceAppender(),
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.INCONSISTENT
    assert result.error is not None
    assert result.error.error_code == "trace_event_invalid"


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


def test_final_action_requires_router_controlled_completion() -> None:
    loop, _, _, _, tools, _ = _build_loop([_final_action(), _read_file_action()])

    result = loop.run("task-001")

    assert result.status is TaskStatus.BLOCKED
    assert result.steps == 1
    assert result.tool_calls == ()
    assert not tools.actions
    assert result.error is not None
    assert result.error.error_code == "final_requires_router_completion"


def test_tool_observation_is_fed_into_next_context() -> None:
    loop, llm, _, _, _, feedback = _build_loop([_read_file_action(), _finish_action()])

    loop.run("task-001")

    assert llm.contexts[1] == {
        "task_id": "task-001",
        "phase": "code",
        "observation": {
            "kind": "tool_result",
            "result": ToolResult(success=True, action_name="read_file"),
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
    loop, llm, _, _, _, _ = _build_loop(
        [
            {
                "type": "tool_call",
                "phase": "code",
                "tool_name": "run_tests",
                "args": {},
                "reason": None,
            },
            _finish_action(),
        ],
        max_steps=2,
    )
    loop._feedback_builder = FeedbackBuilder()  # type: ignore[attr-defined]

    result = loop.run("task-001")

    assert result.status is TaskStatus.BLOCKED
    assert result.error is not None
    assert result.error.error_code == "max_steps_exceeded"
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


def test_agent_loop_rejects_non_positive_max_steps() -> None:
    with pytest.raises(ValueError, match="max_steps must be positive"):
        _build_loop([_finish_action()], max_steps=0)


def _build_loop(
    actions: list[dict[str, object]],
    *,
    max_steps: int = 3,
    state: TaskState | None = None,
    decision: StubPolicyDecision | None = None,
    events: list[str] | None = None,
    trace_appender: SpyTraceAppender | None = None,
    checkpoint_manager: StubCheckpointManager | None = None,
    rollback_manager: StubRollbackManager | None = None,
    state_store: StubStateStore | None = None,
) -> tuple[
    AgentLoop,
    MockLLM,
    SpyContextBuilder,
    SpyPolicy,
    SpyToolRegistry,
    SpyFeedbackBuilder,
]:
    recorded_events = events if events is not None else []
    llm = MockLLM(actions)
    context_builder = SpyContextBuilder()
    policy = SpyPolicy(decision or StubPolicyDecision(allowed=True), recorded_events)
    tools = SpyToolRegistry(recorded_events)
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
        max_steps=max_steps,
        mutation_guard=InMemoryMutationGuard(),
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
        max_trace_events=40,
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


def _finish_action() -> dict[str, object]:
    return {
        "type": "finish_phase",
        "phase": "code",
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
