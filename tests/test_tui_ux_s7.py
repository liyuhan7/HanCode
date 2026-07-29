"""Post-implementation regression coverage for S7 TUI UX behavior."""

from __future__ import annotations

from datetime import UTC, datetime

from hancode.app.delivery_inspection_service import TestReportSummary as ReportSummary
from hancode.core.models import Phase
from hancode.interfaces.tui.commands import parse_command
from hancode.interfaces.tui.presenters import present_test_report
from hancode.interfaces.tui.semantic_presenters import present_activity_groups
from hancode.interfaces.tui.themes import DARK_THEME_NAME, LIGHT_THEME_NAME, alternate_theme
from hancode.interfaces.tui.widgets.phase_bar import render_phase_bar
from hancode.storage.trace import TraceEvent


def _event(seq: int, event_type: str, *, tool_name: str | None = None) -> TraceEvent:
    action = None if tool_name is None else {"tool_name": tool_name, "args": {}, "reason": "test"}
    return TraceEvent(
        event_id=f"evt-{seq:06d}",
        seq=seq,
        event_type=event_type,
        task_id="task-001",
        phase=Phase.TEST,
        timestamp=datetime.now(UTC),
        status="succeeded",
        action=action,
    )


def test_s7_commands_accept_only_frozen_modes() -> None:
    assert parse_command("/view inspect").name == "view"  # type: ignore[union-attr]
    assert parse_command("/theme light").name == "theme"  # type: ignore[union-attr]
    assert parse_command("/view raw").error_code == "tui_view_mode_invalid"  # type: ignore[union-attr]
    assert parse_command("/theme solarized").error_code == "tui_theme_invalid"  # type: ignore[union-attr]


def test_s7_activity_groups_reads_and_test_result() -> None:
    groups = present_activity_groups(
        (
            _event(1, "tool_called", tool_name="read_file"),
            _event(2, "tool_called", tool_name="search_text"),
            _event(3, "tool_called", tool_name="run_tests"),
            _event(4, "test_completed"),
        )
    )
    assert groups[0].title == "已检查 2 个位置"
    assert groups[1].title == "测试通过"


def test_s7_test_report_exposes_only_persisted_summary_fields() -> None:
    view = present_test_report(
        ReportSummary(
            status="failed",
            command="pytest -q",
            passed_count=3,
            failed_count=1,
            content="# 测试报告",
            truncated=False,
            failure_category="assertion_failure",
            summary="1 failed, 3 passed",
            next_action_hint="Inspect the failing assertion.",
        )
    )
    assert view.failure_category == "assertion_failure"
    assert view.summary == "1 failed, 3 passed"
    assert view.next_action_hint == "Inspect the failing assertion."


def test_s7_theme_cycle_and_chinese_empty_phase_bar() -> None:
    assert alternate_theme(DARK_THEME_NAME) == LIGHT_THEME_NAME
    assert alternate_theme(LIGHT_THEME_NAME) == DARK_THEME_NAME
    assert "需求分析" in render_phase_bar(None)
