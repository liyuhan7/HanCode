"""Delivery artifact generation split by output responsibility."""

from hancode.delivery_support import result as _result
from hancode.delivery_support.result import (
    DeliveryResult,
    KnowledgeCategory,
    KnowledgeItem,
    RequirementCoverage,
    RequirementStatus,
    ResultBuilder,
)
from hancode.delivery_support.deliverables import write_deliverables
from hancode.delivery_support.knowledge import write_knowledge
from hancode.delivery_support.reports import write_test_report
from hancode.delivery_support.review import write_review

_result.write_deliverables = write_deliverables
_result.write_knowledge = write_knowledge
_result.write_test_report = write_test_report
_result.write_review = write_review

__all__ = [
    "DeliveryResult",
    "KnowledgeCategory",
    "KnowledgeItem",
    "RequirementCoverage",
    "RequirementStatus",
    "ResultBuilder",
    "write_deliverables",
    "write_knowledge",
    "write_test_report",
    "write_review",
]
