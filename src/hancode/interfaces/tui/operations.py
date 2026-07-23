"""Textual-independent operation boundary for the HanCode TUI.

The TUI app owns Textual lifecycle and rendering only.  This module contains
the stable request/result vocabulary and the application-service executor used
by the session controller.  It deliberately does not create a second task
state machine or duplicate any harness operation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from hancode.app.approval_service import ApprovalService
from hancode.app.build_service import BuildSummary
from hancode.app.build_service import BuildService
from hancode.app.change_inspection_service import ChangeInspectionService
from hancode.app.checkpoint_inspection_service import CheckpointInspectionService
from hancode.app.delivery_inspection_service import (
    DeliveryInspectionService,
    TestReportSummary,
)
from hancode.app.delivery_service import DeliveryService
from hancode.app.inspection_service import ArtifactPreview, InspectionService, TracePage
from hancode.app.interaction_service import InteractionService
from hancode.app.recovery_service import RecoveryService, RecoverySummary, RollbackPreview
from hancode.app.task_models import TaskSummary
from hancode.app.task_service import TaskService
from hancode.core.change_models import CheckpointSummary, DiffScope, TaskDiff
from hancode.core.delivery_evidence import DeliveryEvidence, DeliveryResult
from hancode.core.errors import HanCodeError, StructuredError
from hancode.runtime.observation import TraceObserver
from hancode.runtime.agent_loop import AgentRunResult
from hancode.storage.export import ExportResult
from hancode.storage.trace import TraceEvent


class TuiOperationKind(str, Enum):
    """Business operations currently exposed by the TUI boundary."""

    CREATE_TASK = "create_task"
    LIST_TASKS = "list_tasks"
    SELECT_TASK = "select_task"
    RUN_TASK = "run_task"
    ANSWER_INTERACTION = "answer_interaction"
    APPROVE = "approve"
    REJECT = "reject"
    GET_STATUS = "get_status"
    GET_APPROVAL = "get_approval"
    PREVIEW_ROLLBACK = "preview_rollback"
    ROLLBACK = "rollback"
    LIST_ARTIFACTS = "list_artifacts"
    READ_ARTIFACT = "read_artifact"

    # Reserved by the S5 contract.  Their UI and query worker implementations
    # land in later slices; keeping the names here prevents another operation
    # vocabulary from being invented by those slices.
    DIFF = "diff"
    TEST_REPORT = "test_report"
    CHECKPOINTS = "checkpoints"
    DELIVERY = "delivery"
    EXPORT = "export"
    BUILD = "build"
    TRACE = "trace"


TuiIntentKind = TuiOperationKind


@dataclass(frozen=True, slots=True)
class TuiIntent:
    """A validated user intention before a request ID is assigned."""

    kind: TuiOperationKind
    task_id: str | None = None
    goal: str | None = None
    resume: bool = False
    answer: str | None = None
    interaction_id: str | None = None
    approval_id: str | None = None
    reason: str | None = None
    artifact_name: str | None = None
    diff_scope: str | None = None
    diff_path: str | None = None
    event_id: str | None = None
    export_output_dir: Path | None = None


@dataclass(frozen=True, slots=True)
class TuiOperation:
    """An executable, request-identified application operation."""

    request_id: str
    kind: TuiOperationKind
    task_id: str | None = None
    goal: str | None = None
    resume: bool = False
    answer: str | None = None
    interaction_id: str | None = None
    approval_id: str | None = None
    reason: str | None = None
    artifact_name: str | None = None
    diff_scope: str | None = None
    diff_path: str | None = None
    event_id: str | None = None
    export_output_dir: Path | None = None

    @classmethod
    def from_intent(cls, intent: TuiIntent, *, request_id: str) -> TuiOperation:
        return cls(
            request_id=request_id,
            kind=intent.kind,
            task_id=intent.task_id,
            goal=intent.goal,
            resume=intent.resume,
            answer=intent.answer,
            interaction_id=intent.interaction_id,
            approval_id=intent.approval_id,
            reason=intent.reason,
            artifact_name=intent.artifact_name,
            diff_scope=intent.diff_scope,
            diff_path=intent.diff_path,
            event_id=intent.event_id,
            export_output_dir=intent.export_output_dir,
        )


@dataclass(frozen=True, slots=True)
class TaskSelectionResult:
    summary: TaskSummary
    trace_events: tuple[TraceEvent, ...]


TuiOperationValue = (
    TaskSummary
    | tuple[TaskSummary, ...]
    | TaskSelectionResult
    | AgentRunResult
    | ArtifactPreview
    | RollbackPreview
    | RecoverySummary
    | BuildSummary
    | TestReportSummary
    | TaskDiff
    | tuple[CheckpointSummary, ...]
    | DeliveryEvidence
    | TracePage
    | DeliveryResult
    | ExportResult
    | dict[str, object]
    | None
)


@dataclass(frozen=True, slots=True)
class TuiOperationResult:
    request_id: str
    kind: TuiOperationKind
    task_id: str | None
    value: TuiOperationValue
    event_id: str | None = None


class TuiOperationError(Exception):
    """A structured, request-scoped operation failure."""

    def __init__(
        self,
        request_id: str,
        kind: TuiOperationKind,
        task_id: str | None,
        structured_error: StructuredError,
    ) -> None:
        self.request_id = request_id
        self.kind = kind
        self.task_id = task_id
        self.structured_error = structured_error
        super().__init__(f"{structured_error.error_code}: {structured_error.message}")


@dataclass(frozen=True, slots=True)
class TuiServices:
    """All application services available to the TUI composition root."""

    task: TaskService
    interaction: InteractionService
    approval: ApprovalService
    inspection: InspectionService
    changes: ChangeInspectionService
    test_reports: DeliveryInspectionService
    checkpoints: CheckpointInspectionService
    recovery: RecoveryService
    delivery: DeliveryService
    build: BuildService | None = None


class TuiOperationExecutor:
    """Execute TUI operations through injected application services."""

    def __init__(self, project_root: Path, services: TuiServices) -> None:
        self._project_root = project_root
        self._services = services

    def execute(
        self,
        operation: TuiOperation,
        trace_observer: TraceObserver | None = None,
    ) -> TuiOperationResult:
        try:
            value = self._execute(operation, trace_observer=trace_observer)
        except HanCodeError as exc:
            raise TuiOperationError(
                operation.request_id,
                operation.kind,
                operation.task_id,
                exc.structured_error,
            ) from exc
        except Exception as exc:
            error = StructuredError(
                error_code="tui_operation_internal_error",
                message="TUI operation failed unexpectedly.",
                phase="spec",
                denied_rule="tui_operation_internal_error",
                suggested_fix="Inspect the task state and retry the operation.",
            )
            raise TuiOperationError(
                operation.request_id,
                operation.kind,
                operation.task_id,
                error,
            ) from exc
        return TuiOperationResult(
            request_id=operation.request_id,
            kind=operation.kind,
            task_id=operation.task_id,
            value=value,
            event_id=operation.event_id,
        )

    def _execute(
        self,
        operation: TuiOperation,
        *,
        trace_observer: TraceObserver | None,
    ) -> TuiOperationValue:
        kind = operation.kind
        task_id = operation.task_id
        if kind is TuiOperationKind.CREATE_TASK:
            if not operation.goal or not operation.goal.strip():
                raise HanCodeError(_invalid_operation("A task goal is required."))
            return self._services.task.create(self._project_root, operation.goal)
        if kind is TuiOperationKind.LIST_TASKS:
            return self._services.task.list_tasks(self._project_root)
        if kind is TuiOperationKind.SELECT_TASK:
            return self._select_task(task_id)
        if kind is TuiOperationKind.RUN_TASK:
            selected = self._require_task(task_id, "run")
            return self._services.task.run(
                self._project_root,
                selected,
                resume=operation.resume,
                trace_observer=trace_observer,
            )
        if kind is TuiOperationKind.ANSWER_INTERACTION:
            return self._services.interaction.answer(
                self._project_root,
                self._require_task(task_id, "answer"),
                operation.answer or "",
                interaction_id=operation.interaction_id,
            )
        if kind is TuiOperationKind.APPROVE:
            return self._services.approval.approve(
                self._require_task(task_id, "approve"),
                approval_id=operation.approval_id,
            )
        if kind is TuiOperationKind.REJECT:
            return self._services.approval.reject(
                self._require_task(task_id, "reject"),
                approval_id=operation.approval_id,
                reason=operation.reason,
            )
        if kind is TuiOperationKind.GET_STATUS:
            return self._services.task.get(
                self._project_root, self._require_task(task_id, "read status")
            )
        if kind is TuiOperationKind.GET_APPROVAL:
            return self._services.approval.get_pending(self._require_task(task_id, "read approval"))
        if kind is TuiOperationKind.PREVIEW_ROLLBACK:
            return self._services.recovery.preview_last(
                self._project_root, self._require_task(task_id, "preview rollback")
            )
        if kind is TuiOperationKind.ROLLBACK:
            return self._services.recovery.rollback_last(
                self._project_root, self._require_task(task_id, "rollback")
            )
        if kind is TuiOperationKind.LIST_ARTIFACTS:
            return self._services.task.get(
                self._project_root, self._require_task(task_id, "list artifacts")
            )
        if kind is TuiOperationKind.READ_ARTIFACT:
            if not operation.artifact_name:
                raise HanCodeError(_invalid_operation("An artifact name is required."))
            return self._services.inspection.read_artifact(
                self._project_root,
                self._require_task(task_id, "read artifact"),
                operation.artifact_name,
            )
        if kind is TuiOperationKind.DIFF:
            try:
                scope = DiffScope(operation.diff_scope or DiffScope.TASK.value)
            except ValueError:
                raise HanCodeError(
                    _invalid_operation("Diff scope must be 'task' or 'latest'.")
                ) from None
            return self._services.changes.get_diff(
                self._project_root,
                self._require_task(task_id, "read diff"),
                scope=scope,
                path=operation.diff_path,
            )
        if kind is TuiOperationKind.TEST_REPORT:
            return self._services.test_reports.read_test_report(
                self._project_root,
                self._require_task(task_id, "read test report"),
            )
        if kind is TuiOperationKind.CHECKPOINTS:
            return self._services.checkpoints.list_checkpoints(
                self._project_root,
                self._require_task(task_id, "list checkpoints"),
            )
        if kind is TuiOperationKind.DELIVERY:
            # get_evidence is intentionally read-only.  Do not use
            # DeliveryService.get_result(), which finalizes the task.
            return self._services.delivery.get_evidence(
                self._project_root,
                self._require_task(task_id, "read delivery evidence"),
            )
        if kind is TuiOperationKind.EXPORT:
            if operation.export_output_dir is None:
                raise HanCodeError(_invalid_operation("An export directory is required."))
            return self._services.delivery.export(
                self._project_root,
                self._require_task(task_id, "export delivery artifacts"),
                operation.export_output_dir,
            )
        if kind is TuiOperationKind.BUILD:
            if self._services.build is None:
                raise HanCodeError(_invalid_operation("Build service is not configured."))
            return self._services.build.run(
                self._project_root,
                self._require_task(task_id, "run build"),
            )
        if kind is TuiOperationKind.TRACE:
            return self._read_trace(self._require_task(task_id, "read trace"))
        raise HanCodeError(
            StructuredError(
                error_code="tui_operation_not_implemented",
                message=f"TUI operation is not implemented: {kind.value}.",
                phase="spec",
                denied_rule="s5_slice_boundary",
                suggested_fix="Use an operation supported by the current TUI slice.",
            )
        )

    def _select_task(self, task_id: str | None) -> TaskSelectionResult:
        selected = self._require_task(task_id, "select task")
        summary = self._services.task.get(self._project_root, selected)
        events: list[TraceEvent] = []
        after_seq = 0
        try:
            while True:
                page = self._services.inspection.read_trace(
                    self._project_root,
                    selected,
                    after_seq=after_seq,
                    limit=500,
                )
                events.extend(page.events)
                if not page.has_more or page.next_seq is None:
                    break
                after_seq = page.next_seq
        except HanCodeError:
            # Selection remains useful when a trace is absent or unreadable;
            # the existing UI treats that case as an empty activity feed.
            events = []
        return TaskSelectionResult(summary=summary, trace_events=tuple(events[-500:]))

    def _read_trace(self, task_id: str) -> TracePage:
        events: list[TraceEvent] = []
        after_seq = 0
        while True:
            page = self._services.inspection.read_trace(
                self._project_root,
                task_id,
                after_seq=after_seq,
                limit=500,
            )
            events.extend(page.events)
            if not page.has_more or page.next_seq is None:
                return TracePage(events=tuple(events[-500:]), next_seq=None, has_more=False)
            after_seq = page.next_seq

    @staticmethod
    def _require_task(task_id: str | None, operation: str) -> str:
        if task_id and task_id.strip():
            return task_id
        raise HanCodeError(_invalid_operation(f"A task is required to {operation}."))


def _invalid_operation(message: str) -> StructuredError:
    return StructuredError(
        error_code="tui_invalid_operation",
        message=message,
        phase="spec",
        denied_rule="tui_operation_contract",
        suggested_fix="Select a task and provide the required operation input.",
    )


__all__ = [
    "TuiIntentKind",
    "TuiOperationKind",
    "TuiIntent",
    "TuiOperation",
    "TaskSelectionResult",
    "TuiOperationResult",
    "TuiOperationValue",
    "TuiOperationError",
    "TuiServices",
    "TuiOperationExecutor",
]
