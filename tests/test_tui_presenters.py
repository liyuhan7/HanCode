"""S5-R1: typed, bounded TUI presentation models."""

from __future__ import annotations

from datetime import UTC, datetime

from hancode.app.task_models import TaskSummary
from hancode.app.delivery_inspection_service import TestReportSummary as ReportSummary
from hancode.core.change_models import (
    ChangeType,
    CheckpointSummary,
    DiffScope,
    FileDiff,
    TaskDiff,
)
from hancode.core.models import Phase, TaskStatus
from hancode.core.delivery_evidence import (
    DeliveryEvidence,
    KnowledgeCategory,
    KnowledgeItem,
    RequirementCoverage,
    RequirementStatus,
)
from hancode.core.state import TaskState
from hancode.interfaces.tui.presenters import (
    ActivityItemView,
    ApprovalView,
    ArtifactView,
    DetailKind,
    EventDetailView,
    InteractionView,
    TaskOverviewView,
    present_approval,
    present_artifact,
    present_checkpoints,
    present_delivery,
    present_diff,
    present_event_detail,
    present_interaction,
    present_task,
    present_test_report,
    present_trace_event,
)
from hancode.storage.trace import TraceEvent
from hancode.app.inspection_service import ArtifactPreview


def _summary(**overrides: object) -> TaskSummary:
    values: dict[str, object] = {
        "task_id": "task-001",
        "goal": "Implement a task",
        "status": TaskStatus.WAITING_INPUT,
        "current_phase": Phase.CODE,
        "retry_budget_remaining": 2,
        "latest_test_status": "passed",
        "files_changed": ("src/main.py",),
        "tests_run": ("pytest -q",),
        "latest_checkpoint": "ckpt-001",
        "rollback_required": False,
        "inconsistent": False,
        "artifacts": {"TEST_REPORT.md": True},
        "resumable": True,
        "latest_build_status": "passed",
        "builds_run": ("python -m build",),
        "requires_input": True,
        "pending_interaction": {
            "interaction_id": "ask-001",
            "phase": "code",
            "question": "Which implementation should I use?",
        },
        "requires_approval": False,
        "pending_approval": None,
    }
    values.update(overrides)
    return TaskSummary(**values)


def _event(
    event_type: str = "tool_completed",
    *,
    action: dict[str, object] | None = None,
    error_summary: str | None = None,
) -> TraceEvent:
    return TraceEvent(
        event_id="evt-000001",
        seq=1,
        event_type=event_type,
        task_id="task-001",
        phase=Phase.CODE,
        timestamp=datetime(2026, 7, 22, tzinfo=UTC),
        status="succeeded",
        action=action,
        error_summary=error_summary,
    )


def test_task_presenter_includes_build_and_bounded_plain_fields() -> None:
    view = present_task(_summary(goal="x" * 5000, files_changed=tuple(f"src/{i}.py" for i in range(200))) )

    assert isinstance(view, TaskOverviewView)
    assert view.latest_build_status == "passed"
    assert view.builds_run == ("python -m build",)
    assert len(view.goal) <= 4096
    assert len(view.files_changed) == 100


def test_task_summary_from_state_preserves_build_evidence() -> None:
    state = TaskState(
        schema_version=1,
        task_id="task-001",
        goal="Build project",
        status=TaskStatus.CREATED,
        current_phase=Phase.CODE,
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
            "spec": False,
            "plan": False,
            "code": False,
            "test": False,
            "review": False,
            "deliver": False,
        },
        artifacts={
            "SPEC.md": False,
            "PLAN.md": False,
            "TEST_REPORT.md": False,
            "REVIEW.md": False,
            "KNOWLEDGE.md": False,
            "DELIVERABLES.md": False,
        },
        builds_run=("python -m build",),
        latest_build_status="passed",
    )

    summary = TaskSummary.from_state(state)

    assert summary.latest_build_status == "passed"
    assert summary.builds_run == ("python -m build",)


def test_detail_kind_covers_r1_presentation_targets() -> None:
    assert DetailKind.TASK.value == "task"
    assert DetailKind.EVENT.value == "event"
    assert DetailKind.INTERACTION.value == "interaction"
    assert DetailKind.APPROVAL.value == "approval"
    assert DetailKind.ARTIFACT.value == "artifact"


def test_interaction_presenter_returns_bounded_question() -> None:
    view = present_interaction(_summary(pending_interaction={
        "interaction_id": "ask-001",
        "phase": "code",
        "question": "q" * 5000,
    }))

    assert isinstance(view, InteractionView)
    assert view.interaction_id == "ask-001"
    assert len(view.question) <= 4096


