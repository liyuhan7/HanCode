"""DeliveryInspectionService — structured test report parsing (S4-R3)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from hancode.core.config import load_config
from hancode.core.delivery_evidence import RequirementCoverage
from hancode.core.errors import HanCodeError, StructuredError
from hancode.core.models import TaskStatus
from hancode.core.state import load_state, reconcile_state
from hancode.runtime.delivery_pipeline import (
    _delivery_blockers,
    _delivery_status,
    _empty_evidence,
)
from hancode.storage.delivery_evidence import DeliveryEvidenceStore
from hancode.storage.workspace import task_path
from hancode.tooling.delivery_tools import read_test_report


@dataclass(frozen=True, slots=True)
class TestReportSummary:
    status: str
    command: str | None
    passed_count: int | None
    failed_count: int | None
    content: str
    truncated: bool


@dataclass(frozen=True, slots=True)
class DeliverySummary:
    task_id: str
    status: str
    blockers: tuple[str, ...]
    latest_test_status: str
    latest_build_status: str
    requirements: tuple[RequirementCoverage, ...]
    knowledge_count: int
    artifacts: Mapping[str, bool]
    export_ready: bool


class DeliveryInspectionService:
    """Read and parse TEST_REPORT.md through the safe read_test_report tool."""

    def read_test_report(
        self,
        project_root: Path,
        task_id: str,
    ) -> TestReportSummary:
        task_root = task_path(project_root, task_id)
        result = read_test_report(project_root, task_root)
        if not result.success:
            raise HanCodeError(
                StructuredError(
                    error_code="delivery_test_report_unavailable",
                    message=result.error_summary or "Test report is not available.",
                    phase="test",
                    denied_rule="test_report_required",
                    suggested_fix="Run tests first to generate a test report.",
                )
            )
        output = result.output
        if not isinstance(output, dict):
            raise HanCodeError(
                StructuredError(
                    error_code="delivery_test_report_invalid",
                    message="Test report returned an invalid result.",
                    phase="test",
                    denied_rule="test_report_required",
                    suggested_fix="Regenerate the test report by running tests.",
                )
            )
        return TestReportSummary(
            status=str(output.get("status", "unknown")),
            command=output.get("command") if isinstance(output.get("command"), str) else None,
            passed_count=output.get("passed_count") if isinstance(output.get("passed_count"), int) else None,
            failed_count=output.get("failed_count") if isinstance(output.get("failed_count"), int) else None,
            content=str(output.get("content", "")),
            truncated=bool(output.get("truncated", False)),
        )

    def read_delivery_summary(
        self,
        project_root: Path,
        task_id: str,
    ) -> DeliverySummary:
        """Read the delivery gate inputs without generating any artifact."""
        task_root = task_path(project_root, task_id)
        state = reconcile_state(task_root, load_state(task_root))
        evidence = DeliveryEvidenceStore().load(task_root) or _empty_evidence(task_id)
        config = load_config(project_root, task_id)
        blockers = _delivery_blockers(
            state,
            evidence,
            build_required=config.build_command is not None,
        )
        status = _delivery_status(state, blockers)
        export_ready = status is TaskStatus.COMPLETED and state.status is TaskStatus.COMPLETED
        return DeliverySummary(
            task_id=task_id,
            status=status.value,
            blockers=blockers,
            latest_test_status=state.latest_test_status,
            latest_build_status=evidence.latest_build_status,
            requirements=evidence.requirements,
            knowledge_count=len(evidence.knowledge_items),
            artifacts=dict(state.artifacts),
            export_ready=export_ready,
        )
