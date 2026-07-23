"""Read-only DeliverySummary gate decisions for the TUI."""

from __future__ import annotations

from pathlib import Path

from hancode.app.delivery_inspection_service import DeliveryInspectionService
from hancode.storage.workspace import init_project_workspace, init_task_workspace


def test_delivery_summary_blocks_when_required_artifacts_are_missing(tmp_path: Path) -> None:
    init_project_workspace(tmp_path, "project-001", "Course", "Assignment")
    init_task_workspace(tmp_path, "task-001", goal="Inspect delivery")

    summary = DeliveryInspectionService().read_delivery_summary(tmp_path, "task-001")

    assert summary.status == "blocked"
    assert summary.export_ready is False
    assert any("REVIEW.md" in blocker for blocker in summary.blockers)
    assert any("KNOWLEDGE.md" in blocker for blocker in summary.blockers)
