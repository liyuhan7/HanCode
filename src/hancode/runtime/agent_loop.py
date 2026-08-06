from __future__ import annotations

from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, replace
from datetime import datetime
import inspect
import json
from pathlib import Path
import re
from typing import Callable, Iterator, Mapping, Protocol
from uuid import uuid4

import hashlib
from hancode.core.actions import Action, ActionType, ParseError, parse_action
from hancode.core.approvals import (
    ApprovalRecord,
    ApprovalStatus,
    compute_action_digest,
)
from hancode.storage.checkpoints import (
    CheckpointFile,
    CheckpointManifest,
    RollbackResult,
    abort_pending_checkpoint,
    commit_checkpoint,
    create_checkpoint,
    reconcile_pending_checkpoint,
    rollback_last_checkpoint,
)
from hancode.core.errors import HanCodeError, StructuredError
from hancode.core.failures import RecoveryMode
from hancode.tooling.file_tools import redact_text
from hancode.providers.base import LLMClient
from hancode.providers.errors import ProviderError
from hancode.providers.mock import MockLLMExhausted
from hancode.runtime.pause import PauseToken
from hancode.core.interactions import InteractionRecord, InteractionStatus
from hancode.core.interventions import (
    ActionCommitStatus,
    DeliveryStatus,
    InterventionRecord,
    SteeringSnapshot,
)
from hancode.core.memory import MemoryRecord
from hancode.core.models import OperationStatus, Phase, Risk, TaskStatus
from hancode.policy.path_policy import PathZone, normalize_project_relative_path
from hancode.core.phases import build_phase_gate
from hancode.core.router import select_next_phase
from hancode.core.state import TaskState, load_state, reconcile_state, save_state
from hancode.runtime.feedback import Observation, FeedbackReport, classify_test_output
from hancode.tooling.registry import ToolResult
from hancode.storage.trace import TraceEvent, append_trace
from hancode.storage.task_lock import FilesystemTaskMutationGuard
from hancode.storage.workspace import task_path
from hancode.storage.memory import FilesystemMemoryStore
from hancode.core.test_remediation import RemediationKind
from hancode.runtime.test_remediation import build_test_failure_record
from hancode.runtime.recovery import RecoveryCoordinator
from hancode.storage.test_remediations import TestRemediationStore
from hancode.storage.test_strategies import TestStrategyStore


class StateStore(Protocol):
    def load(self, task_id: str) -> TaskState: ...

    def save(self, task_id: str, state: TaskState) -> None: ...


class MemoryStore(Protocol):
    def ensure_capacity(self, task_id: str, *, reserved_bytes: int) -> None: ...

    def record_tool_result(
        self,
        task_id: str,
        *,
        phase: Phase,
        action: Action,
        result: ToolResult,
        observation: object,
        state: TaskState,
    ) -> MemoryRecord: ...

    def record_rollback(
        self,
        task_id: str,
        *,
        phase: Phase,
        result: RollbackResult,
        observation: object,
        state: TaskState,
    ) -> MemoryRecord: ...


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

    def abort(
        self, task_id: str, checkpoint_id: str, *, restore_files: bool
    ) -> CheckpointManifest: ...


class RollbackManager(Protocol):
    def rollback_last(self, task_id: str) -> RollbackResult: ...


class ContextBuilder(Protocol):
    def build(
        self,
        *,
        task_id: str,
        phase: Phase,
        state: TaskState,
        observation: object | None = None,
        user_interventions: tuple[InterventionRecord, ...] = ...,
        intervention_revision: int = ...,
    ) -> dict[str, object]: ...


class InterventionStorePort(Protocol):
    def prepare_context(self, task_id: str, run_id: str) -> SteeringSnapshot: ...

    def mark_delivered(
        self,
        task_id: str,
        run_id: str,
        expected_revision: int,
        sequences: tuple[int, ...],
    ) -> object: ...

    def current_revision(self, task_id: str) -> int: ...

    def mark_consumed(
        self,
        task_id: str,
        run_id: str,
        sequences: tuple[int, ...],
    ) -> object: ...

    def commit_action(
        self,
        task_id: str,
        run_id: str,
        expected_revision: int,
        delivery_sequences: tuple[int, ...],
        action_digest: str,
        commit_key: str,
        acknowledge: bool,
    ) -> object: ...


class PolicyDecisionLike(Protocol):
    allowed: bool
    reason: str
    requires_checkpoint: bool
    target_zone: PathZone | None
    denied_rule: str | None
    suggested_fix: str


class Policy(Protocol):
    def evaluate(
        self, *, action: Action, phase: Phase, state: TaskState
    ) -> PolicyDecisionLike: ...


class ToolRegistry(Protocol):
    def dispatch(self, action: Action) -> ToolResult: ...


class DeliveryPipelinePort(Protocol):
    def record_test(
        self, task_root: Path, report: FeedbackReport, command: str
    ) -> object: ...

    def record_build(self, task_root: Path, task_id: str, status: str) -> None: ...

    def record_diff(
        self,
        task_root: Path,
        task_id: str,
        digest: str | None,
        *,
        drifted: bool = False,
    ) -> None: ...

    def finalize(self, task_root: Path, task_id: str) -> object: ...


class MutationGuard(Protocol):
    def acquire(self, task_id: str, phase: Phase) -> AbstractContextManager[None]: ...


class ApprovalPolicyPort(Protocol):
    def evaluate(
        self,
        *,
        action: Action,
        policy_decision: PolicyDecisionLike,
        state: TaskState,
    ) -> object: ...
    # Returns an object with .required, .category, .reason, .risk_level, .targets


class ApprovalStore(Protocol):
    def create(
        self,
        task_id: str,
        state: TaskState,
        record: ApprovalRecord,
    ) -> tuple[TaskState, ApprovalRecord]: ...

    def load_pending(
        self,
        task_id: str,
        approval_id: str,
    ) -> ApprovalRecord: ...

    def decide(
        self,
        task_id: str,
        approved: bool,
        *,
        approval_id: str,
        reason: str | None = None,
    ) -> object: ...

    def mark_executing(
        self,
        task_id: str,
        approval_id: str,
        *,
        expected_checkpoint_id: str | None,
    ) -> object: ...

    def mark_consumed(
        self,
        task_id: str,
        approval_id: str,
        *,
        execution_checkpoint_id: str | None = None,
    ) -> object: ...

    def mark_expired(
        self, task_id: str, approval_id: str
    ) -> object: ...


class ApprovalRequestBuilderPort(Protocol):
    def build(
        self,
        *,
        project_id: str,
        task_id: str,
        state: TaskState,
        action: Action,
        requirement: object,
        project_root: Path,
        run_id: str | None = None,
        steering_revision_at_request: int | None = None,
    ) -> ApprovalRecord: ...


class FeedbackBuilder(Protocol):
    def from_parse_error(self, error: ParseError) -> object: ...

    def from_policy_denial(self, decision: PolicyDecisionLike) -> object: ...

    def from_tool_result(self, result: ToolResult, *, phase: Phase) -> object: ...

    def from_checkpoint_manifest(self, manifest: CheckpointManifest) -> object: ...

    def from_rollback_result(self, result: RollbackResult, *, phase: Phase) -> object: ...


class _FilesystemTaskAdapter:
    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root.resolve()

    def _task_root(self, task_id: str) -> Path:
        return task_path(self._project_root, task_id)


class FilesystemStateStore(_FilesystemTaskAdapter):
    def load(self, task_id: str) -> TaskState:
        return load_state(self._task_root(task_id))

    def save(self, task_id: str, state: TaskState) -> None:
        save_state(self._task_root(task_id), state)

    def reconcile(self, task_id: str, *, recover_pending: bool = False) -> TaskState:
        root = self._task_root(task_id)
        state = load_state(root)
        state = reconcile_pending_checkpoint(root, state, recover=recover_pending)
        return reconcile_state(root, state)


class FilesystemTraceAppender(_FilesystemTaskAdapter):
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
        return append_trace(
            self._task_root(task_id),
            event_type=event_type,
            task_id=task_id,
            phase=phase,
            status=status,
            action=action,
            observation=observation,
            error_summary=error_summary,
            state_transition=state_transition,
        )


class FilesystemCheckpointManager(_FilesystemTaskAdapter):
    def create(self, task_id: str, files: list[Path], reason: str) -> CheckpointManifest:
        return create_checkpoint(self._task_root(task_id), files, reason)

    def commit(self, task_id: str, checkpoint_id: str) -> CheckpointManifest:
        return commit_checkpoint(self._task_root(task_id), checkpoint_id)

    def abort(
        self, task_id: str, checkpoint_id: str, *, restore_files: bool
    ) -> CheckpointManifest:
        return abort_pending_checkpoint(
            self._task_root(task_id),
            checkpoint_id,
            restore_files=restore_files,
        )


class FilesystemRollbackManager(_FilesystemTaskAdapter):
    def rollback_last(self, task_id: str) -> RollbackResult:
        return rollback_last_checkpoint(self._task_root(task_id), record_trace=False)


class _FailClosedMutationGuard:
    def acquire(self, task_id: str, phase: Phase) -> AbstractContextManager[None]:
        raise HanCodeError(
            StructuredError(
                error_code="mutation_lock_required",
                message="A mutation lock is required for high-risk actions.",
                phase=phase.value,
                denied_rule="mutation_lock_required",
                suggested_fix="Configure a task-scoped mutation lock before retrying.",
            )
        )


class InMemoryMutationGuard:
    @contextmanager
    def acquire(self, task_id: str, phase: Phase) -> Iterator[None]:
        yield


class FilesystemMutationGuard(FilesystemTaskMutationGuard):
    """Compatibility name for the shared task mutation guard."""

    def __init__(self, project_root: Path) -> None:
        super().__init__(
            project_root,
            task_path_resolver=lambda root, task_id: task_path(root, task_id),
        )


@dataclass(frozen=True, slots=True)
class FilesystemAgentLoopPorts:
    state_store: FilesystemStateStore
    trace_appender: FilesystemTraceAppender
    checkpoint_manager: FilesystemCheckpointManager
    rollback_manager: FilesystemRollbackManager
    mutation_guard: FilesystemMutationGuard
    memory_store: FilesystemMemoryStore

    @classmethod
    def from_project_root(cls, project_root: Path) -> FilesystemAgentLoopPorts:
        return cls(
            state_store=FilesystemStateStore(project_root),
            trace_appender=FilesystemTraceAppender(project_root),
            checkpoint_manager=FilesystemCheckpointManager(project_root),
            rollback_manager=FilesystemRollbackManager(project_root),
            mutation_guard=FilesystemMutationGuard(project_root),
            memory_store=FilesystemMemoryStore(project_root),
        )


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


@dataclass(frozen=True, slots=True)
class _RejectedApproval:
    """Safe feedback emitted after a human rejects one approval request."""

    approval_id: str
    tool_name: str
    reason: str

    def to_observation(self) -> dict[str, object]:
        return {
            "kind": "approval_rejected",
            "approval_id": self.approval_id,
            "decision": "rejected",
            "tool_name": self.tool_name,
            "reason": self.reason,
        }


