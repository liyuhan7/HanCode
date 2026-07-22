"""DeliveryPipeline — unified delivery artifact generation (S4-R5).

The pipeline is the single authority for generating:
- TEST_REPORT.md (from real test ToolResult)
- REVIEW.md (via structured record_review)
- KNOWLEDGE.md (via structured record_knowledge)
- DELIVERABLES.md (auto-generated at finalize)

Delegates to delivery_support._write_artifact for atomic writes and state sync.
"""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import Sequence

from hancode.core.delivery_evidence import (
    DeliveryEvidence,
    DeliveryResult,
    KnowledgeCategory as NewKnowledgeCategory,
    KnowledgeItem as NewKnowledgeItem,
    RequirementCoverage as NewRequirementCoverage,
    RequirementStatus as NewRequirementStatus,
)
from hancode.core.config import load_config
from hancode.core.models import Phase, TaskStatus
from hancode.delivery_support.result import (
    KnowledgeCategory,
    KnowledgeItem,
    RequirementCoverage,
    RequirementStatus,
    _coverage_digest,
    _write_artifact,
)
from hancode.runtime.feedback import FeedbackReport
from hancode.core.state import TaskState, load_state
from hancode.storage.delivery_evidence import DeliveryEvidenceStore


class DeliveryPipeline:
    """Orchestrate delivery artifact generation from authoritative sources."""

    def __init__(self) -> None:
        self._store = DeliveryEvidenceStore()

    # ------------------------------------------------------------------
    # record_test — TEST_REPORT.md from real ToolResult
    # ------------------------------------------------------------------

    def record_test(
        self,
        task_root: Path,
        report: FeedbackReport,
        command: str,
    ) -> Path:
        status = "passed" if report.passed else "failed"
        content = (
            "# 测试报告\n\n"
            "| 字段 | 值 |\n"
            "| --- | --- |\n"
            f"| 命令 | `{command}` |\n"
            f"| 状态 | {status} |\n"
            f"| 失败分类 | {report.failure_category.value} |\n"
            f"| 通过数 | {report.passed_count} |\n"
            f"| 失败数 | {report.failed_count} |\n\n"
            "## 摘要\n\n"
            f"{report.summary}\n\n"
            "## 下一步\n\n"
            f"{report.next_action_hint}\n"
        )
        path = _write_artifact(task_root, "TEST_REPORT.md", content)
        self._merge_evidence(
            task_root,
            task_root.name,
            latest_test_report_sha256=sha256(path.read_bytes()).hexdigest(),
        )
        return path

    # ------------------------------------------------------------------
    # record_review — REVIEW.md from structured evidence
    # ------------------------------------------------------------------

    def record_review(
        self,
        task_root: Path,
        task_id: str,
        requirements: Sequence[RequirementCoverage | NewRequirementCoverage],
        risks: Sequence[str],
    ) -> Path:
        normalized_requirements = tuple(
            _normalize_requirement(item) for item in requirements
        )
        rows = "".join(
            f"| {item.requirement_id} | {item.status.value} | "
            f"{item.evidence} | {item.risk or 'None.'} |\n"
            for item in normalized_requirements
        )
        risk_lines = "\n".join(f"- {risk}" for risk in risks) or "- None."
        content = (
            "# 审查记录\n\n"
            "## 需求覆盖\n\n"
            "| 需求 | 状态 | 证据 | 风险 |\n"
            "| --- | --- | --- | --- |\n"
            f"{rows}\n"
            "## 审查风险\n\n"
            f"{risk_lines}\n"
        )
        path = _write_artifact(task_root, "REVIEW.md", content)
        self._merge_evidence(
            task_root,
            task_id,
            requirements=tuple(
                NewRequirementCoverage(
                    requirement_id=item.requirement_id,
                    status=NewRequirementStatus(item.status.value),
                    evidence=item.evidence,
                    risk=item.risk,
                    is_core=item.is_core,
                )
                for item in normalized_requirements
            ),
            review_risks=tuple(risks),
        )
        return path

    # ------------------------------------------------------------------
    # record_knowledge — KNOWLEDGE.md from structured items
    # ------------------------------------------------------------------

    def record_knowledge(
        self,
        task_root: Path,
        task_id: str,
        items: Sequence[KnowledgeItem | NewKnowledgeItem],
    ) -> Path:
        normalized_items = tuple(_normalize_knowledge_item(item) for item in items)
        sections = (
            (KnowledgeCategory.REQUIREMENT_UNDERSTANDING, "需求理解"),
            (KnowledgeCategory.DESIGN_DECISION, "设计决策"),
            (KnowledgeCategory.TESTING_EXPERIENCE, "测试经验"),
            (KnowledgeCategory.ERROR_FIX, "错误修复"),
            (KnowledgeCategory.REUSABLE_PATTERN, "可复用模式"),
            (KnowledgeCategory.BUG_FIX, "缺陷修复"),
            (KnowledgeCategory.TEST_INSIGHT, "测试洞察"),
            (KnowledgeCategory.PROCESS_IMPROVEMENT, "流程改进"),
            (KnowledgeCategory.OTHER, "其他"),
        )
        grouped = {
            category: [i for i in normalized_items if i.category is category]
            for category, _ in sections
        }
        lines = ["# 知识沉淀\n"]
        for category, title in sections:
            entries = grouped[category]
            if not entries:
                continue
            lines.append(f"## {title}\n")
            for item in entries:
                lines.append(f"- **{item.summary}**")
                lines.append(f"  {item.detail}")
                if item.source_trace_id:
                    lines.append(f"  _Trace: `{item.source_trace_id}`_")
                lines.append("")
        path = _write_artifact(task_root, "KNOWLEDGE.md", "\n".join(lines) + "\n")
        self._merge_evidence(
            task_root,
            task_id,
            knowledge_items=tuple(
                NewKnowledgeItem(
                    category=NewKnowledgeCategory(item.category.value),
                    summary=item.summary,
                    detail=item.detail,
                    source_trace_id=item.source_trace_id,
                )
                for item in normalized_items
            ),
        )
        return path

    def record_build(self, task_root: Path, task_id: str, status: str) -> None:
        if status not in {"none", "passed", "failed", "timed_out"}:
            raise ValueError("invalid build status")
        self._merge_evidence(task_root, task_id, latest_build_status=status)

    def record_diff(
        self, task_root: Path, task_id: str, digest: str | None, *, drifted: bool = False
    ) -> None:
        if drifted:
            current = self._store.load(task_root) or _empty_evidence(task_id)
            self._store.save(task_root, replace(current, latest_diff_sha256=None))
            return
        self._merge_evidence(
            task_root,
            task_id,
            latest_diff_sha256=digest,
        )

    # ------------------------------------------------------------------
    # finalize — DELIVERABLES.md + DeliveryResult
    # ------------------------------------------------------------------

    def finalize(
        self,
        task_root: Path,
        task_id: str,
    ) -> DeliveryResult:
        evidence = self._store.load(task_root) or _empty_evidence(task_id)
        state = load_state(task_root)
        project_root = task_root.resolve().parents[2]
        config = load_config(project_root, task_id)
        blockers = _delivery_blockers(
            state,
            evidence,
            build_required=config.build_command is not None,
        )
        status = _delivery_status(state, blockers)
        digest_coverage = tuple(
            RequirementCoverage(
                requirement_id=item.requirement_id,
                status=RequirementStatus(item.status.value),
                evidence=item.evidence,
                risk=item.risk,
                is_core=item.is_core,
            )
            for item in evidence.requirements
        )
        coverage_digest = _coverage_digest(digest_coverage)
        artifacts = dict(state.artifacts)
        artifacts["DELIVERABLES.md"] = True
        artifact_rows = "".join(
            f"| {name} | {'present' if present or name == 'DELIVERABLES.md' else 'missing'} |\n"
            for name, present in artifacts.items()
        )
        deliverables = (
            "# 交付清单\n\n"
            "## 交付物\n\n"
            "| 文件 | 状态 |\n"
            "| --- | --- |\n"
            f"{artifact_rows}\n"
            "## 测试状态\n\n"
            f"- {state.latest_test_status}\n\n"
            "## 阻断原因\n\n"
            + "\n".join(f"- {item}" for item in blockers)
            + ("\n" if blockers else "- None.\n")
            + "\n## 最终状态\n\n"
            f"- {status.value}\n"
        )
        _write_artifact(
            task_root,
            "DELIVERABLES.md",
            deliverables,
            state_transform=lambda current: replace(
                current,
                status=status,
                delivery_coverage_digest=coverage_digest,
            ),
        )
        result = DeliveryResult(
            task_id=evidence.task_id,
            requirements=evidence.requirements,
            knowledge_items=evidence.knowledge_items,
            review_risks=evidence.review_risks,
            latest_test_report_sha256=evidence.latest_test_report_sha256,
            latest_diff_sha256=evidence.latest_diff_sha256,
            latest_build_status=evidence.latest_build_status,
            status=status,
            blockers=blockers,
        )
        self._store.save(task_root, result)
        return result

    def _merge_evidence(
        self,
        task_root: Path,
        task_id: str,
        *,
        requirements: tuple[NewRequirementCoverage, ...] | None = None,
        knowledge_items: tuple[NewKnowledgeItem, ...] | None = None,
        review_risks: tuple[str, ...] | None = None,
        latest_test_report_sha256: str | None = None,
        latest_diff_sha256: str | None = None,
        latest_build_status: str | None = None,
    ) -> None:
        current = self._store.load(task_root) or _empty_evidence(task_id)
        updated = replace(
            current,
            requirements=current.requirements if requirements is None else requirements,
            knowledge_items=(
                current.knowledge_items
                if knowledge_items is None
                else knowledge_items
            ),
            review_risks=current.review_risks if review_risks is None else review_risks,
            latest_test_report_sha256=(
                current.latest_test_report_sha256
                if latest_test_report_sha256 is None
                else latest_test_report_sha256
            ),
            latest_diff_sha256=(
                current.latest_diff_sha256
                if latest_diff_sha256 is None
                else latest_diff_sha256
            ),
            latest_build_status=(
                current.latest_build_status
                if latest_build_status is None
                else latest_build_status
            ),
        )
        self._store.save(task_root, updated)


