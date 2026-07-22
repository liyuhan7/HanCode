"""Delivery evidence models — S4-R5."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from hancode.core.models import TaskStatus

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
    source_trace_id: str | None


@dataclass(frozen=True, slots=True)
class DeliveryEvidence:
    task_id: str
    requirements: tuple[RequirementCoverage, ...]
    knowledge_items: tuple[KnowledgeItem, ...]
    review_risks: tuple[str, ...]
    latest_test_report_sha256: str | None
    latest_diff_sha256: str | None
    latest_build_status: str


@dataclass(frozen=True, slots=True)
class DeliveryResult(DeliveryEvidence):
    """Final delivery decision built from persisted evidence and task state."""

    status: TaskStatus
    blockers: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "task_id": self.task_id,
            "requirements": [
                {
                    "requirement_id": item.requirement_id,
                    "status": item.status.value,
                    "evidence": item.evidence,
                    "risk": item.risk,
                    "is_core": item.is_core,
                }
                for item in self.requirements
            ],
            "knowledge_items": [
                {
                    "category": item.category.value,
                    "summary": item.summary,
                    "detail": item.detail,
                    "source_trace_id": item.source_trace_id,
                }
                for item in self.knowledge_items
            ],
            "review_risks": list(self.review_risks),
            "latest_test_report_sha256": self.latest_test_report_sha256,
            "latest_diff_sha256": self.latest_diff_sha256,
            "latest_build_status": self.latest_build_status,
            "blockers": list(self.blockers),
        }
