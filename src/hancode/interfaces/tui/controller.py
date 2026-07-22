"""Textual-independent TUI session controller (S5-R0).

The controller turns validated user intents into request-scoped operations,
delegates service work to :class:`TuiOperationExecutor`, and applies results to
the immutable view state.  Textual is intentionally absent from this module.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from hancode.app.approval_service import ApprovalService
from hancode.app.change_inspection_service import ChangeInspectionService
from hancode.app.checkpoint_inspection_service import CheckpointInspectionService
from hancode.app.delivery_inspection_service import DeliveryInspectionService
from hancode.app.delivery_service import DeliveryService
from hancode.app.inspection_service import InspectionService
from hancode.app.interaction_service import InteractionService
from hancode.app.recovery_service import RecoveryService
from hancode.app.task_models import TaskSummary
from hancode.app.task_service import TaskService
from hancode.core.errors import HanCodeError, StructuredError
from hancode.interfaces.tui.operations import (
    TaskSelectionResult,
    TuiIntent,
    TuiOperation,
    TuiOperationError,
    TuiOperationExecutor,
    TuiOperationKind,
    TuiOperationResult,
    TuiServices,
)
from hancode.interfaces.tui.view_state import (
    MAX_EVENT_BUFFER,
    TuiViewState,
    reduce_run_finished,
    reduce_task_selected,
    reduce_trace_arrived,
)
from hancode.runtime.agent_loop import AgentRunResult
from hancode.runtime.observation import TraceObserver
from hancode.storage.trace import TraceEvent


_MUTATIONS = frozenset(
    {
        TuiOperationKind.CREATE_TASK,
        TuiOperationKind.RUN_TASK,
        TuiOperationKind.ANSWER_INTERACTION,
        TuiOperationKind.APPROVE,
        TuiOperationKind.REJECT,
        TuiOperationKind.ROLLBACK,
    }
)
_TASK_REQUIRED = frozenset(
    kind
    for kind in TuiOperationKind
    if kind not in {TuiOperationKind.CREATE_TASK, TuiOperationKind.LIST_TASKS}
)


class TuiSessionController:
    """Map user intents to application operations and own the view state."""

    def __init__(
        self,
        project_root: Path,
        *,
        services: TuiServices | None = None,
        executor: TuiOperationExecutor | None = None,
        task_service: TaskService | None = None,
        interaction_service: InteractionService | None = None,
        approval_service: ApprovalService | None = None,
        inspection_service: InspectionService | None = None,
        recovery_service: RecoveryService | None = None,
    ) -> None:
        self._project_root = project_root
        self._services = services or TuiServices(
            task=task_service or TaskService(),
            interaction=interaction_service or InteractionService(),
            approval=approval_service or ApprovalService(project_root),
            inspection=inspection_service or InspectionService(),
            changes=ChangeInspectionService(),
            test_reports=DeliveryInspectionService(),
            checkpoints=CheckpointInspectionService(),
            recovery=recovery_service or RecoveryService(),
            delivery=DeliveryService(),
        )
        self._executor = executor or TuiOperationExecutor(project_root, self._services)
        self._state = TuiViewState.initial(project_root)
        self._active_request_id: str | None = None
        self._active_operation_task_id: str | None = None

    @property
    def state(self) -> TuiViewState:
        return self._state

    @property
    def services(self) -> TuiServices:
        return self._services

    @property
    def executor(self) -> TuiOperationExecutor:
        return self._executor

    def can_mutate(self) -> bool:
        """Whether a mutating operation may begin."""

        return not self._state.busy

    def dispatch(self, intent: TuiIntent) -> TuiOperation | None:
        """Validate an intent and assign a request ID, without doing I/O."""

        if self._state.busy:
            return self._reject(
                "tui_operation_busy",
                "任务正在运行，无法开始新的操作。",
                "等待当前任务结束后重试。",
            )

        task_id = intent.task_id
        if intent.kind in _TASK_REQUIRED:
            task_id = task_id or self._state.active_task_id
            if not task_id:
                return self._reject(
                    "tui_task_required",
                    "当前没有选中的任务。",
                    "先选择或创建一个任务。",
                )
        if intent.kind in _MUTATIONS and task_id != self._state.active_task_id:
            return self._reject(
                "tui_task_not_active",
                "只能操作当前选中的任务。",
                "先使用 /use <task-id> 切换任务。",
            )
        if intent.kind in {TuiOperationKind.APPROVE, TuiOperationKind.REJECT}:
            if intent.approval_id is None:
                approval_id = self._state.pending_approval_id
            else:
                approval_id = intent.approval_id
            if approval_id is None:
                return self._reject(
                    "tui_approval_required",
                    "当前没有待处理的 Approval。",
                    "等待 Approval 请求后再作出显式决定。",
                )
            intent = replace(intent, approval_id=approval_id)
        if intent.kind is TuiOperationKind.ANSWER_INTERACTION:
            interaction_id = intent.interaction_id or self._state.pending_interaction_id
            if interaction_id is None:
                return self._reject(
                    "tui_interaction_required",
                    "当前没有待回答的问题。",
                    "等待 ASK_USER 请求后再提交回答。",
                )
            intent = replace(intent, interaction_id=interaction_id)
        return TuiOperation.from_intent(replace(intent, task_id=task_id), request_id=uuid4().hex)

    def begin_operation(self, operation: TuiOperation) -> str:
        """Mark a request active and return its request ID."""

        if self._state.busy:
            raise HanCodeError(
                StructuredError(
                    error_code="tui_operation_busy",
                    message="任务正在运行，无法开始新的操作。",
                    phase="spec",
                    denied_rule="single_mutation_worker",
                    suggested_fix="等待当前任务结束后重试。",
                )
            )
        self._active_request_id = operation.request_id
        self._active_operation_task_id = operation.task_id
        is_mutation = operation.kind in _MUTATIONS
        self._state = replace(
            self._state,
            current_request_id=operation.request_id,
            busy=is_mutation,
            running_task_id=operation.task_id if is_mutation else None,
            last_error=None,
        )
        return operation.request_id

    def execute(
        self,
        operation: TuiOperation,
        *,
        trace_observer: TraceObserver | None = None,
    ) -> TuiOperationResult:
        """Delegate the operation to the Textual-independent executor."""

        return self._executor.execute(operation, trace_observer=trace_observer)

    def apply_result(self, result: TuiOperationResult) -> None:
        """Apply only the result belonging to the active request/task."""

        if not self._accepts_result(result.request_id, result.task_id):
            return
        kind = result.kind
        value = result.value
        if kind is TuiOperationKind.LIST_TASKS:
            if isinstance(value, tuple) and all(isinstance(item, TaskSummary) for item in value):
                self._state = replace(self._state, tasks=value)
        elif kind is TuiOperationKind.CREATE_TASK:
            if isinstance(value, TaskSummary):
                self._state = self._with_active_summary(value, add_to_tasks=True)
        elif kind is TuiOperationKind.SELECT_TASK:
            if isinstance(value, TaskSelectionResult):
                self._state = reduce_task_selected(
                    replace(
                        self._state,
                        trace_events=tuple(value.trace_events[-MAX_EVENT_BUFFER:]),
                        selected_event_id=None,
                    ),
                    value.summary,
                )
        elif kind in {
            TuiOperationKind.GET_STATUS,
            TuiOperationKind.LIST_ARTIFACTS,
            TuiOperationKind.ANSWER_INTERACTION,
            TuiOperationKind.APPROVE,
            TuiOperationKind.REJECT,
        }:
            if isinstance(value, TaskSummary):
                self._state = self._with_active_summary(value)
        elif kind is TuiOperationKind.RUN_TASK:
            if isinstance(value, AgentRunResult):
                self._state = self._with_active_summary(TaskSummary.from_state(value.final_state))
        elif kind is TuiOperationKind.READ_ARTIFACT:
            from hancode.app.inspection_service import ArtifactPreview

            if isinstance(value, ArtifactPreview):
                self._state = replace(
                    self._state,
                    selected_artifact=value.name,
                    artifact_preview=value.content,
                )
        self._finish_operation()

    def apply_error(self, error: TuiOperationError) -> None:
        """Surface a structured error and clear the active operation."""

        if self._active_request_id != error.request_id:
            return
        self._state = replace(
            self._state,
            last_error=error.structured_error,
        )
        self._finish_operation()

    def _accepts_result(self, request_id: str, task_id: str | None) -> bool:
        if self._active_request_id != request_id:
            return False
        if (
            task_id is not None
            and self._active_operation_task_id is not None
            and task_id != self._active_operation_task_id
        ):
            return False
        return True

    def _finish_operation(self) -> None:
        self._active_request_id = None
        self._active_operation_task_id = None
        self._state = replace(
            self._state,
            current_request_id=None,
            busy=False,
            running_task_id=None,
        )

    def _execute_sync(self, intent: TuiIntent) -> TuiOperationResult:
        operation = self.dispatch(intent)
        if operation is None:
            error = self._state.last_error or _controller_error(
                "tui_invalid_operation",
                "TUI operation was rejected.",
                "Retry after checking the selected task.",
            )
            raise HanCodeError(error)
        self.begin_operation(operation)
        try:
            result = self.execute(operation)
        except TuiOperationError as exc:
            self.apply_error(exc)
            raise HanCodeError(exc.structured_error) from exc
        self.apply_result(result)
        return result

    # Compatibility helpers used by the existing TUI and its S4 tests.  They
    # now route through the operation boundary rather than calling services.
    def refresh_tasks(self) -> None:
        self._execute_sync(TuiIntent(kind=TuiOperationKind.LIST_TASKS))

    def select_task(self, task_id: str) -> None:
        self._execute_sync(TuiIntent(kind=TuiOperationKind.SELECT_TASK, task_id=task_id))

    def mark_running(self, task_id: str) -> None:
        self._state = self._state.with_busy(True, running_task_id=task_id)

    def on_trace(self, event: TraceEvent) -> None:
        running_task_id = self._state.running_task_id
        if running_task_id is not None and event.task_id != running_task_id:
            return
        self._state = reduce_trace_arrived(self._state, event)

    def clear_activity(self) -> None:
        self._state = replace(self._state, trace_events=(), selected_event_id=None)

    def on_run_finished(self) -> None:
        running_task_id = self._state.running_task_id
        self._active_request_id = None
        self._active_operation_task_id = None
        self._state = reduce_run_finished(self._state)
        if running_task_id is not None:
            try:
                self._execute_sync(
                    TuiIntent(
                        kind=TuiOperationKind.GET_STATUS,
                        task_id=running_task_id,
                    )
                )
            except HanCodeError:
                return

    def set_active_summary(self, summary: TaskSummary) -> None:
        self._state = self._with_active_summary(summary)

    def _with_active_summary(
        self, summary: TaskSummary, *, add_to_tasks: bool = False
    ) -> TuiViewState:
        state = reduce_task_selected(self._state, summary)
        if not add_to_tasks:
            return state
        tasks = tuple(summary if item.task_id == summary.task_id else item for item in state.tasks)
        if not any(item.task_id == summary.task_id for item in tasks):
            tasks = (*tasks, summary)
        return replace(state, tasks=tasks)

    def _reject(
        self,
        error_code: str,
        message: str,
        suggested_fix: str,
    ) -> TuiOperation | None:
        self._state = replace(
            self._state,
            last_error=_controller_error(error_code, message, suggested_fix),
        )
        return None


def _controller_error(error_code: str, message: str, suggested_fix: str) -> StructuredError:
    return StructuredError(
        error_code=error_code,
        message=message,
        phase="spec",
        denied_rule="tui_operation_contract",
        suggested_fix=suggested_fix,
    )


__all__ = ["TuiSessionController"]
