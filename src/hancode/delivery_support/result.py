"""Deterministic generation of task delivery artifacts."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import re
from tempfile import mkstemp
from typing import Callable, Iterable, Sequence

from hancode.runtime.agent_loop import AgentRunResult
from hancode.core.errors import HanCodeError, StructuredError
from hancode.runtime.feedback import FeedbackReport
from hancode.tooling.file_tools import redact_text
from hancode.core.models import Phase, Risk, TaskStatus
from hancode.core.state import TaskState, load_state, reconcile_state, save_state


_BASIC_AUTHORIZATION_SECRET = re.compile(
    r"(?im)(authorization\s*:\s*basic\s+)[^\s,;]+"
)


class RequirementStatus(str, Enum):
    COVERED = "covered"
    PARTIAL = "partial"
    NOT_COVERED = "not_covered"
    MISSING = "missing"
    UNTESTED = "untested"


class KnowledgeCategory(str, Enum):
    REQUIREMENT_UNDERSTANDING = "requirement_understanding"
    DESIGN_DECISION = "design_decision"
    TESTING_EXPERIENCE = "testing_experience"
    ERROR_FIX = "error_fix"
    REUSABLE_PATTERN = "reusable_pattern"
    BUG_FIX = "bug_fix"
    TEST_INSIGHT = "test_insight"
    PROCESS_IMPROVEMENT = "process_improvement"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class RequirementCoverage:
    requirement_id: str
    status: RequirementStatus
    evidence: str
    risk: str | None
    is_core: bool


@dataclass(frozen=True, slots=True)
class KnowledgeItem:
    category: KnowledgeCategory
    summary: str
    detail: str
    source_phase: Phase = Phase.DELIVER
    source_trace_id: str | None = None


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    status: TaskStatus
    task_id: str
    course_project_summary: str
    requirements_coverage: tuple[RequirementCoverage, ...]
    files_changed: tuple[str, ...]
    tests_run: tuple[str, ...]
    latest_test_status: str
    latest_checkpoint: str | None
    rollback_done: bool
    deliverables: tuple[str, ...]
    knowledge_items: tuple[KnowledgeItem, ...]
    trace_event_ids: tuple[str, ...]
    risks: tuple[Risk, ...]
    next_steps: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        coverage = tuple(_sanitize_coverage(item) for item in self.requirements_coverage)
        knowledge_items = tuple(
            _sanitize_knowledge_item(item) for item in self.knowledge_items
        )
        risks = tuple(_sanitize_risk(risk) for risk in self.risks)
        return {
            "status": self.status.value,
            "task_id": _redacted_text(self.task_id),
            "course_project_summary": _redacted_text(self.course_project_summary),
            "requirements_covered": [
                _coverage_to_dict(item) for item in coverage
            ],
            "files_changed": [_redacted_text(value) for value in self.files_changed],
            "tests_run": [_redacted_text(value) for value in self.tests_run],
            "test_status": _redacted_text(self.latest_test_status),
            "checkpoints": (
                []
                if self.latest_checkpoint is None
                else [_redacted_text(self.latest_checkpoint)]
            ),
            "rollback_performed": self.rollback_done,
            "deliverables": [_redacted_text(value) for value in self.deliverables],
            "knowledge_items": [
                _knowledge_item_to_dict(item) for item in knowledge_items
            ],
            "trace_event_ids": [_redacted_text(value) for value in self.trace_event_ids],
            "risks": [risk.to_dict() for risk in risks],
            "next_steps": [_redacted_text(value) for value in self.next_steps],
        }


class ResultBuilder:
    """Build the final deterministic result from authoritative task state."""

    def build(
        self,
        task_root: Path,
        run_result: AgentRunResult,
        coverage: Sequence[RequirementCoverage] = (),
        knowledge_items: Sequence[KnowledgeItem] = (),
    ) -> DeliveryResult:
        root = _task_root(task_root)
        state = reconcile_state(root, load_state(root))
        sanitized_coverage = tuple(_sanitize_coverage(item) for item in coverage)
        sanitized_knowledge_items = tuple(
            _sanitize_knowledge_item(item) for item in knowledge_items
        )
        risks = [_sanitize_risk(risk) for risk in run_result.risks]
        blockers = _delivery_blockers(state, coverage)
        risks.extend(Risk(level="high", message=message) for message in blockers)
        risks.extend(_non_core_risks(coverage))
        status = _final_status(state, blockers)
        return DeliveryResult(
            status=status,
            task_id=_redacted_text(state.task_id),
            course_project_summary=_redacted_text(
                state.goal or "No task goal recorded."
            ),
            requirements_coverage=sanitized_coverage,
            files_changed=tuple(_redacted_text(path) for path in state.files_changed),
            tests_run=tuple(_redacted_text(command) for command in state.tests_run),
            latest_test_status=state.latest_test_status,
            latest_checkpoint=(
                None
                if state.latest_checkpoint is None
                else _redacted_text(state.latest_checkpoint)
            ),
            rollback_done=state.rollback_done,
            deliverables=tuple(
                artifact for artifact, present in state.artifacts.items() if present
            ),
            knowledge_items=sanitized_knowledge_items,
            trace_event_ids=tuple(
                _redacted_text(event.event_id) for event in run_result.trace_events
            ),
            risks=tuple(_sanitize_risk(risk) for risk in risks),
            next_steps=tuple(
                _redacted_text(step) for step in _next_steps(status, blockers)
            ),
        )


def _write_test_report_impl(task_root: Path, report: FeedbackReport, command: str) -> Path:
    if not isinstance(command, str) or not command.strip():
        raise _delivery_error(
            "delivery_command_required",
            "Test report generation requires a non-empty test command.",
            "Provide the configured test command used to produce the feedback.",
        )
    status = "passed" if report.passed else "failed"
    content = (
        "# 测试报告\n\n"
        "| 字段 | 值 |\n"
        "| --- | --- |\n"
        f"| 命令 | `{_cell(command)}` |\n"
        f"| 状态 | {status} |\n"
        f"| 失败分类 | {report.failure_category.value} |\n"
        f"| 通过数 | {report.passed_count} |\n"
        f"| 失败数 | {report.failed_count} |\n\n"
        "## 摘要\n\n"
        f"{_markdown_literal(report.summary)}\n\n"
        "## 下一步\n\n"
        f"{_markdown_literal(report.next_action_hint)}\n"
    )
    return _write_artifact(task_root, "TEST_REPORT.md", content)


def _write_review_impl(
    task_root: Path,
    coverage: list[RequirementCoverage],
    risks: list[str],
) -> Path:
    _require_items(coverage, "delivery_requirement_coverage_required", "requirement coverage")
    rows = "".join(
        f"| {_cell(item.requirement_id)} | {item.status.value} | "
        f"{_cell(item.evidence)} | {_cell(item.risk or 'None.')} |\n"
        for item in coverage
    )
    risk_lines = "\n".join(f"- {_markdown_literal(risk)}" for risk in risks) or "- None."
    content = (
        "# 审查记录\n\n"
        "## 需求覆盖\n\n"
        "| 需求 | 状态 | 证据 | 风险 |\n"
        "| --- | --- | --- | --- |\n"
        f"{rows}\n"
        "## 审查风险\n\n"
        f"{risk_lines}\n"
    )
    return _write_artifact(task_root, "REVIEW.md", content)


def _write_knowledge_impl(task_root: Path, items: list[KnowledgeItem]) -> Path:
    _require_items(items, "delivery_knowledge_items_required", "knowledge items")
    sections = (
        (KnowledgeCategory.REQUIREMENT_UNDERSTANDING, "需求理解"),
        (KnowledgeCategory.DESIGN_DECISION, "设计决策"),
        (KnowledgeCategory.TESTING_EXPERIENCE, "测试经验"),
        (KnowledgeCategory.ERROR_FIX, "错误修复"),
        (KnowledgeCategory.REUSABLE_PATTERN, "可复用模式"),
    )
    grouped = {category: [item for item in items if item.category is category] for category, _ in sections}
    missing = [title for category, title in sections if not grouped[category]]
    if missing:
        raise _delivery_error(
            "delivery_knowledge_categories_required",
            "Knowledge delivery requires every required category.",
            f"Add entries for: {', '.join(missing)}.",
        )
    if not any(
        isinstance(item.source_trace_id, str) and item.source_trace_id.strip()
        for item in items
    ):
        raise _delivery_error(
            "delivery_knowledge_provenance_required",
            "Knowledge delivery requires at least one trace reference.",
            "Provide a non-empty source_trace_id for at least one knowledge item.",
        )
    body = "# 知识沉淀\n"
    for category, title in sections:
        body += f"\n## {title}\n\n"
        for item in grouped[category]:
            body += (
                f"### {_markdown_literal(item.summary)}\n\n"
                f"{_markdown_literal(item.detail)}\n\n"
                f"来源：{item.source_phase.value} / "
                f"{_markdown_literal(item.source_trace_id or '未提供')}\n"
            )
    return _write_artifact(task_root, "KNOWLEDGE.md", body)


def _write_deliverables_impl(
    task_root: Path,
    result: AgentRunResult,
    coverage: Sequence[RequirementCoverage] = (),
) -> Path:
    if not isinstance(result, AgentRunResult):
        raise _delivery_error(
            "delivery_result_invalid",
            "Deliverables generation requires an AgentRunResult.",
            "Pass the deterministic result returned by AgentLoop.",
        )
    root = _task_root(task_root)
    state = _load_consistent_state(root)
    coverage_digest = _coverage_digest(coverage)
    prospective_artifacts = dict(state.artifacts)
    prospective_artifacts["DELIVERABLES.md"] = True
    prospective_state = replace(
        state,
        artifacts=prospective_artifacts,
        delivery_coverage_digest=coverage_digest,
    )
    blockers = _delivery_blockers(prospective_state, coverage)
    status = _final_status(prospective_state, blockers)
    artifacts = "".join(
        f"| {artifact} | {'present' if present else 'missing'} |\n"
        for artifact, present in prospective_state.artifacts.items()
    )
    risk_messages = [risk.message for risk in result.risks] + list(blockers)
    risks = "\n".join(f"- {_markdown_literal(message)}" for message in risk_messages) or "- None."
    content = (
        "# 交付清单\n\n"
        "## 交付物\n\n"
        "| 文件 | 状态 |\n"
        "| --- | --- |\n"
        f"{artifacts}\n"
        "## 测试状态\n\n"
        f"- {prospective_state.latest_test_status}\n\n"
        "## 风险\n\n"
        f"{risks}\n\n"
        "## 最终状态\n\n"
        f"- {status.value}\n"
    )
    return _write_artifact(
        root,
        "DELIVERABLES.md",
        content,
        state_transform=lambda current: replace(
            current,
            status=status,
            delivery_coverage_digest=coverage_digest,
        ),
    )


def _delivery_blockers(
    state: TaskState, coverage: Sequence[RequirementCoverage]
) -> tuple[str, ...]:
    blockers: list[str] = []
    if state.files_changed and not state.tests_run:
        blockers.append("业务代码已变更，但没有测试记录。")
    if state.latest_test_status == "failed":
        blockers.append("测试失败，任务不能交付。")
    elif state.latest_test_status != "passed":
        blockers.append("缺少通过的测试结果。")
    for artifact in ("TEST_REPORT.md", "REVIEW.md", "KNOWLEDGE.md", "DELIVERABLES.md"):
        if not state.artifacts[artifact]:
            blockers.append(f"缺少必需交付物：{artifact}。")
    core_coverage = [item for item in coverage if item.is_core]
    if not core_coverage:
        blockers.append("缺少核心需求覆盖证据。")
    for item in core_coverage:
        if item.status is not RequirementStatus.COVERED or not item.evidence.strip():
            blockers.append(f"核心需求未覆盖：{item.requirement_id}。")
    if (
        state.artifacts["DELIVERABLES.md"]
        and state.delivery_coverage_digest != _coverage_digest(coverage)
    ):
        blockers.append("需求覆盖与已持久化交付回执不一致。")
    return tuple(blockers)


def _final_status(state: TaskState, blockers: Sequence[str]) -> TaskStatus:
    if state.inconsistent or state.status is TaskStatus.INCONSISTENT:
        return TaskStatus.INCONSISTENT
    if state.status is TaskStatus.FAILED:
        return TaskStatus.FAILED
    if state.status is TaskStatus.BLOCKED:
        return TaskStatus.BLOCKED
    return TaskStatus.BLOCKED if blockers else TaskStatus.COMPLETED


def _non_core_risks(coverage: Sequence[RequirementCoverage]) -> Iterable[Risk]:
    for item in coverage:
        if not item.is_core and item.status is not RequirementStatus.COVERED:
            yield Risk(
                level="medium",
                message=(
                    f"非核心需求未完全验证：{item.requirement_id} "
                    f"({item.status.value})。"
                ),
                mitigation=item.risk or "Record evidence before a later delivery.",
            )


def _next_steps(status: TaskStatus, blockers: Sequence[str]) -> tuple[str, ...]:
    if status is TaskStatus.COMPLETED:
        return ()
    if status is TaskStatus.INCONSISTENT:
        return ("修复任务产物与状态一致性后再继续。",)
    if status is TaskStatus.FAILED:
        return ("检查结构化失败信息后再重试。",)
    return tuple(blockers)


def _write_artifact(
    task_root: Path,
    filename: str,
    content: str,
    state_transform: Callable[[TaskState], TaskState] | None = None,
) -> Path:
    root = _task_root(task_root)
    state = _load_consistent_state(root)
    target = root / filename
    if _is_link(target):
        raise _delivery_error(
            "delivery_artifact_link_not_allowed",
            "Delivery artifact path must not be a link.",
            "Replace the artifact link with a regular file inside the task workspace.",
        )
    descriptor: int | None = None
    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = mkstemp(prefix=f".{filename}-", suffix=".tmp", dir=root)
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as artifact_file:
            descriptor = None
            artifact_file.write(_redacted_text(content))
        os.replace(temporary_path, target)
        temporary_path = None
    except OSError as exc:
        raise _delivery_error(
            "delivery_write_error",
            "Delivery artifact could not be written.",
            "Check task workspace write permissions and retry.",
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    try:
        artifacts = dict(state.artifacts)
        artifacts[filename] = True
        updated_state = replace(state, artifacts=artifacts)
        if state_transform is not None:
            updated_state = state_transform(updated_state)
        save_state(root, updated_state)
    except HanCodeError as exc:
        raise _delivery_error(
            "delivery_state_sync_failed",
            "Delivery artifact was written but task state could not be synchronized.",
            "Repair state.json and reconcile the artifact before continuing.",
        ) from exc
    return target


def _task_root(task_root: Path) -> Path:
    if not isinstance(task_root, Path) or _is_link(task_root) or not task_root.is_dir():
        raise _delivery_error(
            "delivery_path_invalid",
            "Task root must be a regular directory.",
            "Use the canonical task workspace directory.",
        )
    return task_root.resolve()


def _load_consistent_state(task_root: Path) -> TaskState:
    state = reconcile_state(task_root, load_state(task_root))
    if state.inconsistent or state.status is TaskStatus.INCONSISTENT:
        raise _delivery_error(
            "delivery_state_inconsistent",
            "Task artifacts do not match the authoritative task state.",
            "Repair task artifacts or state.json before generating another delivery artifact.",
        )
    return state


def _is_link(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        return bool(is_junction is not None and is_junction())
    except (AttributeError, OSError, RuntimeError):
        return True


def _require_items(items: Sequence[object], error_code: str, label: str) -> None:
    if not items:
        raise _delivery_error(
            error_code,
            f"Delivery generation requires {label}.",
            f"Provide at least one {label} entry.",
        )


def _cell(value: str) -> str:
    return _markdown_literal(value).replace("|", "\\|").strip()


def _markdown_literal(value: str) -> str:
    return (
        _redacted_text(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\\", "\\\\")
        .replace("`", "\\`")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace(":", "&#58;")
        .replace("\r", " ")
        .replace("\n", " ")
    )


def _redacted_text(value: str) -> str:
    return redact_text(_BASIC_AUTHORIZATION_SECRET.sub(r"\1[REDACTED]", value))


def _coverage_digest(coverage: Sequence[RequirementCoverage]) -> str:
    records = [
        {
            "requirement_id": item.requirement_id,
            "status": item.status.value,
            "evidence": item.evidence,
            "risk": item.risk,
            "is_core": item.is_core,
        }
        for item in coverage
    ]
    records.sort(key=lambda record: json.dumps(record, ensure_ascii=False, sort_keys=True))
    encoded = json.dumps(
        records,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sanitize_coverage(item: RequirementCoverage) -> RequirementCoverage:
    return RequirementCoverage(
        requirement_id=_redacted_text(item.requirement_id),
        status=item.status,
        evidence=_redacted_text(item.evidence),
        risk=None if item.risk is None else _redacted_text(item.risk),
        is_core=item.is_core,
    )


def _sanitize_knowledge_item(item: KnowledgeItem) -> KnowledgeItem:
    return KnowledgeItem(
        category=item.category,
        summary=_redacted_text(item.summary),
        detail=_redacted_text(item.detail),
        source_phase=item.source_phase,
        source_trace_id=(
            None
            if item.source_trace_id is None
            else _redacted_text(item.source_trace_id)
        ),
    )


def _sanitize_risk(risk: Risk) -> Risk:
    return Risk(
        level=_redacted_text(risk.level),
        message=_redacted_text(risk.message),
        mitigation=(
            None if risk.mitigation is None else _redacted_text(risk.mitigation)
        ),
    )


def _coverage_to_dict(item: RequirementCoverage) -> dict[str, object]:
    return {
        "requirement_id": item.requirement_id,
        "status": item.status.value,
        "evidence": item.evidence,
        "risk": item.risk,
        "is_core": item.is_core,
    }


def _knowledge_item_to_dict(item: KnowledgeItem) -> dict[str, object]:
    return {
        "category": item.category.value,
        "summary": item.summary,
        "detail": item.detail,
        "source_phase": item.source_phase.value,
        "source_trace_id": item.source_trace_id,
    }


def _delivery_error(error_code: str, message: str, suggested_fix: str) -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code=error_code,
            message=message,
            phase=Phase.DELIVER.value,
            denied_rule="delivery_artifact_contract",
            suggested_fix=suggested_fix,
        )
    )


# Keep direct imports from the result module available; delivery_support.__init__
# replaces these names with the responsibility-specific wrappers at import time.
write_test_report = _write_test_report_impl
write_review = _write_review_impl
write_knowledge = _write_knowledge_impl
write_deliverables = _write_deliverables_impl