_TEST_DISCOVERY_TOOLS = frozenset(
    {
        "get_diff",
        "list_checkpoints",
        "list_files",
        "read_file",
        "read_test_report",
        "search_text",
    }
)
_REVIEW_EVIDENCE_TOOLS = _TEST_DISCOVERY_TOOLS
_CODE_EXPLORATION_TOOLS = frozenset(
    {
        "get_diff",
        "list_checkpoints",
        "list_files",
        "memory_read",
        "memory_search",
        "read_file",
        "read_test_report",
        "search_text",
    }
)
_MEMORY_INVALIDATION_RESERVATION_BYTES = 65_536
_TEST_COMMAND_QUESTION = (
    "No executable behavioral test command was found. "
    "Provide one exact command to run, or add a project test runner before resuming."
)
_CODE_EXPLORATION_QUESTION = (
    "CODE has repeated read-only exploration without a source write. "
    "Use sections.writable_roots and write_file to create an allowed target, "
    "or explain what is blocking progress."
)


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
        memory_store: MemoryStore,
        max_steps: int,
        provider_protocol_retries: int = 2,
        interaction_enabled: bool = False,
        mutation_guard: MutationGuard | None = None,
        approval_policy: ApprovalPolicyPort | None = None,
        approval_store: ApprovalStore | None = None,
        approval_request_builder: ApprovalRequestBuilderPort | None = None,
        project_root: Path | None = None,
        delivery_pipeline: DeliveryPipelinePort | None = None,
        build_required: bool = False,
        recovery_coordinator: RecoveryCoordinator | None = None,
        pause_token: PauseToken | None = None,
        intervention_store: InterventionStorePort | None = None,
    ) -> None:
        if not isinstance(max_steps, int) or isinstance(max_steps, bool) or max_steps <= 0:
            raise ValueError("max_steps must be positive")
        if (
            not isinstance(provider_protocol_retries, int)
            or isinstance(provider_protocol_retries, bool)
            or provider_protocol_retries < 0
        ):
            raise ValueError("provider_protocol_retries must be a non-negative integer")
        if not isinstance(interaction_enabled, bool):
            raise ValueError("interaction_enabled must be a bool")
        self._llm = llm
        self._context_builder = context_builder
        self._policy = policy
        self._tool_registry = tool_registry
        self._feedback_builder = feedback_builder
        self._state_store = state_store
        self._trace_appender = trace_appender
        self._checkpoint_manager = checkpoint_manager
        self._rollback_manager = rollback_manager
        self._memory_store = memory_store
        self._mutation_guard = mutation_guard or _FailClosedMutationGuard()
        self._max_steps = max_steps
        self._provider_protocol_retries = provider_protocol_retries
        self._interaction_enabled = interaction_enabled
        self._approval_policy = approval_policy
        self._approval_store = approval_store
        self._approval_request_builder = approval_request_builder
        self._project_root = project_root or Path(".")
        self._delivery_pipeline = delivery_pipeline
        self._build_required = build_required
        self._recovery_coordinator = recovery_coordinator or RecoveryCoordinator()
        self._pause_token = pause_token
        self._intervention_store = intervention_store

    def run(self, task_id: str, *, resume: bool = False) -> AgentRunResult:
        if not isinstance(resume, bool):
            raise ValueError("resume must be a bool")
        result: AgentRunResult | None = None
        body_started = False
        lock_phase = Phase.SPEC
        try:
            state_hint = self._state_store.load(task_id)
            if _is_valid_task_state(state_hint, task_id):
                lock_phase = state_hint.current_phase
        except Exception:
            pass
        try:
            with self._mutation_guard.acquire(task_id, lock_phase):
                body_started = True
                result = self._run_unlocked(task_id, resume=resume)
        except HanCodeError as exc:
            if body_started and result is not None:
                final_state, persistence_error = self._persist_inconsistent_result_state(
                    task_id, result.final_state
                )
                return replace(
                    result,
                    status=TaskStatus.INCONSISTENT,
                    error=_safe_structured_error(persistence_error or exc.structured_error),
                    final_state=final_state,
                )
            if body_started:
                return self._failed_run_result(
                    task_id,
                    exc.structured_error,
                    status=TaskStatus.INCONSISTENT,
                    phase=lock_phase,
                )
            state = self._safe_failure_state(task_id, lock_phase)
            if state.status not in {
                TaskStatus.BLOCKED,
                TaskStatus.FAILED,
                TaskStatus.INCONSISTENT,
            }:
                state = replace(state, status=TaskStatus.BLOCKED)
            return _make_result(
                TaskStatus.BLOCKED,
                0,
                (),
                None,
                exc.structured_error,
                state,
            )
        except Exception as exc:
            if body_started and result is not None:
                error = _agent_loop_error(result.final_state.current_phase, exc)
                final_state, persistence_error = self._persist_inconsistent_result_state(
                    task_id, result.final_state
                )
                return replace(
                    result,
                    status=TaskStatus.INCONSISTENT,
                    error=_safe_structured_error(persistence_error or error),
                    final_state=final_state,
                )
            if body_started:
                return self._failed_run_result(
                    task_id,
                    _agent_loop_error(lock_phase, exc),
                    status=TaskStatus.INCONSISTENT,
                    phase=lock_phase,
                )
            state = self._safe_failure_state(task_id, lock_phase)
            if state.status not in {
                TaskStatus.BLOCKED,
                TaskStatus.FAILED,
                TaskStatus.INCONSISTENT,
            }:
                state = replace(state, status=TaskStatus.BLOCKED)
            error = _mutation_lock_error(lock_phase)
            return _make_result(TaskStatus.BLOCKED, 0, (), None, error, state)
        if result is None:
            return self._failed_run_result(
                task_id,
                _agent_loop_error(lock_phase, RuntimeError("missing run result")),
                status=TaskStatus.INCONSISTENT,
                phase=lock_phase,
            )
        return result

    def _persist_inconsistent_result_state(
        self, task_id: str, state: TaskState
    ) -> tuple[TaskState, StructuredError | None]:
        if not _is_valid_task_state(state, task_id):
            return (
                _emergency_failure_state(task_id, Phase.SPEC),
                _state_adapter_error(Phase.SPEC),
            )
        inconsistent_state = replace(
            state,
            status=TaskStatus.INCONSISTENT,
            inconsistent=True,
            pending_interaction_id=None,
            interactions=(),
        )
        try:
            self._state_store.save(task_id, inconsistent_state)
        except HanCodeError as exc:
            return inconsistent_state, exc.structured_error
        except Exception:
            return inconsistent_state, _state_persistence_error(state.current_phase)
        return inconsistent_state, None

    def _safe_failure_state(self, task_id: str, phase: Phase) -> TaskState:
        try:
            state = self._state_store.load(task_id)
            if _is_valid_task_state(state, task_id):
                return state
        except Exception:
            pass
        return _emergency_failure_state(task_id, phase)

    def _failed_run_result(
        self,
        task_id: str,
        error: StructuredError,
        *,
        status: TaskStatus,
        phase: Phase,
    ) -> AgentRunResult:
        state = self._safe_failure_state(task_id, phase)
        final_state, _persistence_error = self._persist_inconsistent_result_state(
            task_id, state
        )
        return _make_result(
            status,
            0,
            (),
            None,
            error,
            final_state,
        )

    def _prepare_steering_snapshot(
        self, task_id: str, state: TaskState
    ) -> SteeringSnapshot | None:
        """Snapshot the current run's steering before building context.

        Returns None when no store is configured or the task has no active run
        identity, preserving the pre-S17 behaviour for existing callers.
        """
        if self._intervention_store is None:
            return None
        run_id = state.active_run_id
        if not run_id:
            return None
        return self._intervention_store.prepare_context(task_id, run_id)

    def _mark_steering_delivered(
        self, task_id: str, snapshot: SteeringSnapshot | None
    ) -> bool:
        """Mark steering delivered; return True if the snapshot is now stale.

        A stale snapshot means new steering arrived after the snapshot was
        taken, so the loop must discard the about-to-be-built provider call and
        re-prepare context instead of acting on outdated steering.
        """
        if self._intervention_store is None or snapshot is None:
            return False
        if not snapshot.delivery_sequences:
            return False
        result = self._intervention_store.mark_delivered(
            task_id,
            snapshot.run_id,
            snapshot.revision,
            snapshot.delivery_sequences,
        )
        status = getattr(result, "status", None)
        return status is DeliveryStatus.STALE

    def _steering_revision_changed(
        self, task_id: str, snapshot: SteeringSnapshot | None
    ) -> bool:
        """True if steering revision advanced since the snapshot was taken."""
        if self._intervention_store is None or snapshot is None:
            return False
        return self._intervention_store.current_revision(task_id) != snapshot.revision

    def _commit_steering_action(
        self,
        task_id: str,
        snapshot: SteeringSnapshot | None,
        *,
        action_digest: str,
        commit_key: str,
        acknowledge: bool,
    ) -> bool:
        """Commit an action against steering; return True to REPLAN.

        Returns False (proceed) when no store/snapshot is configured, so
        pre-S17 callers are unaffected.
        """
        if self._intervention_store is None or snapshot is None:
            return False
        result = self._intervention_store.commit_action(
            task_id,
            snapshot.run_id,
            snapshot.revision,
            snapshot.delivery_sequences,
            action_digest,
            commit_key,
            acknowledge,
        )
        return getattr(result, "status", None) is ActionCommitStatus.REPLAN

    def _acknowledge_steering(
        self,
        task_id: str,
        snapshot: SteeringSnapshot | None,
        trace_events: list[TraceEvent],
        phase: Phase,
    ) -> None:
        """Mark the steering this action handled as CONSUMED after a real apply.

        Only called at confirmed success choke points (tool dispatched, phase
        finished). Policy denials, recovery rejections, parse failures and
        REPLAN never reach here, so they never acknowledge steering. The
        snapshot's ``delivery_sequences`` are exactly the records this action
        observed; newer steering that arrived after the snapshot is not in the
        list and stays effective for the next turn.
        """
        if self._intervention_store is None or snapshot is None:
            return
        if not snapshot.delivery_sequences:
            return
        mark_consumed = getattr(self._intervention_store, "mark_consumed", None)
        if not callable(mark_consumed):
            return
        try:
            mark_consumed(task_id, snapshot.run_id, snapshot.delivery_sequences)
        except HanCodeError:
            # Acknowledgement is best-effort audit metadata; a failure here must
            # not corrupt an already-applied action. Steering stays effective.
            return
        self._append_trace(
            task_id,
            trace_events,
            event_type="intervention_consumed",
            phase=phase,
            status="succeeded",
            observation={
                "revision": snapshot.revision,
                "sequences": list(snapshot.delivery_sequences),
            },
        )

    def _run_unlocked(self, task_id: str, *, resume: bool = False) -> AgentRunResult:
        state = self._state_store.load(task_id)
        if not _is_valid_task_state(state, task_id):
            raise HanCodeError(_state_adapter_error(Phase.SPEC))
        if state.active_run_id is None and self._approval_store is not None:
            state = replace(state, active_run_id=f"run-{uuid4().hex}")
            self._state_store.save(task_id, state)
        observation: object | None = None
        tool_calls: list[str] = []
        last_recoverable_error: StructuredError | None = None
        trace_events: list[TraceEvent] = []
        pending_risks: list[Risk] = []
        steps_completed = 0
        consecutive_provider_failures = 0
        completed_test_discovery_actions: set[str] = set()
        completed_review_evidence_actions: set[str] = set()
        review_progress_warning = False
        completed_code_exploration_actions: set[str] = set()
        code_progress_warning = False

        def _result(
            status: TaskStatus,
            steps: int,
            calls: tuple[str, ...],
            final_observation: object | None,
            error: StructuredError | None,
            final_state: TaskState,
            *,
            risks: tuple[Risk, ...] = (),
        ) -> AgentRunResult:
            return _make_result(
                status,
                steps,
                calls,
                final_observation,
                error,
                final_state,
                risks=(*pending_risks, *risks),
                trace_events=tuple(trace_events),
            )

        def _pause_if_requested(steps: int) -> AgentRunResult | None:
            if self._pause_token is None or not self._pause_token.is_requested():
                return None
            paused_state = self._save_if_changed(
                task_id, state, replace(state, status=TaskStatus.PAUSED)
            )
            trace_error = self._append_trace(
                task_id,
                trace_events,
                event_type="run_paused",
                phase=paused_state.current_phase,
                status="succeeded",
                observation={"reason": "pause_requested"},
            )
            if trace_error is not None:
                inconsistent_state, state_error = self._mark_inconsistent(
                    task_id, paused_state, trace_error
                )
                return _result(
                    TaskStatus.INCONSISTENT,
                    steps,
                    tuple(tool_calls),
                    observation,
                    state_error,
                    inconsistent_state,
                )
            return _result(
                TaskStatus.PAUSED,
                steps,
                tuple(tool_calls),
                observation,
                None,
                paused_state,
            )

        reconcile = getattr(self._state_store, "reconcile", None)
        if callable(reconcile):
            try:
                sig = inspect.signature(reconcile)
                accepts_recover_pending = "recover_pending" in sig.parameters
            except (ValueError, TypeError):
                accepts_recover_pending = False
            if accepts_recover_pending:
                reconciled_state = reconcile(task_id, recover_pending=resume)
            else:
                reconciled_state = reconcile(task_id)
            if not _is_valid_task_state(reconciled_state, task_id):
                raise HanCodeError(_state_adapter_error(state.current_phase))
            reconciliation_changed = reconciled_state != state
            trace_error = self._append_trace(
                task_id,
                trace_events,
                event_type=(
                    "state_inconsistent"
                    if reconciled_state.inconsistent and reconciliation_changed
                    else "state_reconciled"
                ),
                phase=reconciled_state.current_phase,
                status=(
                    "failed"
                    if reconciled_state.inconsistent and reconciliation_changed
                    else "succeeded"
                ),
                observation={"changed": reconciliation_changed},
            )
            if trace_error is not None:
                state = replace(
                    reconciled_state,
                    status=TaskStatus.INCONSISTENT,
                    inconsistent=True,
                )
                return _result(
                    TaskStatus.INCONSISTENT,
                    0,
                    (),
                    observation,
                    trace_error,
                    state,
                )
            state = reconciled_state

        if state.status is TaskStatus.PAUSED:
            if not resume:
                return _result(
                    TaskStatus.PAUSED,
                    0,
                    (),
                    observation,
                    StructuredError(
                        error_code="task_paused",
                        message="Task is paused and requires an explicit resume.",
                        phase=state.current_phase.value,
                        denied_rule=None,
                        suggested_fix="Resume the task when it is safe to continue.",
                    ),
                    state,
                )
            state = self._save_if_changed(
                task_id, state, replace(state, status=TaskStatus.RUNNING)
            )
            trace_error = self._append_trace(
                task_id,
                trace_events,
                event_type="run_resumed",
                phase=state.current_phase,
                status="running",
            )
            if trace_error is not None:
                state, state_error = self._mark_inconsistent(task_id, state, trace_error)
                return _result(
                    TaskStatus.INCONSISTENT, 0, (), observation, state_error, state
                )

        if state.active_failure is not None:
            active_failure = state.active_failure
            observation = self._recovery_coordinator.observation_from_state(state)
            if active_failure.recovery_mode is RecoveryMode.BLOCKED:
                state = self._save_if_changed(
                    task_id, state, replace(state, status=TaskStatus.BLOCKED)
                )
                trace_error = self._append_trace(
                    task_id,
                    trace_events,
                    event_type="recovery_no_progress",
                    phase=state.current_phase,
                    status="failed",
                    observation={
                        "failure_id": active_failure.failure_id,
                        "repeat_count": active_failure.repeat_count,
                    },
                )
                return _result(
                    TaskStatus.BLOCKED,
                    0,
                    (),
                    observation,
                    _recovery_no_progress_error(state.current_phase),
                    state,
                    risks=(
                        (_trace_failure_risk(trace_error),)
                        if trace_error is not None
                        else ()
                    ),
                )

        if resume:
            if state.status is TaskStatus.BLOCKED and not state.inconsistent:
                state = self._save_if_changed(
                    task_id, state, replace(state, status=TaskStatus.RUNNING)
                )
            elif (
                (state.inconsistent or state.status is TaskStatus.INCONSISTENT)
                and state.rollback_required
                and _is_valid_checkpoint_id(state.latest_checkpoint)
            ):
                state = self._save_if_changed(
                    task_id,
                    state,
                    replace(
                        state,
                        status=TaskStatus.RUNNING,
                        current_phase=Phase.REVIEW,
                        inconsistent=False,
                    ),
                )
            elif state.inconsistent or state.status is TaskStatus.INCONSISTENT:
                state = self._save_if_changed(
                    task_id,
                    state,
                    replace(state, status=TaskStatus.INCONSISTENT, inconsistent=True),
                )
                return _result(
                    TaskStatus.INCONSISTENT,
                    0,
                    (),
                    observation,
                    _resume_state_error(state.current_phase),
                    state,
                )
            elif state.status is TaskStatus.FAILED:
                return _result(
                    TaskStatus.FAILED,
                    0,
                    (),
                    observation,
                    _resume_state_error(state.current_phase),
                    state,
                )
            elif state.status is TaskStatus.WAITING_INPUT:
                answered_pending = _answered_pending_interaction(state)
                if answered_pending is not None:
                    state = self._save_if_changed(
                        task_id,
                        state,
                        replace(
                            state,
                            status=TaskStatus.RUNNING,
                            pending_interaction_id=None,
                        ),
                    )
                    for event_type, event_status in (
                        ("interaction_resumed", "running"),
                        ("interaction_pending_cleared", "succeeded"),
                    ):
                        trace_error = self._append_trace(
                            task_id,
                            trace_events,
                            event_type=event_type,
                            phase=state.current_phase,
                            status=event_status,
                            observation={
                                "interaction_id": answered_pending.interaction_id,
                            },
                        )
                        if trace_error is not None:
                            state, state_error = self._mark_inconsistent(
                                task_id, state, trace_error
                            )
                            return _result(
                                TaskStatus.INCONSISTENT,
                                0,
                                (),
                                observation,
                                state_error,
                                state,
                            )
            elif state.status is TaskStatus.WAITING_APPROVAL:
                approval_result = self._handle_approval_resume(
                    task_id, state, trace_events
                )
                if approval_result is not None:
                    if isinstance(approval_result, Action):
                        # Approved: execute the action directly
                        approved_action = approval_result
                        state = self._state_store.load(task_id)
                        if not _is_valid_task_state(state, task_id):
                            raise HanCodeError(_state_adapter_error(Phase.SPEC))
                        paused_result = _pause_if_requested(steps_completed)
                        if paused_result is not None:
                            return paused_result
                        routing = select_next_phase(
                            state, build_required=self._build_required
                        )
                        decision = self._policy.evaluate(
                            action=approved_action,
                            phase=routing.phase,
                            state=state,
                        )
                        if not decision.allowed:
                            state = self._block(task_id, state)
                            return _result(
                                TaskStatus.BLOCKED,
                                0,
                                tuple(tool_calls),
                                observation,
                                StructuredError(
                                    error_code="policy_denied",
                                    message="The approved action is no longer allowed by policy.",
                                    phase=routing.phase.value,
                                    denied_rule=decision.denied_rule,
                                    suggested_fix=decision.suggested_fix,
                                ),
                                state,
                            )
                        # Execute the approved action directly without calling Provider
                        exec_result = self._execute_approved_action(
                            task_id,
                            state,
                            approved_action,
                            decision,
                            routing.phase,
                            trace_events,
                        )
                        tool_calls.extend(exec_result.tool_calls)
                        pending_risks.extend(exec_result.risks)
                        steps_completed += exec_result.steps
                        state = exec_result.final_state
                        observation = exec_result.final_observation

                        if (
                            exec_result.error is not None
                            or exec_result.status is not TaskStatus.RUNNING
                        ):
                            return _result(
                                exec_result.status,
                                steps_completed,
                                tuple(tool_calls),
                                observation,
                                exec_result.error,
                                state,
                            )
                    elif isinstance(approval_result, _RejectedApproval):
                        observation = approval_result.to_observation()
                    else:
                        # AgentRunResult returned (still pending or error).
                        return approval_result
                # Reload state after approval handling
                state = self._state_store.load(task_id)
                if not _is_valid_task_state(state, task_id):
                    raise HanCodeError(_state_adapter_error(Phase.SPEC))

        if (
            resume
            and state.latest_test_status == "failed"
            and state.latest_test_failure_digest is None
        ):
            try:
                task_root = task_path(self._project_root, task_id)
                report_path = task_root / "TEST_REPORT.md"
                legacy_output = (
                    report_path.read_text(encoding="utf-8")
                    if report_path.is_file() and not report_path.is_symlink()
                    else "Legacy failed test result has no diagnostic report."
                )
                report = classify_test_output(legacy_output, 1)
                command_argv = None
                if state.test_strategy_digest is not None:
                    try:
                        command_argv = TestStrategyStore(self._project_root).load(
                            task_id
                        ).command_argv
                    except HanCodeError:
                        command_argv = None
                legacy_failure = build_test_failure_record(
                    task_id=task_id,
                    attempt_seq=state.test_attempt_seq + 1,
                    strategy_digest=state.test_strategy_digest,
                    command_argv=command_argv,
                    category=report.failure_category,
                    exit_code=None,
                    timed_out=False,
                    passed_count=report.passed_count,
                    failed_count=report.failed_count,
                    output=legacy_output,
                    project_root=self._project_root,
                    legacy_evidence=True,
                )
                TestRemediationStore(self._project_root).save_failure(legacy_failure)
                state = self._save_if_changed(
                    task_id,
                    state,
                    replace(
                        state,
                        latest_test_failure_digest=legacy_failure.digest,
                        test_attempt_seq=state.test_attempt_seq + 1,
                        latest_remediation_digest=None,
                        remediation_applied=False,
                    ),
                )
                trace_error = self._append_trace(
                    task_id,
                    trace_events,
                    event_type="legacy_test_failure_migrated",
                    phase=state.current_phase,
                    status="succeeded",
                    observation={
                        "attempt_id": legacy_failure.attempt_id,
                        "failure_digest": legacy_failure.digest,
                        "category": legacy_failure.category.value,
                    },
                )
                if trace_error is not None:
                    state, state_error = self._mark_inconsistent(
                        task_id, state, trace_error
                    )
                    return _result(
                        TaskStatus.INCONSISTENT,
                        steps_completed,
                        tuple(tool_calls),
                        observation,
                        state_error,
                        state,
                    )
            except (OSError, UnicodeError, ValueError, HanCodeError):
                state, state_error = self._mark_inconsistent(
                    task_id, state, _state_persistence_error(state.current_phase)
                )
                return _result(
                    TaskStatus.INCONSISTENT,
                    steps_completed,
                    tuple(tool_calls),
                    observation,
                    state_error,
                    state,
                )

        traced_phase: Phase | None = (
            state.current_phase if steps_completed > 0 else None
        )
        for step in range(steps_completed + 1, self._max_steps + 1):
            routing = select_next_phase(state, build_required=self._build_required)
            paused_result = _pause_if_requested(step - 1)
            if paused_result is not None and not routing.completed and not routing.blocked:
                return paused_result
            if routing.rollback_required:
                state = self._enter_phase(task_id, state, routing.phase)
                state, observation, error, status = self._perform_rollback(
                    task_id, state, routing.phase, trace_events
                )
                return _result(
                    status,
                    step,
                    tuple(tool_calls),
                    observation,
                    error,
                    state,
                )
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
                trace_error = self._append_trace(
                    task_id,
                    trace_events,
                    event_type="run_completed",
                    phase=routing.phase,
                    status="succeeded",
                )
                if trace_error is not None:
                    pending_risks.append(_trace_failure_risk(trace_error))
                return _result(
                    TaskStatus.COMPLETED, step - 1, tuple(tool_calls), observation, None, state
                )
            if routing.blocked:
                if state.status is TaskStatus.WAITING_INPUT:
                    return _result(
                        TaskStatus.WAITING_INPUT,
                        step - 1,
                        tuple(tool_calls),
                        _pending_interaction_observation(state),
                        None,
                        state,
                    )
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

            if (
                routing.phase is Phase.TEST
                and state.current_phase is Phase.TEST
                and state.test_strategy_digest is None
                and state.phase_completed.get(Phase.CODE.value, False)
            ):
                phase_completed = dict(state.phase_completed)
                phase_completed[Phase.CODE.value] = False
                phase_completed[Phase.TEST.value] = False
                previous_phase = state.current_phase
                state = self._save_if_changed(
                    task_id,
                    state,
                    replace(
                        state,
                        status=TaskStatus.RUNNING,
                        current_phase=Phase.CODE,
                        source_edits_this_phase=0,
                        phase_completed=phase_completed,
                    ),
                )
                trace_error = self._append_trace(
                    task_id,
                    trace_events,
                    event_type="test_strategy_missing",
                    phase=Phase.TEST,
                    status="succeeded",
                    observation={
                        "reason": "strategy_not_recorded",
                        "next_phase": Phase.CODE.value,
                    },
                    state_transition={
                        "current_phase": [previous_phase.value, Phase.CODE.value]
                    },
                )
                if trace_error is not None:
                    state = self._block(task_id, state)
                    return _result(
                        TaskStatus.BLOCKED,
                        step - 1,
                        tuple(tool_calls),
                        observation,
                        trace_error,
                        state,
                    )
                routing = select_next_phase(
                    state, build_required=self._build_required
                )

            state = self._enter_phase(task_id, state, routing.phase)
            if routing.phase is not traced_phase:
                trace_error = self._append_trace(
                    task_id,
                    trace_events,
                    event_type="phase_started",
                    phase=routing.phase,
                    status="running",
                )
                if trace_error is not None:
                    pending_risks.append(_trace_failure_risk(trace_error))
                traced_phase = routing.phase
            steering_snapshot = self._prepare_steering_snapshot(task_id, state)
            try:
                if steering_snapshot is not None:
                    context = dict(
                        self._context_builder.build(
                            task_id=task_id,
                            phase=routing.phase,
                            state=state,
                            observation=observation,
                            user_interventions=steering_snapshot.effective_records,
                            intervention_revision=steering_snapshot.revision,
                        )
                    )
                else:
                    context = dict(
                        self._context_builder.build(
                            task_id=task_id,
                            phase=routing.phase,
                            state=state,
                            observation=observation,
                        )
                    )
            except HanCodeError as exc:
                state = self._block(task_id, state)
                return _result(
                    TaskStatus.BLOCKED,
                    step,
                    tuple(tool_calls),
                    observation,
                    exc.structured_error,
                    state,
                )
            except Exception:
                state, state_error = self._mark_inconsistent(
                    task_id,
                    state,
                    _agent_loop_error(routing.phase, RuntimeError("context build failed")),
                )
                return _result(
                    TaskStatus.INCONSISTENT,
                    step,
                    tuple(tool_calls),
                    observation,
                    state_error,
                    state,
                )
            if self._mark_steering_delivered(task_id, steering_snapshot):
                # New steering arrived before the provider call. Do not call the
                # provider; re-plan the next turn with the fresh snapshot.
                self._append_trace(
                    task_id,
                    trace_events,
                    event_type="stale_context_discarded",
                    phase=routing.phase,
                    status="succeeded",
                    observation={"boundary": "before_provider"},
                )
                continue
            paused_result = _pause_if_requested(step - 1)
            if paused_result is not None:
                return paused_result
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
            except ProviderError as exc:
                trace_error = self._append_trace(
                    task_id,
                    trace_events,
                    event_type="provider_call_failed",
                    phase=routing.phase,
                    status="failed",
                    observation={
                        "error_code": exc.structured_error.error_code,
                    },
                    error_summary=redact_text(exc.structured_error.message),
                )
                if (
                    trace_error is None
                    and exc.protocol_retryable
                    and consecutive_provider_failures < self._provider_protocol_retries
                ):
                    consecutive_provider_failures += 1
                    last_recoverable_error = exc.structured_error
                    observation = {
                        "kind": "provider_error",
                        "error_code": exc.structured_error.error_code,
                        "message": redact_text(exc.structured_error.message),
                        "retryable": True,
                        "attempt": consecutive_provider_failures,
                    }
                    continue

                state = self._block(task_id, state)
                if trace_error is not None:
                    return _result(
                        TaskStatus.BLOCKED,
                        step,
                        tuple(tool_calls),
                        observation,
                        exc.structured_error,
                        state,
                        risks=(_trace_failure_risk(trace_error),),
                    )
                return _result(
                    TaskStatus.BLOCKED,
                    step,
                    tuple(tool_calls),
                    observation,
                    exc.structured_error,
                    state,
                )

            # A decoded provider object has already consumed the protocol
            # boundary.  Subsequent parse failures belong to S11 recovery and
            # must not consume the provider protocol retry budget.
            consecutive_provider_failures = 0
            last_recoverable_error = None

            # Steering that arrived while the provider was thinking makes this
            # raw output stale. Discard it before parsing so no parse failure,
            # recovery budget, or side effect is charged to the old decision.
            if self._steering_revision_changed(task_id, steering_snapshot):
                self._append_trace(
                    task_id,
                    trace_events,
                    event_type="stale_context_discarded",
                    phase=routing.phase,
                    status="succeeded",
                    observation={"boundary": "after_provider"},
                )
                continue

            action = parse_action(raw_action, routing.phase)
            if isinstance(action, ParseError):
                parse_error = _structured_parse_error(action)
                last_recoverable_error = parse_error
                trace_error = self._append_trace(
                    task_id,
                    trace_events,
                    event_type="action_parse_failed",
                    phase=routing.phase,
                    status="failed",
                    observation={"error_code": action.error_code},
                    error_summary=redact_text(action.message),
                )
                if trace_error is not None:
                    state = self._block(task_id, state)
                    return _result(
                        TaskStatus.BLOCKED,
                        step,
                        tuple(tool_calls),
                        observation,
                        parse_error,
                        state,
                        risks=(_trace_failure_risk(trace_error),),
                    )
                # Preserve the existing FeedbackBuilder hook for adapters and
                # observers; the persisted recovery observation below is the
                # machine-facing S11 signal.
                _, feedback_error = self._build_feedback(
                    lambda: self._feedback_builder.from_parse_error(action),
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
                recovery = self._recovery_coordinator.record_parse_failure(
                    state=state,
                    raw_action=raw_action,
                    parse_error=action,
                    phase=routing.phase,
                )
                state = self._save_if_changed(task_id, state, recovery.state)
                observation = recovery.observation
                if recovery.should_block:
                    trace_error = self._append_trace(
                        task_id,
                        trace_events,
                        event_type="recovery_no_progress",
                        phase=routing.phase,
                        status="failed",
                        observation={
                            "failure_id": state.active_failure.failure_id
                            if state.active_failure is not None
                            else None,
                            "repeat_count": (
                                state.active_failure.repeat_count
                                if state.active_failure is not None
                                else None
                            ),
                        },
                    )
                    return _result(
                        TaskStatus.BLOCKED,
                        step,
                        tuple(tool_calls),
                        observation,
                        _recovery_no_progress_error(routing.phase),
                        state,
                        risks=(
                            (_trace_failure_risk(trace_error),)
                            if trace_error is not None
                            else ()
                        ),
                    )
                continue

            paused_result = _pause_if_requested(step - 1)
            if paused_result is not None:
                return paused_result

            # A valid action proves the provider recovered.  Do not let an older
            # retryable provider or parse error masquerade as the later terminal
            # error when this run eventually reaches its step limit.
            last_recoverable_error = None

            # Commit gate: linearize this action against steering before any
            # side effect (recovery bookkeeping, checkpoint, dispatch). If
            # steering advanced the revision, REPLAN with the fresh snapshot.
            # Acknowledgement (marking steering CONSUMED) is deferred to the
            # R3 Prepare-Commit-Apply refactor; steering stays effective here.
            if steering_snapshot is not None:
                action_digest = compute_action_digest(
                    action_type=action.type,
                    phase=action.phase,
                    tool_name=action.tool_name or "",
                    args=action.args,
                    reason=action.reason or "",
                )
                if self._commit_steering_action(
                    task_id,
                    steering_snapshot,
                    action_digest=action_digest,
                    commit_key=f"{steering_snapshot.run_id}:step-{step}:{action_digest}",
                    acknowledge=False,
                ):
                    self._append_trace(
                        task_id,
                        trace_events,
                        event_type="stale_action_discarded",
                        phase=routing.phase,
                        status="succeeded",
                        observation={"boundary": "commit_gate"},
                    )
                    continue

            recovery_guard = self._recovery_coordinator.guard_action(
                state=state, action=action
            )
            if recovery_guard is not None:
                state = self._save_if_changed(task_id, state, recovery_guard.state)
                observation = recovery_guard.observation
                trace_error = self._append_trace(
                    task_id,
                    trace_events,
                    event_type="recovery_action_rejected",
                    phase=routing.phase,
                    status="failed",
                    action=_trace_action(action, None, include_path=True),
                    observation={
                        "failure_id": state.active_failure.failure_id
                        if state.active_failure is not None
                        else None,
                        "repeat_count": (
                            state.active_failure.repeat_count
                            if state.active_failure is not None
                            else None
                        ),
                    },
                )
                if recovery_guard.should_block:
                    return _result(
                        TaskStatus.BLOCKED,
                        step,
                        tuple(tool_calls),
                        observation,
                        _recovery_no_progress_error(routing.phase),
                        state,
                        risks=(
                            (_trace_failure_risk(trace_error),)
                            if trace_error is not None
                            else ()
                        ),
                    )
                continue
            test_discovery_key = _test_discovery_action_key(action, routing.phase)
            if (
                state.latest_test_status == "none"
                and state.test_strategy_digest is None
                and test_discovery_key is not None
                and test_discovery_key in completed_test_discovery_actions
            ):
                trace_error = self._append_trace(
                    task_id,
                    trace_events,
                    event_type="test_strategy_missing",
                    phase=routing.phase,
                    status="waiting" if self._interaction_enabled else "failed",
                    observation={
                        "reason": "repeated_test_discovery",
                        "tool_name": action.tool_name,
                    },
                    error_summary=(
                        None
                        if self._interaction_enabled
                        else "No executable behavioral test command was found."
                    ),
                )
                if trace_error is not None:
                    state = self._block(task_id, state)
                    return _result(
                        TaskStatus.BLOCKED,
                        step,
                        tuple(tool_calls),
                        observation,
                        trace_error,
                        state,
                    )
                if not self._interaction_enabled:
                    state = self._block(task_id, state)
                    return _result(
                        TaskStatus.BLOCKED,
                        step,
                        tuple(tool_calls),
                        observation,
                        _test_strategy_missing_error(routing.phase),
                        state,
                    )
                interaction_action = Action(
                    type=ActionType.ASK_USER,
                    phase=routing.phase,
                    tool_name=None,
                    args={"question": _TEST_COMMAND_QUESTION},
                    reason="A behavioral test command is required to continue TEST.",
                )
                state, interaction = self._request_user_input(
                    task_id,
                    state,
                    interaction_action,
                    routing.phase,
                )
                trace_error = self._append_trace(
                    task_id,
                    trace_events,
                    event_type="interaction_requested",
                    phase=routing.phase,
                    status="waiting",
                    observation={
                        "interaction_id": interaction.interaction_id,
                        "question_length": len(interaction.question),
                    },
                )
                return _result(
                    TaskStatus.WAITING_INPUT,
                    step,
                    tuple(tool_calls),
                    {
                        "interaction_id": interaction.interaction_id,
                        "question": interaction.question,
                    },
                    trace_error,
                    state,
                    risks=(
                        (_trace_failure_risk(trace_error),)
                        if trace_error is not None
                        else ()
                    ),
                )

            code_exploration_key = _code_exploration_action_key(action, routing.phase)
            if (
                code_exploration_key is not None
                and state.source_edits_this_phase == 0
                and code_exploration_key in completed_code_exploration_actions
            ):
                if code_progress_warning:
                    stalled_error = _code_progress_stalled_error(routing.phase)
                    trace_error = self._append_trace(
                        task_id,
                        trace_events,
                        event_type="code_exploration_stalled",
                        phase=routing.phase,
                        status="waiting" if self._interaction_enabled else "failed",
                        observation={
                            "reason": "repeated_code_exploration",
                            "tool_name": action.tool_name,
                            "source_edits_this_phase": state.source_edits_this_phase,
                        },
                        error_summary=(
                            None
                            if self._interaction_enabled
                            else redact_text(stalled_error.message)
                        ),
                    )
                    if trace_error is not None:
                        state = self._block(task_id, state)
                        return _result(
                            TaskStatus.BLOCKED,
                            step,
                            tuple(tool_calls),
                            observation,
                            trace_error,
                            state,
                        )
                    if not self._interaction_enabled:
                        state = self._block(task_id, state)
                        return _result(
                            TaskStatus.BLOCKED,
                            step,
                            tuple(tool_calls),
                            observation,
                            stalled_error,
                            state,
                        )
                    interaction_action = Action(
                        type=ActionType.ASK_USER,
                        phase=routing.phase,
                        tool_name=None,
                        args={"question": _CODE_EXPLORATION_QUESTION},
                        reason="Repeated CODE exploration needs a concrete next step.",
                    )
                    try:
                        state, interaction = self._request_user_input(
                            task_id,
                            state,
                            interaction_action,
                            routing.phase,
                        )
                    except HanCodeError as exc:
                        state = self._block(task_id, state)
                        return _result(
                            TaskStatus.BLOCKED,
                            step,
                            tuple(tool_calls),
                            observation,
                            exc.structured_error,
                            state,
                        )
                    trace_error = self._append_trace(
                        task_id,
                        trace_events,
                        event_type="interaction_requested",
                        phase=routing.phase,
                        status="waiting",
                        observation={
                            "interaction_id": interaction.interaction_id,
                            "question_length": len(interaction.question),
                            "reason": "code_exploration_stalled",
                        },
                    )
                    return _result(
                        TaskStatus.WAITING_INPUT,
                        step,
                        tuple(tool_calls),
                        {
                            "interaction_id": interaction.interaction_id,
                            "question": interaction.question,
                        },
                        trace_error,
                        state,
                        risks=(
                            (_trace_failure_risk(trace_error),)
                            if trace_error is not None
                            else ()
                        ),
                    )

                code_progress_warning = True
                trace_error = self._append_trace(
                    task_id,
                    trace_events,
                    event_type="code_exploration_repeated",
                    phase=routing.phase,
                    status="waiting",
                    observation={
                        "reason": "repeated_code_exploration",
                        "tool_name": action.tool_name,
                        "source_edits_this_phase": state.source_edits_this_phase,
                    },
                )
                if trace_error is not None:
                    state = self._block(task_id, state)
                    return _result(
                        TaskStatus.BLOCKED,
                        step,
                        tuple(tool_calls),
                        observation,
                        trace_error,
                        state,
                    )
                observation = {
                    "kind": "code_exploration_repeated",
                    "summary": (
                        "A completed read-only exploration was repeated without a source write."
                    ),
                    "next_action_hint": (
                        "Use sections.writable_roots and write_file directly; "
                        "do not repeat list_files, read_file, or search_text."
                    ),
                    "source_edits_this_phase": state.source_edits_this_phase,
                }
                continue

            decision = self._policy.evaluate(
                action=action,
                phase=routing.phase,
                state=state,
            )
            if not _is_valid_policy_decision(action, decision, routing.phase, task_id):
                fallback_error = _checkpoint_guard_error(
                    "policy_decision_invalid",
                    "Policy returned a decision that does not match the action target.",
                    routing.phase,
                    "structured_policy_decision_required",
                    "Repair the policy adapter before retrying the action.",
                )
                state, state_error = self._mark_inconsistent(
                    task_id, state, fallback_error
                )
                return _result(
                    TaskStatus.INCONSISTENT,
                    step,
                    tuple(tool_calls),
                    observation,
                    state_error,
                    state,
                )
            if not decision.allowed:
                policy_error = StructuredError(
                    error_code="policy_denied",
                    message=decision.reason,
                    phase=routing.phase.value,
                    denied_rule=decision.denied_rule,
                    suggested_fix=decision.suggested_fix,
                )
                last_recoverable_error = policy_error
                trace_error = self._append_trace(
                    task_id,
                    trace_events,
                    event_type="policy_denied",
                    phase=routing.phase,
                    status="denied",
                    action=_trace_action(action, decision, include_path=True),
                    error_summary=redact_text(decision.reason),
                )
                if trace_error is not None:
                    state = self._block(task_id, state)
                    return _result(
                        TaskStatus.BLOCKED,
                        step,
                        tuple(tool_calls),
                        observation,
                        policy_error,
                        state,
                        risks=(_trace_failure_risk(trace_error),),
                    )
                if self._recovery_coordinator.supports_policy_denial(decision):
                    _, feedback_error = self._build_feedback(
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
                    recovery = self._recovery_coordinator.record_policy_failure(
                        state=state,
                        action=action,
                        decision=decision,
                        phase=routing.phase,
                    )
                    state = self._save_if_changed(task_id, state, recovery.state)
                    observation = recovery.observation
                    if recovery.should_block:
                        trace_error = self._append_trace(
                            task_id,
                            trace_events,
                            event_type="recovery_no_progress",
                            phase=routing.phase,
                            status="failed",
                            observation={
                                "failure_id": state.active_failure.failure_id
                                if state.active_failure is not None
                                else None,
                                "repeat_count": (
                                    state.active_failure.repeat_count
                                    if state.active_failure is not None
                                    else None
                                ),
                            },
                        )
                        return _result(
                            TaskStatus.BLOCKED,
                            step,
                            tuple(tool_calls),
                            observation,
                            _recovery_no_progress_error(routing.phase),
                            state,
                            risks=(
                                (_trace_failure_risk(trace_error),)
                                if trace_error is not None
                                else ()
                            ),
                        )
                    continue
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

            review_evidence_key = _review_evidence_action_key(
                action, routing.phase, task_id
            )
            if (
                review_evidence_key is not None
                and review_evidence_key in completed_review_evidence_actions
            ):
                if review_progress_warning:
                    trace_error = self._append_trace(
                        task_id,
                        trace_events,
                        event_type="review_progress_stalled",
                        phase=routing.phase,
                        status="failed",
                        observation={
                            "reason": "repeated_review_evidence",
                            "evidence_count": len(completed_review_evidence_actions),
                        },
                    )
                    if trace_error is not None:
                        state = self._block(task_id, state)
                        return _result(
                            TaskStatus.BLOCKED,
                            step,
                            tuple(tool_calls),
                            observation,
                            trace_error,
                            state,
                            risks=(_trace_failure_risk(trace_error),),
                        )
                    state = self._block(task_id, state)
                    return _result(
                        TaskStatus.BLOCKED,
                        step,
                        tuple(tool_calls),
                        observation,
                        _review_progress_stalled_error(routing.phase),
                        state,
                    )
                review_progress_warning = True
                trace_error = self._append_trace(
                    task_id,
                    trace_events,
                    event_type="review_progress_warning",
                    phase=routing.phase,
                    status="waiting",
                    observation={
                        "reason": "repeated_review_evidence",
                        "evidence_count": len(completed_review_evidence_actions),
                    },
                )
                if trace_error is not None:
                    state = self._block(task_id, state)
                    return _result(
                        TaskStatus.BLOCKED,
                        step,
                        tuple(tool_calls),
                        observation,
                        trace_error,
                        state,
                        risks=(_trace_failure_risk(trace_error),),
                    )
                observation = {
                    "kind": "review_action_repeated",
                    "summary": "Review evidence was already inspected.",
                    "next_action_hint": (
                        "Record the review with the available evidence instead of "
                        "reading it again."
                    ),
                    "evidence_count": len(completed_review_evidence_actions),
                }
                continue

            if action.type is ActionType.ASK_USER:
                try:
                    state, interaction = self._request_user_input(
                        task_id,
                        state,
                        action,
                        routing.phase,
                    )
                except HanCodeError as exc:
                    state = self._block(task_id, state)
                    return _result(
                        TaskStatus.BLOCKED,
                        step,
                        tuple(tool_calls),
                        observation,
                        exc.structured_error,
                        state,
                    )
                trace_error = self._append_trace(
                    task_id,
                    trace_events,
                    event_type="interaction_requested",
                    phase=routing.phase,
                    status="waiting",
                    observation={
                        "interaction_id": interaction.interaction_id,
                        "question_length": len(interaction.question),
                    },
                )
                if trace_error is not None:
                    return _result(
                        TaskStatus.WAITING_INPUT,
                        step,
                        tuple(tool_calls),
                        {
                            "interaction_id": interaction.interaction_id,
                            "question": interaction.question,
                        },
                        trace_error,
                        state,
                        risks=(_trace_failure_risk(trace_error),),
                    )
                return _result(
                    TaskStatus.WAITING_INPUT,
                    step,
                    tuple(tool_calls),
                    {
                        "interaction_id": interaction.interaction_id,
                        "question": interaction.question,
                    },
                    None,
                    state,
                )

            if action.type is ActionType.TOOL_CALL:
                if not isinstance(action.tool_name, str) or not action.tool_name:
                    state, state_error = self._mark_inconsistent(
                        task_id,
                        state,
                        _checkpoint_guard_error(
                            "action_schema_invalid",
                            "Tool action is missing a valid tool name.",
                            routing.phase,
                            "structured_action_required",
                            "Repair the action parser before retrying the task.",
                        ),
                    )
                    return _result(
                        TaskStatus.INCONSISTENT,
                        step,
                        tuple(tool_calls),
                        observation,
                        state_error,
                        state,
                    )

                # ---- Approval Gate (inserted before checkpoint and tool dispatch) ----
                if (
                    self._approval_policy is not None
                    and self._approval_store is not None
                    and self._approval_request_builder is not None
                ):
                    approval_req = self._approval_policy.evaluate(
                        action=action,
                        policy_decision=decision,
                        state=state,
                    )
                    if getattr(approval_req, "required", False):
                        # Build approval record and pause
                        state, approval_record = self._request_approval(
                            task_id,
                            state,
                            action,
                            approval_req,
                            routing.phase,
                        )
                        trace_error = self._append_trace(
                            task_id,
                            trace_events,
                            event_type="approval_requested",
                            phase=routing.phase,
                            status="waiting",
                            observation={
                                "approval_id": approval_record.approval_id,
                                "category": approval_record.category.value,
                                "tool_name": action.tool_name,
                            },
                        )
                        if trace_error is not None:
                            return _result(
                                TaskStatus.WAITING_APPROVAL,
                                step,
                                tuple(tool_calls),
                                {
                                    "approval_id": approval_record.approval_id,
                                    "tool_name": action.tool_name,
                                    "reason": approval_record.action.reason,
                                },
                                trace_error,
                                state,
                                risks=(_trace_failure_risk(trace_error),),
                            )
                        return _result(
                            TaskStatus.WAITING_APPROVAL,
                            step,
                            tuple(tool_calls),
                            {
                                "approval_id": approval_record.approval_id,
                                "tool_name": action.tool_name,
                                "reason": approval_record.action.reason,
                            },
                            None,
                            state,
                        )

                source_write = _is_source_write_action(action, decision, task_id)
                if action.tool_name in {"write_file", "edit_file", "rollback_last_checkpoint"}:
                    try:
                        self._memory_store.ensure_capacity(
                            task_id,
                            reserved_bytes=_MEMORY_INVALIDATION_RESERVATION_BYTES,
                        )
                    except HanCodeError as exc:
                        state = self._block(task_id, state)
                        return _result(
                            TaskStatus.BLOCKED,
                            step,
                            tuple(tool_calls),
                            observation,
                            exc.structured_error,
                            state,
                        )
                    except Exception:
                        state = self._block(task_id, state)
                        return _result(
                            TaskStatus.BLOCKED,
                            step,
                            tuple(tool_calls),
                            observation,
                            _memory_persistence_error(routing.phase),
                            state,
                        )
                trace_error = self._append_trace(
                    task_id,
                    trace_events,
                    event_type="tool_called",
                    phase=routing.phase,
                    status="running",
                    action=_trace_action(action, decision, include_path=True),
                    observation={"tool_name": action.tool_name},
                )
                if trace_error is not None:
                    state = self._block(task_id, state)
                    return _result(
                        TaskStatus.BLOCKED,
                        step,
                        tuple(tool_calls),
                        observation,
                        trace_error,
                        state,
                    )
                if action.tool_name == "rollback_last_checkpoint":
                    tool_calls.append(action.tool_name)
                    state, observation, error, status = self._perform_rollback(
                        task_id, state, routing.phase, trace_events
                    )
                    return _result(
                        status,
                        step,
                        tuple(tool_calls),
                        observation,
                        error,
                        state,
                    )
                if source_write:
                    trace_error = self._append_trace(
                        task_id,
                        trace_events,
                        event_type="source_write_authorized",
                        phase=routing.phase,
                        status="running",
                        action=_trace_action(action, decision, include_path=True),
                        observation={
                            "tool_name": action.tool_name,
                            "path": action.args.get("path"),
                        },
                    )
                    if trace_error is not None:
                        state = self._block(task_id, state)
                        return _result(
                            TaskStatus.BLOCKED,
                            step,
                            tuple(tool_calls),
                            observation,
                            trace_error,
                            state,
                        )
                checkpoint: CheckpointManifest | None = None
                checkpoint_aborted = False
                requires_checkpoint = decision.requires_checkpoint or source_write
                if requires_checkpoint:
                    path_value = action.args.get("path")
                    if not isinstance(path_value, str) or not path_value.strip():
                        state, state_error = self._mark_inconsistent(
                            task_id,
                            state,
                            _checkpoint_guard_error(
                                "action_schema_invalid",
                                "Checkpointed write action is missing a valid path.",
                                routing.phase,
                                "structured_action_required",
                                "Repair the action parser before retrying the source write.",
                            ),
                        )
                        return _result(
                            TaskStatus.INCONSISTENT,
                            step,
                            tuple(tool_calls),
                            observation,
                            state_error,
                            state,
                            risks=(_checkpoint_failure_risk(),),
                        )
                    path = path_value
                    if not isinstance(action.reason, str) or not action.reason.strip():
                        state, state_error = self._mark_inconsistent(
                            task_id,
                            state,
                            _checkpoint_guard_error(
                                "action_schema_invalid",
                                "Checkpointed write action is missing a reason.",
                                routing.phase,
                                "structured_action_required",
                                "Repair the action parser before retrying the source write.",
                            ),
                        )
                        return _result(
                            TaskStatus.INCONSISTENT,
                            step,
                            tuple(tool_calls),
                            observation,
                            state_error,
                            state,
                            risks=(_checkpoint_failure_risk(),),
                        )
                    previous_checkpoint_seq = state.checkpoint_seq
                    try:
                        checkpoint = self._checkpoint_manager.create(
                            task_id,
                            [Path(path)],
                            action.reason,
                        )
                    except HanCodeError as exc:
                        state, create_error = self._checkpoint_create_failure(
                            task_id, state, routing.phase, exc.structured_error
                        )
                        return _result(
                            TaskStatus.INCONSISTENT,
                            step,
                            tuple(tool_calls),
                            observation,
                            create_error,
                            state,
                            risks=(_checkpoint_failure_risk(),),
                        )
                    except Exception:
                        state, create_error = self._checkpoint_create_failure(
                            task_id,
                            state,
                            routing.phase,
                            _checkpoint_guard_error(
                                "checkpoint_create_failed",
                                "Checkpoint could not be created before the source write.",
                                routing.phase,
                                "checkpoint_creation_required",
                                "Restore checkpoint storage before retrying the source write.",
                            ),
                        )
                        return _result(
                            TaskStatus.INCONSISTENT,
                            step,
                            tuple(tool_calls),
                            observation,
                            create_error,
                            state,
                            risks=(_checkpoint_failure_risk(),),
                        )
                    if not isinstance(checkpoint, CheckpointManifest):
                        state, state_error = self._checkpoint_create_failure(
                            task_id,
                            state,
                            routing.phase,
                            _checkpoint_guard_error(
                                "checkpoint_manifest_invalid",
                                "Checkpoint manager returned an invalid manifest.",
                                routing.phase,
                                "checkpoint_manifest_required",
                                "Repair the checkpoint manager before retrying the source write.",
                            ),
                        )
                        return _result(
                            TaskStatus.INCONSISTENT,
                            step,
                            tuple(tool_calls),
                            observation,
                            state_error,
                            state,
                            risks=(_checkpoint_failure_risk(),),
                        )
                    if not _is_valid_checkpoint_id(checkpoint.checkpoint_id):
                        state, state_error = self._checkpoint_create_failure(
                            task_id,
                            state,
                            routing.phase,
                            _checkpoint_guard_error(
                                "checkpoint_manifest_invalid",
                                "Checkpoint manager returned an invalid checkpoint ID.",
                                routing.phase,
                                "checkpoint_id_required",
                                "Repair the checkpoint manager before retrying the source write.",
                            ),
                        )
                        return _result(
                            TaskStatus.INCONSISTENT,
                            step,
                            tuple(tool_calls),
                            observation,
                            state_error,
                            state,
                            risks=(_checkpoint_failure_risk(),),
                        )
                    try:
                        loaded_state = self._state_store.load(task_id)
                        if not _is_valid_task_state(loaded_state, task_id):
                            raise HanCodeError(_state_adapter_error(routing.phase))
                        state = loaded_state
                    except HanCodeError:
                        state, reload_error = self._checkpoint_reload_failure(
                            task_id,
                            state,
                            checkpoint,
                            previous_checkpoint_seq,
                            routing.phase,
                        )
                        return _result(
                            TaskStatus.INCONSISTENT,
                            step,
                            tuple(tool_calls),
                            observation,
                            reload_error,
                            state,
                            risks=(_checkpoint_failure_risk(),),
                        )
                    except Exception:
                        state, reload_error = self._checkpoint_reload_failure(
                            task_id,
                            state,
                            checkpoint,
                            previous_checkpoint_seq,
                            routing.phase,
                        )
                        return _result(
                            TaskStatus.INCONSISTENT,
                            step,
                            tuple(tool_calls),
                            observation,
                            reload_error,
                            state,
                            risks=(_checkpoint_failure_risk(),),
                        )
                    if not _is_checkpoint_state_ready(state, task_id, routing.phase):
                        state = self._block(task_id, state)
                        return _result(
                            TaskStatus.BLOCKED,
                            step,
                            tuple(tool_calls),
                            observation,
                            _checkpoint_guard_error(
                                "checkpoint_state_invalid",
                                "Task state is not consistent with the pending checkpoint.",
                                routing.phase,
                                "consistent_checkpoint_state_required",
                                "Reconcile task state before retrying the source write.",
                            ),
                            state,
                        )
                    if (
                        state.latest_checkpoint != checkpoint.checkpoint_id
                        or state.checkpoint_seq != previous_checkpoint_seq + 1
                    ):
                        pointer_error = _checkpoint_guard_error(
                            "checkpoint_state_invalid",
                            "Checkpoint creation did not persist the expected task-state pointer.",
                            routing.phase,
                            "checkpoint_state_pointer_required",
                            "Reconcile latest_checkpoint and checkpoint_seq before retrying the source write.",
                        )
                        recovery_state = replace(
                            state,
                            latest_checkpoint=checkpoint.checkpoint_id,
                            checkpoint_seq=previous_checkpoint_seq + 1,
                        )
                        state, state_error = self._mark_inconsistent(
                            task_id, recovery_state, pointer_error
                        )
                        return _result(
                            TaskStatus.INCONSISTENT,
                            step,
                            tuple(tool_calls),
                            observation,
                            state_error,
                            state,
                            risks=(_checkpoint_failure_risk(),),
                        )
                    if not _is_pending_checkpoint_for(
                        checkpoint,
                        task_id,
                        routing.phase,
                        Path(path),
                        expected_checkpoint_id=state.latest_checkpoint,
                    ):
                        state = self._block(task_id, state)
                        return _result(
                            TaskStatus.BLOCKED,
                            step,
                            tuple(tool_calls),
                            observation,
                            _checkpoint_guard_error(
                                "checkpoint_manifest_invalid",
                                "Checkpoint metadata does not match the pending source write.",
                                routing.phase,
                                "matching_pending_checkpoint_required",
                                "Repair the checkpoint manager before retrying the source write.",
                            ),
                            state,
                        )
                try:
                    tool_result = self._tool_registry.dispatch(action)
                except HanCodeError as exc:
                    if _memory_tool_integrity_failure(action, exc.structured_error):
                        trace_error = self._append_trace(
                            task_id,
                            trace_events,
                            event_type="tool_failed",
                            phase=routing.phase,
                            status="failed",
                            action=_trace_action(action, decision, include_path=False),
                            observation={"dispatch_failed": True},
                            error_summary=redact_text(exc.structured_error.message),
                        )
                        state = self._block(task_id, state)
                        return _result(
                            TaskStatus.BLOCKED,
                            step,
                            tuple(tool_calls),
                            observation,
                            exc.structured_error,
                            state,
                            risks=(
                                (_trace_failure_risk(trace_error),)
                                if trace_error is not None
                                else ()
                            ),
                        )
                    trace_error = self._append_trace(
                        task_id,
                        trace_events,
                        event_type="tool_failed",
                        phase=routing.phase,
                        status="failed",
                        action=_trace_action(action, decision, include_path=True),
                        observation={"dispatch_failed": True},
                        error_summary=redact_text(exc.structured_error.message),
                    )
                    state, state_error = self._mark_inconsistent(
                        task_id, state, trace_error or exc.structured_error
                    )
                    return _result(
                        TaskStatus.INCONSISTENT,
                        step,
                        tuple(tool_calls),
                        observation,
                        state_error,
                        state,
                        risks=(_checkpoint_failure_risk(),) if requires_checkpoint else (),
                    )
                except Exception:
                    fallback_error = _checkpoint_guard_error(
                        "tool_dispatch_failed",
                        "Tool dispatch failed after the checkpoint guard.",
                        routing.phase,
                        "tool_dispatch_required",
                        "Repair the tool registry before retrying the action.",
                    )
                    trace_error = self._append_trace(
                        task_id,
                        trace_events,
                        event_type="tool_failed",
                        phase=routing.phase,
                        status="failed",
                        action=_trace_action(action, decision, include_path=True),
                        observation={"dispatch_failed": True},
                        error_summary=redact_text(fallback_error.message),
                    )
                    state, state_error = self._mark_inconsistent(
                        task_id, state, trace_error or fallback_error
                    )
                    return _result(
                        TaskStatus.INCONSISTENT,
                        step,
                        tuple(tool_calls),
                        observation,
                        state_error,
                        state,
                        risks=(_checkpoint_failure_risk(),) if requires_checkpoint else (),
                    )
                if not _is_valid_tool_result(tool_result, action):
                    fallback_error = _checkpoint_guard_error(
                        "tool_result_invalid",
                        "Tool dispatch returned a result that does not match the tool protocol.",
                        routing.phase,
                        "structured_tool_result_required",
                        "Repair the tool adapter so it returns a validated ToolResult.",
                    )
                    trace_error = self._append_trace(
                        task_id,
                        trace_events,
                        event_type="tool_failed",
                        phase=routing.phase,
                        status="failed",
                        action=_trace_action(action, decision, include_path=True),
                        observation={"result_valid": False},
                        error_summary=redact_text(fallback_error.message),
                    )
                    state, state_error = self._mark_inconsistent(
                        task_id, state, trace_error or fallback_error
                    )
                    return _result(
                        TaskStatus.INCONSISTENT,
                        step,
                        tuple(tool_calls),
                        observation,
                        state_error,
                        state,
                        risks=(_checkpoint_failure_risk(),) if requires_checkpoint else (),
                    )
                observation, feedback_error = self._build_feedback(
                    lambda: self._feedback_builder.from_tool_result(
                        tool_result, phase=routing.phase
                    ),
                    routing.phase,
                )
                if feedback_error is not None:
                    if _memory_failure_requires_inconsistent(action, tool_result):
                        state, state_error = self._mark_inconsistent(
                            task_id,
                            state,
                            feedback_error,
                            rollback_required=requires_checkpoint,
                        )
                        return _result(
                            TaskStatus.INCONSISTENT,
                            step,
                            tuple(tool_calls),
                            observation,
                            state_error,
                            state,
                        )
                    state = self._block(task_id, state)
                    return _result(
                        TaskStatus.BLOCKED,
                        step,
                        tuple(tool_calls),
                        observation,
                        feedback_error,
                        state,
                    )
                try:
                    memory_record = self._memory_store.record_tool_result(
                        task_id,
                        phase=routing.phase,
                        action=action,
                        result=tool_result,
                        observation=observation,
                        state=state,
                    )
                except HanCodeError as exc:
                    if _memory_failure_requires_inconsistent(action, tool_result):
                        state, state_error = self._mark_inconsistent(
                            task_id,
                            state,
                            exc.structured_error,
                            rollback_required=requires_checkpoint,
                        )
                        return _result(
                            TaskStatus.INCONSISTENT,
                            step,
                            tuple(tool_calls),
                            observation,
                            state_error,
                            state,
                        )
                    if _memory_failure_needs_checkpoint_abort(
                        action, tool_result, requires_checkpoint
                    ):
                        path_value = action.args.get("path")
                        assert isinstance(path_value, str)
                        state, abort_error = self._abort_checkpoint_after_no_mutation_failure(
                            task_id, state, checkpoint, routing.phase, path_value
                        )
                        if abort_error is not None:
                            state, state_error = self._mark_inconsistent(
                                task_id,
                                state,
                                abort_error,
                                rollback_required=True,
                            )
                            return _result(
                                TaskStatus.INCONSISTENT,
                                step,
                                tuple(tool_calls),
                                observation,
                                state_error,
                                state,
                                risks=(_checkpoint_failure_risk(),),
                            )
                    state = self._block(task_id, state)
                    return _result(
                        TaskStatus.BLOCKED,
                        step,
                        tuple(tool_calls),
                        observation,
                        exc.structured_error,
                        state,
                    )
                except Exception:
                    if _memory_failure_requires_inconsistent(action, tool_result):
                        state, state_error = self._mark_inconsistent(
                            task_id,
                            state,
                            _memory_persistence_error(routing.phase),
                            rollback_required=requires_checkpoint,
                        )
                        return _result(
                            TaskStatus.INCONSISTENT,
                            step,
                            tuple(tool_calls),
                            observation,
                            state_error,
                            state,
                        )
                    if _memory_failure_needs_checkpoint_abort(
                        action, tool_result, requires_checkpoint
                    ):
                        path_value = action.args.get("path")
                        assert isinstance(path_value, str)
                        state, abort_error = self._abort_checkpoint_after_no_mutation_failure(
                            task_id, state, checkpoint, routing.phase, path_value
                        )
                        if abort_error is not None:
                            state, state_error = self._mark_inconsistent(
                                task_id,
                                state,
                                abort_error,
                                rollback_required=True,
                            )
                            return _result(
                                TaskStatus.INCONSISTENT,
                                step,
                                tuple(tool_calls),
                                observation,
                                state_error,
                                state,
                                risks=(_checkpoint_failure_risk(),),
                            )
                    state = self._block(task_id, state)
                    return _result(
                        TaskStatus.BLOCKED,
                        step,
                        tuple(tool_calls),
                        observation,
                        _memory_persistence_error(routing.phase),
                        state,
                    )
                observation = _attach_memory_reference(observation, memory_record)
                tool_event_type = "tool_completed" if tool_result.success else "tool_failed"
                tool_event_status = "succeeded" if tool_result.success else "failed"
                trace_error = self._append_trace(
                    task_id,
                    trace_events,
                    event_type=tool_event_type,
                    phase=routing.phase,
                    status=tool_event_status,
                    action=_trace_action(action, decision, include_path=True),
                    observation=_tool_trace_observation(tool_result, memory_record),
                    error_summary=(
                        None
                        if tool_result.success
                        else redact_text(_tool_error_summary(tool_result))
                    ),
                )
                if trace_error is not None:
                    state, state_error = self._mark_inconsistent(
                        task_id, state, trace_error
                    )
                    return _result(
                        TaskStatus.INCONSISTENT,
                        step,
                        tuple(tool_calls),
                        observation,
                        state_error,
                        state,
                        risks=(_checkpoint_failure_risk(),) if requires_checkpoint else (),
                    )
                if tool_result.success:
                    completed_key = _test_discovery_action_key(action, routing.phase)
                    if completed_key is not None:
                        completed_test_discovery_actions.add(completed_key)
                    if code_exploration_key is not None:
                        is_new_code_exploration = (
                            code_exploration_key not in completed_code_exploration_actions
                        )
                        completed_code_exploration_actions.add(code_exploration_key)
                        if is_new_code_exploration:
                            code_progress_warning = False
                tool_calls.append(action.tool_name)
                if requires_checkpoint:
                    if not tool_result.success:
                        if tool_result.mutation_applied is False:
                            if checkpoint is None:
                                state, state_error = self._mark_inconsistent(
                                    task_id,
                                    state,
                                    _checkpoint_guard_error(
                                        "checkpoint_manifest_missing",
                                        "A checkpoint manifest is required before aborting the source write.",
                                        routing.phase,
                                        "checkpoint_manifest_required",
                                        "Repair checkpoint creation before retrying the source write.",
                                    ),
                                    rollback_required=True,
                                )
                                return _result(
                                    TaskStatus.INCONSISTENT,
                                    step,
                                    tuple(tool_calls),
                                    observation,
                                    state_error,
                                    state,
                                    risks=(_checkpoint_failure_risk(),),
                                )
                            try:
                                aborted = self._checkpoint_manager.abort(
                                    task_id,
                                    checkpoint.checkpoint_id,
                                    restore_files=False,
                                )
                            except HanCodeError as exc:
                                state, state_error = self._mark_inconsistent(
                                    task_id,
                                    state,
                                    exc.structured_error,
                                    rollback_required=True,
                                )
                                return _result(
                                    TaskStatus.INCONSISTENT,
                                    step,
                                    tuple(tool_calls),
                                    observation,
                                    state_error,
                                    state,
                                    risks=(_checkpoint_failure_risk(),),
                                )
                            except Exception:
                                state, state_error = self._mark_inconsistent(
                                    task_id,
                                    state,
                                    _checkpoint_guard_error(
                                        "pending_checkpoint_abort_failed",
                                        "Pending checkpoint could not be safely aborted.",
                                        routing.phase,
                                        "pending_checkpoint_abort_persistence_required",
                                        "Repair checkpoint storage before retrying the source write.",
                                    ),
                                    rollback_required=True,
                                )
                                return _result(
                                    TaskStatus.INCONSISTENT,
                                    step,
                                    tuple(tool_calls),
                                    observation,
                                    state_error,
                                    state,
                                    risks=(_checkpoint_failure_risk(),),
                                )
                            if not _is_aborted_checkpoint_for(
                                aborted,
                                task_id,
                                routing.phase,
                                Path(path),
                                checkpoint.checkpoint_id,
                            ):
                                state, state_error = self._mark_inconsistent(
                                    task_id,
                                    state,
                                    _checkpoint_guard_error(
                                        "checkpoint_manifest_invalid",
                                        "Checkpoint manager returned an invalid aborted manifest.",
                                        routing.phase,
                                        "aborted_checkpoint_manifest_required",
                                        "Repair checkpoint abort persistence before retrying the source write.",
                                    ),
                                    rollback_required=True,
                                )
                                return _result(
                                    TaskStatus.INCONSISTENT,
                                    step,
                                    tuple(tool_calls),
                                    observation,
                                    state_error,
                                    state,
                                    risks=(_checkpoint_failure_risk(),),
                                )
                            try:
                                reloaded_state = self._state_store.load(task_id)
                            except HanCodeError as exc:
                                state, state_error = self._mark_inconsistent(
                                    task_id,
                                    state,
                                    exc.structured_error,
                                    rollback_required=True,
                                )
                                return _result(
                                    TaskStatus.INCONSISTENT,
                                    step,
                                    tuple(tool_calls),
                                    observation,
                                    state_error,
                                    state,
                                    risks=(_checkpoint_failure_risk(),),
                                )
                            except Exception:
                                state, state_error = self._mark_inconsistent(
                                    task_id,
                                    state,
                                    _state_persistence_error(routing.phase),
                                    rollback_required=True,
                                )
                                return _result(
                                    TaskStatus.INCONSISTENT,
                                    step,
                                    tuple(tool_calls),
                                    observation,
                                    state_error,
                                    state,
                                    risks=(_checkpoint_failure_risk(),),
                                )
                            if not _is_valid_task_state(reloaded_state, task_id):
                                state, state_error = self._mark_inconsistent(
                                    task_id,
                                    state,
                                    _checkpoint_guard_error(
                                        "checkpoint_state_invalid",
                                        "Task state is invalid after aborting the pending checkpoint.",
                                        routing.phase,
                                        "consistent_checkpoint_state_required",
                                        "Reconcile task state before retrying the source write.",
                                    ),
                                    rollback_required=True,
                                )
                                return _result(
                                    TaskStatus.INCONSISTENT,
                                    step,
                                    tuple(tool_calls),
                                    observation,
                                    state_error,
                                    state,
                                    risks=(_checkpoint_failure_risk(),),
                                )
                            state = reloaded_state
                            checkpoint_aborted = True
                        else:
                            fallback_error = _checkpoint_guard_error(
                                "checkpointed_write_failed",
                                "Checkpointed source write failed; task state is inconsistent.",
                                routing.phase,
                                "checkpointed_write_must_be_reconciled",
                                "Inspect the source file and checkpoint before continuing.",
                            )
                            state, state_error = self._mark_inconsistent(
                                task_id, state, fallback_error, rollback_required=True
                            )
                            return _result(
                                TaskStatus.INCONSISTENT,
                                step,
                                tuple(tool_calls),
                                observation,
                                state_error,
                                state,
                                risks=(_checkpoint_failure_risk(),),
                            )
                    if checkpoint is None:
                        if not checkpoint_aborted:
                            state, state_error = self._mark_inconsistent(
                                task_id,
                                state,
                                _checkpoint_guard_error(
                                    "checkpoint_manifest_missing",
                                    "A checkpoint manifest is required before committing the source write.",
                                    routing.phase,
                                    "checkpoint_manifest_required",
                                    "Repair checkpoint creation before retrying the source write.",
                                ),
                            )
                            return _result(
                                TaskStatus.INCONSISTENT,
                                step,
                                tuple(tool_calls),
                                observation,
                                state_error,
                                state,
                                risks=(_checkpoint_failure_risk(),),
                            )
                    if not checkpoint_aborted:
                        assert checkpoint is not None
                        try:
                            committed = self._checkpoint_manager.commit(
                                task_id, checkpoint.checkpoint_id
                            )
                        except HanCodeError as exc:
                            state, state_error = self._mark_inconsistent(
                                task_id, state, exc.structured_error
                            )
                            return _result(
                                TaskStatus.INCONSISTENT,
                                step,
                                tuple(tool_calls),
                                observation,
                                state_error,
                                state,
                                risks=(_checkpoint_failure_risk(),),
                            )
                        except Exception:
                            fallback_error = _checkpoint_guard_error(
                                "checkpoint_commit_failed",
                                "Checkpoint could not be committed after the source write.",
                                routing.phase,
                                "checkpoint_commit_required",
                                "Reconcile the source file and checkpoint before continuing.",
                            )
                            state, state_error = self._mark_inconsistent(
                                task_id, state, fallback_error
                            )
                            return _result(
                                TaskStatus.INCONSISTENT,
                                step,
                                tuple(tool_calls),
                                observation,
                                state_error,
                                state,
                                risks=(_checkpoint_failure_risk(),),
                            )
                        if not _is_committed_checkpoint_for(
                            committed,
                            task_id,
                            routing.phase,
                            Path(path),
                            checkpoint.checkpoint_id,
                            pending_checkpoint=checkpoint,
                        ):
                            fallback_error = _checkpoint_guard_error(
                                "checkpoint_manifest_invalid",
                                "Committed checkpoint metadata does not match the source write.",
                                routing.phase,
                                "committed_checkpoint_manifest_required",
                                "Repair the checkpoint manager before continuing.",
                            )
                            state, state_error = self._mark_inconsistent(
                                task_id, state, fallback_error
                            )
                            return _result(
                                TaskStatus.INCONSISTENT,
                                step,
                                tuple(tool_calls),
                                observation,
                                state_error,
                                state,
                                risks=(_checkpoint_failure_risk(),),
                            )
                if (
                    not tool_result.success
                    and action.tool_name in {"write_file", "edit_file"}
                    and tool_result.mutation_applied is not False
                ):
                    state, state_error = self._mark_inconsistent(
                        task_id,
                        state,
                        _mutation_effect_unknown_error(routing.phase),
                        rollback_required=True,
                    )
                    return _result(
                        TaskStatus.INCONSISTENT,
                        step,
                        tuple(tool_calls),
                        observation,
                        state_error,
                        state,
                        risks=(_checkpoint_failure_risk(),),
                    )
                previous_state = state
                state, post_error = self._post_tool_execution(
                    task_id,
                    state,
                    action,
                    tool_result,
                    routing.phase,
                    requires_checkpoint,
                    source_write=source_write,
                )
                if post_error is not None:
                    state, state_error = self._mark_inconsistent(
                        task_id,
                        state,
                        post_error,
                        rollback_required=requires_checkpoint,
                    )
                    return _result(
                        TaskStatus.INCONSISTENT,
                        step,
                        tuple(tool_calls),
                        observation,
                        state_error,
                        state,
                        risks=(_checkpoint_failure_risk(),) if requires_checkpoint else (),
                    )
                if not tool_result.success and self._recovery_coordinator.supports_tool_failure(
                    action, tool_result
                ):
                    recovery = self._recovery_coordinator.record_tool_failure(
                        state=state,
                        action=action,
                        result=tool_result,
                        phase=routing.phase,
                    )
                    state = self._save_if_changed(task_id, state, recovery.state)
                    observation = _attach_memory_reference(
                        recovery.observation, memory_record
                    )
                    trace_error = self._append_trace(
                        task_id,
                        trace_events,
                        event_type="failure_observed",
                        phase=routing.phase,
                        status="failed",
                        action=_trace_action(action, decision, include_path=True),
                        observation={
                            "failure_id": state.active_failure.failure_id
                            if state.active_failure is not None
                            else None,
                            "fingerprint": (
                                state.active_failure.fingerprint
                                if state.active_failure is not None
                                else None
                            ),
                            "error_code": tool_result.error_code,
                        },
                    )
                    if trace_error is not None:
                        pending_risks.append(_trace_failure_risk(trace_error))
                    if recovery.should_block:
                        trace_error = self._append_trace(
                            task_id,
                            trace_events,
                            event_type="recovery_no_progress",
                            phase=routing.phase,
                            status="failed",
                            observation={
                                "failure_id": state.active_failure.failure_id
                                if state.active_failure is not None
                                else None,
                                "repeat_count": (
                                    state.active_failure.repeat_count
                                    if state.active_failure is not None
                                    else None
                                ),
                            },
                        )
                        if trace_error is not None:
                            pending_risks.append(_trace_failure_risk(trace_error))
                        return _result(
                            TaskStatus.BLOCKED,
                            step,
                            tuple(tool_calls),
                            observation,
                            _recovery_no_progress_error(routing.phase),
                            state,
                        )
                    continue
                resolved_state = self._recovery_coordinator.resolve_after_success(
                    state=state, action=action
                )
                if resolved_state != state:
                    state = self._save_if_changed(task_id, state, resolved_state)
                    trace_error = self._append_trace(
                        task_id,
                        trace_events,
                        event_type="failure_resolved",
                        phase=routing.phase,
                        status="succeeded",
                        action=_trace_action(action, decision, include_path=True),
                        observation={"reason": "successful_alternative_action"},
                    )
                    if trace_error is not None:
                        pending_risks.append(_trace_failure_risk(trace_error))
                strategy_error = _test_strategy_error_code(tool_result)
                semantic_test_report = (
                    _feedback_report_for_test_result(tool_result)
                    if action.tool_name == "run_tests" and strategy_error is None
                    else None
                )
                trace_error = self._record_test_result_trace(
                    task_id,
                    trace_events,
                    phase=routing.phase,
                    action=action,
                    decision=decision,
                    tool_result=tool_result,
                    previous_state=previous_state,
                    state=state,
                )
                if trace_error is not None:
                    state, state_error = self._mark_inconsistent(
                        task_id, state, trace_error
                    )
                    return _result(
                        TaskStatus.INCONSISTENT,
                        step,
                        tuple(tool_calls),
                        observation,
                        state_error,
                        state,
                    )
                if (
                    action.tool_name == "run_tests"
                    and self._delivery_pipeline is not None
                    and semantic_test_report is not None
                ):
                    report = semantic_test_report
                    trace_error = self._append_trace(
                        task_id,
                        trace_events,
                        event_type="test_completed",
                        phase=routing.phase,
                        status="succeeded" if report.passed else "failed",
                        action=_trace_action(action, decision, include_path=False),
                        observation={
                            "exit_code": tool_result.exit_code,
                            "timed_out": tool_result.timed_out,
                            "command": (
                                None
                                if tool_result.command is None
                                else redact_text(tool_result.command)
                            ),
                        },
                    )
                    if trace_error is not None:
                        state, state_error = self._mark_inconsistent(
                            task_id, state, trace_error
                        )
                        return _result(
                            TaskStatus.INCONSISTENT,
                            step,
                            tuple(tool_calls),
                            observation,
                            state_error,
                            state,
                        )
                    trace_error = self._append_trace(
                        task_id,
                        trace_events,
                        event_type="feedback_generated",
                        phase=routing.phase,
                        status="succeeded",
                        observation={"failure_category": report.failure_category.value},
                    )
                    if trace_error is not None:
                        state, state_error = self._mark_inconsistent(
                            task_id, state, trace_error
                        )
                        return _result(
                            TaskStatus.INCONSISTENT,
                            step,
                            tuple(tool_calls),
                            observation,
                            state_error,
                            state,
                        )
                    if report.passed and previous_state.latest_test_failure_digest:
                        trace_error = self._append_trace(
                            task_id,
                            trace_events,
                            event_type="test_failure_cleared",
                            phase=routing.phase,
                            status="succeeded",
                            observation={
                                "failure_digest": previous_state.latest_test_failure_digest,
                                "remediation_digest": previous_state.latest_remediation_digest,
                            },
                        )
                        if trace_error is not None:
                            state, state_error = self._mark_inconsistent(
                                task_id, state, trace_error
                            )
                            return _result(
                                TaskStatus.INCONSISTENT,
                                step,
                                tuple(tool_calls),
                                observation,
                                state_error,
                                state,
                            )
                if action.tool_name in {"record_review", "record_knowledge"}:
                    try:
                        state = self._state_store.load(task_id)
                    except Exception:
                        fallback_error = _state_persistence_error(routing.phase)
                        state, state_error = self._mark_inconsistent(
                            task_id, state, fallback_error
                        )
                        return _result(
                            TaskStatus.INCONSISTENT,
                            step,
                            tuple(tool_calls),
                            observation,
                            state_error,
                            state,
                        )
                    if tool_result.success:
                        artifact = (
                            "REVIEW.md"
                            if action.tool_name == "record_review"
                            else "KNOWLEDGE.md"
                        )
                        trace_error = self._append_trace(
                            task_id,
                            trace_events,
                            event_type="deliverable_created",
                            phase=routing.phase,
                            status="succeeded",
                            observation={"artifact": artifact},
                        )
                        if trace_error is not None:
                            state, state_error = self._mark_inconsistent(
                                task_id, state, trace_error
                            )
                            return _result(
                                TaskStatus.INCONSISTENT,
                                step,
                                tuple(tool_calls),
                                observation,
                                state_error,
                                state,
                            )
                if (
                    action.tool_name == "record_review"
                    and tool_result.success
                    and previous_state.phase_completed[Phase.REVIEW.value] is False
                    and state.phase_completed[Phase.REVIEW.value]
                ):
                    trace_error = self._append_trace(
                        task_id,
                        trace_events,
                        event_type="phase_completed",
                        phase=Phase.REVIEW,
                        status="succeeded",
                    )
                    if trace_error is not None:
                        state, state_error = self._mark_inconsistent(
                            task_id, state, trace_error
                        )
                        return _result(
                            TaskStatus.INCONSISTENT,
                            step,
                            tuple(tool_calls),
                            observation,
                            state_error,
                            state,
                        )
                if action.tool_name == "record_remediation" and tool_result.success:
                    trace_error = self._append_trace(
                        task_id,
                        trace_events,
                        event_type="remediation_recorded",
                        phase=routing.phase,
                        status="succeeded",
                        observation={
                            "failure_digest": state.latest_test_failure_digest,
                            "remediation_digest": state.latest_remediation_digest,
                            "decision": (
                                tool_result.output.get("kind")
                                if isinstance(tool_result.output, Mapping)
                                else None
                            ),
                        },
                    )
                    if trace_error is not None:
                        state, state_error = self._mark_inconsistent(
                            task_id, state, trace_error
                        )
                        return _result(
                            TaskStatus.INCONSISTENT,
                            step,
                            tuple(tool_calls),
                            observation,
                            state_error,
                            state,
                        )
                if (
                    not previous_state.remediation_applied
                    and state.remediation_applied
                ):
                    trace_error = self._append_trace(
                        task_id,
                        trace_events,
                        event_type="remediation_applied",
                        phase=routing.phase,
                        status="succeeded",
                        observation={
                            "failure_digest": state.latest_test_failure_digest,
                            "remediation_digest": state.latest_remediation_digest,
                        },
                    )
                    if trace_error is not None:
                        state, state_error = self._mark_inconsistent(
                            task_id, state, trace_error
                        )
                        return _result(
                            TaskStatus.INCONSISTENT,
                            step,
                            tuple(tool_calls),
                            observation,
                            state_error,
                            state,
                        )
                if review_evidence_key is not None and tool_result.success:
                    completed_review_evidence_actions.add(review_evidence_key)
                    review_progress_warning = False
                if (
                    action.tool_name == "run_tests"
                    and semantic_test_report is not None
                    and not semantic_test_report.passed
                ):
                    try:
                        recorded_failure = TestRemediationStore(
                            self._project_root
                        ).load_failure(task_id)
                    except HanCodeError:
                        state, state_error = self._mark_inconsistent(
                            task_id,
                            state,
                            _state_persistence_error(routing.phase),
                        )
                        return _result(
                            TaskStatus.INCONSISTENT,
                            step,
                            tuple(tool_calls),
                            observation,
                            state_error,
                            state,
                        )
                    trace_error = self._append_trace(
                        task_id,
                        trace_events,
                        event_type=(
                            "test_failure_repeated"
                            if recorded_failure.repeat_count > 0
                            else "test_failure_recorded"
                        ),
                        phase=routing.phase,
                        status="failed",
                        observation={
                            "attempt_id": recorded_failure.attempt_id,
                            "failure_digest": recorded_failure.digest,
                            "category": recorded_failure.category.value,
                            "repeat_count": recorded_failure.repeat_count,
                        },
                    )
                    if trace_error is not None:
                        state, state_error = self._mark_inconsistent(
                            task_id, state, trace_error
                        )
                        return _result(
                            TaskStatus.INCONSISTENT,
                            step,
                            tuple(tool_calls),
                            observation,
                            state_error,
                            state,
                        )
                    trace_error = self._append_trace(
                        task_id,
                        trace_events,
                        event_type="test_failed",
                        phase=routing.phase,
                        status="failed",
                        action=_trace_action(action, decision, include_path=False),
                        observation={
                            "action_name": tool_result.action_name,
                            "exit_code": tool_result.exit_code,
                            "timed_out": tool_result.timed_out,
                            "command": (
                                None
                                if tool_result.command is None
                                else redact_text(tool_result.command)
                            ),
                        },
                        error_summary=redact_text(
                            tool_result.error_summary
                            or (
                                "Test command timed out."
                                if tool_result.timed_out
                                else "The registered strategy did not produce passing tests."
                            )
                        ),
                        state_transition={
                            "latest_test_status": [
                                previous_state.latest_test_status,
                                "failed",
                            ]
                        },
                    )
                    if trace_error is not None:
                        state = self._block(task_id, state)
                        return _result(
                            TaskStatus.BLOCKED,
                            step,
                            tuple(tool_calls),
                            observation,
                            trace_error,
                            state,
                        )
                    if recorded_failure.repeat_count >= 2:
                        trace_error = self._append_trace(
                            task_id,
                            trace_events,
                            event_type="remediation_input_required",
                            phase=routing.phase,
                            status="waiting" if self._interaction_enabled else "blocked",
                            observation={
                                "failure_digest": recorded_failure.digest,
                                "repeat_count": recorded_failure.repeat_count,
                            },
                        )
                        if trace_error is not None:
                            state, state_error = self._mark_inconsistent(
                                task_id, state, trace_error
                            )
                            return _result(
                                TaskStatus.INCONSISTENT,
                                step,
                                tuple(tool_calls),
                                observation,
                                state_error,
                                state,
                            )
                        if self._interaction_enabled:
                            no_progress_action = Action(
                                type=ActionType.ASK_USER,
                                phase=routing.phase,
                                tool_name=None,
                                args={
                                    "question": (
                                        "The same test failure remained after two "
                                        "autonomous remediation attempts. What "
                                        "project-specific constraint should be used next?"
                                    )
                                },
                                reason="Autonomous remediation made no progress.",
                            )
                            state, interaction = self._request_user_input(
                                task_id,
                                state,
                                no_progress_action,
                                routing.phase,
                            )
                            return _result(
                                TaskStatus.WAITING_INPUT,
                                step,
                                tuple(tool_calls),
                                {
                                    "interaction_id": interaction.interaction_id,
                                    "question": interaction.question,
                                },
                                None,
                                state,
                            )
                        state = self._block(task_id, state)
                        return _result(
                            TaskStatus.BLOCKED,
                            step,
                            tuple(tool_calls),
                            observation,
                            _test_remediation_no_progress_error(routing.phase),
                            state,
                        )
                if state.retry_budget_remaining < previous_state.retry_budget_remaining:
                    trace_error = self._append_trace(
                        task_id,
                        trace_events,
                        event_type="retry_budget_consumed",
                        phase=routing.phase,
                        status="succeeded",
                        observation={
                            "before": previous_state.retry_budget_remaining,
                            "after": state.retry_budget_remaining,
                        },
                        state_transition={
                            "retry_budget_remaining": [
                                previous_state.retry_budget_remaining,
                                state.retry_budget_remaining,
                            ]
                        },
                    )
                    if trace_error is not None:
                        state, state_error = self._mark_inconsistent(
                            task_id, state, trace_error
                        )
                        return _result(
                            TaskStatus.INCONSISTENT,
                            step,
                            tuple(tool_calls),
                            observation,
                            state_error,
                            state,
                            risks=(_checkpoint_failure_risk(),),
                        )
                self._acknowledge_steering(
                    task_id, steering_snapshot, trace_events, routing.phase
                )
                continue

            if action.type is ActionType.FINISH_PHASE:
                if routing.phase is Phase.DELIVER and self._delivery_pipeline is not None:
                    try:
                        delivery_result = self._delivery_pipeline.finalize(
                            task_path(self._project_root, task_id), task_id
                        )
                    except HanCodeError as exc:
                        # finalize() may have persisted DELIVERABLES.md state
                        # before failing; reload so _block() does not overwrite it.
                        state = self._state_store.load(task_id)
                        state = self._block(task_id, state)
                        return _result(
                            TaskStatus.BLOCKED,
                            step,
                            tuple(tool_calls),
                            observation,
                            exc.structured_error,
                            state,
                        )
                    delivery_status = getattr(delivery_result, "status", None)
                    if delivery_status is not TaskStatus.COMPLETED:
                        blockers = getattr(delivery_result, "blockers", ())
                        # finalize() persisted the delivery summary (DELIVERABLES.md
                        # present, coverage digest) before reporting a blocked gate.
                        # Reload the authoritative state so _block() preserves it
                        # instead of re-saving a stale snapshot.
                        state = self._state_store.load(task_id)
                        state = self._block(task_id, state)
                        return _result(
                            TaskStatus.BLOCKED,
                            step,
                            tuple(tool_calls),
                            observation,
                            _delivery_gate_error(routing.phase, blockers),
                            state,
                        )
                    state = self._state_store.load(task_id)
                    trace_error = self._append_trace(
                        task_id,
                        trace_events,
                        event_type="deliverable_created",
                        phase=routing.phase,
                        status="succeeded",
                        observation={"artifact": "DELIVERABLES.md"},
                    )
                    if trace_error is not None:
                        state, state_error = self._mark_inconsistent(
                            task_id, state, trace_error
                        )
                        return _result(
                            TaskStatus.INCONSISTENT,
                            step,
                            tuple(tool_calls),
                            observation,
                            state_error,
                            state,
                        )
                had_interactions = bool(state.interactions)
                phase_finished_state = _state_after_phase_finish(state, routing.phase)
                phase_finished_state = self._recovery_coordinator.resolve_after_success(
                    state=phase_finished_state, action=action
                )
                state = self._save_if_changed(
                    task_id, state, phase_finished_state
                )
                if had_interactions:
                    trace_error = self._append_trace(
                        task_id,
                        trace_events,
                        event_type="interaction_history_cleared",
                        phase=routing.phase,
                        status="succeeded",
                    )
                    if trace_error is not None:
                        pending_risks.append(_trace_failure_risk(trace_error))
                trace_error = self._append_trace(
                    task_id,
                    trace_events,
                    event_type="phase_completed",
                    phase=routing.phase,
                    status="succeeded",
                )
                if trace_error is not None:
                    pending_risks.append(_trace_failure_risk(trace_error))
                self._acknowledge_steering(
                    task_id, steering_snapshot, trace_events, routing.phase
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
                        error_code="final_not_model_selectable",
                        message=(
                            "Global completion is controlled by the deterministic router."
                        ),
                        phase=routing.phase.value,
                        denied_rule="router_completion_required",
                        suggested_fix=(
                            "Finish the current phase and let the router determine completion."
                        ),
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

        final_routing = select_next_phase(
            state, build_required=self._build_required
        )
        if final_routing.rollback_required:
            state = self._enter_phase(task_id, state, final_routing.phase)
            state, observation, error, status = self._perform_rollback(
                task_id, state, final_routing.phase, trace_events
            )
            return _result(
                status,
                self._max_steps,
                tuple(tool_calls),
                observation,
                error,
                state,
            )

        if final_routing.completed:
            state = self._save_if_changed(
                task_id,
                state,
                replace(
                    state,
                    status=TaskStatus.COMPLETED,
                    current_phase=final_routing.phase,
                ),
            )
            trace_error = self._append_trace(
                task_id,
                trace_events,
                event_type="run_completed",
                phase=final_routing.phase,
                status="succeeded",
            )
            if trace_error is not None:
                pending_risks.append(_trace_failure_risk(trace_error))
            return _result(
                TaskStatus.COMPLETED,
                self._max_steps,
                tuple(tool_calls),
                observation,
                None,
                state,
            )

        if final_routing.blocked:
            status = (
                state.status
                if state.status
                in {TaskStatus.BLOCKED, TaskStatus.FAILED, TaskStatus.INCONSISTENT}
                else TaskStatus.BLOCKED
            )
            state = self._save_if_changed(
                task_id,
                state,
                replace(state, status=status, current_phase=final_routing.phase),
            )
            return _result(
                status,
                self._max_steps,
                tuple(tool_calls),
                observation,
                StructuredError(
                    error_code=final_routing.reason,
                    message="Agent loop reached a blocked routing decision.",
                    phase=final_routing.phase.value,
                    denied_rule=final_routing.reason,
                    suggested_fix="Resolve the routing condition before running the agent loop again.",
                ),
                state,
            )

        max_steps_error = last_recoverable_error or StructuredError(
            error_code="max_steps_exceeded",
            message="Agent loop reached the configured maximum number of steps.",
            phase=routing.phase.value,
            denied_rule="max_steps_limit",
            suggested_fix="Increase max_steps or make the action sequence terminate earlier.",
        )
        trace_error = self._append_trace(
            task_id,
            trace_events,
            event_type="run_blocked",
            phase=routing.phase,
            status="failed",
            observation={"error_code": max_steps_error.error_code},
            error_summary=redact_text(max_steps_error.message),
        )
        if trace_error is not None:
            pending_risks.append(_trace_failure_risk(trace_error))
        state = self._block(task_id, state)
        return _result(
            TaskStatus.BLOCKED,
            self._max_steps,
            tuple(tool_calls),
            observation,
            max_steps_error,
            state,
        )

    def _enter_phase(self, task_id: str, state: TaskState, phase: Phase) -> TaskState:
        phase_changed = state.current_phase is not phase
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
                interactions=() if phase_changed else state.interactions,
                pending_interaction_id=(
                    None if phase_changed else state.pending_interaction_id
                ),
            ),
        )

    def _request_user_input(
        self,
        task_id: str,
        state: TaskState,
        action: Action,
        phase: Phase,
    ) -> tuple[TaskState, InteractionRecord]:
        raw_question = action.args.get("question")
        if not isinstance(raw_question, str) or not raw_question.strip():
            raise HanCodeError(
                StructuredError(
                    error_code="interaction_question_required",
                    message="ASK_USER requires a non-empty question.",
                    phase=phase.value,
                    denied_rule="interaction_question_required",
                    suggested_fix="Provide one precise non-empty question.",
                )
            )
        safe_question = redact_text(raw_question.strip())
        if not safe_question.strip() or safe_question.strip() == "[REDACTED]":
            raise HanCodeError(
                StructuredError(
                    error_code="interaction_question_contains_only_sensitive_content",
                    message="The ASK_USER question contains only sensitive content.",
                    phase=phase.value,
                    denied_rule="interaction_question_safe_required",
                    suggested_fix="Do not include credentials or secrets in ASK_USER questions.",
                )
            )
        interaction = InteractionRecord(
            interaction_id=f"ask-{state.interaction_seq + 1:06d}",
            phase=phase,
            question=safe_question,
            answer=None,
            status=InteractionStatus.WAITING,
        )
        updated = replace(
            state,
            status=TaskStatus.WAITING_INPUT,
            interaction_seq=state.interaction_seq + 1,
            interactions=(*state.interactions, interaction),
            pending_interaction_id=interaction.interaction_id,
        )
        return self._save_if_changed(task_id, state, updated), interaction

    def _block(self, task_id: str, state: TaskState) -> TaskState:
        return self._save_if_changed(task_id, state, replace(state, status=TaskStatus.BLOCKED))

    def _mark_inconsistent(
        self,
        task_id: str,
        state: TaskState,
        fallback_error: StructuredError | None = None,
        *,
        rollback_required: bool = False,
    ) -> tuple[TaskState, StructuredError | None]:
        can_recover_checkpoint = (
            rollback_required
            and _is_valid_checkpoint_id(state.latest_checkpoint)
        )
        inconsistent_state = replace(
            state,
            status=TaskStatus.INCONSISTENT,
            inconsistent=True,
            rollback_required=state.rollback_required or can_recover_checkpoint,
            pending_interaction_id=None,
            pending_approval_id=None,
            interactions=(),
        )
        try:
            self._state_store.save(task_id, inconsistent_state)
        except HanCodeError as exc:
            return inconsistent_state, exc.structured_error
        except Exception:
            return inconsistent_state, _state_persistence_error(state.current_phase)
        return inconsistent_state, fallback_error

    def _checkpoint_reload_failure(
        self,
        task_id: str,
        state: TaskState,
        checkpoint: CheckpointManifest,
        previous_checkpoint_seq: int,
        phase: Phase,
    ) -> tuple[TaskState, StructuredError]:
        recovery_state = replace(
            state,
            latest_checkpoint=checkpoint.checkpoint_id,
            checkpoint_seq=max(state.checkpoint_seq, previous_checkpoint_seq + 1),
            status=TaskStatus.INCONSISTENT,
            inconsistent=True,
        )
        try:
            self._state_store.save(task_id, recovery_state)
        except HanCodeError as exc:
            return recovery_state, exc.structured_error
        except Exception:
            return recovery_state, _state_persistence_error(phase)
        return recovery_state, _checkpoint_guard_error(
            "checkpoint_state_reload_failed",
            "Checkpoint state could not be reloaded after creation.",
            phase,
            "checkpoint_state_reload_required",
            "Reconcile the persisted checkpoint and task state before retrying.",
        )

    def _checkpoint_create_failure(
        self,
        task_id: str,
        state: TaskState,
        phase: Phase,
        error: StructuredError,
    ) -> tuple[TaskState, StructuredError]:
        try:
            current = self._state_store.load(task_id)
        except HanCodeError as exc:
            return replace(state, status=TaskStatus.INCONSISTENT, inconsistent=True), exc.structured_error
        except Exception:
            return replace(state, status=TaskStatus.INCONSISTENT, inconsistent=True), _state_persistence_error(phase)
        if not _is_valid_task_state(current, task_id):
            return replace(state, status=TaskStatus.INCONSISTENT, inconsistent=True), _state_adapter_error(phase)
        inconsistent = replace(current, status=TaskStatus.INCONSISTENT, inconsistent=True)
        try:
            self._state_store.save(task_id, inconsistent)
        except HanCodeError as exc:
            return inconsistent, exc.structured_error
        except Exception:
            return inconsistent, _state_persistence_error(phase)
        return inconsistent, error

    def _perform_rollback(
        self,
        task_id: str,
        state: TaskState,
        phase: Phase,
        trace_events: list[TraceEvent],
    ) -> tuple[TaskState, object | None, StructuredError | None, TaskStatus]:
        return self._perform_rollback_unlocked(task_id, state, phase, trace_events)

    def _perform_rollback_unlocked(
        self,
        task_id: str,
        state: TaskState,
        phase: Phase,
        trace_events: list[TraceEvent],
    ) -> tuple[TaskState, object | None, StructuredError | None, TaskStatus]:
        trace_error = self._append_trace(
            task_id,
            trace_events,
            event_type="rollback_started",
            phase=phase,
            status="running",
            observation={"checkpoint_id": state.latest_checkpoint},
            state_transition={"rollback_required": [state.rollback_required, True]},
        )
        if trace_error is not None:
            return self._rollback_failure(task_id, state, trace_error)
        try:
            rollback = self._rollback_manager.rollback_last(task_id)
        except HanCodeError as exc:
            return self._rollback_exception_failure(
                task_id, state, phase, trace_events, exc.structured_error
            )
        except Exception:
            return self._rollback_exception_failure(
                task_id,
                state,
                phase,
                trace_events,
                StructuredError(
                    error_code="rollback_execution_failed",
                    message="Rollback could not be executed.",
                    phase=phase.value,
                    denied_rule="rollback_execution_required",
                    suggested_fix="Restore checkpoint storage before retrying rollback.",
                ),
            )

        if not _is_valid_rollback_result(rollback, state):
            return self._rollback_invalid_result_failure(
                task_id,
                state,
                phase,
                trace_events,
            )

        observation, feedback_error = self._build_feedback(
            lambda: self._feedback_builder.from_rollback_result(rollback, phase=phase), phase
        )
        if feedback_error is not None:
            return self._rollback_observation_failure(
                task_id, state, phase, trace_events, feedback_error, observation
            )
        if rollback.status is OperationStatus.SUCCEEDED:
            memory_state = state
            try:
                memory_state = self._state_store.load(task_id)
                memory_record = self._memory_store.record_rollback(
                    task_id,
                    phase=phase,
                    result=rollback,
                    observation=observation,
                    state=memory_state,
                )
            except HanCodeError as exc:
                state, state_error = self._mark_inconsistent(
                    task_id, memory_state, exc.structured_error
                )
                return state, observation, state_error, TaskStatus.INCONSISTENT
            except Exception:
                state, state_error = self._mark_inconsistent(
                    task_id,
                    memory_state,
                    _memory_persistence_error(phase),
                )
                return state, observation, state_error, TaskStatus.INCONSISTENT
            observation = _attach_memory_reference(observation, memory_record)
            loaded: TaskState | None = None
            try:
                loaded = self._state_store.load(task_id)
                if not _is_valid_task_state(loaded, task_id):
                    raise HanCodeError(_state_adapter_error(phase))
                if (
                    loaded.task_id != task_id
                    or loaded.inconsistent
                    or loaded.status is TaskStatus.INCONSISTENT
                    or loaded.current_phase is not Phase.REVIEW
                    or not _is_rollback_state_reconciled(loaded)
                ):
                    raise HanCodeError(_rollback_state_error(phase))
                phase_completed = dict(loaded.phase_completed)
                phase_completed.update(
                    {
                        Phase.CODE.value: False,
                        Phase.TEST.value: False,
                        Phase.REVIEW.value: False,
                    }
                )
                updated = self._save_if_changed(
                    task_id,
                    loaded,
                    replace(
                        loaded,
                        current_phase=Phase.REVIEW,
                        status=TaskStatus.RUNNING,
                        latest_test_status="none",
                        test_status_consumed=False,
                        source_edits_this_phase=0,
                        rollback_required=False,
                        rollback_done=True,
                        phase_completed=phase_completed,
                    ),
                )
            except HanCodeError as exc:
                return self._rollback_post_state_failure(
                    task_id, state, phase, trace_events, exc.structured_error, observation
                )
            except Exception:
                return self._rollback_post_state_failure(
                    task_id, state, phase, trace_events, _rollback_state_error(phase), observation
                )
            trace_error = self._append_trace(
                task_id,
                trace_events,
                event_type="rollback_performed",
                phase=phase,
                status="succeeded",
                observation=_rollback_trace_observation(rollback, memory_record),
                state_transition={"rollback_done": [state.rollback_done, True]},
            )
            if trace_error is not None:
                inconsistent = replace(updated, status=TaskStatus.INCONSISTENT, inconsistent=True)
                return self._rollback_state_update(
                    task_id,
                    updated,
                    inconsistent,
                    trace_error,
                    observation,
                )
            return (
                updated,
                observation,
                None,
                TaskStatus.RUNNING,
            )
        trace_error = self._append_trace(
            task_id,
            trace_events,
            event_type="rollback_performed",
            phase=phase,
            status=rollback.status.value,
            observation=_rollback_trace_observation(rollback),
            error_summary=(
                None
                if rollback.error_summary is None
                else redact_text(rollback.error_summary)
            ),
        )
        if trace_error is not None:
            return self._rollback_failure(task_id, state, trace_error)
        return self._rollback_failure(
            task_id,
            state,
            rollback.error
            or StructuredError(
                error_code="rollback_failed",
                message="Rollback did not complete successfully.",
                phase=phase.value,
                denied_rule="rollback_succeeded_required",
                suggested_fix="Inspect the checkpoint and resolve the rollback failure.",
            ),
            observation,
            rollback.status,
        )

    def _rollback_post_state_failure(
        self,
        task_id: str,
        state: TaskState,
        phase: Phase,
        trace_events: list[TraceEvent],
        error: StructuredError,
        observation: object | None,
    ) -> tuple[TaskState, object | None, StructuredError, TaskStatus]:
        trace_error = self._append_trace(
            task_id,
            trace_events,
            event_type="rollback_performed",
            phase=phase,
            status="failed",
            observation={"checkpoint_id": state.latest_checkpoint},
            error_summary=redact_text(error.message),
        )
        final_error = trace_error or error
        try:
            current = self._state_store.load(task_id)
        except HanCodeError as exc:
            return (
                replace(state, status=TaskStatus.INCONSISTENT, inconsistent=True),
                observation,
                exc.structured_error,
                TaskStatus.INCONSISTENT,
            )
        except Exception:
            return (
                replace(state, status=TaskStatus.INCONSISTENT, inconsistent=True),
                observation,
                _state_persistence_error(phase),
                TaskStatus.INCONSISTENT,
            )
        if not _is_valid_task_state(current, task_id):
            return (
                replace(state, status=TaskStatus.INCONSISTENT, inconsistent=True),
                observation,
                _state_adapter_error(phase),
                TaskStatus.INCONSISTENT,
            )
        inconsistent = replace(current, status=TaskStatus.INCONSISTENT, inconsistent=True)
        try:
            self._state_store.save(task_id, inconsistent)
        except HanCodeError as exc:
            return inconsistent, observation, exc.structured_error, TaskStatus.INCONSISTENT
        except Exception:
            return (
                inconsistent,
                observation,
                _state_persistence_error(phase),
                TaskStatus.INCONSISTENT,
            )
        return inconsistent, observation, final_error, TaskStatus.INCONSISTENT

    def _rollback_invalid_result_failure(
        self,
        task_id: str,
        state: TaskState,
        phase: Phase,
        trace_events: list[TraceEvent],
    ) -> tuple[TaskState, object | None, StructuredError, TaskStatus]:
        error = StructuredError(
            error_code="rollback_result_invalid",
            message="Rollback adapter returned a result that violates its protocol.",
            phase=phase.value,
            denied_rule="structured_rollback_result_required",
            suggested_fix="Repair the rollback adapter and reconcile the checkpoint before retrying.",
        )
        trace_error = self._append_trace(
            task_id,
            trace_events,
            event_type="rollback_performed",
            phase=phase,
            status="failed",
            observation={"checkpoint_id": state.latest_checkpoint},
            error_summary=redact_text(error.message),
        )
        if trace_error is not None:
            error = trace_error
        try:
            current = self._state_store.load(task_id)
        except HanCodeError as exc:
            return replace(state, status=TaskStatus.INCONSISTENT, inconsistent=True), None, exc.structured_error, TaskStatus.INCONSISTENT
        except Exception:
            return replace(state, status=TaskStatus.INCONSISTENT, inconsistent=True), None, _state_persistence_error(phase), TaskStatus.INCONSISTENT
        if not _is_valid_task_state(current, task_id):
            return replace(state, status=TaskStatus.INCONSISTENT, inconsistent=True), None, _state_adapter_error(phase), TaskStatus.INCONSISTENT
        inconsistent = replace(
            current,
            status=TaskStatus.INCONSISTENT,
            inconsistent=True,
        )
        try:
            self._state_store.save(task_id, inconsistent)
        except HanCodeError as exc:
            return inconsistent, None, exc.structured_error, TaskStatus.INCONSISTENT
        except Exception:
            return (
                inconsistent,
                None,
                _state_persistence_error(phase),
                TaskStatus.INCONSISTENT,
            )
        return inconsistent, None, error, TaskStatus.INCONSISTENT

    def _rollback_observation_failure(
        self,
        task_id: str,
        state: TaskState,
        phase: Phase,
        trace_events: list[TraceEvent],
        error: StructuredError,
        observation: object | None,
    ) -> tuple[TaskState, object | None, StructuredError, TaskStatus]:
        trace_error = self._append_trace(
            task_id,
            trace_events,
            event_type="rollback_performed",
            phase=phase,
            status="failed",
            observation={"checkpoint_id": state.latest_checkpoint},
            error_summary=redact_text(error.message),
        )
        final_error = trace_error or error
        try:
            current = self._state_store.load(task_id)
        except HanCodeError as exc:
            current = replace(state, status=TaskStatus.INCONSISTENT, inconsistent=True)
            return current, observation, exc.structured_error, TaskStatus.INCONSISTENT
        except Exception:
            current = replace(state, status=TaskStatus.INCONSISTENT, inconsistent=True)
            return current, observation, _state_persistence_error(phase), TaskStatus.INCONSISTENT
        if not _is_valid_task_state(current, task_id):
            return (
                replace(state, status=TaskStatus.INCONSISTENT, inconsistent=True),
                observation,
                _state_adapter_error(phase),
                TaskStatus.INCONSISTENT,
            )
        inconsistent = replace(
            current,
            status=TaskStatus.INCONSISTENT,
            inconsistent=True,
        )
        try:
            self._state_store.save(task_id, inconsistent)
        except HanCodeError as exc:
            return inconsistent, observation, exc.structured_error, TaskStatus.INCONSISTENT
        except Exception:
            return (
                inconsistent,
                observation,
                _state_persistence_error(phase),
                TaskStatus.INCONSISTENT,
            )
        return inconsistent, observation, final_error, TaskStatus.INCONSISTENT

    def _rollback_exception_failure(
        self,
        task_id: str,
        state: TaskState,
        phase: Phase,
        trace_events: list[TraceEvent],
        error: StructuredError,
        observation: object | None = None,
    ) -> tuple[TaskState, object | None, StructuredError, TaskStatus]:
        trace_error = self._append_trace(
            task_id,
            trace_events,
            event_type="rollback_performed",
            phase=phase,
            status="failed",
            observation={
                "checkpoint_id": state.latest_checkpoint,
                "failure_stage": "rollback_execution",
            },
            error_summary=redact_text(error.message),
        )
        return self._rollback_failure(
            task_id,
            state,
            trace_error or error,
            observation,
        )

    def _rollback_failure(
        self,
        task_id: str,
        state: TaskState,
        error: StructuredError,
        observation: object | None = None,
        rollback_status: OperationStatus = OperationStatus.BLOCKED,
    ) -> tuple[TaskState, object | None, StructuredError, TaskStatus]:
        try:
            state = self._state_store.load(task_id)
        except HanCodeError as exc:
            return (
                replace(state, status=TaskStatus.INCONSISTENT, inconsistent=True),
                observation,
                exc.structured_error,
                TaskStatus.INCONSISTENT,
            )
        except Exception:
            return (
                replace(state, status=TaskStatus.INCONSISTENT, inconsistent=True),
                observation,
                _state_persistence_error(state.current_phase),
                TaskStatus.INCONSISTENT,
            )
        if not _is_valid_task_state(state, task_id):
            return (
                _emergency_failure_state(task_id, Phase.REVIEW),
                observation,
                _state_adapter_error(Phase.REVIEW),
                TaskStatus.INCONSISTENT,
            )
        if state.inconsistent or state.status is TaskStatus.INCONSISTENT:
            inconsistent = replace(
                state,
                status=TaskStatus.INCONSISTENT,
                inconsistent=True,
                rollback_required=True,
                rollback_done=False,
            )
            try:
                self._state_store.save(task_id, inconsistent)
            except HanCodeError as exc:
                return inconsistent, observation, exc.structured_error, TaskStatus.INCONSISTENT
            except Exception:
                return (
                    inconsistent,
                    observation,
                    _state_persistence_error(state.current_phase),
                    TaskStatus.INCONSISTENT,
                )
            return inconsistent, observation, error, TaskStatus.INCONSISTENT
        status = TaskStatus.FAILED if rollback_status is OperationStatus.FAILED else TaskStatus.BLOCKED
        updated = replace(
            state,
            status=status,
            rollback_required=True,
            rollback_done=False,
        )
        try:
            saved = self._save_if_changed(task_id, state, updated)
        except HanCodeError as exc:
            inconsistent = replace(updated, status=TaskStatus.INCONSISTENT, inconsistent=True)
            try:
                self._state_store.save(task_id, inconsistent)
            except HanCodeError as persistence_exc:
                return (
                    inconsistent,
                    observation,
                    persistence_exc.structured_error,
                    TaskStatus.INCONSISTENT,
                )
            except Exception:
                return (
                    inconsistent,
                    observation,
                    _state_persistence_error(updated.current_phase),
                    TaskStatus.INCONSISTENT,
                )
            return inconsistent, observation, exc.structured_error, TaskStatus.INCONSISTENT
        except Exception:
            inconsistent = replace(updated, status=TaskStatus.INCONSISTENT, inconsistent=True)
            try:
                self._state_store.save(task_id, inconsistent)
            except HanCodeError as persistence_exc:
                return (
                    inconsistent,
                    observation,
                    persistence_exc.structured_error,
                    TaskStatus.INCONSISTENT,
                )
            except Exception:
                return (
                    inconsistent,
                    observation,
                    _state_persistence_error(updated.current_phase),
                    TaskStatus.INCONSISTENT,
                )
            return (
                inconsistent,
                observation,
                _rollback_state_error(state.current_phase),
                TaskStatus.INCONSISTENT,
            )
        return saved, observation, error, status

    def _rollback_state_update(
        self,
        task_id: str,
        previous: TaskState,
        updated: TaskState,
        error: StructuredError,
        observation: object | None,
    ) -> tuple[TaskState, object | None, StructuredError, TaskStatus]:
        try:
            saved = self._save_if_changed(task_id, previous, updated)
        except HanCodeError as exc:
            inconsistent = replace(updated, status=TaskStatus.INCONSISTENT, inconsistent=True)
            try:
                self._state_store.save(task_id, inconsistent)
            except HanCodeError as persistence_exc:
                return (
                    inconsistent,
                    observation,
                    persistence_exc.structured_error,
                    TaskStatus.INCONSISTENT,
                )
            except Exception:
                return (
                    inconsistent,
                    observation,
                    _state_persistence_error(updated.current_phase),
                    TaskStatus.INCONSISTENT,
                )
            return inconsistent, observation, exc.structured_error, TaskStatus.INCONSISTENT
        except Exception:
            inconsistent = replace(updated, status=TaskStatus.INCONSISTENT, inconsistent=True)
            try:
                self._state_store.save(task_id, inconsistent)
            except HanCodeError as persistence_exc:
                return (
                    inconsistent,
                    observation,
                    persistence_exc.structured_error,
                    TaskStatus.INCONSISTENT,
                )
            except Exception:
                return (
                    inconsistent,
                    observation,
                    _state_persistence_error(updated.current_phase),
                    TaskStatus.INCONSISTENT,
                )
            return (
                inconsistent,
                observation,
                _rollback_state_error(updated.current_phase),
                TaskStatus.INCONSISTENT,
            )
        return saved, observation, error, updated.status

    def _append_trace(
        self,
        task_id: str,
        trace_events: list[TraceEvent],
        *,
        event_type: str,
        phase: Phase,
        status: str,
        action: Mapping[str, object] | None = None,
        observation: Mapping[str, object] | None = None,
        error_summary: str | None = None,
        state_transition: Mapping[str, object] | None = None,
    ) -> StructuredError | None:
        try:
            event = self._trace_appender.append(
                task_id,
                event_type=event_type,
                phase=phase,
                status=status,
                action=action,
                observation=observation,
                error_summary=error_summary,
                state_transition=state_transition,
            )
        except HanCodeError as exc:
            return exc.structured_error
        except Exception:
            return StructuredError(
                error_code="trace_write_failed",
                message="The audit trace could not be persisted.",
                phase=phase.value,
                denied_rule="trace_write_required",
                    suggested_fix="Restore trace storage before continuing with high-risk actions.",
                )
        if trace_events:
            expected_seq = trace_events[-1].seq + 1
        else:
            expected_seq = event.seq if isinstance(event, TraceEvent) else 1
        event_id = event.event_id if isinstance(event, TraceEvent) else None
        event_seq = event.seq if isinstance(event, TraceEvent) else None
        expected_event_id = (
            f"evt-{event_seq:06d}"
            if isinstance(event_seq, int) and not isinstance(event_seq, bool)
            else None
        )
        # Allow event_seq >= expected_seq: other components (e.g. the
        # checkpoint manager) write trace events directly to disk, so the
        # in-memory list can lag by one or more events.  Only reject a
        # strictly *regressing* seq which indicates a genuine appender bug.
        if not _is_valid_trace_event(event, task_id, phase, event_type, status) or (
            event_id != expected_event_id
            or (trace_events and event_seq < expected_seq)
        ):
            return StructuredError(
                error_code="trace_event_invalid",
                message="Trace adapter returned an event that does not match the trace protocol.",
                phase=phase.value,
                denied_rule="structured_trace_event_required",
                suggested_fix="Repair the trace adapter before continuing the task.",
            )
        trace_events.append(event)
        return None

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

    # ---- S3-R3 Approval helpers ----

    def _request_approval(
        self,
        task_id: str,
        state: TaskState,
        action: Action,
        requirement: object,
        phase: Phase,
    ) -> tuple[TaskState, ApprovalRecord]:
        """Build and persist an approval request, transitioning task to WAITING_APPROVAL."""
        builder = self._approval_request_builder
        store = self._approval_store
        # The approval gate only reaches here when both are wired (checked at
        # the call site); assert for the type-checker and fail loudly otherwise.
        assert builder is not None and store is not None

        record = builder.build(
            project_id=self._resolve_project_id(task_id),
            task_id=task_id,
            state=state,
            action=action,
            requirement=requirement,
            project_root=self._resolve_project_root(task_id),
            run_id=state.active_run_id,
            steering_revision_at_request=(
                self._intervention_store.current_revision(task_id)
                if state.active_run_id is not None and self._intervention_store is not None
                else (0 if state.active_run_id is not None else None)
            ),
        )

        updated_state, persisted_record = store.create(task_id, state, record)
        return updated_state, persisted_record

    def _handle_approval_resume(
        self,
        task_id: str,
        state: TaskState,
        trace_events: list[TraceEvent],
    ) -> AgentRunResult | Action | _RejectedApproval | None:
        """Handle WAITING_APPROVAL on resume: AgentRunResult, an Action, or None."""
        if self._approval_store is None:
            error = StructuredError(
                error_code="approval_store_missing",
                message="Task is waiting for approval but no approval store is configured.",
                phase=state.current_phase.value,
                denied_rule="approval_store_required",
                suggested_fix="Configure an approval store to handle approval decisions.",
            )
            return _make_result(
                TaskStatus.INCONSISTENT,
                0,
                (),
                None,
                error,
                _inconsistent(state),
            )

        approval_id = state.pending_approval_id
        if approval_id is None:
            error = StructuredError(
                error_code="approval_state_invalid",
                message="WAITING_APPROVAL state has no pending_approval_id.",
                phase=state.current_phase.value,
                denied_rule="approval_state_invariant",
                suggested_fix="Reconcile the task state.",
            )
            return _make_result(
                TaskStatus.INCONSISTENT,
                0,
                (),
                None,
                error,
                _inconsistent(state),
            )

        try:
            record = self._approval_store.load_pending(task_id, approval_id)
        except HanCodeError as exc:
            return _make_result(
                TaskStatus.INCONSISTENT,
                0,
                (),
                None,
                exc.structured_error,
                _inconsistent(state),
            )

        status = record.status

        binding_issue = self._approval_binding_issue(task_id, state, record)
        if binding_issue is not None:
            if status in (ApprovalStatus.PENDING, ApprovalStatus.APPROVED):
                return self._expire_approval(
                    task_id,
                    state,
                    approval_id,
                    "approval_binding_stale",
                    "The approval binding no longer matches the active run or steering revision.",
                    binding_issue,
                    trace_events,
                )
            if status in (ApprovalStatus.EXECUTING, ApprovalStatus.CONSUMED):
                return self._fail_closed_approval_binding(
                    task_id, state, record, binding_issue, trace_events
                )

        if status == ApprovalStatus.EXPIRED:
            return self._recover_expired_approval(task_id, state, approval_id, trace_events)

        if status == ApprovalStatus.PENDING:
            # Still waiting
            return _make_result(
                TaskStatus.WAITING_APPROVAL,
                0,
                (),
                {"approval_id": approval_id, "status": "pending"},
                None,
                state,
            )

        if status == ApprovalStatus.REJECTED:
            # Clear the pending pointer and feed the decision back to the
            # Provider on this same resume.  Do not expose the action payload
            # or preview: the tool name and a redacted human reason are enough
            # for the Agent to revise its next action safely.
            updated_state = replace(
                state,
                status=TaskStatus.RUNNING,
                pending_approval_id=None,
            )
            try:
                self._state_store.save(task_id, updated_state)
            except HanCodeError as exc:
                return _make_result(
                    TaskStatus.INCONSISTENT,
                    0,
                    (),
                    None,
                    exc.structured_error,
                    _inconsistent(state),
                )

            return _RejectedApproval(
                approval_id=approval_id,
                tool_name=record.action.tool_name or "unknown",
                reason=redact_text(
                    record.rejection_reason or "No rejection reason provided."
                ),
            )

        if status == ApprovalStatus.CONSUMED:
            # Crash after execution completed but before state was cleared.
            # The manifest is authoritative: the write already happened, so
            # just clear the pending pointer and continue — never re-dispatch.
            cleared = replace(
                state, status=TaskStatus.RUNNING, pending_approval_id=None
            )
            try:
                self._state_store.save(task_id, cleared)
            except HanCodeError as exc:
                return _make_result(
                    TaskStatus.INCONSISTENT, 0, (), None, exc.structured_error,
                    _inconsistent(state),
                )
            return None

        if status == ApprovalStatus.EXECUTING:
            # A crash landed mid-execution. We cannot know whether the source
            # write hit disk, so we fail closed to INCONSISTENT rather than
            # risk a duplicate write (design §12: no repeated source write).
            error = StructuredError(
                error_code="approval_execution_interrupted",
                message="Approval execution was interrupted; task needs manual reconciliation.",
                phase=state.current_phase.value,
                denied_rule="approval_execution_atomicity",
                suggested_fix="Inspect the workspace and checkpoint, then rollback or continue manually.",
            )
            interrupted = _inconsistent(state)
            # Persist the fail-closed transition so a later load sees the task
            # is INCONSISTENT, not still waiting — otherwise a naive re-resume
            # would loop back into this same branch forever.
            try:
                self._state_store.save(task_id, interrupted)
            except HanCodeError:
                pass
            return _make_result(
                TaskStatus.INCONSISTENT, 0, (), None, error, interrupted,
            )

        if status == ApprovalStatus.APPROVED:
            # Fail closed if the manifest's action digest no longer matches
            # its signed fields (tamper/corruption).
            if not self._digest_intact(record):
                return self._expire_approval(
                    task_id, state, approval_id,
                    "approval_digest_mismatch",
                    "The approved action manifest failed its integrity check.",
                    "approval_digest_must_match",
                    trace_events,
                )
            # Fail closed if the workspace changed under the approved action.
            if not self._validate_approval_preconditions(state, record):
                return self._expire_approval(
                    task_id, state, approval_id,
                    "approval_stale",
                    "The approved action no longer matches the current workspace.",
                    "approval_preconditions_must_match",
                    trace_events,
                )

            approval_gate = self._approval_commit_gate(
                task_id, state, record, trace_events
            )
            if approval_gate is False:
                return self._expire_approval(
                    task_id,
                    state,
                    approval_id,
                    "approval_steering_changed",
                    "Steering changed before the approved action commit gate.",
                    "approval_commit_replan",
                    trace_events,
                )
            if approval_gate is not True:
                return approval_gate

            # Reconstruct the exact approved action. State stays WAITING_APPROVAL
            # so that a crash before execution re-enters this handler cleanly;
            # _execute_approved_action performs all state/manifest transitions.
            approved_action = Action(
                type=record.action.type,
                phase=record.action.phase,
                tool_name=record.action.tool_name,
                args=dict(record.action.args),
                reason=record.action.reason,
            )
            return approved_action

        # PENDING is handled above; EXPIRED / REJECTED handled below.
        error = StructuredError(
            error_code="approval_state_unexpected",
            message=f"Unexpected approval status on resume: {status}.",
            phase=state.current_phase.value,
            denied_rule="approval_state_invalid",
            suggested_fix="Reconcile the approval state.",
        )
        return _make_result(
            TaskStatus.INCONSISTENT,
            0,
            (),
            None,
            error,
            _inconsistent(state),
        )

    def _expire_approval(
        self,
        task_id: str,
        state: TaskState,
        approval_id: str,
        error_code: str,
        message: str,
        denied_rule: str,
        trace_events: list[TraceEvent],
    ) -> AgentRunResult | None:
        """Expire a stale approval, then let the same run re-plan."""
        if self._approval_store is None:
            return self._fail_closed_approval_binding(
                task_id, state, None, "approval_store_missing", trace_events
            )
        try:
            self._approval_store.mark_expired(task_id, approval_id)
        except HanCodeError as exc:
            return self._fail_closed_approval_transition(task_id, state, exc.structured_error)
        except Exception:
            return self._fail_closed_approval_transition(
                task_id,
                state,
                StructuredError(
                    error_code="approval_expiration_failed",
                    message="The stale approval could not be expired safely.",
                    phase=state.current_phase.value,
                    denied_rule="approval_expiration_required",
                    suggested_fix="Reconcile the approval manifest before resuming.",
                ),
            )
        expired_state = replace(state, status=TaskStatus.RUNNING, pending_approval_id=None)
        try:
            self._state_store.save(task_id, expired_state)
        except Exception:
            return self._fail_closed_approval_transition(
                task_id,
                state,
                StructuredError(
                    error_code="approval_state_sync_failed",
                    message="The expired approval state could not be persisted safely.",
                    phase=state.current_phase.value,
                    denied_rule="approval_state_sync_required",
                    suggested_fix="Reconcile state.json and the approval manifest before resuming.",
                ),
            )
        trace_error = self._append_trace(
            task_id,
            trace_events,
            event_type="approval_expired_by_intervention",
            phase=state.current_phase,
            status="succeeded",
            observation={"approval_id": approval_id, "reason": denied_rule},
        )
        if trace_error is not None:
            return self._fail_closed_approval_transition(task_id, expired_state, trace_error)
        return None

    def _approval_binding_issue(
        self, task_id: str, state: TaskState, record: ApprovalRecord
    ) -> str | None:
        if record.run_id is None or record.steering_revision_at_request is None:
            return "approval_binding_missing"
        if record.run_id != state.active_run_id:
            return "approval_run_id_mismatch"
        if self._intervention_store is None:
            return "approval_steering_store_missing"
        try:
            current_revision = self._intervention_store.current_revision(task_id)
        except Exception:
            return "approval_steering_revision_unavailable"
        if current_revision != record.steering_revision_at_request:
            return "approval_steering_revision_mismatch"
        return None

    def _fail_closed_approval_binding(
        self,
        task_id: str,
        state: TaskState,
        record: ApprovalRecord | None,
        reason: str,
        trace_events: list[TraceEvent],
    ) -> AgentRunResult:
        approval_id = record.approval_id if record is not None else "unknown"
        error = StructuredError(
            error_code="approval_binding_invalid",
            message="Approval binding cannot be verified; execution is blocked.",
            phase=state.current_phase.value,
            denied_rule=reason,
            suggested_fix="Reconcile the approval manifest and active run before resuming.",
        )
        inconsistent = _inconsistent(state)
        try:
            self._state_store.save(task_id, inconsistent)
        except Exception:
            pass
        return _make_result(
            TaskStatus.INCONSISTENT,
            0,
            (),
            {"approval_id": approval_id},
            error,
            inconsistent,
            trace_events=tuple(trace_events),
        )

    def _fail_closed_approval_transition(
        self, task_id: str, state: TaskState, error: StructuredError
    ) -> AgentRunResult:
        inconsistent = _inconsistent(state)
        try:
            self._state_store.save(task_id, inconsistent)
        except Exception:
            pass
        return _make_result(
            TaskStatus.INCONSISTENT, 0, (), None, error, inconsistent
        )

    def _recover_expired_approval(
        self,
        task_id: str,
        state: TaskState,
        approval_id: str,
        trace_events: list[TraceEvent],
    ) -> AgentRunResult | None:
        """Finish cleanup when EXPIRED was persisted before state cleanup."""
        cleared = replace(state, status=TaskStatus.RUNNING, pending_approval_id=None)
        try:
            self._state_store.save(task_id, cleared)
        except Exception:
            return self._fail_closed_approval_transition(
                task_id,
                state,
                StructuredError(
                    error_code="approval_state_sync_failed",
                    message="The expired approval pointer could not be cleared safely.",
                    phase=state.current_phase.value,
                    denied_rule="approval_state_sync_required",
                    suggested_fix="Reconcile state.json and the approval manifest before resuming.",
                ),
            )
        trace_error = self._append_trace(
            task_id,
            trace_events,
            event_type="approval_expired_recovered",
            phase=state.current_phase,
            status="succeeded",
            observation={"approval_id": approval_id},
        )
        if trace_error is not None:
            return self._fail_closed_approval_transition(task_id, cleared, trace_error)
        return None

    def _validate_approval_preconditions(
        self, state: TaskState, record: ApprovalRecord
    ) -> bool:
        """Check that approval preconditions still hold (design §11).

        Fails closed if the phase, task, checkpoint pointers, OR any target
        file's on-disk hash changed since the approval was requested.
        """
        if record.phase is not state.current_phase:
            return False
        if record.task_id != state.task_id:
            return False
        if record.checkpoint_seq_at_request != state.checkpoint_seq:
            return False
        if record.latest_checkpoint_at_request != state.latest_checkpoint:
            return False
        # Target-hash re-check: the workspace must not have changed under the
        # approved action. Any drift (content, existence) invalidates it.
        for target in record.targets:
            full_path = (self._project_root / target.path).resolve()
            current_hash = _hash_file_if_exists(full_path)
            if current_hash != target.before_sha256:
                return False
        return True

    def _approval_commit_gate(
        self,
        task_id: str,
        state: TaskState,
        record: ApprovalRecord,
        trace_events: list[TraceEvent],
    ) -> bool | AgentRunResult:
        """Revalidate steering immediately before an approved action executes."""
        if self._intervention_store is None or record.run_id is None:
            return self._fail_closed_approval_binding(
                task_id, state, record, "approval_commit_binding_missing", trace_events
            )
        revision = record.steering_revision_at_request
        if revision is None:
            return self._fail_closed_approval_binding(
                task_id, state, record, "approval_commit_revision_missing", trace_events
            )
        try:
            result = self._intervention_store.commit_action(
                task_id,
                record.run_id,
                revision,
                (),
                record.action.sha256,
                f"approval:{record.approval_id}:{record.action.sha256}",
                False,
            )
        except HanCodeError as exc:
            return self._fail_closed_approval_transition(
                task_id, state, exc.structured_error
            )
        except Exception:
            return self._fail_closed_approval_transition(
                task_id,
                state,
                StructuredError(
                    error_code="approval_commit_gate_failed",
                    message="The approval commit gate could not be evaluated safely.",
                    phase=state.current_phase.value,
                    denied_rule="approval_commit_gate_required",
                    suggested_fix="Reconcile steering state before resuming.",
                ),
            )
        status = getattr(result, "status", None)
        if status is ActionCommitStatus.REPLAN:
            return False
        if status is ActionCommitStatus.COMMITTED:
            return True
        return self._fail_closed_approval_transition(
            task_id,
            state,
            StructuredError(
                error_code="approval_commit_gate_invalid",
                message="The approval commit gate returned an invalid result.",
                phase=state.current_phase.value,
                denied_rule="approval_commit_result_required",
                suggested_fix="Repair the intervention store before resuming.",
            ),
        )

    def _digest_intact(self, record: ApprovalRecord) -> bool:
        """Recompute the action digest and compare to the persisted one (§10).

        Detects a manifest whose action fields were altered after signing.
        """
        recomputed = compute_action_digest(
            action_type=record.action.type,
            phase=record.action.phase,
            tool_name=record.action.tool_name,
            args=record.action.args,
            reason=record.action.reason,
        )
        return recomputed == record.action.sha256

    def _resolve_project_id(self, task_id: str) -> str:
        """Resolve project ID from workspace."""
        try:
            from hancode.storage.workspace import load_project_metadata
            metadata = load_project_metadata(self._project_root / ".hancode" / "project.json")
            return str(metadata.get("project_id", "unknown"))
        except Exception:
            return "unknown"

    def _resolve_project_root(self, task_id: str) -> Path:
        """Resolve project root path."""
        return self._project_root

    def _post_tool_execution(
        self,
        task_id: str,
        state: TaskState,
        action: Action,
        tool_result: ToolResult,
        phase: Phase,
        requires_checkpoint: bool,
        *,
        source_write: bool,
    ) -> tuple[TaskState, StructuredError | None]:
        """Persist state and delivery evidence after any tool execution."""
        updated_state = _state_after_tool(
            state,
            action,
            tool_result,
            requires_checkpoint,
            source_write=source_write,
        )
        try:
            remediation_store = TestRemediationStore(self._project_root)
            if (
                action.tool_name == "run_tests"
                and _test_strategy_error_code(tool_result) is None
            ):
                report = _feedback_report_for_test_result(tool_result)
                if not report.passed:
                    previous_failure = None
                    diagnostic_rerun_applied = False
                    if (
                        state.latest_test_status != "passed"
                        and state.latest_remediation_digest is not None
                        and state.latest_test_failure_digest is not None
                    ):
                        try:
                            previous_failure = remediation_store.load_failure(task_id)
                            previous_remediation = remediation_store.load_remediation(
                                task_id
                            )
                            diagnostic_rerun_applied = (
                                previous_remediation.failure_digest
                                == previous_failure.digest
                                and previous_remediation.kind
                                is RemediationKind.RERUN_FOR_DIAGNOSIS
                            )
                        except HanCodeError:
                            previous_failure = None
                    command_argv = None
                    if state.test_strategy_digest is not None:
                        try:
                            command_argv = TestStrategyStore(self._project_root).load(
                                task_id
                            ).command_argv
                        except HanCodeError:
                            command_argv = None
                    output = "\n".join(
                        value
                        for value in (
                            tool_result.error_summary,
                            tool_result.stdout,
                            tool_result.stderr,
                        )
                        if isinstance(value, str) and value
                    )
                    failure = build_test_failure_record(
                        task_id=task_id,
                        attempt_seq=state.test_attempt_seq + 1,
                        strategy_digest=state.test_strategy_digest,
                        command_argv=command_argv,
                        category=report.failure_category,
                        exit_code=tool_result.exit_code,
                        timed_out=tool_result.timed_out,
                        passed_count=report.passed_count,
                        failed_count=report.failed_count,
                        output=output,
                        project_root=self._project_root,
                        previous=previous_failure,
                        diagnostic_rerun_applied=diagnostic_rerun_applied,
                    )
                    remediation_store.save_failure(failure)
                    updated_state = replace(
                        updated_state,
                        latest_test_failure_digest=failure.digest,
                        latest_remediation_digest=None,
                        test_attempt_seq=state.test_attempt_seq + 1,
                        remediation_applied=False,
                    )
                else:
                    updated_state = replace(updated_state, remediation_applied=False)

            if action.tool_name == "record_remediation" and tool_result.success:
                remediation = remediation_store.load_remediation(task_id)
                if (
                    remediation.failure_digest != state.latest_test_failure_digest
                    or remediation.task_id != task_id
                ):
                    raise ValueError("stale remediation decision")
                phase_completed = dict(updated_state.phase_completed)
                phase_completed[Phase.REVIEW.value] = False
                if remediation.kind in {
                    RemediationKind.MODIFY_SOURCE,
                    RemediationKind.MODIFY_TEST,
                    RemediationKind.REPLACE_TEST_STRATEGY,
                }:
                    phase_completed[Phase.CODE.value] = False
                    updated_state = replace(
                        updated_state,
                        test_status_consumed=True,
                        test_strategy_digest=(
                            None
                            if remediation.kind
                            in {
                                RemediationKind.MODIFY_TEST,
                                RemediationKind.REPLACE_TEST_STRATEGY,
                            }
                            else updated_state.test_strategy_digest
                        ),
                        latest_remediation_digest=remediation.digest,
                        remediation_applied=False,
                        phase_completed=phase_completed,
                    )
                elif remediation.kind is RemediationKind.RERUN_FOR_DIAGNOSIS:
                    phase_completed[Phase.TEST.value] = False
                    updated_state = replace(
                        updated_state,
                        latest_test_status="none",
                        test_status_consumed=False,
                        latest_remediation_digest=remediation.digest,
                        phase_completed=phase_completed,
                    )
                elif remediation.kind is RemediationKind.REQUEST_INPUT:
                    if not self._interaction_enabled or remediation.question is None:
                        return state, _remediation_input_unavailable_error(phase)
                    interaction = InteractionRecord(
                        interaction_id=f"ask-{state.interaction_seq + 1:06d}",
                        phase=phase,
                        question=remediation.question,
                        answer=None,
                        status=InteractionStatus.WAITING,
                    )
                    updated_state = replace(
                        updated_state,
                        status=TaskStatus.WAITING_INPUT,
                        interaction_seq=state.interaction_seq + 1,
                        interactions=(*state.interactions, interaction),
                        pending_interaction_id=interaction.interaction_id,
                        latest_remediation_digest=remediation.digest,
                        phase_completed=phase_completed,
                    )
                elif remediation.kind is RemediationKind.ROLLBACK:
                    updated_state = replace(
                        updated_state,
                        latest_remediation_digest=remediation.digest,
                        rollback_required=True,
                        phase_completed=phase_completed,
                    )

            if source_write and tool_result.success and state.latest_remediation_digest:
                remediation = remediation_store.load_remediation(task_id)
                path = action.args.get("path")
                try:
                    normalized_path = (
                        normalize_project_relative_path(path)
                        if isinstance(path, str)
                        else None
                    )
                except ValueError:
                    normalized_path = None
                if (
                    not state.remediation_applied
                    and remediation.kind
                    in {RemediationKind.MODIFY_SOURCE, RemediationKind.MODIFY_TEST}
                    and normalized_path in remediation.planned_paths
                ):
                    phase_completed = dict(updated_state.phase_completed)
                    phase_completed[Phase.TEST.value] = False
                    updated_state = replace(
                        updated_state,
                        latest_test_status="none",
                        test_status_consumed=False,
                        remediation_applied=True,
                        retry_budget_remaining=max(
                            0, state.retry_budget_remaining - 1
                        ),
                        test_strategy_digest=(
                            None
                            if remediation.kind is RemediationKind.MODIFY_TEST
                            else updated_state.test_strategy_digest
                        ),
                        phase_completed=phase_completed,
                    )

            if (
                action.tool_name == "record_test_strategy"
                and tool_result.success
                and state.latest_remediation_digest is not None
                and not state.remediation_applied
            ):
                remediation = remediation_store.load_remediation(task_id)
                failure = remediation_store.load_failure(task_id)
                if (
                    remediation.kind is RemediationKind.REPLACE_TEST_STRATEGY
                    and updated_state.test_strategy_digest is not None
                    and updated_state.test_strategy_digest != failure.strategy_digest
                ):
                    updated_state = replace(
                        updated_state,
                        latest_test_status="none",
                        test_status_consumed=False,
                        remediation_applied=True,
                        retry_budget_remaining=max(
                            0, state.retry_budget_remaining - 1
                        ),
                    )
            state = self._save_if_changed(task_id, state, updated_state)
            pipeline = self._delivery_pipeline
            if pipeline is not None:
                task_root = task_path(self._project_root, task_id)
                if (
                    action.tool_name == "run_tests"
                    and _test_strategy_error_code(tool_result) is None
                ):
                    pipeline.record_test(
                        task_root,
                        _feedback_report_for_test_result(tool_result),
                        (
                            redact_text(tool_result.command)
                            if tool_result.command
                            else "run_tests"
                        ),
                    )
                elif action.tool_name == "run_build":
                    pipeline.record_build(
                        task_root,
                        task_id,
                        _build_status_for_tool_result(tool_result),
                    )
                elif action.tool_name == "get_diff" and tool_result.success:
                    diff_evidence = _diff_evidence_from_output(tool_result.output)
                    if diff_evidence is not None:
                        digest, drifted = diff_evidence
                        pipeline.record_diff(
                            task_root,
                            task_id,
                            digest,
                            drifted=drifted,
                        )
                state = self._state_store.load(task_id)
        except HanCodeError as exc:
            return state, exc.structured_error
        except Exception:
            return state, _state_persistence_error(phase)
        return state, None

    def _record_test_result_trace(
        self,
        task_id: str,
        trace_events: list[TraceEvent],
        *,
        phase: Phase,
        action: Action,
        decision: PolicyDecisionLike,
        tool_result: ToolResult,
        previous_state: TaskState,
        state: TaskState,
    ) -> StructuredError | None:
        if action.tool_name != "run_tests":
            return None
        strategy_error = _test_strategy_error_code(tool_result)
        if strategy_error is not None:
            return self._append_trace(
                task_id,
                trace_events,
                event_type="test_strategy_invalid",
                phase=phase,
                status="failed",
                action=_trace_action(action, decision, include_path=False),
                observation={
                    "error_code": strategy_error,
                    "next_phase": Phase.CODE.value,
                },
                state_transition={
                    "test_strategy_digest": [
                        previous_state.test_strategy_digest,
                        None,
                    ]
                },
            )

        return self._append_trace(
            task_id,
            trace_events,
            event_type="test_result_recorded",
            phase=phase,
            status="succeeded",
            action=_trace_action(action, decision, include_path=False),
            observation={
                "command": (
                    None
                    if tool_result.command is None
                    else redact_text(tool_result.command)
                ),
                "test_status": state.latest_test_status,
                "test_report_written": state.artifacts.get("TEST_REPORT.md", False),
            },
            state_transition={
                "status": [previous_state.status.value, state.status.value],
                "latest_test_status": [
                    previous_state.latest_test_status,
                    state.latest_test_status,
                ],
                "phase_completed.test": [
                    previous_state.phase_completed.get(Phase.TEST.value, False),
                    state.phase_completed.get(Phase.TEST.value, False),
                ],
                "artifacts.TEST_REPORT.md": [
                    previous_state.artifacts.get("TEST_REPORT.md", False),
                    state.artifacts.get("TEST_REPORT.md", False),
                ],
            },
        )

    def _execute_approved_action(
        self,
        task_id: str,
        state: TaskState,
        action: Action,
        decision: PolicyDecisionLike,
        phase: Phase,
        trace_events: list[TraceEvent],
    ) -> AgentRunResult:
        """Execute an approved action directly (no Provider call)."""
        tool_calls: list[str] = []
        source_write = _is_source_write_action(action, decision, task_id)

        if action.tool_name in {"write_file", "edit_file"}:
            try:
                self._memory_store.ensure_capacity(
                    task_id,
                    reserved_bytes=_MEMORY_INVALIDATION_RESERVATION_BYTES,
                )
            except HanCodeError as exc:
                state = self._block(task_id, state)
                return _make_result(
                    TaskStatus.BLOCKED, 0, (), None, exc.structured_error, state
                )
            except Exception:
                state = self._block(task_id, state)
                return _make_result(
                    TaskStatus.BLOCKED,
                    0,
                    (),
                    None,
                    _memory_persistence_error(phase),
                    state,
                )

        # Trace
        trace_error = self._append_trace(
            task_id,
            trace_events,
            event_type="approval_execution_started",
            phase=phase,
            status="running",
            action=_trace_action(action, decision, include_path=True),
            observation={"tool_name": action.tool_name},
        )
        if trace_error is not None:
            state = self._block(task_id, state)
            return _make_result(
                TaskStatus.BLOCKED,
                0,
                (),
                None,
                trace_error,
                state,
            )

        approval_id = state.pending_approval_id
        checkpoint: CheckpointManifest | None = None
        requires_checkpoint = decision.requires_checkpoint or source_write
        if requires_checkpoint:
            # Create the guarding checkpoint. Never swallow failure: a source
            # write without a committed checkpoint is unrecoverable (§3.3).
            path_value = action.args.get("path")
            if not isinstance(path_value, str) or not path_value.strip():
                state, state_error = self._mark_inconsistent(
                    task_id, state, _checkpoint_guard_error(
                        "action_schema_invalid",
                        "Approved write action is missing a valid path.",
                        phase, "structured_action_required",
                        "Reconcile the approval manifest.",
                    ),
                )
                return _make_result(
                    TaskStatus.INCONSISTENT, 0, tuple(tool_calls), None,
                    state_error, state, risks=(_checkpoint_failure_risk(),),
                )
            try:
                checkpoint = self._checkpoint_manager.create(
                    task_id, [Path(path_value)], action.reason or "approved action"
                )
            except Exception as exc:
                state, state_error = self._checkpoint_create_failure(
                    task_id, state, phase,
                    _agent_loop_error(phase, exc),
                )
                return _make_result(
                    TaskStatus.INCONSISTENT, 0, tuple(tool_calls), None,
                    state_error, state, risks=(_checkpoint_failure_risk(),),
                )
            # Reload state because checkpoint creation advances the pointer.
            state = self._state_store.load(task_id)
            _sync_trace_events_from_storage(
                task_path(self._project_root, task_id), trace_events
            )

        # Mark every approved action EXECUTING before dispatch, including
        # actions that do not require a checkpoint.
        if approval_id is not None and self._approval_store is not None:
            try:
                self._approval_store.mark_executing(
                    task_id,
                    approval_id,
                    expected_checkpoint_id=(
                        checkpoint.checkpoint_id if checkpoint is not None else None
                    ),
                )
            except Exception as exc:
                state, state_error = self._mark_inconsistent(
                    task_id, state, _agent_loop_error(phase, exc)
                )
                return _make_result(
                    TaskStatus.INCONSISTENT,
                    0,
                    tuple(tool_calls),
                    None,
                    state_error,
                    state,
                    risks=(_checkpoint_failure_risk(),) if requires_checkpoint else (),
                )

        # Dispatch the approved tool (no Provider call).
        try:
            tool_result = self._tool_registry.dispatch(action)
        except Exception as exc:
            if checkpoint is not None:
                self._abort_checkpoint_quietly(task_id, checkpoint)
            state, state_error = self._mark_inconsistent(
                task_id, state, StructuredError(
                    error_code="approved_action_dispatch_failed",
                    message=f"Failed to execute approved action: {exc}.",
                    phase=phase.value,
                    denied_rule="approved_action_dispatch",
                    suggested_fix="Check the tool registry and retry.",
                ),
            )
            return _make_result(
                TaskStatus.INCONSISTENT, 1, tuple(tool_calls), None,
                state_error, state,
                risks=(_checkpoint_failure_risk(),) if requires_checkpoint else (),
            )

        tool_calls.append(action.tool_name or "unknown")

        if not _is_valid_tool_result(tool_result, action):
            if checkpoint is not None:
                self._abort_checkpoint_quietly(task_id, checkpoint)
            state, state_error = self._mark_inconsistent(
                task_id,
                state,
                _checkpoint_guard_error(
                    "tool_result_invalid",
                    "Tool dispatch returned a result that does not match the tool protocol.",
                    phase,
                    "structured_tool_result_required",
                    "Repair the tool adapter so it returns a validated ToolResult.",
                ),
                rollback_required=requires_checkpoint,
            )
            return _make_result(
                TaskStatus.INCONSISTENT,
                1,
                tuple(tool_calls),
                None,
                state_error,
                state,
                risks=(_checkpoint_failure_risk(),) if requires_checkpoint else (),
            )

        observation, feedback_error = self._build_feedback(
            lambda: self._feedback_builder.from_tool_result(tool_result, phase=phase),
            phase,
        )
        if feedback_error is not None:
            state, state_error = self._mark_inconsistent(
                task_id,
                state,
                feedback_error,
                rollback_required=requires_checkpoint,
            )
            return _make_result(
                TaskStatus.INCONSISTENT,
                1,
                tuple(tool_calls),
                observation,
                state_error,
                state,
            )
        try:
            memory_record = self._memory_store.record_tool_result(
                task_id,
                phase=phase,
                action=action,
                result=tool_result,
                observation=observation,
                state=state,
            )
        except HanCodeError as exc:
            state, state_error = self._mark_inconsistent(
                task_id,
                state,
                exc.structured_error,
                rollback_required=requires_checkpoint,
            )
            return _make_result(
                TaskStatus.INCONSISTENT,
                1,
                tuple(tool_calls),
                observation,
                state_error,
                state,
            )
        except Exception:
            state, state_error = self._mark_inconsistent(
                task_id,
                state,
                _memory_persistence_error(phase),
                rollback_required=requires_checkpoint,
            )
            return _make_result(
                TaskStatus.INCONSISTENT,
                1,
                tuple(tool_calls),
                observation,
                state_error,
                state,
            )
        observation = _attach_memory_reference(observation, memory_record)

        # Trace completion
        tool_event_type = "tool_completed" if tool_result.success else "tool_failed"
        tool_event_status = "succeeded" if tool_result.success else "failed"
        trace_error = self._append_trace(
            task_id,
            trace_events,
            event_type=tool_event_type,
            phase=phase,
            status=tool_event_status,
            action=_trace_action(action, decision, include_path=True),
            observation=_tool_trace_observation(tool_result, memory_record),
            error_summary=(
                None
                if tool_result.success
                else redact_text(_tool_error_summary(tool_result))
            ),
        )
        if trace_error is not None:
            state, state_error = self._mark_inconsistent(task_id, state, trace_error)
            return _make_result(
                TaskStatus.INCONSISTENT,
                1,
                tuple(tool_calls),
                None,
                state_error,
                state,
            )

        if not tool_result.success:
            # The approved tool ran but reported failure. Abort the pending
            # checkpoint (no mutation to keep) and consume the approval so it
            # cannot be replayed, then surface feedback to the loop.
            if checkpoint is not None:
                self._abort_checkpoint_quietly(task_id, checkpoint)
            if (
                action.tool_name in {"write_file", "edit_file"}
                and tool_result.mutation_applied is not False
            ):
                state, state_error = self._mark_inconsistent(
                    task_id,
                    state,
                    _mutation_effect_unknown_error(phase),
                    rollback_required=True,
                )
                return _make_result(
                    TaskStatus.INCONSISTENT,
                    1,
                    tuple(tool_calls),
                    None,
                    state_error,
                    state,
                    risks=(_checkpoint_failure_risk(),),
                )
            previous_state = state
            state, post_error = self._post_tool_execution(
                task_id,
                state,
                action,
                tool_result,
                phase,
                requires_checkpoint,
                source_write=source_write,
            )
            if post_error is not None:
                state, state_error = self._mark_inconsistent(
                    task_id,
                    state,
                    post_error,
                    rollback_required=requires_checkpoint,
                )
                return _make_result(
                    TaskStatus.INCONSISTENT,
                    1,
                    tuple(tool_calls),
                    None,
                    state_error,
                    state,
                )
            trace_error = self._record_test_result_trace(
                task_id,
                trace_events,
                phase=phase,
                action=action,
                decision=decision,
                tool_result=tool_result,
                previous_state=previous_state,
                state=state,
            )
            if trace_error is not None:
                state, state_error = self._mark_inconsistent(
                    task_id, state, trace_error
                )
                return _make_result(
                    TaskStatus.INCONSISTENT,
                    1,
                    tuple(tool_calls),
                    None,
                    state_error,
                    state,
                )
            self._consume_and_clear(task_id, state, approval_id, None)
            reloaded = self._state_store.load(task_id)
            return _make_result(
                reloaded.status, 1, tuple(tool_calls), observation, None, reloaded
            )

        # Success: commit the guarding checkpoint before recording state.
        commit_id = checkpoint.checkpoint_id if checkpoint is not None else None
        if checkpoint is not None:
            try:
                self._checkpoint_manager.commit(task_id, checkpoint.checkpoint_id)
            except Exception as exc:
                state, state_error = self._mark_inconsistent(
                    task_id, state, _agent_loop_error(phase, exc),
                    rollback_required=True,
                )
                return _make_result(
                    TaskStatus.INCONSISTENT, 1, tuple(tool_calls), None,
                    state_error, state, risks=(_checkpoint_failure_risk(),),
                )

            _sync_trace_events_from_storage(
                task_path(self._project_root, task_id), trace_events
            )

        previous_state = state
        state, post_error = self._post_tool_execution(
            task_id,
            state,
            action,
            tool_result,
            phase,
            requires_checkpoint,
            source_write=source_write,
        )
        if post_error is not None:
            state, state_error = self._mark_inconsistent(
                task_id,
                state,
                post_error,
                rollback_required=requires_checkpoint,
            )
            return _make_result(
                TaskStatus.INCONSISTENT,
                1,
                tuple(tool_calls),
                None,
                state_error,
                state,
            )
        trace_error = self._record_test_result_trace(
            task_id,
            trace_events,
            phase=phase,
            action=action,
            decision=decision,
            tool_result=tool_result,
            previous_state=previous_state,
            state=state,
        )
        if trace_error is not None:
            state, state_error = self._mark_inconsistent(
                task_id, state, trace_error
            )
            return _make_result(
                TaskStatus.INCONSISTENT,
                1,
                tuple(tool_calls),
                None,
                state_error,
                state,
            )

        resolved_state = self._recovery_coordinator.resolve_after_success(
            state=state, action=action
        )
        if resolved_state != state:
            state = self._save_if_changed(task_id, state, resolved_state)
            self._append_trace(
                task_id,
                trace_events,
                event_type="failure_resolved",
                phase=phase,
                status="succeeded",
                action=_trace_action(action, decision, include_path=True),
                observation={"reason": "approved_action_succeeded"},
            )

        # Consume the approval (authoritative marker) BEFORE clearing state, so
        # a crash in between leaves a CONSUMED manifest the resume path honours.
        state = self._consume_and_clear(task_id, state, approval_id, commit_id)

        self._append_trace(
            task_id, trace_events, event_type="approval_consumed",
            phase=phase, status="succeeded",
            observation={"tool_name": action.tool_name},
        )
        return _make_result(
            state.status, 1, tuple(tool_calls),
            observation,
            None, state,
        )

    def _consume_and_clear(
        self,
        task_id: str,
        state: TaskState,
        approval_id: str | None,
        commit_id: str | None,
    ) -> TaskState:
        """Mark the manifest CONSUMED, then clear the pending pointer + reset."""
        if approval_id is not None and self._approval_store is not None:
            try:
                self._approval_store.mark_consumed(
                    task_id, approval_id, execution_checkpoint_id=commit_id
                )
            except HanCodeError:
                raise
            except Exception as exc:
                raise HanCodeError(
                    StructuredError(
                        error_code="approval_state_sync_failed",
                        message=(
                            "The approved action executed, but the approval "
                            "manifest could not be marked consumed."
                        ),
                        phase=state.current_phase.value,
                        denied_rule="approval_state_sync_required",
                        suggested_fix=(
                            "Reconcile the approval manifest before resuming."
                        ),
                    )
                ) from exc
        try:
            latest = self._state_store.load(task_id)
        except HanCodeError:
            raise
        except Exception as exc:
            raise HanCodeError(
                StructuredError(
                    error_code="approval_state_sync_failed",
                    message=(
                        "The approved action executed, but the task approval "
                        "state could not be loaded for synchronization."
                    ),
                    phase=state.current_phase.value,
                    denied_rule="approval_state_sync_required",
                    suggested_fix=(
                        "Reconcile state.json and the approval manifest before resuming."
                    ),
                )
            ) from exc
        cleared = replace(
            latest, status=TaskStatus.RUNNING, pending_approval_id=None
        )
        try:
            self._state_store.save(task_id, cleared)
        except HanCodeError:
            raise
        except Exception as exc:
            raise HanCodeError(
                StructuredError(
                    error_code="approval_state_sync_failed",
                    message=(
                        "The approved action executed, but the task approval state "
                        "could not be synchronized."
                    ),
                    phase=state.current_phase.value,
                    denied_rule="approval_state_sync_required",
                    suggested_fix=(
                        "Reconcile state.json and the approval manifest before resuming."
                    ),
                )
            ) from exc
        return cleared

    def _abort_checkpoint_quietly(
        self, task_id: str, checkpoint: CheckpointManifest
    ) -> None:
        """Best-effort abort of a pending checkpoint without restoring files."""
        try:
            self._checkpoint_manager.abort(
                task_id, checkpoint.checkpoint_id, restore_files=False
            )
        except Exception:
            pass

    def _abort_checkpoint_after_no_mutation_failure(
        self,
        task_id: str,
        state: TaskState,
        checkpoint: CheckpointManifest | None,
        phase: Phase,
        path: str,
    ) -> tuple[TaskState, StructuredError | None]:
        """Abort a pending checkpoint before blocking a known no-op write."""
        if checkpoint is None:
            return state, _checkpoint_guard_error(
                "checkpoint_manifest_missing",
                "A checkpoint manifest is required before aborting the source write.",
                phase,
                "checkpoint_manifest_required",
                "Repair checkpoint creation before retrying the source write.",
            )
        try:
            aborted = self._checkpoint_manager.abort(
                task_id, checkpoint.checkpoint_id, restore_files=False
            )
        except HanCodeError as exc:
            return state, exc.structured_error
        except Exception:
            return state, _checkpoint_guard_error(
                "pending_checkpoint_abort_failed",
                "Pending checkpoint could not be safely aborted.",
                phase,
                "pending_checkpoint_abort_persistence_required",
                "Repair checkpoint storage before retrying the source write.",
            )
        if not _is_aborted_checkpoint_for(
            aborted, task_id, phase, Path(path), checkpoint.checkpoint_id
        ):
            return state, _checkpoint_guard_error(
                "checkpoint_manifest_invalid",
                "Checkpoint manager returned an invalid aborted manifest.",
                phase,
                "aborted_checkpoint_manifest_required",
                "Repair checkpoint abort persistence before retrying the source write.",
            )
        try:
            reloaded = self._state_store.load(task_id)
        except HanCodeError as exc:
            return state, exc.structured_error
        except Exception:
            return state, _state_persistence_error(phase)
        if not _is_valid_task_state(reloaded, task_id):
            return state, _checkpoint_guard_error(
                "checkpoint_state_invalid",
                "Task state is invalid after aborting the pending checkpoint.",
                phase,
                "consistent_checkpoint_state_required",
                "Reconcile task state before retrying the source write.",
            )
        return reloaded, None


def _sync_trace_events_from_storage(
    task_root: Path, trace_events: list[TraceEvent]
) -> None:
    """Include checkpoint-manager events emitted outside AgentLoop's list."""
    try:
        lines = (task_root / "trace.jsonl").read_text(encoding="utf-8").splitlines()
        last_seq = trace_events[-1].seq if trace_events else 0
        for line in lines:
            payload = json.loads(line)
            sequence = int(payload["seq"])
            if sequence <= last_seq:
                continue
            trace_events.append(
                TraceEvent(
                    event_id=str(payload["event_id"]),
                    seq=sequence,
                    event_type=str(payload["event_type"]),
                    task_id=str(payload["task_id"]),
                    phase=Phase(str(payload["phase"])),
                    timestamp=datetime.fromisoformat(str(payload["timestamp"])),
                    status=str(payload["status"]),
                    action=payload.get("action"),
                    observation=payload.get("observation"),
                    error_summary=payload.get("error_summary"),
                    state_transition=payload.get("state_transition"),
                )
            )
            last_seq = sequence
    except (OSError, UnicodeError, TypeError, ValueError, KeyError, json.JSONDecodeError):
        return


def _inconsistent(state: TaskState) -> TaskState:
    """Build an INCONSISTENT state that satisfies the state invariant.

    A non-WAITING task must not carry pending interaction/approval pointers
    (see TaskState.__post_init__). Transitioning to INCONSISTENT from a
    WAITING_APPROVAL state therefore has to clear both pointers, or the very
    next load() would raise on the invariant. This mirrors the fix applied to
    reconcile_state and keeps the recovered task loadable.
    """
    return replace(
        state,
        status=TaskStatus.INCONSISTENT,
        inconsistent=True,
        pending_approval_id=None,
        pending_interaction_id=None,
    )


def _make_result(
    status: TaskStatus,
    steps: int,
    tool_calls: tuple[str, ...],
    observation: object | None,
    error: StructuredError | None,
    final_state: TaskState,
    *,
    risks: tuple[Risk, ...] = (),
    trace_events: tuple[TraceEvent, ...] = (),
) -> AgentRunResult:
    return AgentRunResult(
        status=status,
        steps=steps,
        tool_calls=tool_calls,
        risks=risks,
        final_observation=observation,
        error=_safe_structured_error(error),
        final_state=final_state,
        retry_budget_remaining=final_state.retry_budget_remaining,
        trace_events=trace_events,
    )


def _answered_pending_interaction(state: TaskState) -> InteractionRecord | None:
    if state.pending_interaction_id is None:
        return None
    for interaction in state.interactions:
        if (
            interaction.interaction_id == state.pending_interaction_id
            and interaction.status is InteractionStatus.ANSWERED
        ):
            return interaction
    return None


def _pending_interaction_observation(state: TaskState) -> dict[str, object] | None:
    if state.pending_interaction_id is None:
        return None
    for interaction in state.interactions:
        if interaction.interaction_id == state.pending_interaction_id:
            return {
                "interaction_id": interaction.interaction_id,
                "question": interaction.question,
            }
    return None


def _safe_structured_error(error: StructuredError | None) -> StructuredError | None:
    if error is None:
        return None
    if not isinstance(error, StructuredError):
        return StructuredError(
            error_code="agent_error_unstructured",
            message="Agent loop received an invalid structured error.",
            phase="unknown",
            denied_rule="structured_error_required",
            suggested_fix="Repair the failing adapter so it returns StructuredError.",
        )

    def _safe_text(value: object, fallback: str) -> str:
        if not isinstance(value, str):
            return fallback
        return redact_text(value)

    return replace(
        error,
        error_code=_safe_text(error.error_code, "agent_error"),
        message=_safe_text(error.message, "Agent loop failed."),
        phase=_safe_text(error.phase, "unknown"),
        denied_rule=(
            None
            if error.denied_rule is None
            else _safe_text(error.denied_rule, "structured_error_rule_invalid")
        ),
        suggested_fix=_safe_text(
            error.suggested_fix,
            "Repair the structured error before retrying the task.",
        ),
    )


def _observation_for_context(observation: object) -> object:
    to_dict = getattr(observation, "to_dict", None)
    if not callable(to_dict):
        return observation
    try:
        converted = to_dict()
    except Exception as exc:
        raise HanCodeError(
            StructuredError(
                error_code="context_observation_invalid",
                message="Feedback observation could not be converted for the LLM context.",
                phase="unknown",
                denied_rule="context_observation_json_safe",
                suggested_fix="Repair the feedback observation before retrying the task.",
            )
        ) from exc
    if not isinstance(converted, Mapping):
        raise HanCodeError(
            StructuredError(
                error_code="context_observation_invalid",
                message="Feedback observation must expose a mapping representation.",
                phase="unknown",
                denied_rule="context_observation_json_safe",
                suggested_fix="Repair the feedback observation before retrying the task.",
            )
        )
    return _context_value(converted)


def _context_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _context_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_context_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return [_context_value(item) for item in sorted(value, key=repr)]
    return value


def _emergency_failure_state(task_id: str, phase: Phase) -> TaskState:
    safe_task_id = task_id if isinstance(task_id, str) and task_id else "unknown-task"
    return TaskState(
        schema_version=1,
        task_id=safe_task_id,
        goal=None,
        status=TaskStatus.INCONSISTENT,
        current_phase=phase,
        files_changed=(),
        latest_checkpoint=None,
        checkpoint_seq=0,
        tests_run=(),
        latest_test_status="none",
        test_status_consumed=False,
        retry_budget_remaining=0,
        inconsistent=True,
        source_edits_this_phase=0,
        rollback_required=False,
        rollback_done=False,
        phase_completed={phase_name.value: False for phase_name in Phase},
        artifacts={
            "SPEC.md": False,
            "PLAN.md": False,
            "TEST_REPORT.md": False,
            "REVIEW.md": False,
            "KNOWLEDGE.md": False,
            "DELIVERABLES.md": False,
        },
    )


def _agent_loop_error(phase: Phase, exception: Exception) -> StructuredError:
    del exception
    return StructuredError(
        error_code="agent_loop_failed",
        message="The agent loop failed before it could produce a structured result.",
        phase=phase.value,
        denied_rule="agent_loop_error_structured",
        suggested_fix="Inspect the affected adapter and restore the task before retrying.",
    )


def _resume_state_error(phase: Phase) -> StructuredError:
    return StructuredError(
        error_code="task_resume_not_allowed",
        message="The task cannot be resumed from its current terminal state.",
        phase=phase.value,
        denied_rule="explicit_resume_recovery_required",
        suggested_fix="Reconcile the inconsistent or failed task state before retrying.",
    )


def _structured_parse_error(error: ParseError) -> StructuredError:
    return StructuredError(
        error_code=redact_text(error.error_code),
        message=redact_text(error.message),
        phase=redact_text(error.phase),
        denied_rule=None if error.denied_rule is None else redact_text(error.denied_rule),
        suggested_fix=redact_text(error.suggested_fix),
    )


def _checkpoint_guard_error(
    error_code: str,
    message: str,
    phase: Phase,
    denied_rule: str,
    suggested_fix: str,
) -> StructuredError:
    return StructuredError(
        error_code=error_code,
        message=message,
        phase=phase.value,
        denied_rule=denied_rule,
        suggested_fix=suggested_fix,
    )


def _checkpoint_failure_risk() -> Risk:
    return Risk(
        level="high",
        message="A checkpointed source write may not be recoverable automatically.",
        mitigation="Reconcile the source file and checkpoint before continuing.",
    )


def _trace_failure_risk(error: StructuredError) -> Risk:
    return Risk(
        level="medium",
        message="The audit trace could not be persisted for a non-mutating loop event.",
        mitigation=redact_text(error.suggested_fix),
    )


def _rollback_trace_observation(
    rollback: RollbackResult, memory_record: object | None = None
) -> dict[str, object]:
    observation: dict[str, object] = {
        "checkpoint_id": rollback.checkpoint_id,
        "restored_files": list(rollback.restored_files),
        "failed_files": list(rollback.failed_files),
    }
    if memory_record is not None:
        observation.update(
            {
                "memory_id": getattr(memory_record, "memory_id", None),
                "content_sha256": getattr(memory_record, "content_sha256", None),
                "blob_bytes": getattr(memory_record, "blob_bytes", None),
                "workspace_generation": getattr(
                    memory_record, "workspace_generation", None
                ),
                "invalidation_reason": "rollback",
            }
        )
    return observation


def _is_valid_rollback_result(result: object, state: TaskState) -> bool:
    if not isinstance(result, RollbackResult):
        return False
    if not isinstance(result.status, OperationStatus):
        return False
    if (
        not _is_valid_checkpoint_id(state.latest_checkpoint)
        or result.checkpoint_id != state.latest_checkpoint
    ):
        return False
    if not isinstance(result.restored_files, tuple) or not all(
        _is_safe_relative_path(path) for path in result.restored_files
    ):
        return False
    if not isinstance(result.failed_files, tuple) or not all(
        _is_safe_relative_path(path) for path in result.failed_files
    ):
        return False
    if (
        len(set(result.restored_files)) != len(result.restored_files)
        or len(set(result.failed_files)) != len(result.failed_files)
        or set(result.restored_files).intersection(result.failed_files)
    ):
        return False
    if result.error is not None and not isinstance(result.error, StructuredError):
        return False
    if result.status is OperationStatus.SUCCEEDED:
        return result.error is None and not result.failed_files and bool(result.restored_files)
    return result.error is not None


def _is_rollback_state_reconciled(state: TaskState) -> bool:
    return (
        state.rollback_required is False
        and state.rollback_done is True
        and state.latest_test_status == "none"
        and state.test_status_consumed is False
        and state.source_edits_this_phase == 0
        and state.phase_completed[Phase.CODE.value] is False
        and state.phase_completed[Phase.TEST.value] is False
        and state.phase_completed[Phase.REVIEW.value] is False
    )


def _is_safe_relative_path(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    normalized = value.replace("\\", "/")
    path = Path(normalized)
    return (
        not path.is_absolute()
        and path.as_posix() == normalized
        and all(part not in {"", ".", ".."} for part in path.parts)
    )


def _is_valid_task_state(state: object, task_id: str) -> bool:
    return (
        isinstance(state, TaskState)
        and state.task_id == task_id
        and (
            state.latest_checkpoint is None
            or _is_valid_checkpoint_id(state.latest_checkpoint)
        )
    )


def _is_valid_checkpoint_id(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"ckpt-[0-9]{3,}", value))


def _state_adapter_error(phase: Phase) -> StructuredError:
    return StructuredError(
        error_code="state_adapter_invalid",
        message="State adapter returned a value that does not match the task-state schema.",
        phase=phase.value,
        denied_rule="structured_task_state_required",
        suggested_fix="Repair the state adapter and restore the task state before retrying.",
    )


def _rollback_state_error(phase: Phase) -> StructuredError:
    return StructuredError(
        error_code="rollback_state_update_failed",
        message="Rollback state could not be persisted by the agent loop.",
        phase=phase.value,
        denied_rule="rollback_state_update_required",
        suggested_fix="Restore task state storage before retrying rollback.",
    )


def _state_persistence_error(phase: Phase) -> StructuredError:
    return StructuredError(
        error_code="state_persistence_failed",
        message="Task state could not be persisted after the guarded action.",
        phase=phase.value,
        denied_rule="state_write_required",
        suggested_fix="Restore task state storage before continuing.",
    )


def _mutation_lock_error(phase: Phase) -> StructuredError:
    return StructuredError(
        error_code="mutation_lock_unavailable",
        message="The task mutation lock could not be acquired.",
        phase=phase.value,
        denied_rule="mutation_lock_required",
        suggested_fix="Restore task workspace lock access before retrying.",
    )


def _trace_action(
    action: Action,
    decision: PolicyDecisionLike | None,
    *,
    include_path: bool,
) -> dict[str, object]:
    args: dict[str, object] = {}
    if include_path and isinstance(action.args.get("path"), str):
        args["path"] = action.args["path"]
    command = action.args.get("command")
    if action.tool_name == "run_tests" and isinstance(command, str):
        args["command"] = redact_text(command)
    target_zone = getattr(decision, "target_zone", None)
    reason = redact_text(action.reason or "Run the configured test command.")
    policy_decision = None
    if decision is not None:
        policy_decision = {
            "allowed": decision.allowed,
            "message": redact_text(decision.reason),
            "phase": action.phase.value,
            "requires_checkpoint": decision.requires_checkpoint,
            "target_zone": (
                target_zone.value
                if isinstance(target_zone, PathZone)
                else None
            ),
            "denied_rule": decision.denied_rule,
            "suggested_fix": redact_text(decision.suggested_fix),
        }
    return {
        "tool_name": action.tool_name or "unknown",
        "args": args,
        "reason": reason,
        "policy_decision": policy_decision,
    }


def _state_after_tool(
    state: TaskState,
    action: Action,
    result: ToolResult,
    requires_checkpoint: bool,
    *,
    source_write: bool,
) -> TaskState:
    phase_completed = dict(state.phase_completed)
    if action.tool_name == "run_tests":
        if _test_strategy_error_code(result) is not None:
            phase_completed[Phase.TEST.value] = False
            return replace(
                state,
                test_strategy_digest=None,
                phase_completed=phase_completed,
            )
        report = _feedback_report_for_test_result(result)
        phase_completed[Phase.TEST.value] = False
        return replace(
            state,
            tests_run=(
                *state.tests_run,
                redact_text(result.command) if result.command else "run_tests",
            ),
            latest_test_status="passed" if report.passed else "failed",
            test_status_consumed=False,
            phase_completed=phase_completed,
        )

    if action.tool_name == "record_test_strategy" and result.success:
        digest = (
            result.output.get("test_strategy_digest")
            if isinstance(result.output, Mapping)
            else None
        )
        if (
            isinstance(digest, str)
            and len(digest) == 64
            and all(character in "0123456789abcdef" for character in digest)
        ):
            return replace(state, test_strategy_digest=digest)

    if action.tool_name == "record_remediation" and result.success:
        digest = (
            result.output.get("remediation_digest")
            if isinstance(result.output, Mapping)
            else None
        )
        if _is_sha256(digest):
            return replace(state, latest_remediation_digest=digest)

    if action.tool_name == "run_build":
        build_status = (
            "timed_out"
            if result.timed_out
            else "passed"
            if result.success
            else "failed"
        )
        return replace(
            state,
            builds_run=(
                *state.builds_run,
                redact_text(result.command) if result.command else "run_build",
            ),
            latest_build_status=build_status,
        )

    if action.tool_name == "record_review" and result.success:
        artifacts = dict(state.artifacts)
        artifacts["REVIEW.md"] = True
        phase_completed = dict(state.phase_completed)
        phase_completed[Phase.REVIEW.value] = True
        reviewed_state = replace(
            state,
            artifacts=artifacts,
            phase_completed=phase_completed,
        )
        if (
            action.phase is Phase.REVIEW
            and build_phase_gate(Phase.REVIEW, reviewed_state).can_finish
        ):
            return _state_after_phase_finish(reviewed_state, Phase.REVIEW)
        return reviewed_state

    if not source_write and result.success and action.tool_name in {"write_file", "edit_file"}:
        path = action.args.get("path")
        artifact_name = _artifact_name(path) if isinstance(path, str) else None
        if isinstance(artifact_name, str) and artifact_name in state.artifacts:
            artifacts = dict(state.artifacts)
            artifacts[artifact_name] = True
            # Atomically mark the phase as completed when its definitive
            # artifact is written, so that an interrupt between the tool
            # result and a subsequent FINISH_PHASE action does not leave
            # the state inconsistent on resume.
            phase_completed = dict(state.phase_completed)
            if artifact_name == "SPEC.md":
                phase_completed[Phase.SPEC.value] = True
            elif artifact_name == "PLAN.md":
                phase_completed[Phase.PLAN.value] = True
            elif artifact_name == "REVIEW.md":
                phase_completed[Phase.REVIEW.value] = True
            elif artifact_name == "DELIVERABLES.md":
                phase_completed[Phase.DELIVER.value] = True
            return replace(state, artifacts=artifacts, phase_completed=phase_completed)

    if not source_write or not result.success:
        return state
    source_edits = state.source_edits_this_phase + 1
    path = action.args.get("path")
    canonical_path = _canonical_relative_path(path) if isinstance(path, str) else None
    files_changed = (
        state.files_changed
        if canonical_path is None or canonical_path in state.files_changed
        else (*state.files_changed, canonical_path)
    )
    if (
        state.current_phase is Phase.CODE
        and state.latest_test_status == "failed"
        and state.test_status_consumed
        and state.source_edits_this_phase == 0
        and state.retry_budget_remaining > 0
        and requires_checkpoint
        and state.latest_remediation_digest is None
    ):
        phase_completed[Phase.TEST.value] = False
        return replace(
            state,
            latest_test_status="none",
            test_status_consumed=False,
            retry_budget_remaining=state.retry_budget_remaining - 1,
            source_edits_this_phase=source_edits,
            files_changed=files_changed,
            phase_completed=phase_completed,
        )
    return replace(
        state,
        source_edits_this_phase=source_edits,
        files_changed=files_changed,
    )


def _delivery_gate_error(phase: Phase, blockers: object) -> StructuredError:
    safe_blockers = tuple(
        redact_text(item) for item in blockers if isinstance(item, str)
    ) if isinstance(blockers, (list, tuple)) else ()
    detail = " ".join(safe_blockers) if safe_blockers else "Inspect delivery evidence."
    return StructuredError(
        error_code="delivery_gate_blocked",
        message=f"Delivery gates are not satisfied. {detail}",
        phase=phase.value,
        denied_rule="delivery_gates_required",
        suggested_fix="Resolve the reported delivery blockers before finishing.",
    )


def _feedback_report_for_test_result(result: ToolResult) -> FeedbackReport:
    output = "\n".join(
        value
        for value in (result.error_summary, result.stdout, result.stderr)
        if isinstance(value, str) and value
    )
    return classify_test_output(
        output,
        result.exit_code if result.exit_code is not None else (0 if result.success else 1),
        result.timed_out,
    )


def _test_strategy_error_code(result: ToolResult) -> str | None:
    if not isinstance(result.output, Mapping):
        return None
    value = result.output.get("strategy_error")
    return value if isinstance(value, str) and value else None


def _build_status_for_tool_result(result: ToolResult) -> str:
    if result.timed_out:
        return "timed_out"
    return "passed" if result.success else "failed"


def _diff_evidence_from_output(output: object) -> tuple[str, bool] | None:
    if not isinstance(output, Mapping):
        return None
    try:
        serialized = json.dumps(output, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return None
    risks = output.get("risks")
    drifted = isinstance(risks, (list, tuple)) and (
        "workspace_changed_after_checkpoint" in risks
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest(), drifted


def _hash_file_if_exists(path: Path) -> str | None:
    """Return the sha256 of a file, or None if it does not exist/unreadable.

    Mirrors ApprovalRequestBuilder._compute_file_hash so the resume-time
    re-check compares like-for-like against the recorded before_sha256.
    """
    try:
        if not path.is_file():
            return None
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except (OSError, UnicodeError):
        return None


def _is_source_write_action(
    action: Action, decision: PolicyDecisionLike, task_id: str
) -> bool:
    if action.tool_name not in {"write_file", "edit_file"}:
        return False
    target_zone = getattr(decision, "target_zone", None)
    if target_zone is not None:
        return target_zone is PathZone.SOURCE
    target = action.args.get("path")
    return not _is_artifact_path(target, task_id)


def _is_valid_policy_decision(
    action: Action, decision: PolicyDecisionLike, phase: Phase, task_id: str
) -> bool:
    allowed = getattr(decision, "allowed", None)
    requires_checkpoint = getattr(decision, "requires_checkpoint", None)
    reason = getattr(decision, "reason", None)
    suggested_fix = getattr(decision, "suggested_fix", None)
    denied_rule = getattr(decision, "denied_rule", None)
    if not isinstance(allowed, bool):
        return False
    if not isinstance(requires_checkpoint, bool):
        return False
    if not isinstance(reason, str) or not isinstance(suggested_fix, str):
        return False
    if denied_rule is not None and not isinstance(denied_rule, str):
        return False
    target_zone = getattr(decision, "target_zone", None)
    if target_zone is not None and not isinstance(target_zone, PathZone):
        return False
    decision_phase = getattr(decision, "phase", None)
    if decision_phase is not None and (
        not isinstance(decision_phase, Phase) or decision_phase is not phase
    ):
        return False
    if action.type is not ActionType.TOOL_CALL:
        return not requires_checkpoint
    if action.tool_name not in {
        "write_file",
        "edit_file",
    }:
        return not requires_checkpoint
    if not allowed:
        # A denied write may intentionally contain an unsafe, protected, or
        # out-of-scope target.  Those action defects belong to the normal
        # policy-denial feedback loop; they do not prove the Policy adapter is
        # structurally inconsistent.  A denied decision must still avoid
        # authorizing a checkpoint or claiming a writable target zone.
        return not requires_checkpoint and target_zone is None
    target = action.args.get("path")
    if not isinstance(target, str) or not target.strip():
        return False
    if not _is_safe_relative_path(target):
        return False
    if not isinstance(action.reason, str) or not action.reason.strip():
        return False
    is_artifact = _is_artifact_path(target, task_id)
    if _is_task_artifact_path(target) and not is_artifact:
        return False
    if allowed and target_zone not in {PathZone.SOURCE, PathZone.ARTIFACT}:
        return False
    if is_artifact and requires_checkpoint:
        return False
    if target_zone is PathZone.ARTIFACT and not is_artifact:
        return False
    if target_zone is PathZone.SOURCE and is_artifact:
        return False
    return True


def _is_valid_tool_result(result: object, action: Action) -> bool:
    if not isinstance(result, ToolResult):
        return False
    if action.type is not ActionType.TOOL_CALL or action.tool_name is None:
        return False
    if not isinstance(result.success, bool) or result.action_name != action.tool_name:
        return False
    if result.error_summary is not None and not isinstance(result.error_summary, str):
        return False
    if result.stdout is not None and not isinstance(result.stdout, str):
        return False
    if result.stderr is not None and not isinstance(result.stderr, str):
        return False
    if result.exit_code is not None and (
        not isinstance(result.exit_code, int) or isinstance(result.exit_code, bool)
    ):
        return False
    if result.command is not None and not isinstance(result.command, str):
        return False
    if not _is_json_safe(result.output):
        return False
    if result.mutation_applied is not None and not isinstance(result.mutation_applied, bool):
        return False
    if result.error_code is not None and (
        not isinstance(result.error_code, str)
        or not result.error_code
        or not re.fullmatch(r"[a-z0-9_]+", result.error_code)
    ):
        return False
    return isinstance(result.timed_out, bool)


def _tool_trace_observation(
    result: ToolResult, memory_record: MemoryRecord | object | None = None
) -> dict[str, object]:
    observation: dict[str, object] = {
        "action_name": result.action_name,
        "error_code": result.error_code,
        "exit_code": result.exit_code,
        "timed_out": result.timed_out,
        "command": None if result.command is None else redact_text(result.command),
        "mutation_applied": result.mutation_applied,
        "stdout_chars": None if result.stdout is None else len(result.stdout),
        "stderr_chars": None if result.stderr is None else len(result.stderr),
    }
    if memory_record is not None:
        memory_kind = getattr(memory_record, "kind", None)
        invalidation_reason = (
            None
            if getattr(memory_kind, "value", memory_kind) != "invalidation"
            else (
                "mutation_effect_unknown"
                if not result.success and result.mutation_applied is None
                else result.action_name
            )
        )
        observation.update(
            {
                "memory_id": getattr(memory_record, "memory_id", None),
                "content_sha256": getattr(memory_record, "content_sha256", None),
                "blob_bytes": getattr(memory_record, "blob_bytes", None),
                "workspace_generation": getattr(
                    memory_record, "workspace_generation", None
                ),
                "invalidation_reason": invalidation_reason,
            }
        )
    return observation


def _tool_error_summary(result: ToolResult) -> str:
    if result.error_summary:
        return result.error_summary
    if result.timed_out:
        return "Tool action timed out."
    return "Tool action failed."


def _attach_memory_reference(observation: object, record: object) -> object:
    reference = {
        "memory_id": getattr(record, "memory_id", None),
        "persisted": True,
        "has_content": getattr(record, "blob_ref", None) is not None,
        "workspace_generation": getattr(record, "workspace_generation", None),
    }
    if isinstance(observation, Observation):
        details = dict(observation.details)
        details["memory_ref"] = reference
        return replace(observation, details=details)
    if isinstance(observation, Mapping):
        attached = dict(observation)
        attached["memory_ref"] = reference
        return attached
    return {"observation": _context_value(observation), "memory_ref": reference}


def _memory_persistence_error(phase: Phase) -> StructuredError:
    return StructuredError(
        error_code="memory_write_error",
        message="Task runtime memory could not be persisted.",
        phase=phase.value,
        denied_rule="memory_persistence_required",
        suggested_fix="Restore task memory storage before continuing.",
    )


def _memory_failure_requires_inconsistent(action: Action, result: ToolResult) -> bool:
    return action.tool_name in {"write_file", "edit_file"} and (
        result.success or result.mutation_applied is None
    )


def _memory_tool_integrity_failure(
    action: Action, error: StructuredError
) -> bool:
    return action.tool_name in {"memory_read", "memory_search"} and error.error_code in {
        "memory_corrupt",
        "memory_task_identity_mismatch",
        "memory_path_link_not_allowed",
        "memory_write_error",
    }


def _memory_failure_needs_checkpoint_abort(
    action: Action, result: ToolResult, requires_checkpoint: bool
) -> bool:
    return (
        requires_checkpoint
        and action.tool_name in {"write_file", "edit_file"}
        and not result.success
        and result.mutation_applied is False
    )


def _is_valid_trace_event(
    event: object,
    task_id: str,
    phase: Phase,
    expected_event_type: str,
    expected_status: str,
) -> bool:
    valid = (
        isinstance(event, TraceEvent)
        and event.task_id == task_id
        and event.phase is phase
        and event.event_type == expected_event_type
        and event.status == expected_status
        and isinstance(event.seq, int)
        and not isinstance(event.seq, bool)
        and event.seq > 0
        and isinstance(event.event_id, str)
        and bool(event.event_id)
        and isinstance(event.timestamp, datetime)
        and isinstance(event.event_type, str)
        and bool(event.event_type)
        and isinstance(event.status, str)
        and bool(event.status)
    )
    if not valid or not isinstance(event, TraceEvent):
        return False
    if not all(
        _is_json_safe(value)
        for value in (event.action, event.observation, event.state_transition)
    ):
        return False
    if event.event_type not in {"tool_called", "tool_completed", "tool_failed"}:
        return True
    action = event.action
    if not isinstance(action, Mapping):
        return False
    tool_name = action.get("tool_name")
    args = action.get("args")
    reason = action.get("reason")
    policy_decision = action.get("policy_decision")
    if (
        not isinstance(tool_name, str)
        or not tool_name.strip()
        or not isinstance(args, Mapping)
        or not isinstance(reason, str)
        or not reason.strip()
        or not isinstance(policy_decision, Mapping)
        or not isinstance(policy_decision.get("allowed"), bool)
        or not isinstance(policy_decision.get("message"), str)
        or not isinstance(policy_decision.get("phase"), str)
        or policy_decision.get("phase") != phase.value
        or "denied_rule" not in policy_decision
        or (
            policy_decision.get("denied_rule") is not None
            and not isinstance(policy_decision.get("denied_rule"), str)
        )
        or not isinstance(policy_decision.get("suggested_fix"), str)
    ):
        return False
    return event.event_type != "tool_failed" or (
        isinstance(event.error_summary, str) and bool(event.error_summary.strip())
    )


def _is_json_safe(value: object) -> bool:
    if value is None or isinstance(value, (bool, int, float, str)):
        return True
    if isinstance(value, Mapping):
        return all(isinstance(key, str) and _is_json_safe(item) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return all(_is_json_safe(item) for item in value)
    return False


def _is_artifact_path(target: object, task_id: str | None = None) -> bool:
    if not isinstance(target, str):
        return False
    normalized = target.replace("\\", "/")
    artifact_names = {
        "SPEC.md",
        "PLAN.md",
        "TEST_REPORT.md",
        "REVIEW.md",
        "KNOWLEDGE.md",
        "DELIVERABLES.md",
    }
    if normalized in artifact_names:
        return True
    parts = normalized.split("/")
    return (
        task_id is not None
        and len(parts) == 4
        and parts[:2] == [".hancode", "tasks"]
        and parts[2] == task_id
        and parts[-1] in artifact_names
    )


def _is_task_artifact_path(target: str) -> bool:
    normalized = target.replace("\\", "/")
    parts = normalized.split("/")
    return len(parts) == 4 and parts[:2] == [".hancode", "tasks"]


def _artifact_name(target: str) -> str:
    return target.replace("\\", "/").rsplit("/", 1)[-1]


def _canonical_relative_path(target: str) -> str:
    return Path(target.replace("\\", "/")).as_posix()


def _is_checkpoint_state_ready(state: TaskState, task_id: str, phase: Phase) -> bool:
    return (
        state.task_id == task_id
        and state.current_phase is phase
        and state.status is TaskStatus.RUNNING
        and not state.inconsistent
        and not state.rollback_required
    )


def _is_pending_checkpoint_for(
    checkpoint: CheckpointManifest,
    task_id: str,
    phase: Phase,
    expected_path: Path,
    *,
    expected_checkpoint_id: str | None,
) -> bool:
    return _is_checkpoint_manifest_for(
        checkpoint,
        task_id=task_id,
        phase=phase,
        expected_path=expected_path,
        expected_status="pending",
        expected_rollback_available=False,
        expected_checkpoint_id=expected_checkpoint_id,
        require_after_sha256=False,
    )


def _is_aborted_checkpoint_for(
    checkpoint: CheckpointManifest,
    task_id: str,
    phase: Phase,
    expected_path: Path,
    expected_checkpoint_id: str,
) -> bool:
    return _is_checkpoint_manifest_for(
        checkpoint,
        task_id=task_id,
        phase=phase,
        expected_path=expected_path,
        expected_status="aborted",
        expected_rollback_available=False,
        expected_checkpoint_id=expected_checkpoint_id,
        require_after_sha256=False,
    )


def _is_committed_checkpoint_for(
    checkpoint: CheckpointManifest,
    task_id: str,
    phase: Phase,
    expected_path: Path,
    expected_checkpoint_id: str,
    *,
    pending_checkpoint: CheckpointManifest,
) -> bool:
    return _is_checkpoint_manifest_for(
        checkpoint,
        task_id=task_id,
        phase=phase,
        expected_path=expected_path,
        expected_status="committed",
        expected_rollback_available=True,
        expected_checkpoint_id=expected_checkpoint_id,
        require_after_sha256=True,
        expected_pending=pending_checkpoint,
    )


def _is_checkpoint_manifest_for(
    checkpoint: CheckpointManifest,
    *,
    task_id: str,
    phase: Phase,
    expected_path: Path,
    expected_status: str,
    expected_rollback_available: bool,
    expected_checkpoint_id: str | None,
    require_after_sha256: bool,
    expected_pending: CheckpointManifest | None = None,
) -> bool:
    if not isinstance(checkpoint, CheckpointManifest):
        return False
    if (
        checkpoint.schema_version != 1
        or not isinstance(checkpoint.project_id, str)
        or not checkpoint.project_id
        or not _is_valid_checkpoint_id(checkpoint.checkpoint_id)
        or (
            expected_checkpoint_id is not None
            and checkpoint.checkpoint_id != expected_checkpoint_id
        )
        or checkpoint.task_id != task_id
        or checkpoint.phase is not phase
        or checkpoint.status != expected_status
        or checkpoint.rollback_available is not expected_rollback_available
        or not isinstance(checkpoint.reason, str)
        or not checkpoint.reason
        or not isinstance(checkpoint.created_at, datetime)
        or not isinstance(checkpoint.files, tuple)
        or not checkpoint.files
    ):
        return False
    expected_path_text = expected_path.as_posix()
    paths: set[str] = set()
    for file in checkpoint.files:
        if not isinstance(file, CheckpointFile):
            return False
        if not isinstance(file.path, str) or not file.path:
            return False
        try:
            relative_path = Path(file.path)
        except (OSError, TypeError, ValueError):
            return False
        if (
            relative_path.is_absolute()
            or relative_path.as_posix() != file.path.replace("\\", "/")
            or any(part in {"", ".", ".."} for part in relative_path.parts)
            or file.action not in {"create", "modify"}
        ):
            return False
        normalized_path = relative_path.as_posix()
        if normalized_path in paths:
            return False
        paths.add(normalized_path)
        if file.action == "create":
            if file.before_snapshot is not None or file.before_sha256 is not None:
                return False
        elif (
            not isinstance(file.before_snapshot, str)
            or not file.before_snapshot.strip()
            or not _is_sha256(file.before_sha256)
        ):
            return False
        if not _is_optional_sha256(file.after_sha256):
            return False
        if expected_status in {"pending", "aborted"} and file.after_sha256 is not None:
            return False
        if require_after_sha256 and not _is_sha256(file.after_sha256):
            return False
    if paths != {expected_path_text}:
        return False
    if expected_pending is not None:
        if (
            checkpoint.project_id != expected_pending.project_id
            or checkpoint.reason != expected_pending.reason
            or checkpoint.created_at != expected_pending.created_at
            or len(checkpoint.files) != len(expected_pending.files)
        ):
            return False
        for committed_file, pending_file in zip(
            checkpoint.files, expected_pending.files, strict=True
        ):
            if (
                committed_file.path != pending_file.path
                or committed_file.action != pending_file.action
                or committed_file.before_snapshot != pending_file.before_snapshot
                or committed_file.before_sha256 != pending_file.before_sha256
            ):
                return False
    return True


def _is_optional_sha256(value: object) -> bool:
    return value is None or _is_sha256(value)


def _test_discovery_action_key(action: Action, phase: Phase) -> str | None:
    if (
        phase is not Phase.TEST
        or action.type is not ActionType.TOOL_CALL
        or action.tool_name not in _TEST_DISCOVERY_TOOLS
    ):
        return None
    return json.dumps(
        {
            "tool_name": action.tool_name,
            "args": dict(action.args),
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _code_exploration_action_key(action: Action, phase: Phase) -> str | None:
    if (
        phase is not Phase.CODE
        or action.type is not ActionType.TOOL_CALL
        or action.tool_name not in _CODE_EXPLORATION_TOOLS
    ):
        return None
    return json.dumps(
        {
            "tool_name": action.tool_name,
            "args": dict(action.args),
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _review_evidence_action_key(
    action: Action, phase: Phase, task_id: str
) -> str | None:
    if (
        phase is not Phase.REVIEW
        or action.type is not ActionType.TOOL_CALL
        or action.tool_name not in _REVIEW_EVIDENCE_TOOLS
    ):
        return None
    args = dict(action.args)
    if action.tool_name == "read_file":
        path = args.get("path")
        if isinstance(path, str):
            normalized_path = path.replace("\\", "/").lstrip("./")
            task_report = f"hancode/tasks/{task_id}/TEST_REPORT.md"
            if normalized_path == task_report:
                return "read_test_report"
    return json.dumps(
        {"tool_name": action.tool_name, "args": args},
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _review_progress_stalled_error(phase: Phase) -> StructuredError:
    return StructuredError(
        error_code="review_progress_stalled",
        message="Review repeated evidence inspection without recording a review.",
        phase=phase.value,
        denied_rule="review_progress_required",
        suggested_fix="Record REVIEW.md from the available evidence before resuming.",
    )


def _code_progress_stalled_error(phase: Phase) -> StructuredError:
    return StructuredError(
        error_code="code_progress_stalled",
        message="CODE repeated completed read-only exploration without a source write.",
        phase=phase.value,
        denied_rule="code_source_progress_required",
        suggested_fix=(
            "Use write_file under sections.writable_roots, or provide human guidance "
            "before resuming."
        ),
    )


def _remediation_input_unavailable_error(phase: Phase) -> StructuredError:
    return StructuredError(
        error_code="remediation_input_unavailable",
        message="The remediation requires human input but interaction is disabled.",
        phase=phase.value,
        denied_rule="interaction_required",
        suggested_fix="Enable interaction or provide a safe autonomous remediation.",
    )


def _test_remediation_no_progress_error(phase: Phase) -> StructuredError:
    return StructuredError(
        error_code="test_remediation_no_progress",
        message="The same test failure remained after two remediation attempts.",
        phase=phase.value,
        denied_rule="remediation_progress_required",
        suggested_fix="Request human input or rollback to the latest checkpoint.",
    )


def _recovery_no_progress_error(phase: Phase) -> StructuredError:
    return StructuredError(
        error_code="recovery_no_progress",
        message="The same Action or file-tool failure reached the recovery limit.",
        phase=phase.value,
        denied_rule="recovery_attempt_limit",
        suggested_fix="Choose a different Action or provide human guidance before resuming.",
    )


def _mutation_effect_unknown_error(phase: Phase) -> StructuredError:
    return StructuredError(
        error_code="mutation_effect_unknown",
        message="A write tool failed without a trustworthy mutation effect.",
        phase=phase.value,
        denied_rule="mutation_effect_must_be_known",
        suggested_fix="Inspect the target and checkpoint manually before continuing.",
    )


def _test_strategy_missing_error(phase: Phase) -> StructuredError:
    return StructuredError(
        error_code="test_strategy_missing",
        message="No executable behavioral test command was found.",
        phase=phase.value,
        denied_rule="test_strategy_required",
        suggested_fix=(
            "Configure test_command or add a project test runner before resuming."
        ),
    )


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _state_after_phase_finish(state: TaskState, phase: Phase) -> TaskState:
    phase_completed = dict(state.phase_completed)
    phase_completed[phase.value] = True
    base = replace(
        state,
        phase_completed=phase_completed,
        interactions=(),
        pending_interaction_id=None,
    )
    if (
        phase is Phase.REVIEW
        and state.latest_test_status == "failed"
        and not state.test_status_consumed
        and state.retry_budget_remaining > 0
    ):
        phase_completed[Phase.CODE.value] = False
        return replace(
            base,
            phase_completed=phase_completed,
            test_status_consumed=True,
        )
    return base
