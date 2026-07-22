"""Delivery evidence models — S4-R5."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


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
