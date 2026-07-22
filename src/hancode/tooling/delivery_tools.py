"""Delivery tools — read_test_report (S4-R3)."""

from __future__ import annotations

import re
from pathlib import Path

from hancode.core.state import load_state, reconcile_state
from hancode.tooling.registry import ToolResult


def _is_link(path: Path) -> bool:
    try:
        is_junction = getattr(path, "is_junction", None)
        return path.is_symlink() or bool(is_junction and is_junction())
    except (AttributeError, OSError, RuntimeError):
        return True


def read_test_report(project_root: Path, task_root: Path) -> ToolResult:
    """Read the TEST_REPORT.md artifact with structured parsing."""
    project_root = project_root.resolve()
    task_root = task_root.resolve()
    state = reconcile_state(task_root, load_state(task_root))

    if not state.artifacts.get("TEST_REPORT.md"):
        return ToolResult(
            success=False,
            action_name="read_test_report",
            error_summary="TEST_REPORT.md is not present in task artifacts.",
        )

    report_path = task_root / "TEST_REPORT.md"
    resolved = report_path.resolve()
    if resolved.parent != task_root.resolve():
        return ToolResult(
            success=False,
            action_name="read_test_report",
            error_summary="TEST_REPORT.md is outside the task workspace.",
        )

    if _is_link(report_path):
        return ToolResult(
            success=False,
            action_name="read_test_report",
            error_summary="TEST_REPORT.md must not be a symlink or junction.",
        )

    if not report_path.is_file():
        return ToolResult(
            success=False,
            action_name="read_test_report",
            error_summary="TEST_REPORT.md is not a regular file.",
        )

    try:
        content = report_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ToolResult(
            success=False,
            action_name="read_test_report",
            error_summary="TEST_REPORT.md cannot be read.",
        )

    # Parse structured counts
    status = _parse_status(content)
    passed_count = _parse_count(content, "passed")
    failed_count = _parse_count(content, "failed")
    command = _parse_command(content)

    return ToolResult(
        success=True,
        action_name="read_test_report",
        output={
            "status": status,
            "command": command,
            "passed_count": passed_count,
            "failed_count": failed_count,
            "content": content,
            "truncated": False,
        },
    )


def _parse_status(content: str) -> str:
    if "failed" in content.lower():
        return "failed"
    if "passed" in content.lower() or "通过" in content:
        return "passed"
    return "unknown"


def _parse_count(content: str, label: str) -> int | None:
    pattern = rf"{label}[:\s]+(\d+)"
    m = re.search(pattern, content, re.IGNORECASE)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


def _parse_command(content: str) -> str | None:
    m = re.search(r"(?:[Cc]ommand|测试命令).*?`([^`]+)`", content)
    if m:
        return m.group(1).strip()
    return None
