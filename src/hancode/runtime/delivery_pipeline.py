"""DeliveryPipeline — unified delivery artifact generation (S4-R5).

The pipeline is the single authority for generating:
- TEST_REPORT.md (from real test ToolResult)
- REVIEW.md (via structured record_review)
- KNOWLEDGE.md (via structured record_knowledge)
- DELIVERABLES.md (auto-generated at finalize)

Delegates to delivery_support._write_artifact for atomic writes and state sync.
"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Sequence

from hancode.core.delivery_evidence import (
    DeliveryEvidence,
    KnowledgeCategory as NewKnowledgeCategory,
    KnowledgeItem as NewKnowledgeItem,
    RequirementCoverage as NewRequirementCoverage,
    RequirementStatus as NewRequirementStatus,
)
from hancode.delivery_support.result import (
    KnowledgeCategory,
    KnowledgeItem,
    RequirementCoverage,
    RequirementStatus,
    _write_artifact,
)
from hancode.core.models import Phase
from hancode.runtime.feedback import FeedbackReport
from hancode.core.state import load_state
from hancode.storage.delivery_evidence import DeliveryEvidenceStore


class DeliveryPipeline:
    """Orchestrate delivery artifact generation from authoritative sources."""

    def __init__(self) -> None:
        self._store = DeliveryEvidenceStore()
        self._accumulated_requirements: tuple[RequirementCoverage, ...] = ()
        self._accumulated_knowledge: tuple[KnowledgeItem, ...] = ()
        self._accumulated_risks: tuple[str, ...] = ()

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
        return _write_artifact(task_root, "TEST_REPORT.md", content)

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
        self._accumulated_requirements = normalized_requirements
        self._accumulated_risks = tuple(risks)

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
        return _write_artifact(task_root, "REVIEW.md", content)

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
        self._accumulated_knowledge = normalized_items

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
        return _write_artifact(task_root, "KNOWLEDGE.md", "\n".join(lines) + "\n")

    # ------------------------------------------------------------------
    # finalize — DELIVERABLES.md + DeliveryResult
    # ------------------------------------------------------------------

    def finalize(
        self,
        task_root: Path,
        task_id: str,
    ) -> DeliveryEvidence:
        test_report_path = task_root / "TEST_REPORT.md"
        test_report_sha = None
        if test_report_path.is_file():
            test_report_sha = sha256(test_report_path.read_bytes()).hexdigest()

        evidence = DeliveryEvidence(
            task_id=task_id,
            requirements=tuple(
                NewRequirementCoverage(
                    requirement_id=r.requirement_id,
                    status=NewRequirementStatus(str(r.status.value)),
                    evidence=r.evidence,
                    risk=r.risk,
                    is_core=r.is_core,
                )
                for r in self._accumulated_requirements
            ),
            knowledge_items=tuple(
                NewKnowledgeItem(
                    category=NewKnowledgeCategory(str(k.category.value)),
                    summary=k.summary,
                    detail=k.detail,
                    source_trace_id=k.source_trace_id,
                )
                for k in self._accumulated_knowledge
            ),
            review_risks=self._accumulated_risks,
            latest_test_report_sha256=test_report_sha,
            latest_diff_sha256=None,
            latest_build_status="none",
        )
        state = load_state(task_root)
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
            f"- {state.latest_test_status}\n"
        )
        _write_artifact(task_root, "DELIVERABLES.md", deliverables)
        self._store.save(task_root, evidence)
        return evidence


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
