"""Pure, bounded view models for the HanCode TUI (S5-R1).

The presenter layer converts application/domain values into immutable values
that widgets can render as plain text. It owns no service, storage, or Textual
dependency and therefore remains deterministic in unit tests.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import PureWindowsPath
from typing import Mapping

from hancode.app.delivery_inspection_service import DeliverySummary, TestReportSummary
from hancode.app.build_service import BuildSummary
from hancode.app.inspection_service import ArtifactPreview
from hancode.app.recovery_service import RollbackPreview
from hancode.app.task_models import TaskSummary
from hancode.core.change_models import CheckpointSummary, TaskDiff
from hancode.core.delivery_evidence import DeliveryEvidence
from hancode.storage.export import ExportResult
from hancode.storage.trace import TraceEvent
from hancode.tooling.file_tools import redact_text


MAX_VIEW_TEXT_CHARS = 4096
MAX_VIEW_ITEMS = 100
_WINDOWS_ABSOLUTE_PATH = re.compile(r"^[A-Za-z]:[\\/]|^[\\/]{1,2}")


class DetailKind(str, Enum):
    TASK = "task"
    EVENT = "event"
    INTERACTION = "interaction"
    APPROVAL = "approval"
    ARTIFACT = "artifact"
    DIFF = "diff"
    TEST_REPORT = "test_report"
    CHECKPOINTS = "checkpoints"
    DELIVERY = "delivery"
    HELP = "help"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class TaskOverviewView:
    task_id: str
    goal: str
    status: str
    current_phase: str
    retry_budget_remaining: int
    latest_test_status: str
    latest_build_status: str
    builds_run: tuple[str, ...]
    files_changed: tuple[str, ...]
    tests_run: tuple[str, ...]
    latest_checkpoint: str | None
    rollback_required: bool
    inconsistent: bool
    artifacts: tuple[tuple[str, bool], ...]
    resumable: bool
    requires_input: bool
    requires_approval: bool


@dataclass(frozen=True, slots=True)
class ActivityItemView:
    event_id: str
    seq: int
    event_type: str
    phase: str
    status: str
    label: str
    tool_name: str | None


@dataclass(frozen=True, slots=True)
class EventDetailView:
    event_id: str
    seq: int
    event_type: str
    phase: str
    status: str
    tool_name: str | None
    target_path: str | None
    error_summary: str | None


@dataclass(frozen=True, slots=True)
class InteractionView:
    interaction_id: str
    phase: str
    question: str


@dataclass(frozen=True, slots=True)
class ApprovalView:
    approval_id: str
    tool_name: str
    category: str
    risk_level: str
    reason: str
    targets: tuple[str, ...]
    diff_preview: str


@dataclass(frozen=True, slots=True)
class ArtifactView:
    name: str
    content: str
    char_count: int
    truncated: bool


@dataclass(frozen=True, slots=True)
class DiffFileView:
    path: str
    change_type: str
    drifted: bool
    binary: bool
    unified_diff: str
    truncated: bool


@dataclass(frozen=True, slots=True)
class DiffView:
    task_id: str
    scope: str
    checkpoint_ids: tuple[str, ...]
    files: tuple[DiffFileView, ...]
    truncated: bool
    risks: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TestReportView:
    status: str
    command: str | None
    passed_count: int | None
    failed_count: int | None
    content: str
    truncated: bool


@dataclass(frozen=True, slots=True)
class CheckpointView:
    checkpoint_id: str
    phase: str
    reason: str
    created_at: str
    status: str
    files: tuple[str, ...]
    rollback_available: bool


@dataclass(frozen=True, slots=True)
class CheckpointListView:
    checkpoints: tuple[CheckpointView, ...]


@dataclass(frozen=True, slots=True)
class RequirementCoverageView:
    requirement_id: str
    status: str
    evidence: str
    risk: str | None
    is_core: bool


@dataclass(frozen=True, slots=True)
class DeliveryView:
    status: str
    blockers: tuple[str, ...]
    latest_test_status: str
    latest_build_status: str
    requirement_coverage: tuple[RequirementCoverageView, ...]
    knowledge_count: int
    artifacts: tuple[tuple[str, bool], ...]
    export_ready: bool


@dataclass(frozen=True, slots=True)
class ExportResultView:
    task_id: str
    output_dir: str
    artifacts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RollbackView:
    checkpoint_id: str | None
    available: bool
    files: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BuildView:
    command: str
    status: str
    exit_code: int | None
    timed_out: bool


def present_build(summary: BuildSummary) -> BuildView:
    return BuildView(
        command=_text(summary.command),
        status=_text(summary.status),
        exit_code=summary.exit_code,
        timed_out=summary.timed_out,
    )


def present_task(summary: TaskSummary) -> TaskOverviewView:
    return TaskOverviewView(
        task_id=_text(summary.task_id),
        goal=_text(summary.goal or ""),
        status=summary.status.value,
        current_phase=summary.current_phase.value,
        retry_budget_remaining=summary.retry_budget_remaining,
        latest_test_status=_text(summary.latest_test_status),
        latest_build_status=_text(summary.latest_build_status),
        builds_run=_texts(summary.builds_run),
        files_changed=_texts(summary.files_changed, path=True),
        tests_run=_texts(summary.tests_run),
        latest_checkpoint=(
            None if summary.latest_checkpoint is None else _text(summary.latest_checkpoint)
        ),
        rollback_required=summary.rollback_required,
        inconsistent=summary.inconsistent,
        artifacts=tuple(
            (_text(name), bool(present))
            for name, present in list(summary.artifacts.items())[:MAX_VIEW_ITEMS]
        ),
        resumable=summary.resumable,
        requires_input=summary.requires_input,
        requires_approval=summary.requires_approval,
    )


def present_trace_event(event: TraceEvent) -> ActivityItemView:
    tool_name = _tool_name(event.action)
    label = _EVENT_LABELS.get(event.event_type, event.event_type)
    if tool_name:
        label = f"{label} {tool_name}"
    return ActivityItemView(
        event_id=_text(event.event_id),
        seq=event.seq,
        event_type=_text(event.event_type),
        phase=event.phase.value,
        status=_text(event.status),
        label=_text(label),
        tool_name=tool_name,
    )


def present_event_detail(event: TraceEvent) -> EventDetailView:
    target = None
    if event.action is not None:
        raw_target = event.action.get("path") or event.action.get("target_path")
        if isinstance(raw_target, str):
            target = _path(raw_target)
    return EventDetailView(
        event_id=_text(event.event_id),
        seq=event.seq,
        event_type=_text(event.event_type),
        phase=event.phase.value,
        status=_text(event.status),
        tool_name=_tool_name(event.action),
        target_path=target,
        error_summary=(
            None if event.error_summary is None else _text(event.error_summary)
        ),
    )


def present_interaction(summary: TaskSummary) -> InteractionView | None:
    pending = summary.pending_interaction
    if not summary.requires_input or pending is None:
        return None
    interaction_id = pending.get("interaction_id")
    phase = pending.get("phase")
    question = pending.get("question")
    if not all(isinstance(value, str) for value in (interaction_id, phase, question)):
        return None
    return InteractionView(
        interaction_id=_text(interaction_id),
        phase=_text(phase),
        question=_text(question),
    )


def present_approval(summary: TaskSummary) -> ApprovalView | None:
    pending = summary.pending_approval
    if not summary.requires_approval or pending is None:
        return None
    return present_approval_detail(pending)


def present_approval_detail(detail: Mapping[str, object]) -> ApprovalView | None:
    approval_id = detail.get("approval_id")
    if not isinstance(approval_id, str):
        return None
    preview = detail.get("preview")
    if not isinstance(preview, Mapping):
        preview = {}
    raw_diff = preview.get("unified_diff") or detail.get("diff_preview")
    raw_targets = detail.get("targets", ())
    targets = raw_targets if isinstance(raw_targets, (list, tuple)) else ()
    return ApprovalView(
        approval_id=_text(approval_id),
        tool_name=_text(_value(detail, "tool_name")),
        category=_text(_value(detail, "category")),
        risk_level=_text(_value(detail, "risk_level")),
        reason=_text(_value(detail, "reason")),
        targets=_paths(targets),
        diff_preview=_text(raw_diff),
    )


def present_artifact(preview: ArtifactPreview) -> ArtifactView:
    return ArtifactView(
        name=_text(preview.name),
        content=_text(preview.content),
        char_count=preview.char_count,
        truncated=preview.truncated,
    )


def present_diff(diff: TaskDiff) -> DiffView:
    return DiffView(
        task_id=_text(diff.task_id),
        scope=diff.scope.value,
        checkpoint_ids=_texts(diff.checkpoint_ids),
        files=tuple(
            DiffFileView(
                path=_path(file.path),
                change_type=file.change_type.value,
                drifted=file.drifted,
                binary=file.binary,
                unified_diff=_text(file.unified_diff or ""),
                truncated=file.truncated,
            )
            for file in diff.files[:MAX_VIEW_ITEMS]
        ),
        truncated=diff.truncated,
        risks=_texts(diff.risks),
    )


def present_test_report(report: TestReportSummary) -> TestReportView:
    return TestReportView(
        status=_text(report.status),
        command=None if report.command is None else _text(report.command),
        passed_count=report.passed_count,
        failed_count=report.failed_count,
        content=_text(report.content),
        truncated=report.truncated,
    )


def present_checkpoints(
    checkpoints: tuple[CheckpointSummary, ...],
) -> CheckpointListView:
    return CheckpointListView(
        checkpoints=tuple(
            CheckpointView(
                checkpoint_id=_text(item.checkpoint_id),
                phase=item.phase.value,
                reason=_text(item.reason),
                created_at=_text(item.created_at),
                status=_text(item.status),
                files=_texts(item.files, path=True),
                rollback_available=item.rollback_available,
            )
            for item in checkpoints[:MAX_VIEW_ITEMS]
        )
    )


def present_delivery(
    evidence: DeliveryEvidence | DeliverySummary | None,
    summary: TaskSummary | None = None,
) -> DeliveryView:
    if evidence is None:
        return DeliveryView(
            status="blocked",
            blockers=("delivery evidence unavailable",),
            latest_test_status=(
                "unknown" if summary is None else _text(summary.latest_test_status)
            ),
            latest_build_status=(
                "unknown" if summary is None else _text(summary.latest_build_status)
            ),
            requirement_coverage=(),
            knowledge_count=0,
            artifacts=(),
            export_ready=False,
        )
    if isinstance(evidence, DeliverySummary):
        requirements = tuple(
            RequirementCoverageView(
                requirement_id=_text(item.requirement_id),
                status=item.status.value,
                evidence=_text(item.evidence),
                risk=None if item.risk is None else _text(item.risk),
                is_core=item.is_core,
            )
            for item in evidence.requirements[:MAX_VIEW_ITEMS]
        )
        return DeliveryView(
            status=_text(evidence.status),
            blockers=_texts(evidence.blockers),
            latest_test_status=_text(evidence.latest_test_status),
            latest_build_status=_text(evidence.latest_build_status),
            requirement_coverage=requirements,
            knowledge_count=min(evidence.knowledge_count, MAX_VIEW_ITEMS),
            artifacts=tuple(
                (_text(name), bool(present))
                for name, present in list(evidence.artifacts.items())[:MAX_VIEW_ITEMS]
            ),
            export_ready=evidence.export_ready,
        )
    requirements = tuple(
        RequirementCoverageView(
            requirement_id=_text(item.requirement_id),
            status=item.status.value,
            evidence=_text(item.evidence),
            risk=None if item.risk is None else _text(item.risk),
            is_core=item.is_core,
        )
        for item in evidence.requirements[:MAX_VIEW_ITEMS]
    )
    blockers = list(_texts(evidence.review_risks))
    blockers.extend(
        item.requirement_id
        for item in requirements
        if item.is_core and item.status not in {"covered"}
    )
    artifacts = () if summary is None else tuple(
        (_text(name), bool(present))
        for name, present in list(summary.artifacts.items())[:MAX_VIEW_ITEMS]
    )
    export_ready = bool(artifacts) and not blockers and not (
        summary.inconsistent if summary is not None else False
    )
    status = "ready" if export_ready else "blocked"
    return DeliveryView(
        status=status,
        blockers=tuple(dict.fromkeys(blockers))[:MAX_VIEW_ITEMS],
        latest_test_status=(
            "unknown" if summary is None else _text(summary.latest_test_status)
        ),
        latest_build_status=_text(evidence.latest_build_status),
        requirement_coverage=requirements,
        knowledge_count=min(len(evidence.knowledge_items), MAX_VIEW_ITEMS),
        artifacts=artifacts,
        export_ready=export_ready,
    )


def present_export(result: ExportResult) -> ExportResultView:
    return ExportResultView(
        task_id=_text(result.task_id),
        output_dir=_path(str(result.output_dir)),
        artifacts=_texts(result.artifacts, path=True),
    )


def present_rollback(preview: RollbackPreview) -> RollbackView:
    return RollbackView(
        checkpoint_id=(
            None if preview.checkpoint_id is None else _text(preview.checkpoint_id)
        ),
        available=preview.available,
        files=_texts(preview.files, path=True),
    )


def _value(mapping: Mapping[str, object], key: str) -> object:
    value = mapping.get(key)
    return "" if value is None else value


def _texts(values: tuple[str, ...], *, path: bool = False) -> tuple[str, ...]:
    return tuple(
        (_path(value) if path else _text(value))
        for value in values[:MAX_VIEW_ITEMS]
    )


def _paths(values: tuple[object, ...] | list[object]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values[:MAX_VIEW_ITEMS]:
        if isinstance(value, Mapping):
            value = value.get("path")
        if isinstance(value, str):
            result.append(_path(value))
    return tuple(result)


def _tool_name(action: Mapping[str, object] | None) -> str | None:
    if action is None:
        return None
    value = action.get("tool_name")
    return _text(value) if isinstance(value, str) else None


def _path(value: str) -> str:
    text = _text(value)
    if _WINDOWS_ABSOLUTE_PATH.match(text) or PureWindowsPath(text).is_absolute():
        return "<absolute-path-hidden>"
    return text


def _text(value: object, *, limit: int = MAX_VIEW_TEXT_CHARS) -> str:
    raw = "" if value is None else str(value)
    safe = redact_text(raw)
    safe = "".join(char for char in safe if char in "\n\r\t" or ord(char) >= 32)
    return safe[:limit]


_EVENT_LABELS: dict[str, str] = {
    "task_started": "TASK started",
    "run_started": "RUN started",
    "provider_called": "PROVIDER called",
    "phase_started": "PHASE start",
    "phase_completed": "PHASE done",
    "interaction_requested": "ASK agent asks",
    "interaction_answered": "ASK answer submitted",
    "interaction_resumed": "ASK resumed",
    "tool_called": "TOOL called",
    "tool_completed": "TOOL ok",
    "tool_failed": "TOOL failed",
    "policy_denied": "POLICY denied",
    "source_write_authorized": "WRITE authorized",
    "checkpoint_created": "CKPT created",
    "approval_requested": "APPROVAL requested",
    "approval_consumed": "APPROVAL consumed",
    "test_completed": "TEST completed",
    "test_failed": "TEST failed",
    "feedback_generated": "FEEDBACK generated",
    "retry_budget_consumed": "RETRY consumed",
    "rollback_performed": "ROLLBACK done",
    "deliverable_created": "DELIVERABLE created",
    "run_completed": "RUN completed",
    "task_blocked": "TASK blocked",
}


__all__ = [
    "MAX_VIEW_TEXT_CHARS",
    "MAX_VIEW_ITEMS",
    "DetailKind",
    "TaskOverviewView",
    "ActivityItemView",
    "EventDetailView",
    "InteractionView",
    "ApprovalView",
    "ArtifactView",
    "DiffFileView",
    "DiffView",
    "TestReportView",
    "CheckpointView",
    "CheckpointListView",
    "RequirementCoverageView",
    "DeliveryView",
    "ExportResultView",
    "RollbackView",
    "BuildView",
    "present_task",
    "present_trace_event",
    "present_event_detail",
    "present_interaction",
    "present_approval",
    "present_approval_detail",
    "present_artifact",
    "present_diff",
    "present_test_report",
    "present_checkpoints",
    "present_delivery",
    "present_export",
    "present_rollback",
    "present_build",
]
