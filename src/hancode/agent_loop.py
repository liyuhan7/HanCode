from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Mapping, Protocol

from hancode.actions import Action, ActionType, ParseError, parse_action
from hancode.checkpoints import CheckpointManifest, RollbackResult
from hancode.errors import HanCodeError, StructuredError
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
        observation: object | None = None
        tool_calls: list[str] = []
        last_recoverable_error: StructuredError | None = None
        for step in range(1, self._max_steps + 1):
            routing = select_next_phase(state)
            if routing.completed:
                state = self._save_if_changed(
                    task_id,
                    state,
                    replace(
                        state,
                        status=TaskStatus.COMPLETED,
                        current_phase=routing.phase,
                    ),
                )
                return _result(
                    TaskStatus.COMPLETED, step - 1, tuple(tool_calls), observation, None, state
                )
            if routing.blocked:
                status = (
                    state.status
                    if state.status
                    in {TaskStatus.BLOCKED, TaskStatus.FAILED, TaskStatus.INCONSISTENT}
                    else TaskStatus.BLOCKED
                )
                state = self._save_if_changed(
                    task_id, state, replace(state, status=status, current_phase=routing.phase)
                )
                return _result(
                    status,
                    step - 1,
                    tuple(tool_calls),
                    observation,
                    StructuredError(
                        error_code=routing.reason,
                        message="Agent loop cannot continue from the current routing decision.",
                        phase=routing.phase.value,
                        denied_rule=routing.reason,
                        suggested_fix="Resolve the task state before running the agent loop again.",
                    ),
                    state,
                )

            state = self._enter_phase(task_id, state, routing.phase)
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
                state = self._block(task_id, state)
                error = last_recoverable_error or StructuredError(
                    error_code=exc.error_code,
                    message=str(exc),
                    phase=routing.phase.value,
                    denied_rule=None,
                    suggested_fix=exc.suggested_fix,
                )
                return _result(
                    TaskStatus.BLOCKED,
                    step,
                    tuple(tool_calls),
                    observation,
                    error,
                    state,
                )

            action = parse_action(raw_action, routing.phase)
            if isinstance(action, ParseError):
                last_recoverable_error = _structured_parse_error(action)
                observation, feedback_error = self._build_feedback(
                    lambda: self._feedback_builder.from_parse_error(action), routing.phase
                )
                if feedback_error is not None:
                    state = self._block(task_id, state)
                    return _result(
                        TaskStatus.BLOCKED,
                        step,
                        tuple(tool_calls),
                        observation,
                        feedback_error,
                        state,
                    )
                continue

            decision = self._policy.evaluate(
                action=action,
                phase=routing.phase,
                state=state,
            )
            if not decision.allowed:
                last_recoverable_error = StructuredError(
                    error_code="policy_denied",
                    message=decision.reason,
                    phase=routing.phase.value,
                    denied_rule=decision.denied_rule,
                    suggested_fix=decision.suggested_fix,
                )
                observation, feedback_error = self._build_feedback(
                    lambda: self._feedback_builder.from_policy_denial(decision),
                    routing.phase,
                )
                if feedback_error is not None:
                    state = self._block(task_id, state)
                    return _result(
                        TaskStatus.BLOCKED,
                        step,
                        tuple(tool_calls),
                        observation,
                        feedback_error,
                        state,
                    )
                continue

            if action.type is ActionType.TOOL_CALL:
                assert action.tool_name is not None
                if action.tool_name == "rollback_last_checkpoint":
                    state = self._block(task_id, state)
                    return _result(
                        TaskStatus.BLOCKED,
                        step,
                        tuple(tool_calls),
                        observation,
                        StructuredError(
                            error_code="rollback_deferred_to_task_4",
                            message="Rollback execution is not available in this task slice.",
                            phase=routing.phase.value,
                            denied_rule="rollback_task_4_required",
                            suggested_fix="Complete Task 4 before requesting rollback execution.",
                        ),
                        state,
                    )
                tool_result = self._tool_registry.dispatch(action)
                tool_calls.append(action.tool_name)
                state = self._save_if_changed(
                    task_id,
                    state,
                    _state_after_tool(state, action, tool_result, decision),
                )
                observation, feedback_error = self._build_feedback(
                    lambda: self._feedback_builder.from_tool_result(
                        tool_result, phase=routing.phase
                    ),
                    routing.phase,
                )
                if feedback_error is not None:
                    state = self._block(task_id, state)
                    return _result(
                        TaskStatus.BLOCKED,
                        step,
                        tuple(tool_calls),
                        observation,
                        feedback_error,
                        state,
                    )
                continue

            if action.type is ActionType.FINISH_PHASE:
                state = self._save_if_changed(
                    task_id, state, _state_after_phase_finish(state, routing.phase)
                )
                continue

            if action.type is ActionType.FINAL:
                state = self._block(task_id, state)
                return _result(
                    TaskStatus.BLOCKED,
                    step,
                    tuple(tool_calls),
                    observation,
                    StructuredError(
                        error_code="final_requires_router_completion",
                        message="Final actions cannot bypass router-controlled completion.",
                        phase=routing.phase.value,
                        denied_rule="router_completion_required",
                        suggested_fix="Finish the current phase and let the router determine completion.",
                    ),
                    state,
                )

            state = self._block(task_id, state)
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

        state = self._block(task_id, state)
        return _result(
            TaskStatus.BLOCKED,
            self._max_steps,
            tuple(tool_calls),
            observation,
            last_recoverable_error
            or StructuredError(
                error_code="max_steps_exceeded",
                message="Agent loop reached the configured maximum number of steps.",
                phase=routing.phase.value,
                denied_rule="max_steps_limit",
                suggested_fix="Increase max_steps or make the action sequence terminate earlier.",
            ),
            state,
        )

    def _enter_phase(self, task_id: str, state: TaskState, phase: Phase) -> TaskState:
        source_edits = (
            0
            if phase is Phase.CODE and state.current_phase is not Phase.CODE
            else state.source_edits_this_phase
        )
        return self._save_if_changed(
            task_id,
            state,
            replace(
                state,
                status=TaskStatus.RUNNING,
                current_phase=phase,
                source_edits_this_phase=source_edits,
            ),
        )

    def _block(self, task_id: str, state: TaskState) -> TaskState:
        return self._save_if_changed(task_id, state, replace(state, status=TaskStatus.BLOCKED))

    def _save_if_changed(
        self, task_id: str, previous: TaskState, updated: TaskState
    ) -> TaskState:
        if updated != previous:
            self._state_store.save(task_id, updated)
        return updated

    @staticmethod
    def _build_feedback(
        factory: Callable[[], object], phase: Phase
    ) -> tuple[object | None, StructuredError | None]:
        try:
            return factory(), None
        except HanCodeError as exc:
            return None, exc.structured_error
        except Exception:
            return (
                None,
                StructuredError(
                    error_code="feedback_construction_failed",
                    message="Feedback could not be constructed from the current loop event.",
                    phase=phase.value,
                    denied_rule="feedback_construction",
                    suggested_fix="Repair the feedback builder input or implementation.",
                ),
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


def _state_after_tool(
    state: TaskState,
    action: Action,
    result: ToolResult,
    decision: PolicyDecisionLike,
) -> TaskState:
    phase_completed = dict(state.phase_completed)
    if action.tool_name == "run_tests":
        phase_completed[Phase.TEST.value] = False
        return replace(
            state,
            latest_test_status="passed" if result.success else "failed",
            test_status_consumed=False,
            phase_completed=phase_completed,
        )

    if action.tool_name not in {"write_file", "edit_file"} or not result.success:
        return state
    source_edits = state.source_edits_this_phase + 1
    if (
        state.current_phase is Phase.CODE
        and state.latest_test_status == "failed"
        and state.test_status_consumed
        and state.source_edits_this_phase == 0
        and state.retry_budget_remaining > 0
        and decision.requires_checkpoint
    ):
        phase_completed[Phase.TEST.value] = False
        return replace(
            state,
            latest_test_status="none",
            test_status_consumed=False,
            retry_budget_remaining=state.retry_budget_remaining - 1,
            source_edits_this_phase=source_edits,
            phase_completed=phase_completed,
        )
    return replace(state, source_edits_this_phase=source_edits)


def _state_after_phase_finish(state: TaskState, phase: Phase) -> TaskState:
    phase_completed = dict(state.phase_completed)
    phase_completed[phase.value] = True
    if (
        phase is Phase.REVIEW
        and state.latest_test_status == "failed"
        and not state.test_status_consumed
        and state.retry_budget_remaining > 0
    ):
        phase_completed[Phase.CODE.value] = False
        return replace(
            state,
            phase_completed=phase_completed,
            test_status_consumed=True,
        )
    return replace(state, phase_completed=phase_completed)