def test_approval_presenter_redacts_sensitive_preview_and_targets() -> None:
    summary = _summary(
        status=TaskStatus.WAITING_APPROVAL,
        requires_input=False,
        pending_interaction=None,
        requires_approval=True,
        pending_approval={
            "approval_id": "approval-001",
            "tool_name": "write_file",
            "category": "source_write",
            "risk_level": "high",
            "reason": "write token=secret-value",
            "targets": ["src/main.py", "C:/Users/student/.env"],
            "diff_preview": "Authorization: Bearer secret-value",
        },
    )

    view = present_approval(summary)

    assert isinstance(view, ApprovalView)
    assert view.approval_id == "approval-001"
    assert "secret-value" not in view.reason
    assert "secret-value" not in view.diff_preview
    assert view.targets[0] == "src/main.py"
    assert view.targets[1] == "<absolute-path-hidden>"


def test_trace_presenter_preserves_unknown_event_without_sensitive_text() -> None:
    view = present_trace_event(
        _event(
            "future_event",
            action={"tool_name": "inspect", "token": "secret-value"},
            error_summary="password=secret-value",
        )
    )

    assert isinstance(view, ActivityItemView)
    assert view.event_type == "future_event"
    assert "future_event" in view.label
    assert "secret-value" not in view.label


def test_event_detail_presenter_hides_absolute_path_and_redacts_error() -> None:
    view = present_event_detail(
        _event(
            action={"tool_name": "write_file", "path": "C:/Users/a/.env"},
            error_summary="token=secret-value",
        )
    )

    assert isinstance(view, EventDetailView)
    assert view.target_path == "<absolute-path-hidden>"
    assert view.error_summary is not None
    assert "secret-value" not in view.error_summary


def test_artifact_presenter_keeps_safe_preview_metadata() -> None:
    view = present_artifact(
        ArtifactPreview(
            name="TEST_REPORT.md",
            content="passed",
            char_count=6,
            truncated=False,
        )
    )

    assert isinstance(view, ArtifactView)
    assert view.name == "TEST_REPORT.md"
    assert view.content == "passed"
    assert view.char_count == 6


def test_inspection_presenters_bound_paths_and_content() -> None:
    diff = present_diff(
        TaskDiff(
            task_id="task-001",
            scope=DiffScope.LATEST,
            checkpoint_ids=("ckpt-001",),
            files=(
                FileDiff(
                    path="C:/Users/a/.env",
                    change_type=ChangeType.MODIFIED,
                    before_sha256="before",
                    current_sha256="after",
                    binary=False,
                    drifted=True,
                    unified_diff="token=secret-value" * 500,
                    truncated=True,
                ),
            ),
            truncated=False,
            risks=("password=secret-value",),
        )
    )
    report = present_test_report(
        ReportSummary(
            status="passed",
            command="pytest -q",
            passed_count=3,
            failed_count=0,
            content="Authorization: Bearer secret-value",
            truncated=False,
        )
    )

    assert diff.files[0].path == "<absolute-path-hidden>"
    assert len(diff.files[0].unified_diff) <= 4096
    assert "secret-value" not in diff.files[0].unified_diff
    assert "secret-value" not in diff.risks
    assert "secret-value" not in report.content


def test_checkpoint_and_delivery_presenters_return_safe_view_models() -> None:
    checkpoints = present_checkpoints(
        (
            CheckpointSummary(
                checkpoint_id="ckpt-001",
                phase=Phase.CODE,
                reason="created for C:/Users/a/.env",
                created_at="2026-07-23T00:00:00+00:00",
                status="committed",
                files=("C:/Users/a/.env", "src/main.py"),
                rollback_available=True,
            ),
        )
    )
    delivery = present_delivery(
        DeliveryEvidence(
            task_id="task-001",
            requirements=(
                RequirementCoverage(
                    requirement_id="FR-1",
                    status=RequirementStatus.PARTIAL,
                    evidence="token=secret-value",
                    risk="password=secret-value",
                    is_core=True,
                ),
            ),
            knowledge_items=(
                KnowledgeItem(
                    category=KnowledgeCategory.OTHER,
                    summary="summary",
                    detail="detail",
                    source_trace_id=None,
                ),
            ),
            review_risks=(),
            latest_test_report_sha256="test",
            latest_diff_sha256="diff",
            latest_build_status="passed",
        ),
        _summary(artifacts={"TEST_REPORT.md": True}),
    )

    assert checkpoints.checkpoints[0].files[0] == "<absolute-path-hidden>"
    assert "secret-value" not in checkpoints.checkpoints[0].reason
    assert delivery.status == "blocked"
    assert delivery.blockers == ("FR-1",)
    assert "secret-value" not in delivery.requirement_coverage[0].evidence
