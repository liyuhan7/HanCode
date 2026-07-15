from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol

from hancode.actions import Action, ActionType, ParseError, parse_action
from hancode.checkpoints import CheckpointManifest, RollbackResult
from hancode.errors import StructuredError
from hancode.llm import LLMClient, MockLLMExhausted
from hancode.models import Phase, Risk, TaskStatus
from hancode.router import select_next_phase
from hancode.state import TaskState
from hancode.tools import ToolResult
from hancode.trace import TraceEvent


class StateStore(Protocol):
    def load(self, task_id: str) -> TaskState: ...

    def save(self, task_id: str, state: TaskState) -> None: ...


class TraceAppender(Protocol):
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
    ) -> TraceEvent: ...


class CheckpointManager(Protocol):
    def create(self, task_id: str, files: list[Path], reason: str) -> CheckpointManifest: ...

    def commit(self, task_id: str, checkpoint_id: str) -> CheckpointManifest: ...


class RollbackManager(Protocol):
    def rollback_last(self, task_id: str) -> RollbackResult: ...


class ContextBuilder(Protocol):
    def build(
        self, *, task_id: str, phase: Phase, state: TaskState
    ) -> dict[str, object]: ...


class PolicyDecisionLike(Protocol):
    allowed: bool
    reason: str
    requires_checkpoint: bool
    denied_rule: str | None
    suggested_fix: str


class Policy(Protocol):
    def evaluate(
        self, *, action: Action, phase: Phase, state: TaskState
    ) -> PolicyDecisionLike: ...


class ToolRegistry(Protocol):
    def dispatch(self, action: Action) -> ToolResult: ...


class FeedbackBuilder(Protocol):
    def from_parse_error(self, error: ParseError) -> object: ...

    def from_policy_denial(self, decision: PolicyDecisionLike) -> object: ...

    def from_tool_result(self, result: ToolResult, *, phase: Phase) -> object: ...

    def from_checkpoint_manifest(self, manifest: CheckpointManifest) -> object: ...

    def from_rollback_result(self, result: RollbackResult, *, phase: Phase) -> object: ...


@dataclass(frozen=True, slots=True)
class AgentRunResult:
    status: TaskStatus
    steps: int
    tool_calls: tuple[str, ...]
    risks: tuple[Risk, ...]
    final_observation: object | None
    error: StructuredError | None
    final_state: TaskState
    retry_budget_remaining: int
    trace_events: tuple[TraceEvent, ...]


