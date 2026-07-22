"""DeliveryInspectionService — structured test report parsing (S4-R3)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from hancode.core.errors import HanCodeError, StructuredError
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
