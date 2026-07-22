from __future__ import annotations

from pathlib import Path
from typing import Sequence

from hancode.core.delivery_evidence import (
    DeliveryEvidence,
    KnowledgeItem,
    RequirementCoverage,
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
        requirements: Sequence[RequirementCoverage],
        risks: Sequence[str],
    ) -> Path:
        task_root = task_path(project_root, task_id)
        return self._pipeline.record_review(task_root, task_id, requirements, risks)

    def record_knowledge(
        self,
        project_root: Path,
        task_id: str,
        items: Sequence[KnowledgeItem],
    ) -> Path:
        task_root = task_path(project_root, task_id)
        return self._pipeline.record_knowledge(task_root, task_id, items)

    def finalize(
        self,
        project_root: Path,
        task_id: str,
    ) -> DeliveryEvidence:
        task_root = task_path(project_root, task_id)
        return self._pipeline.finalize(task_root, task_id)

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
