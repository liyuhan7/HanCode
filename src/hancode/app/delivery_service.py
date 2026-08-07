from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Mapping, Sequence

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
        requirements: Sequence[CoreRequirementCoverage | LegacyRequirementCoverage] | None = None,
        risks: Sequence[str] = (),
        *,
        requirement_reviews: Sequence[Mapping[str, object]] | None = None,
        quality_findings: Sequence[str] = (),
        untested_risks: Sequence[str] = (),
        plan_deviations: Sequence[str] = (),
        delivery_recommendation: str | None = None,
    ) -> Path:
        task_root = task_path(project_root, task_id)
        if requirement_reviews is not None:
            from hancode.app.learning_service import LearningService

            LearningService().record_review(
                project_root,
                task_id,
                requirement_reviews=requirement_reviews,
                quality_findings=quality_findings,
                untested_risks=untested_risks,
                plan_deviations=plan_deviations,
                delivery_recommendation=delivery_recommendation or "",
            )
            return task_root / "REVIEW.md"
        if requirements is None:
            raise ValueError("Legacy review evidence requires requirements.")
        if _has_learning_evidence(project_root, task_id):
            raise ValueError(
                "This task requires structured requirement_reviews for record_review."
            )
        return self._pipeline.record_review(task_root, task_id, requirements, risks)

    def record_knowledge(
        self,
        project_root: Path,
        task_id: str,
        items: Sequence[CoreKnowledgeItem | LegacyKnowledgeItem] | None = None,
        *,
        cards: Sequence[Mapping[str, object]] | None = None,
    ) -> Path:
        task_root = task_path(project_root, task_id)
        if cards is not None:
            from hancode.app.learning_service import LearningService

            LearningService().record_knowledge(project_root, task_id, cards=cards)
            return task_root / "KNOWLEDGE.md"
        if items is None:
            raise ValueError("Legacy knowledge evidence requires items.")
        if _has_learning_evidence(project_root, task_id):
            raise ValueError("This task requires structured cards for record_knowledge.")
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
        if _has_learning_evidence(project_root, task_id):
            return self.finalize_learning(project_root, task_id)
        task_root = task_path(project_root, task_id)
        return self._pipeline.finalize(task_root, task_id)

    def get_result(self, project_root: Path, task_id: str) -> DeliveryResult:
        """Return the persisted delivery decision through the unified pipeline."""
        return self.finalize(project_root, task_id)

    def finalize_learning(
        self,
        project_root: Path,
        task_id: str,
    ) -> DeliveryResult:
        """Publish the S14 design-format delivery summary (DELIVERABLES.md).

        This is the learning-contract delivery closure. It builds the
        DELIVERABLES.md "project delivery summary" index from the collected
        learning snapshot and task state, then returns the submission-eligibility
        decision from :meth:`evaluate_learning`.
        """
        from hancode.core.state import load_state, reconcile_state
        from hancode.delivery_support.collector import collect_learning_delivery
        from hancode.delivery_support.renderer import (
            build_deliverables_markdown,
            replace_generated_region,
        )
        from hancode.delivery_support.result import _write_artifact
        from hancode.storage.workspace import task_path

        task_root = task_path(project_root, task_id)
        collected = collect_learning_delivery(project_root, task_id)
        state = reconcile_state(task_root, load_state(task_root))
        snapshot = collected.snapshot

        evidence_digest = getattr(snapshot, "digest", None)
        latest_diff = None
        for change in snapshot.changes:
            if change.diff_digest:
                latest_diff = change.diff_digest

        core = tuple(r for r in snapshot.requirements if r.is_core)
        core_covered = sum(
            1 for requirement in core if collected.matrix.coverage.get(requirement.id) == "covered"
        )
        submission_files = tuple(
            sorted(
                set(state.files_changed)
                | {
                    artifact
                    for artifact, present in state.artifacts.items()
                    if present
                }
                | {"DELIVERABLES.md"}
            )
        )
        coverage_rows = [
            (
                f"{r.id}：{collected.matrix.coverage.get(r.id, 'not_covered')}；"
                f"{r.student_understanding}"
            )
            for r in snapshot.requirements
        ]

        result = self.evaluate_learning(project_root, task_id)
        body = build_deliverables_markdown(
            task_id=task_id,
            status=result.status.value,
            test_status=(
                snapshot.test_attempts[-1].status
                if snapshot.test_attempts
                else state.latest_test_status
            ),
            build_status=state.latest_build_status,
            core_covered=core_covered,
            core_total=len(core),
            run_notes="运行方式以项目配置为准；见 SPEC.md 的输入、输出和边界条件。",
            test_notes="见 TEST_REPORT.md 的测试尝试与失败记录。",
            submission_files=submission_files,
            coverage_rows=coverage_rows,
            learning_links=(
                ("SPEC.md", "需求理解"),
                ("PLAN.md", "实现计划"),
                ("IMPLEMENTATION.md", "实现记录"),
                ("TEST_REPORT.md", "测试与失败记录"),
                ("REVIEW.md", "最终审查"),
                ("KNOWLEDGE.md", "知识复盘"),
            ),
            known_limits=(),  # REVIEW.md 承载已知限制；此处不重复正文
            evidence_digest=evidence_digest,
            diff_digest=latest_diff,
            checkpoint_id=state.latest_checkpoint,
        )
        existing = task_root / "DELIVERABLES.md"
        rendered = replace_generated_region(
            existing.read_text(encoding="utf-8") if existing.is_file() else "",
            body,
        )
        _write_artifact(
            task_root,
            "DELIVERABLES.md",
            rendered,
            state_transform=lambda current: replace(current, status=result.status),
        )
        if latest_diff is not None:
            self._pipeline.record_diff(task_root, task_id, latest_diff)
        return result

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


def _has_learning_evidence(project_root: Path, task_id: str) -> bool:
    from hancode.app.learning_service import LearningService

    return bool(LearningService().load_snapshot(project_root, task_id).requirements)