class AgentLoop:
    def __init__(
        self,
        *,
        llm: LLMClient,
        context_builder: ContextBuilder,
        policy: Policy,
        tool_registry: ToolRegistry,
        feedback_builder: FeedbackBuilder,
        state_store: StateStore,
        trace_appender: TraceAppender,
        checkpoint_manager: CheckpointManager,
        rollback_manager: RollbackManager,
        max_steps: int,
    ) -> None:
        if not isinstance(max_steps, int) or isinstance(max_steps, bool) or max_steps <= 0:
            raise ValueError("max_steps must be positive")
        self._llm = llm
        self._context_builder = context_builder
        self._policy = policy
        self._tool_registry = tool_registry
        self._feedback_builder = feedback_builder
        self._state_store = state_store
        self._trace_appender = trace_appender
        self._checkpoint_manager = checkpoint_manager
        self._rollback_manager = rollback_manager
        self._max_steps = max_steps

    def run(self, task_id: str) -> AgentRunResult:
        state = self._state_store.load(task_id)
        routing = select_next_phase(state)
        if routing.completed:
            return _result(TaskStatus.COMPLETED, 0, (), None, None, state)
        if routing.blocked:
            status = (
                state.status
                if state.status in {TaskStatus.BLOCKED, TaskStatus.FAILED, TaskStatus.INCONSISTENT}
                else TaskStatus.BLOCKED
            )
            return _result(
                status,
                0,
                (),
                None,
                StructuredError(
                    error_code=routing.reason,
                    message="Agent loop cannot continue from the current routing decision.",
                    phase=routing.phase.value,
                    denied_rule=routing.reason,
                    suggested_fix="Resolve the task state before running the agent loop again.",
                ),
                state,
            )

        observation: object | None = None
        tool_calls: list[str] = []
        for step in range(1, self._max_steps + 1):
            context = dict(
                self._context_builder.build(
                    task_id=task_id,
                    phase=routing.phase,
                    state=state,
                )
            )
            if observation is not None:
                context["observation"] = observation

            try:
                raw_action = self._llm.next_action(context)
            except MockLLMExhausted as exc:
                return _result(
                    TaskStatus.BLOCKED,
                    step,
                    tuple(tool_calls),
                    observation,
                    StructuredError(
                        error_code=exc.error_code,
                        message=str(exc),
                        phase=routing.phase.value,
                        denied_rule=None,
                        suggested_fix=exc.suggested_fix,
                    ),
                    state,
                )

            action = parse_action(raw_action, routing.phase)
            if isinstance(action, ParseError):
                observation = self._feedback_builder.from_parse_error(action)
                return _result(
                    TaskStatus.BLOCKED,
                    step,
                    tuple(tool_calls),
                    observation,
                    _structured_parse_error(action),
                    state,
                )

            decision = self._policy.evaluate(
                action=action,
                phase=routing.phase,
                state=state,
            )
            if not decision.allowed:
                observation = self._feedback_builder.from_policy_denial(decision)
                return _result(
                    TaskStatus.BLOCKED,
                    step,
                    tuple(tool_calls),
                    observation,
                    StructuredError(
                        error_code="policy_denied",
                        message=decision.reason,
                        phase=routing.phase.value,
                        denied_rule=decision.denied_rule,
                        suggested_fix=decision.suggested_fix,
                    ),
                    state,
                )

            if action.type is ActionType.TOOL_CALL:
                assert action.tool_name is not None
                tool_result = self._tool_registry.dispatch(action)
                tool_calls.append(action.tool_name)
                observation = self._feedback_builder.from_tool_result(
                    tool_result, phase=routing.phase
                )
                continue

            if action.type in {ActionType.FINISH_PHASE, ActionType.FINAL}:
                return _result(
                    TaskStatus.RUNNING, step, tuple(tool_calls), observation, None, state
                )

            return _result(
                TaskStatus.BLOCKED,
                step,
                tuple(tool_calls),
                observation,
                StructuredError(
                    error_code="unsupported_control_action",
                    message="This control action is not supported by the minimal agent loop.",
                    phase=routing.phase.value,
                    denied_rule=None,
                    suggested_fix="Use a tool call or finish the current phase.",
                ),
                state,
            )

        return _result(
            TaskStatus.BLOCKED,
            self._max_steps,
            tuple(tool_calls),
            observation,
            StructuredError(
                error_code="max_steps_exceeded",
                message="Agent loop reached the configured maximum number of steps.",
                phase=routing.phase.value,
                denied_rule="max_steps_limit",
                suggested_fix="Increase max_steps or make the action sequence terminate earlier.",
            ),
            state,
        )


def _result(
    status: TaskStatus,
    steps: int,
    tool_calls: tuple[str, ...],
    observation: object | None,
    error: StructuredError | None,
    final_state: TaskState,
) -> AgentRunResult:
    return AgentRunResult(
        status=status,
        steps=steps,
        tool_calls=tool_calls,
        risks=(),
        final_observation=observation,
        error=error,
        final_state=final_state,
        retry_budget_remaining=final_state.retry_budget_remaining,
        trace_events=(),
    )


def _structured_parse_error(error: ParseError) -> StructuredError:
    return StructuredError(
        error_code=error.error_code,
        message=error.message,
        phase=error.phase,
        denied_rule=error.denied_rule,
        suggested_fix=error.suggested_fix,
    )
