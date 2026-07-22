from __future__ import annotations

from pathlib import Path
from typing import Sequence

from hancode.core.delivery_evidence import (
    DeliveryEvidence,
    DeliveryResult,
    KnowledgeItem as CoreKnowledgeItem,
    RequirementCoverage as CoreRequirementCoverage,
)
from hancode.delivery_support.result import (
    KnowledgeItem as LegacyKnowledgeItem,
    RequirementCoverage as LegacyRequirementCoverage,
)
from hancode.runtime.delivery_pipeline import DeliveryPipeline
from hancode.storage.export import ExportResult, export_task_artifacts
from hancode.storage.workspace import task_path


class DeliveryService:
    """Application facade for state-authorized delivery."""

    def __init__(self) -> None:
        self._pipeline = DeliveryPipeline()

    def record_test(
        self,
        project_root: Path,
        task_id: str,
        report: object,  # FeedbackReport
        command: str,
    ) -> Path:
        task_root = task_path(project_root, task_id)
        return self._pipeline.record_test(task_root, report, command)  # type: ignore[arg-type]

    def record_review(
        self,
        project_root: Path,
        task_id: str,
        requirements: Sequence[CoreRequirementCoverage | LegacyRequirementCoverage],
        risks: Sequence[str],
    ) -> Path:
        task_root = task_path(project_root, task_id)
        return self._pipeline.record_review(task_root, task_id, requirements, risks)

    def record_knowledge(
        self,
        project_root: Path,
        task_id: str,
        items: Sequence[CoreKnowledgeItem | LegacyKnowledgeItem],
    ) -> Path:
        task_root = task_path(project_root, task_id)
        return self._pipeline.record_knowledge(task_root, task_id, items)

    def record_diff(
        self,
        project_root: Path,
        task_id: str,
        digest: str | None,
        *,
        drifted: bool = False,
    ) -> None:
        task_root = task_path(project_root, task_id)
        self._pipeline.record_diff(task_root, task_id, digest, drifted=drifted)

    def record_build(self, project_root: Path, task_id: str, status: str) -> None:
        task_root = task_path(project_root, task_id)
        self._pipeline.record_build(task_root, task_id, status)

    def finalize(
        self,
        project_root: Path,
        task_id: str,
    ) -> DeliveryResult:
        task_root = task_path(project_root, task_id)
        return self._pipeline.finalize(task_root, task_id)

    def get_result(self, project_root: Path, task_id: str) -> DeliveryResult:
        """Return the persisted delivery decision through the unified pipeline."""
        return self.finalize(project_root, task_id)

    def get_evidence(
        self,
        project_root: Path,
        task_id: str,
    ) -> DeliveryEvidence | None:
        from hancode.storage.delivery_evidence import DeliveryEvidenceStore
        task_root = task_path(project_root, task_id)
        return DeliveryEvidenceStore().load(task_root)

    def export(self, project_root: Path, task_id: str, output_dir: Path) -> ExportResult:
        return export_task_artifacts(project_root, task_id, output_dir)
