from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import pytest

from hancode.actions import Action
from hancode.agent_loop import AgentLoop
from hancode.checkpoints import CheckpointManifest, RollbackResult
from hancode.config import HanCodeConfig
from hancode.llm import MockLLM
from hancode.models import Phase, TaskStatus
from hancode.state import TaskState
from hancode.tool_policy import PolicyDecision, ToolPolicy
from hancode.tools import ToolResult
from hancode.trace import TraceEvent


@dataclass(frozen=True)
class StubPolicyDecision:
    allowed: bool
    reason: str = "Action is allowed."
    requires_checkpoint: bool = False
    denied_rule: str | None = None
    suggested_fix: str = "Use an allowed action."


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


class SpyTraceAppender:
    def __init__(self) -> None:
        self.calls: list[str] = []

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
        raise AssertionError("T21 Task 1 must not append trace events.")


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


class SpyPolicy:
    def __init__(self, decision: StubPolicyDecision, events: list[str]) -> None:
        self.decision = decision
        self.events = events
        self.actions: list[Action] = []

    def evaluate(
        self, *, action: Action, phase: Phase, state: TaskState
    ) -> StubPolicyDecision:
        assert phase is Phase.CODE
        assert state.current_phase is Phase.CODE
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


def test_agent_loop_calls_llm_with_context() -> None:
    loop, llm, context_builder, _, _, _ = _build_loop([_finish_action()])

    result = loop.run("task-001")

    assert result.status is TaskStatus.RUNNING
    assert context_builder.calls[0][0:2] == ("task-001", Phase.CODE)
    assert llm.contexts == ({"task_id": "task-001", "phase": "code"},)


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


def test_finish_action_stops_loop() -> None:
    loop, _, _, _, tools, _ = _build_loop([_finish_action(), _read_file_action()])

    result = loop.run("task-001")

    assert result.status is TaskStatus.RUNNING
    assert result.steps == 1
    assert result.tool_calls == ()
    assert not tools.actions


def test_agent_loop_result_mirrors_loaded_state_without_new_port_side_effects() -> None:
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

    assert result.final_state is state
    assert result.retry_budget_remaining == state.retry_budget_remaining
    assert result.trace_events == ()
    assert trace_appender.calls == []
    assert checkpoint_manager.calls == []
    assert rollback_manager.calls == []


def test_final_action_stops_loop() -> None:
    loop, _, _, _, tools, _ = _build_loop([_final_action(), _read_file_action()])

    result = loop.run("task-001")

    assert result.status is TaskStatus.RUNNING
    assert result.steps == 1
    assert result.tool_calls == ()
    assert not tools.actions


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


def test_ask_user_blocks_without_tool() -> None:
    loop, _, _, _, tools, _ = _build_loop([_ask_user_action()])

    result = loop.run("task-001")

    assert result.status is TaskStatus.BLOCKED
    assert result.error is not None
    assert result.error.error_code == "unsupported_control_action"
    assert not tools.actions


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
        state_store=StubStateStore(state or _task_state()),
        trace_appender=trace_appender or SpyTraceAppender(),
        checkpoint_manager=checkpoint_manager or StubCheckpointManager(),
        rollback_manager=rollback_manager or StubRollbackManager(),
        max_steps=max_steps,
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