def _empty_evidence(task_id: str) -> DeliveryEvidence:
    return DeliveryEvidence(
        task_id=task_id,
        requirements=(),
        knowledge_items=(),
        review_risks=(),
        latest_test_report_sha256=None,
        latest_diff_sha256=None,
        latest_build_status="none",
    )


def _delivery_blockers(
    state: TaskState,
    evidence: DeliveryEvidence,
    *,
    build_required: bool,
) -> tuple[str, ...]:
    blockers: list[str] = []
    if state.latest_test_status != "passed":
        blockers.append("测试未通过，任务不能标记为 completed。")
    if build_required and evidence.latest_build_status != "passed":
        blockers.append("配置了 Build 命令，但 Build 尚未通过。")
    for artifact in ("TEST_REPORT.md", "REVIEW.md", "KNOWLEDGE.md"):
        if not state.artifacts[artifact]:
            blockers.append(f"缺少必需交付物：{artifact}。")
    core_requirements = [item for item in evidence.requirements if item.is_core]
    if not core_requirements:
        blockers.append("缺少核心需求覆盖证据。")
    for item in core_requirements:
        if item.status is not NewRequirementStatus.COVERED or not item.evidence.strip():
            blockers.append(f"核心需求未覆盖：{item.requirement_id}。")
    if state.latest_checkpoint is not None and evidence.latest_diff_sha256 is None:
        blockers.append("存在 Checkpoint，但缺少最新 Diff 证据。")
    return tuple(blockers)


def _delivery_status(state: TaskState, blockers: Sequence[str]) -> TaskStatus:
    if state.inconsistent or state.status is TaskStatus.INCONSISTENT:
        return TaskStatus.INCONSISTENT
    if state.status is TaskStatus.FAILED:
        return TaskStatus.FAILED
    return TaskStatus.BLOCKED if blockers else TaskStatus.COMPLETED


def _normalize_requirement(
    item: RequirementCoverage | NewRequirementCoverage,
) -> RequirementCoverage:
    if isinstance(item, RequirementCoverage):
        return item
    return RequirementCoverage(
        requirement_id=item.requirement_id,
        status=RequirementStatus(item.status.value),
        evidence=item.evidence,
        risk=item.risk,
        is_core=item.is_core,
    )


def _normalize_knowledge_item(
    item: KnowledgeItem | NewKnowledgeItem,
) -> KnowledgeItem:
    if isinstance(item, KnowledgeItem):
        return item
    return KnowledgeItem(
        category=KnowledgeCategory(item.category.value),
        summary=item.summary,
        detail=item.detail,
        source_phase=Phase.DELIVER,
        source_trace_id=item.source_trace_id,
    )
