from __future__ import annotations

from pathlib import Path
from typing import Sequence

from hancode.core.delivery_evidence import (
    DeliveryEvidence,
    DeliveryResult,
    KnowledgeItem as CoreKnowledgeItem,
    RequirementCoverage as CoreRequirementCoverage,
)
from hancode.core.models import TaskStatus
from hancode.delivery_support.result import (
    KnowledgeItem as LegacyKnowledgeItem,
    RequirementCoverage as LegacyRequirementCoverage,
)
from hancode.runtime.delivery_pipeline import DeliveryPipeline
from hancode.storage.export import (
    ExportProfile,
    ExportResult,
    ProfileExportResult,
    export_task_artifacts,
)
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

    def evaluate_learning(self, project_root: Path, task_id: str) -> DeliveryResult:
        """Run Collect → Validate over structured learning evidence (S14-R5).

        This is the learning-contract-aware decision path. It does not write
        artifacts or mutate state; it reports submission eligibility, the
        learning contract status, blockers, and warnings derived only from the
        authoritative learning events.
        """
        from hancode.core.state import load_state, reconcile_state
        from hancode.delivery_support.collector import collect_learning_delivery
        from hancode.delivery_support.validator import validate_learning_delivery
        from hancode.storage.workspace import task_path

        collected = collect_learning_delivery(project_root, task_id)
        validation = validate_learning_delivery(collected)

        task_root = task_path(project_root, task_id)
        state = reconcile_state(task_root, load_state(task_root))
        legacy_unverified = state.learning_contract_version is None
        contract_status = (
            "legacy_unverified" if legacy_unverified else validation.learning_contract_status
        )
        if state.inconsistent or state.status is TaskStatus.INCONSISTENT:
            status = TaskStatus.INCONSISTENT
        elif state.status is TaskStatus.FAILED:
            status = TaskStatus.FAILED
        elif validation.blockers or legacy_unverified:
            status = TaskStatus.BLOCKED
        else:
            status = TaskStatus.COMPLETED
        submission_eligible = (
            not legacy_unverified
            and not validation.blockers
            and status is TaskStatus.COMPLETED
        )

        snapshot = collected.snapshot
        return DeliveryResult(
            task_id=task_id,
            requirements=(),
            knowledge_items=(),
            review_risks=(),
            latest_test_report_sha256=(
                snapshot.test_attempts[-1].output_digest
                if snapshot.test_attempts
                else None
            ),
            latest_diff_sha256=(
                snapshot.changes[-1].diff_digest if snapshot.changes else None
            ),
            latest_build_status=collected.latest_build_status,
            status=status,
            blockers=validation.blockers,
            submission_eligible=submission_eligible,
            learning_contract_status=contract_status,
            learning_warnings=validation.warnings,
        )

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

    def export_profile(
        self,
        project_root: Path,
        task_id: str,
        output_dir: Path,
        profile: ExportProfile,
    ) -> ProfileExportResult:
        """Publish a task for an explicit audience profile (S14-R6)."""
        from hancode.storage.export import export_task_profile

        return export_task_profile(project_root, task_id, output_dir, profile)
