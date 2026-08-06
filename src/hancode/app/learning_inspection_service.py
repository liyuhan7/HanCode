"""LearningInspectionService — read-only learning views — S14-R7.

A thin, read-only application service the TUI and CLI use to browse structured
learning evidence without touching the authoritative store. It never mutates
state or events; it only projects a validated :class:`LearningSnapshot` and its
traceability matrix into display-friendly view models.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from hancode.app.learning_service import LearningService
from hancode.runtime.traceability_builder import build_traceability


@dataclass(frozen=True, slots=True)
class KnowledgeCardView:
    id: str
    category: str
    principle: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RequirementCoverageView:
    requirement_id: str
    is_core: bool
    coverage: str


@dataclass(frozen=True, slots=True)
class LearningOverview:
    task_id: str
    requirement_count: int
    change_count: int
    test_attempt_count: int
    failure_count: int
    knowledge_cards: tuple[KnowledgeCardView, ...]
    coverage: tuple[RequirementCoverageView, ...]


class LearningInspectionService:
    def __init__(self, service: LearningService | None = None) -> None:
        self._service = service or LearningService()

    def overview(self, project_root: Path, task_id: str) -> LearningOverview:
        snapshot = self._service.load_snapshot(project_root, task_id)
        matrix = build_traceability(snapshot)
        cards = tuple(
            KnowledgeCardView(
                id=card.id,
                category=card.category,
                principle=card.principle,
                evidence_refs=card.evidence_refs,
            )
            for card in snapshot.knowledge_cards
        )
        coverage = tuple(
            RequirementCoverageView(
                requirement_id=requirement.id,
                is_core=requirement.is_core,
                coverage=matrix.coverage.get(requirement.id, "not_covered"),
            )
            for requirement in snapshot.requirements
        )
        return LearningOverview(
            task_id=task_id,
            requirement_count=len(snapshot.requirements),
            change_count=len(snapshot.changes),
            test_attempt_count=len(snapshot.test_attempts),
            failure_count=len(snapshot.failures),
            knowledge_cards=cards,
            coverage=coverage,
        )


__all__ = [
    "KnowledgeCardView",
    "LearningInspectionService",
    "LearningOverview",
    "RequirementCoverageView",
]
