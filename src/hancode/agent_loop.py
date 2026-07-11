from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from hancode.actions import Action, ActionType, ParseError, parse_action
from hancode.errors import StructuredError
from hancode.llm import LLMClient, MockLLMExhausted
from hancode.models import Phase, Risk, TaskStatus
from hancode.router import select_next_phase
from hancode.state import TaskState


class StateStore(Protocol):
    def load(self, task_id: str) -> TaskState: ...


class ContextBuilder(Protocol):
    def build(
        self, *, task_id: str, phase: Phase, state: TaskState
    ) -> dict[str, object]: ...


class PolicyDecisionLike(Protocol):
    allowed: bool
    reason: str
    denied_rule: str | None
    suggested_fix: str


class Policy(Protocol):
    def evaluate(
        self, *, action: Action, phase: Phase, state: TaskState
    ) -> PolicyDecisionLike: ...


class ToolRegistry(Protocol):
    def dispatch(self, action: Action) -> object: ...


class FeedbackBuilder(Protocol):
    def from_parse_error(self, error: ParseError) -> object: ...

    def from_policy_denial(self, decision: PolicyDecisionLike) -> object: ...

    def from_tool_result(self, result: object) -> object: ...


@dataclass(frozen=True, slots=True)
class AgentRunResult:
    status: TaskStatus
    steps: int
    tool_calls: tuple[str, ...]
    risks: tuple[Risk, ...]
    final_observation: object | None
    error: StructuredError | None


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
        self._max_steps = max_steps

    def run(self, task_id: str) -> AgentRunResult:
        state = self._state_store.load(task_id)
        routing = select_next_phase(state)
        if routing.completed:
            return _result(TaskStatus.COMPLETED, 0, (), None, None)
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
                )

            if action.type is ActionType.TOOL_CALL:
                assert action.tool_name is not None
                tool_result = self._tool_registry.dispatch(action)
                tool_calls.append(action.tool_name)
                observation = self._feedback_builder.from_tool_result(tool_result)
                continue

            if action.type in {ActionType.FINISH_PHASE, ActionType.FINAL}:
                return _result(TaskStatus.RUNNING, step, tuple(tool_calls), observation, None)

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
        )


def _result(
    status: TaskStatus,
    steps: int,
    tool_calls: tuple[str, ...],
    observation: object | None,
    error: StructuredError | None,
) -> AgentRunResult:
    return AgentRunResult(
        status=status,
        steps=steps,
        tool_calls=tool_calls,
        risks=(),
        final_observation=observation,
        error=error,
    )


def _structured_parse_error(error: ParseError) -> StructuredError:
    return StructuredError(
        error_code=error.error_code,
        message=error.message,
        phase=error.phase,
        denied_rule=error.denied_rule,
        suggested_fix=error.suggested_fix,
    )
