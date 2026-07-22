"""Delivery tools — read_test_report (S4-R3)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

from hancode.core.delivery_evidence import (
    KnowledgeCategory,
    KnowledgeItem,
    RequirementCoverage,
    RequirementStatus,
)
from hancode.core.state import load_state, reconcile_state
from hancode.tooling.file_tools import redact_text
from hancode.tooling.registry import ToolResult


_MAX_REPORT_CHARS = 12_000


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
        raw_content = report_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ToolResult(
            success=False,
            action_name="read_test_report",
            error_summary="TEST_REPORT.md cannot be read.",
        )

    content = redact_text(raw_content)
    status = _parse_status(content)
    passed_count = _parse_count(content, "passed")
    failed_count = _parse_count(content, "failed")
    command = _parse_command(content)
    truncated = len(content) > _MAX_REPORT_CHARS
    bounded_content = (
        content[:_MAX_REPORT_CHARS] + "\n...[TRUNCATED]"
        if truncated
        else content
    )

    return ToolResult(
        success=True,
        action_name="read_test_report",
        output={
            "status": status,
            "command": command,
            "passed_count": passed_count,
            "failed_count": failed_count,
            "content": bounded_content,
            "truncated": truncated,
        },
    )


def _parse_status(content: str) -> str:
    if "failed" in content.lower():
        return "failed"
    if "passed" in content.lower() or "通过" in content:
        return "passed"
    return "unknown"


def _parse_count(content: str, label: str) -> int | None:
    patterns = [rf"{label}[:\s]+(\d+)"]
    if label == "passed":
        patterns.append(r"通过数\s*\|\s*(\d+)")
    if label == "failed":
        patterns.append(r"失败数\s*\|\s*(\d+)")
    m = next(
        (re.search(pattern, content, re.IGNORECASE) for pattern in patterns),
        None,
    )
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    table_numbers = [
        int(match.group(1))
        for line in content.splitlines()
        for match in [re.fullmatch(r"\s*\|\s*[^|]+\|\s*(\d+)\s*\|?\s*", line)]
        if match is not None
    ]
    if len(table_numbers) >= 2:
        return table_numbers[-2] if label == "passed" else table_numbers[-1]
    return None


def _parse_command(content: str) -> str | None:
    m = re.search(r"(?:[Cc]ommand|测试命令|命令)\s*\|\s*`([^`]+)`", content)
    if m is None:
        m = re.search(r"\|\s*[^|]+\|\s*`([^`]+)`\s*\|", content)
    if m:
        return m.group(1).strip()
    return None


def record_review(
    project_root: Path,
    task_id: str,
    requirements: object,
    risks: object = (),
) -> ToolResult:
    from hancode.app.delivery_service import DeliveryService

    parsed_requirements = _parse_requirements(requirements)
    parsed_risks = _parse_risks(risks)
    if parsed_requirements is None or parsed_risks is None:
        return _invalid_delivery_input("record_review", "Review evidence has an invalid shape.")
    DeliveryService().record_review(project_root, task_id, parsed_requirements, parsed_risks)
    return ToolResult(
        success=True,
        action_name="record_review",
        output={"artifact": "REVIEW.md"},
    )


def record_knowledge(
    project_root: Path,
    task_id: str,
    items: object,
) -> ToolResult:
    from hancode.app.delivery_service import DeliveryService

    parsed_items = _parse_knowledge_items(items)
    if parsed_items is None:
        return _invalid_delivery_input(
            "record_knowledge", "Knowledge evidence has an invalid shape."
        )
    DeliveryService().record_knowledge(project_root, task_id, parsed_items)
    return ToolResult(
        success=True,
        action_name="record_knowledge",
        output={"artifact": "KNOWLEDGE.md"},
    )


def _parse_requirements(value: object) -> list[RequirementCoverage] | None:
    if not isinstance(value, list):
        return None
    parsed: list[RequirementCoverage] = []
    for item in value:
        if not isinstance(item, Mapping):
            return None
        requirement_id = item.get("requirement_id")
        status = item.get("status")
        evidence = item.get("evidence", "")
        risk = item.get("risk")
        is_core = item.get("is_core", False)
        if (
            not isinstance(requirement_id, str)
            or not requirement_id.strip()
            or not isinstance(status, str)
            or not isinstance(evidence, str)
            or (risk is not None and not isinstance(risk, str))
            or not isinstance(is_core, bool)
        ):
            return None
        try:
            requirement_status = RequirementStatus(status)
        except ValueError:
            return None
        parsed.append(
            RequirementCoverage(
                requirement_id=requirement_id,
                status=requirement_status,
                evidence=evidence,
                risk=risk,
                is_core=is_core,
            )
        )
    return parsed


def _parse_risks(value: object) -> list[str] | None:
    if not isinstance(value, list) or any(
        not isinstance(item, str) for item in value
    ):
        return None
    return list(value)


def _parse_knowledge_items(value: object) -> list[KnowledgeItem] | None:
    if not isinstance(value, list):
        return None
    parsed: list[KnowledgeItem] = []
    for item in value:
        if not isinstance(item, Mapping):
            return None
        category = item.get("category")
        summary = item.get("summary")
        detail = item.get("detail")
        source_trace_id = item.get("source_trace_id")
        if (
            not isinstance(category, str)
            or not isinstance(summary, str)
            or not isinstance(detail, str)
            or (source_trace_id is not None and not isinstance(source_trace_id, str))
        ):
            return None
        try:
            knowledge_category = KnowledgeCategory(category)
        except ValueError:
            return None
        parsed.append(
            KnowledgeItem(
                category=knowledge_category,
                summary=summary,
                detail=detail,
                source_trace_id=source_trace_id,
            )
        )
    return parsed


def _invalid_delivery_input(action_name: str, message: str) -> ToolResult:
    return ToolResult(success=False, action_name=action_name, error_summary=message)
