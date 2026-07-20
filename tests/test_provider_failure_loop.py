"""Stage 2: AgentLoop ProviderError semantics tests."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Iterator, Mapping, cast

from hancode.core.errors import StructuredError
from hancode.core.models import Phase, TaskStatus
from hancode.providers.errors import ProviderError
from hancode.runtime.agent_loop import AgentLoop, CheckpointManager, Policy
from hancode.core.state import TaskState
from hancode.storage.checkpoints import CheckpointManifest, RollbackResult
from hancode.storage.trace import TraceEvent
from hancode.tooling.registry import ToolResult
from hancode.policy.path_policy import PathZone


class _ProviderErrorLLM:
    """Provider that always raises ProviderError."""

    def __init__(self, error: ProviderError) -> None:
        self._error = error

    def next_action(self, context: dict[str, object]) -> dict[str, object]:
        raise self._error


class _SuccessLLM:
    """Provider that returns a finish_phase action on first call."""

    def __init__(self) -> None:
        self.called = False

    def next_action(self, context: dict[str, object]) -> dict[str, object]:
        if self.called:
            raise ProviderError(
                StructuredError(
                    error_code="provider_invalid_response",
                    message="Exhausted.",
                    phase="spec",
                    denied_rule="provider_response_valid",
                    suggested_fix="Check provider.",
                ),
                retryable=False,
            )
        self.called = True
        return {
            "type": "finish_phase",
            "phase": context.get("phase", "spec"),
            "tool_name": None,
            "args": {},
            "reason": "Phase complete.",
        }


class _ContextBuilder:
    def build(self, *, task_id: str, phase: Phase, state: TaskState) -> dict[str, object]:
        return {"task_id": task_id, "phase": phase.value, "goal": state.goal or ""}


@dataclass(frozen=True)
class _AllowedDecision:
    allowed: bool = True
    reason: str = "Allowed."
    requires_checkpoint: bool = False
    denied_rule: str | None = None
    suggested_fix: str = "Continue."
    target_zone: PathZone | None = None


class _AllowedPolicy:
    def evaluate(self, *, action: object, phase: Phase, state: TaskState) -> _AllowedDecision:
        return _AllowedDecision()


class _NoopTools:
    def dispatch(self, action: object) -> ToolResult:
        return ToolResult(success=True, action_name="noop")


class _RecordingFeedback:
    def from_parse_error(self, error: object) -> object:
        return {"kind": "parse"}

    def from_policy_denial(self, decision: object) -> object:
        return {"kind": "policy"}

    def from_tool_result(self, result: ToolResult, *, phase: Phase) -> object:
        return {"kind": "tool"}

    def from_checkpoint_manifest(self, manifest: CheckpointManifest) -> object:
        return {"kind": "checkpoint"}

    def from_rollback_result(self, result: RollbackResult, *, phase: Phase) -> object:
        return {"kind": "rollback"}


class _MemoryStateStore:
    def __init__(self, state: TaskState) -> None:
        self.state = state
        self.saves: list[TaskState] = []

    def load(self, task_id: str) -> TaskState:
        return self.state

    def save(self, task_id: str, state: TaskState) -> None:
        self.state = state
        self.saves.append(state)


class _RecordingTraceAppender:
    def __init__(self) -> None:
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


class _NoopCheckpointManager:
    def create(self, task_id: str, files: list[object], reason: str) -> CheckpointManifest:
        raise AssertionError("Should not create checkpoints.")

    def commit(self, task_id: str, checkpoint_id: str) -> CheckpointManifest:
        raise AssertionError("Should not commit checkpoints.")


class _NoopRollbackManager:
    def rollback(self, task_id: str, checkpoint_id: str | None) -> RollbackResult:
        raise AssertionError("Should not rollback.")


class _AllowMutationGuard:
    @contextmanager
    def acquire(self, task_id: str, phase: Phase) -> Iterator[None]:
        yield


def _state() -> TaskState:
    return TaskState(
        schema_version=1,
        task_id="task-001",
        goal="Test goal.",
        status=TaskStatus.CREATED,
        current_phase=Phase.SPEC,
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
            Phase.SPEC.value: False,
            Phase.PLAN.value: False,
            Phase.CODE.value: False,
            Phase.TEST.value: False,
            Phase.REVIEW.value: False,
            Phase.DELIVER.value: False,
        },
        artifacts={
            "SPEC.md": False,
            "PLAN.md": False,
            "TEST_REPORT.md": False,
            "REVIEW.md": False,
            "KNOWLEDGE.md": False,
            "DELIVERABLES.md": False,
        },
    )


def _make_loop(
    llm: object,
    state: TaskState | None = None,
    trace: _RecordingTraceAppender | None = None,
) -> AgentLoop:
    state_store = _MemoryStateStore(state or _state())
    return AgentLoop(
        llm=llm,  # type: ignore[arg-type]
        context_builder=_ContextBuilder(),
        policy=cast(Policy, _AllowedPolicy()),
        tool_registry=_NoopTools(),  # type: ignore[arg-type]
        feedback_builder=_RecordingFeedback(),  # type: ignore[arg-type]
        state_store=state_store,  # type: ignore[arg-type]
        trace_appender=trace or _RecordingTraceAppender(),  # type: ignore[arg-type]
        checkpoint_manager=cast(CheckpointManager, _NoopCheckpointManager()),
        rollback_manager=_NoopRollbackManager(),  # type: ignore[arg-type]
        max_steps=5,
        mutation_guard=_AllowMutationGuard(),  # type: ignore[arg-type]
    )


def _network_error() -> ProviderError:
    return ProviderError(
        StructuredError(
            error_code="provider_network_error",
            message="A network error occurred.",
            phase="spec",
            denied_rule="provider_available",
            suggested_fix="Check provider configuration and retry.",
        ),
        retryable=True,
    )


def test_provider_error_blocks_task() -> None:
    loop = _make_loop(_ProviderErrorLLM(_network_error()))
    result = loop.run("task-001")
    assert result.status is TaskStatus.BLOCKED


def test_provider_error_does_not_mark_inconsistent() -> None:
    loop = _make_loop(_ProviderErrorLLM(_network_error()))
    result = loop.run("task-001")
    assert result.status is not TaskStatus.INCONSISTENT
    assert result.final_state.inconsistent is False


def test_provider_error_does_not_consume_retry_budget() -> None:
    loop = _make_loop(_ProviderErrorLLM(_network_error()))
    result = loop.run("task-001")
    assert result.retry_budget_remaining == 2


def test_provider_error_does_not_trigger_rollback() -> None:
    loop = _make_loop(_ProviderErrorLLM(_network_error()))
    result = loop.run("task-001")
    assert result.final_state.rollback_required is False


def test_provider_error_keeps_phase() -> None:
    loop = _make_loop(_ProviderErrorLLM(_network_error()))
    result = loop.run("task-001")
    assert result.final_state.current_phase is Phase.SPEC


def test_provider_error_appends_trace() -> None:
    trace = _RecordingTraceAppender()
    loop = _make_loop(_ProviderErrorLLM(_network_error()), trace=trace)
    loop.run("task-001")
    provider_events = [e for e in trace.events if e.event_type == "provider_call_failed"]
    assert len(provider_events) == 1
    assert provider_events[0].observation is not None
    assert provider_events[0].observation.get("error_code") == "provider_network_error"


def test_provider_error_trace_does_not_leak_secret() -> None:
    error = ProviderError(
        StructuredError(
            error_code="provider_auth_failed",
            message="Auth failed with key sk-secret-value-12345.",
            phase="spec",
            denied_rule="provider_available",
            suggested_fix="Check credential.",
        ),
        retryable=False,
    )
    trace = _RecordingTraceAppender()
    loop = _make_loop(_ProviderErrorLLM(error), trace=trace)
    loop.run("task-001")
    for event in trace.events:
        event_str = str(event)
        assert "sk-secret-value-12345" not in event_str


def test_provider_error_is_resumable() -> None:
    state_store = _MemoryStateStore(_state())
    loop = _make_loop(_ProviderErrorLLM(_network_error()))
    first_result = loop.run("task-001")
    assert first_result.status is TaskStatus.BLOCKED

    resume_state = replace(first_result.final_state, status=TaskStatus.BLOCKED)
    state_store.state = resume_state
    second_loop = _make_loop(_SuccessLLM())
    second_loop._state_store = state_store  # type: ignore[attr-defined]
    second_result = second_loop.run("task-001", resume=True)
    assert second_result.status is not TaskStatus.INCONSISTENT


def test_valid_provider_action_reaches_parse_action() -> None:
    loop = _make_loop(_SuccessLLM())
    result = loop.run("task-001")
    assert result.status is not TaskStatus.INCONSISTENT
