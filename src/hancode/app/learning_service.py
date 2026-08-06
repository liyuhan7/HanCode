"""LearningService — structured SPEC/PLAN/IMPLEMENTATION recording (S14-R2).

This service is the write path for structured learning evidence during the
spec, plan, and code phases. It appends events to the authoritative learning
event log, rebuilds a :class:`LearningSnapshot` from the full event prefix, and
renders the generated region of the matching Markdown artifact. The Markdown is
a re-generatable view; the events and their derived projection are the source
of truth.

``record_change`` is intentionally a service call (driven by the AgentLoop after
a successful, source-affecting modification), not an LLM-exposed tool.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

from hancode.core.errors import HanCodeError, StructuredError
from hancode.core.learning_evidence import (
    ChangeEvidence,
    DecisionEvidence,
    EvidenceKind,
    FailureEvidence,
    KnowledgeCard,
    LearningSnapshot,
    PlanStepEvidence,
    RecoveryEvidence,
    RequirementEvidence,
    TestAttemptEvidence,
    format_evidence_id,
)
from hancode.delivery_support.renderer import replace_generated_region
from hancode.delivery_support.result import _write_artifact
from hancode.storage.learning_store import LearningEventType, LearningStore
from hancode.storage.workspace import task_path


class LearningService:
    """Record structured learning evidence and render its Markdown view."""

    def __init__(self, store: LearningStore | None = None) -> None:
        self._store = store or LearningStore()

    # ------------------------------------------------------------------
    # record_requirements → SPEC.md
    # ------------------------------------------------------------------

    def record_requirements(
        self,
        project_root: Path,
        task_id: str,
        *,
        goal: str,
        requirements: Sequence[Mapping[str, object]],
        boundaries: Sequence[str] = (),
        constraints: Sequence[str] = (),
        assumptions: Sequence[str] = (),
    ) -> tuple[RequirementEvidence, ...]:
        if not requirements:
            raise _invalid_input("At least one requirement is required.")
        task_root = task_path(project_root, task_id)
        snapshot = self._snapshot(task_root, task_id)
        next_seq = len(snapshot.requirements) + 1
        recorded: list[RequirementEvidence] = []
        for offset, raw in enumerate(requirements):
            evidence = RequirementEvidence(
                id=format_evidence_id(EvidenceKind.REQUIREMENT, next_seq + offset),
                task_id=task_id,
                source_text=_text(raw, "source_text"),
                student_understanding=_text(raw, "student_understanding"),
                acceptance_evidence=_text(raw, "acceptance_evidence"),
                priority=_text(raw, "priority", default="normal"),
                is_core=bool(raw.get("is_core", False)),
            )
            self._store.append(
                task_root,
                task_id,
                LearningEventType.REQUIREMENT_UNDERSTOOD,
                {
                    "kind": "requirement",
                    "id": evidence.id,
                    "source_text": evidence.source_text,
                    "student_understanding": evidence.student_understanding,
                    "acceptance_evidence": evidence.acceptance_evidence,
                    "priority": evidence.priority,
                    "is_core": evidence.is_core,
                    "goal": goal,
                    "boundaries": list(boundaries),
                    "constraints": list(constraints),
                    "assumptions": list(assumptions),
                },
                occurred_at=_now(),
            )
            recorded.append(evidence)

        snapshot = self._snapshot(task_root, task_id)
        body = _render_spec_body(goal, snapshot, boundaries, constraints, assumptions)
        _write_generated(task_root, "SPEC.md", body)
        return tuple(recorded)

    # ------------------------------------------------------------------
    # record_plan → PLAN.md
    # ------------------------------------------------------------------

    def record_plan(
        self,
        project_root: Path,
        task_id: str,
        *,
        decisions: Sequence[Mapping[str, object]],
        plan_steps: Sequence[Mapping[str, object]],
    ) -> tuple[tuple[DecisionEvidence, ...], tuple[PlanStepEvidence, ...]]:
        task_root = task_path(project_root, task_id)
        snapshot = self._snapshot(task_root, task_id)
        known_requirements = {item.id for item in snapshot.requirements}

        decision_seq = len(snapshot.decisions) + 1
        recorded_decisions: list[DecisionEvidence] = []
        for offset, raw in enumerate(decisions):
            requirement_refs = _str_tuple(raw.get("requirement_refs", ()))
            _require_refs(requirement_refs, known_requirements)
            decision = DecisionEvidence(
                id=format_evidence_id(EvidenceKind.DECISION, decision_seq + offset),
                task_id=task_id,
                chosen_option=_text(raw, "chosen_option"),
                rejected_options=_str_tuple(raw.get("rejected_options", ())),
                rationale=_text(raw, "rationale"),
                requirement_refs=requirement_refs,
            )
            self._store.append(
                task_root,
                task_id,
                LearningEventType.DECISION_RECORDED,
                {"kind": "decision", **_decision_payload(decision)},
                occurred_at=_now(),
            )
            recorded_decisions.append(decision)

        snapshot = self._snapshot(task_root, task_id)
        known_decisions = {item.id for item in snapshot.decisions}
        step_seq = len(snapshot.plan_steps) + 1
        recorded_steps: list[PlanStepEvidence] = []
        for offset, raw in enumerate(plan_steps):
            requirement_refs = _str_tuple(raw.get("requirement_refs", ()))
            _require_refs(requirement_refs, known_requirements)
            decision_ref = raw.get("decision_ref")
            if decision_ref is not None and decision_ref not in known_decisions:
                raise _reference_invalid(f"Unknown decision ref: {decision_ref!r}.")
            step = PlanStepEvidence(
                id=format_evidence_id(EvidenceKind.PLAN_STEP, step_seq + offset),
                task_id=task_id,
                description=_text(raw, "description"),
                requirement_refs=requirement_refs,
                planned_paths=_str_tuple(raw.get("planned_paths", ())),
                verification=_text(raw, "verification", default=""),
                decision_ref=decision_ref if isinstance(decision_ref, str) else None,
            )
            self._store.append(
                task_root,
                task_id,
                LearningEventType.DECISION_RECORDED,
                {"kind": "plan_step", **_plan_step_payload(step)},
                occurred_at=_now(),
            )
            recorded_steps.append(step)

        snapshot = self._snapshot(task_root, task_id)
        body = _render_plan_body(snapshot)
        _write_generated(task_root, "PLAN.md", body)
        return tuple(recorded_decisions), tuple(recorded_steps)

    # ------------------------------------------------------------------
    # record_change → IMPLEMENTATION.md (AgentLoop-driven, not an LLM tool)
    # ------------------------------------------------------------------

    def record_change(
        self,
        project_root: Path,
        task_id: str,
        *,
        pre_change_checkpoint_id: str | None,
        action_id: str,
        changed_paths: Sequence[str],
        diff_digest: str,
        reason: str,
        requirement_refs: Sequence[str] = (),
        plan_step_refs: Sequence[str] = (),
    ) -> ChangeEvidence:
        task_root = task_path(project_root, task_id)
        snapshot = self._snapshot(task_root, task_id)
        known_requirements = {item.id for item in snapshot.requirements}
        known_plan_steps = {item.id for item in snapshot.plan_steps}
        requirement_ref_tuple = _str_tuple(requirement_refs)
        plan_step_ref_tuple = _str_tuple(plan_step_refs)
        _require_refs(requirement_ref_tuple, known_requirements)
        _require_refs(plan_step_ref_tuple, known_plan_steps)

        change = ChangeEvidence(
            id=format_evidence_id(EvidenceKind.CHANGE, len(snapshot.changes) + 1),
            task_id=task_id,
            pre_change_checkpoint_id=pre_change_checkpoint_id,
            action_id=action_id,
            changed_paths=_str_tuple(changed_paths),
            diff_digest=diff_digest,
            reason=reason,
            requirement_refs=requirement_ref_tuple,
            plan_step_refs=plan_step_ref_tuple,
        )
        self._store.append(
            task_root,
            task_id,
            LearningEventType.CHANGE_APPLIED,
            {"kind": "change", **_change_payload(change)},
            occurred_at=_now(),
        )
        snapshot = self._snapshot(task_root, task_id)
        body = _render_implementation_body(snapshot)
        _write_generated(task_root, "IMPLEMENTATION.md", body)
        return change

    # ------------------------------------------------------------------
    # record_test_attempt / record_failure / record_recovery → TEST_REPORT.md
    # ------------------------------------------------------------------

    def record_test_attempt(
        self,
        project_root: Path,
        task_id: str,
        *,
        command: str,
        started_at: str,
        finished_at: str,
        exit_code: int,
        status: str,
        passed_count: int,
        failed_count: int,
        failure_category: str | None,
        summary: str,
        output_digest: str,
        tested_change_ids: Sequence[str] = (),
        requirement_refs: Sequence[str] = (),
    ) -> TestAttemptEvidence:
        task_root = task_path(project_root, task_id)
        snapshot = self._snapshot(task_root, task_id)
        known_changes = {item.id for item in snapshot.changes}
        known_requirements = {item.id for item in snapshot.requirements}
        change_refs = _str_tuple(tested_change_ids)
        requirement_ref_tuple = _str_tuple(requirement_refs)
        _require_refs(change_refs, known_changes)
        _require_refs(requirement_ref_tuple, known_requirements)

        attempt = TestAttemptEvidence(
            id=format_evidence_id(
                EvidenceKind.TEST_ATTEMPT, len(snapshot.test_attempts) + 1
            ),
            task_id=task_id,
            command=command,
            started_at=started_at,
            finished_at=finished_at,
            exit_code=exit_code,
            status=status,
            passed_count=passed_count,
            failed_count=failed_count,
            failure_category=failure_category,
            summary=summary,
            output_digest=output_digest,
            tested_change_ids=change_refs,
            requirement_refs=requirement_ref_tuple,
        )
        self._store.append(
            task_root,
            task_id,
            LearningEventType.TEST_EXECUTED,
            {"kind": "test_attempt", **_attempt_payload(attempt)},
            occurred_at=started_at,
        )
        self._render_test_report(task_root, task_id)
        return attempt

    def record_failure(
        self,
        project_root: Path,
        task_id: str,
        *,
        test_attempt_id: str,
        failure_digest: str,
        category: str,
        summary: str,
        failing_tests: Sequence[str] = (),
        affected_paths: Sequence[str] = (),
    ) -> FailureEvidence:
        task_root = task_path(project_root, task_id)
        snapshot = self._snapshot(task_root, task_id)
        known_attempts = {item.id for item in snapshot.test_attempts}
        if test_attempt_id not in known_attempts:
            raise _reference_invalid(
                f"Unknown test attempt: {test_attempt_id!r}."
            )
        failure = FailureEvidence(
            id=format_evidence_id(EvidenceKind.FAILURE, len(snapshot.failures) + 1),
            task_id=task_id,
            test_attempt_id=test_attempt_id,
            failure_digest=failure_digest,
            category=category,
            summary=summary,
            failing_tests=_str_tuple(failing_tests),
            affected_paths=_str_tuple(affected_paths),
        )
        self._store.append(
            task_root,
            task_id,
            LearningEventType.FAILURE_DIAGNOSED,
            {"kind": "failure", **_failure_payload(failure)},
            occurred_at=_now(),
        )
        self._render_test_report(task_root, task_id)
        return failure

    def record_recovery(
        self,
        project_root: Path,
        task_id: str,
        *,
        failure_id: str,
        decision: str,
        planned_paths: Sequence[str],
        reason: str,
        rollback_required: bool,
    ) -> RecoveryEvidence:
        task_root = task_path(project_root, task_id)
        snapshot = self._snapshot(task_root, task_id)
        known_failures = {item.id for item in snapshot.failures}
        if failure_id not in known_failures:
            raise _reference_invalid(f"Unknown failure: {failure_id!r}.")
        recovery = RecoveryEvidence(
            id=format_evidence_id(EvidenceKind.RECOVERY, len(snapshot.recoveries) + 1),
            task_id=task_id,
            failure_id=failure_id,
            decision=decision,
            planned_paths=_str_tuple(planned_paths),
            reason=reason,
            rollback_required=bool(rollback_required),
        )
        event_type = (
            LearningEventType.ROLLBACK_EXECUTED
            if rollback_required
            else LearningEventType.FIX_APPLIED
        )
        self._store.append(
            task_root,
            task_id,
            event_type,
            {"kind": "recovery", **_recovery_payload(recovery)},
            occurred_at=_now(),
        )
        self._render_test_report(task_root, task_id)
        return recovery

    def _render_test_report(self, task_root: Path, task_id: str) -> None:
        snapshot = self._snapshot(task_root, task_id)
        body = _render_test_report_body(snapshot)
        _write_generated(task_root, "TEST_REPORT.md", body)

    # ------------------------------------------------------------------
    # record_review → REVIEW.md
    # ------------------------------------------------------------------

    def record_review(
        self,
        project_root: Path,
        task_id: str,
        *,
        requirement_reviews: Sequence[Mapping[str, object]],
        quality_findings: Sequence[str] = (),
        untested_risks: Sequence[str] = (),
        plan_deviations: Sequence[str] = (),
        delivery_recommendation: str,
    ) -> None:
        task_root = task_path(project_root, task_id)
        snapshot = self._snapshot(task_root, task_id)
        known_requirements = {item.id for item in snapshot.requirements}
        known_changes = {item.id for item in snapshot.changes}
        known_tests = {item.id for item in snapshot.test_attempts}

        normalized_reviews: list[dict[str, object]] = []
        for raw in requirement_reviews:
            requirement_id = _text(raw, "requirement_id")
            if requirement_id not in known_requirements:
                raise _reference_invalid(f"Unknown requirement: {requirement_id!r}.")
            change_refs = _str_tuple(raw.get("change_refs", ()))
            test_refs = _str_tuple(raw.get("test_refs", ()))
            _require_refs(change_refs, known_changes)
            _require_refs(test_refs, known_tests)
            risk = raw.get("risk")
            normalized_reviews.append(
                {
                    "requirement_id": requirement_id,
                    "change_refs": list(change_refs),
                    "test_refs": list(test_refs),
                    "status": _text(raw, "status"),
                    "risk": risk if isinstance(risk, str) else None,
                }
            )

        self._store.append(
            task_root,
            task_id,
            LearningEventType.REQUIREMENT_REVIEWED,
            {
                "kind": "review",
                "requirement_reviews": normalized_reviews,
                "quality_findings": list(_str_tuple(quality_findings)),
                "untested_risks": list(_str_tuple(untested_risks)),
                "plan_deviations": list(_str_tuple(plan_deviations)),
                "delivery_recommendation": delivery_recommendation,
            },
            occurred_at=_now(),
        )
        body = _render_review_body(
            normalized_reviews,
            quality_findings,
            untested_risks,
            plan_deviations,
            delivery_recommendation,
        )
        _write_generated(task_root, "REVIEW.md", body)

    # ------------------------------------------------------------------
    # record_knowledge → KNOWLEDGE.md
    # ------------------------------------------------------------------

    def record_knowledge(
        self,
        project_root: Path,
        task_id: str,
        *,
        cards: Sequence[Mapping[str, object]],
    ) -> tuple[KnowledgeCard, ...]:
        if not cards:
            raise _invalid_input("At least one knowledge card is required.")
        task_root = task_path(project_root, task_id)
        snapshot = self._snapshot(task_root, task_id)
        groundable = (
            {item.id for item in snapshot.requirements}
            | {item.id for item in snapshot.decisions}
            | {item.id for item in snapshot.plan_steps}
            | {item.id for item in snapshot.changes}
            | {item.id for item in snapshot.failures}
            | {item.id for item in snapshot.recoveries}
        )
        concrete = (
            {item.id for item in snapshot.changes}
            | {item.id for item in snapshot.test_attempts}
            | {item.id for item in snapshot.failures}
        )
        card_seq = len(snapshot.knowledge_cards) + 1
        recorded: list[KnowledgeCard] = []
        for offset, raw in enumerate(cards):
            transfer_example = raw.get("transfer_example")
            if not isinstance(transfer_example, str) or not transfer_example.strip():
                raise _invalid_input("KnowledgeCard requires a transfer_example.")
            evidence_refs = _str_tuple(raw.get("evidence_refs", ()))
            _require_refs(evidence_refs, groundable)
            if not any(ref in groundable for ref in evidence_refs):
                raise _reference_invalid(
                    "KnowledgeCard must reference at least one R/D/P/C/F/REC."
                )
            if not any(ref in concrete for ref in evidence_refs):
                raise _reference_invalid(
                    "KnowledgeCard must reference at least one C/T/F."
                )
            card = KnowledgeCard(
                id=format_evidence_id(EvidenceKind.KNOWLEDGE, card_seq + offset),
                task_id=task_id,
                category=_text(raw, "category"),
                problem=_text(raw, "problem"),
                context=_text(raw, "context"),
                principle=_text(raw, "principle"),
                solution=_text(raw, "solution"),
                evidence_refs=evidence_refs,
                applicable_when=_text(raw, "applicable_when"),
                not_applicable_when=_text(raw, "not_applicable_when"),
                common_mistake=_text(raw, "common_mistake"),
                transfer_example=transfer_example,
            )
            self._store.append(
                task_root,
                task_id,
                LearningEventType.KNOWLEDGE_EXTRACTED,
                {"kind": "knowledge", **_knowledge_payload(card)},
                occurred_at=_now(),
            )
            recorded.append(card)

        snapshot = self._snapshot(task_root, task_id)
        body = _render_knowledge_body(snapshot)
        _write_generated(task_root, "KNOWLEDGE.md", body)
        return tuple(recorded)

    # ------------------------------------------------------------------
    # snapshot reconstruction
    # ------------------------------------------------------------------

    def load_snapshot(self, project_root: Path, task_id: str) -> LearningSnapshot:
        return self._snapshot(task_path(project_root, task_id), task_id)

    def _snapshot(self, task_root: Path, task_id: str) -> LearningSnapshot:
        events = self._store.read_events(task_root)
        requirements: list[RequirementEvidence] = []
        decisions: list[DecisionEvidence] = []
        plan_steps: list[PlanStepEvidence] = []
        changes: list[ChangeEvidence] = []
        test_attempts: list[TestAttemptEvidence] = []
        failures: list[FailureEvidence] = []
        recoveries: list[RecoveryEvidence] = []
        knowledge_cards: list[KnowledgeCard] = []
        for event in events:
            payload = event.payload
            kind = payload.get("kind")
            if kind == "requirement":
                requirements.append(
                    RequirementEvidence(
                        id=str(payload["id"]),
                        task_id=task_id,
                        source_text=str(payload["source_text"]),
                        student_understanding=str(payload["student_understanding"]),
                        acceptance_evidence=str(payload["acceptance_evidence"]),
                        priority=str(payload["priority"]),
                        is_core=bool(payload["is_core"]),
                    )
                )
            elif kind == "decision":
                decisions.append(
                    DecisionEvidence(
                        id=str(payload["id"]),
                        task_id=task_id,
                        chosen_option=str(payload["chosen_option"]),
                        rejected_options=_str_tuple(payload.get("rejected_options", ())),
                        rationale=str(payload["rationale"]),
                        requirement_refs=_str_tuple(payload.get("requirement_refs", ())),
                    )
                )
            elif kind == "plan_step":
                decision_ref = payload.get("decision_ref")
                plan_steps.append(
                    PlanStepEvidence(
                        id=str(payload["id"]),
                        task_id=task_id,
                        description=str(payload["description"]),
                        requirement_refs=_str_tuple(payload.get("requirement_refs", ())),
                        planned_paths=_str_tuple(payload.get("planned_paths", ())),
                        verification=str(payload.get("verification", "")),
                        decision_ref=decision_ref if isinstance(decision_ref, str) else None,
                    )
                )
            elif kind == "change":
                checkpoint = payload.get("pre_change_checkpoint_id")
                changes.append(
                    ChangeEvidence(
                        id=str(payload["id"]),
                        task_id=task_id,
                        pre_change_checkpoint_id=(
                            checkpoint if isinstance(checkpoint, str) else None
                        ),
                        action_id=str(payload["action_id"]),
                        changed_paths=_str_tuple(payload.get("changed_paths", ())),
                        diff_digest=str(payload["diff_digest"]),
                        reason=str(payload["reason"]),
                        requirement_refs=_str_tuple(payload.get("requirement_refs", ())),
                        plan_step_refs=_str_tuple(payload.get("plan_step_refs", ())),
                    )
                )
            elif kind == "test_attempt":
                category = payload.get("failure_category")
                test_attempts.append(
                    TestAttemptEvidence(
                        id=str(payload["id"]),
                        task_id=task_id,
                        command=str(payload["command"]),
                        started_at=str(payload["started_at"]),
                        finished_at=str(payload["finished_at"]),
                        exit_code=_as_int(payload["exit_code"]),
                        status=str(payload["status"]),
                        passed_count=_as_int(payload["passed_count"]),
                        failed_count=_as_int(payload["failed_count"]),
                        failure_category=category if isinstance(category, str) else None,
                        summary=str(payload["summary"]),
                        output_digest=str(payload["output_digest"]),
                        tested_change_ids=_str_tuple(payload.get("tested_change_ids", ())),
                        requirement_refs=_str_tuple(payload.get("requirement_refs", ())),
                    )
                )
            elif kind == "failure":
                failures.append(
                    FailureEvidence(
                        id=str(payload["id"]),
                        task_id=task_id,
                        test_attempt_id=str(payload["test_attempt_id"]),
                        failure_digest=str(payload["failure_digest"]),
                        category=str(payload["category"]),
                        summary=str(payload["summary"]),
                        failing_tests=_str_tuple(payload.get("failing_tests", ())),
                        affected_paths=_str_tuple(payload.get("affected_paths", ())),
                    )
                )
            elif kind == "recovery":
                recoveries.append(
                    RecoveryEvidence(
                        id=str(payload["id"]),
                        task_id=task_id,
                        failure_id=str(payload["failure_id"]),
                        decision=str(payload["decision"]),
                        planned_paths=_str_tuple(payload.get("planned_paths", ())),
                        reason=str(payload["reason"]),
                        rollback_required=bool(payload["rollback_required"]),
                    )
                )
            elif kind == "knowledge":
                knowledge_cards.append(
                    KnowledgeCard(
                        id=str(payload["id"]),
                        task_id=task_id,
                        category=str(payload["category"]),
                        problem=str(payload["problem"]),
                        context=str(payload["context"]),
                        principle=str(payload["principle"]),
                        solution=str(payload["solution"]),
                        evidence_refs=_str_tuple(payload.get("evidence_refs", ())),
                        applicable_when=str(payload["applicable_when"]),
                        not_applicable_when=str(payload["not_applicable_when"]),
                        common_mistake=str(payload["common_mistake"]),
                        transfer_example=str(payload["transfer_example"]),
                    )
                )
        return LearningSnapshot(
            task_id=task_id,
            requirements=tuple(requirements),
            decisions=tuple(decisions),
            plan_steps=tuple(plan_steps),
            changes=tuple(changes),
            test_attempts=tuple(test_attempts),
            failures=tuple(failures),
            recoveries=tuple(recoveries),
            knowledge_cards=tuple(knowledge_cards),
            source_event_seq=len(events),
            digest=events[-1].digest if events else None,
        )


# ----------------------------------------------------------------------
# payload helpers
# ----------------------------------------------------------------------


def _decision_payload(decision: DecisionEvidence) -> dict[str, object]:
    return {
        "id": decision.id,
        "chosen_option": decision.chosen_option,
        "rejected_options": list(decision.rejected_options),
        "rationale": decision.rationale,
        "requirement_refs": list(decision.requirement_refs),
    }


def _plan_step_payload(step: PlanStepEvidence) -> dict[str, object]:
    return {
        "id": step.id,
        "description": step.description,
        "requirement_refs": list(step.requirement_refs),
        "planned_paths": list(step.planned_paths),
        "verification": step.verification,
        "decision_ref": step.decision_ref,
    }


def _change_payload(change: ChangeEvidence) -> dict[str, object]:
    return {
        "id": change.id,
        "pre_change_checkpoint_id": change.pre_change_checkpoint_id,
        "action_id": change.action_id,
        "changed_paths": list(change.changed_paths),
        "diff_digest": change.diff_digest,
        "reason": change.reason,
        "requirement_refs": list(change.requirement_refs),
        "plan_step_refs": list(change.plan_step_refs),
    }


# ----------------------------------------------------------------------
# rendering
# ----------------------------------------------------------------------


def _attempt_payload(attempt: TestAttemptEvidence) -> dict[str, object]:
    return {
        "id": attempt.id,
        "command": attempt.command,
        "started_at": attempt.started_at,
        "finished_at": attempt.finished_at,
        "exit_code": attempt.exit_code,
        "status": attempt.status,
        "passed_count": attempt.passed_count,
        "failed_count": attempt.failed_count,
        "failure_category": attempt.failure_category,
        "summary": attempt.summary,
        "output_digest": attempt.output_digest,
        "tested_change_ids": list(attempt.tested_change_ids),
        "requirement_refs": list(attempt.requirement_refs),
    }


def _failure_payload(failure: FailureEvidence) -> dict[str, object]:
    return {
        "id": failure.id,
        "test_attempt_id": failure.test_attempt_id,
        "failure_digest": failure.failure_digest,
        "category": failure.category,
        "summary": failure.summary,
        "failing_tests": list(failure.failing_tests),
        "affected_paths": list(failure.affected_paths),
    }


def _recovery_payload(recovery: RecoveryEvidence) -> dict[str, object]:
    return {
        "id": recovery.id,
        "failure_id": recovery.failure_id,
        "decision": recovery.decision,
        "planned_paths": list(recovery.planned_paths),
        "reason": recovery.reason,
        "rollback_required": recovery.rollback_required,
    }


def _knowledge_payload(card: KnowledgeCard) -> dict[str, object]:
    return {
        "id": card.id,
        "category": card.category,
        "problem": card.problem,
        "context": card.context,
        "principle": card.principle,
        "solution": card.solution,
        "evidence_refs": list(card.evidence_refs),
        "applicable_when": card.applicable_when,
        "not_applicable_when": card.not_applicable_when,
        "common_mistake": card.common_mistake,
        "transfer_example": card.transfer_example,
    }


def _render_review_body(
    requirement_reviews: Sequence[Mapping[str, object]],
    quality_findings: Sequence[str],
    untested_risks: Sequence[str],
    plan_deviations: Sequence[str],
    delivery_recommendation: str,
) -> str:
    rows = ""
    for review in requirement_reviews:
        change_refs = review.get("change_refs", [])
        test_refs = review.get("test_refs", [])
        change_text = "、".join(change_refs) if isinstance(change_refs, list) else "无"
        test_text = "、".join(test_refs) if isinstance(test_refs, list) else "无"
        risk = review.get("risk")
        rows += (
            f"| {_cell(review.get('requirement_id', ''))} | "
            f"{_cell(change_text or '无')} | {_cell(test_text or '无')} | "
            f"{_cell(review.get('status', ''))} | {_cell(risk or '无')} |\n"
        )
    return (
        "# 最终审查\n\n"
        "## 1. 需求追踪矩阵\n\n"
        "| 需求 | 实现 | 测试 | 状态 | 风险 |\n"
        "| --- | --- | --- | --- | --- |\n"
        f"{rows}\n"
        "## 2. 关键代码质量审查\n\n"
        f"{_bullets(quality_findings)}\n\n"
        "## 3. 尚未验证的风险\n\n"
        f"{_bullets(untested_risks)}\n\n"
        "## 4. 偏离原计划的地方\n\n"
        f"{_bullets(plan_deviations)}\n\n"
        "## 5. 是否适合交付\n\n"
        f"- {_cell(delivery_recommendation)}\n"
    )


def _render_knowledge_body(snapshot: LearningSnapshot) -> str:
    sections = []
    for card in snapshot.knowledge_cards:
        evidence = "、".join(card.evidence_refs) or "无"
        sections.append(
            f"## {_cell(card.id)}：{_cell(card.principle)}\n\n"
            f"### 遇到的问题\n\n{_cell(card.problem)}\n\n"
            f"### 背景\n\n{_cell(card.context)}\n\n"
            f"### 本次如何解决\n\n{_cell(card.solution)}\n\n"
            f"### 背后的原则\n\n{_cell(card.principle)}\n\n"
            f"### 证据\n\n- {_cell(evidence)}\n\n"
            f"### 适用场景\n\n{_cell(card.applicable_when)}\n\n"
            f"### 不适用场景\n\n{_cell(card.not_applicable_when)}\n\n"
            f"### 常见错误\n\n{_cell(card.common_mistake)}\n\n"
            f"### 迁移练习\n\n{_cell(card.transfer_example)}\n"
        )
    body = "".join(sections) or "（暂无知识卡片）\n"
    return "# 知识复盘\n\n" + body


def _render_test_report_body(snapshot: LearningSnapshot) -> str:
    commands = sorted({attempt.command for attempt in snapshot.test_attempts})
    covered = sorted(
        {ref for attempt in snapshot.test_attempts for ref in attempt.requirement_refs}
    )
    attempt_rows = "".join(
        f"| {_cell(attempt.id)} | {_cell(attempt.started_at)} | {_cell(attempt.status)} | "
        f"{attempt.passed_count} | {attempt.failed_count} | "
        f"{_cell('、'.join(attempt.tested_change_ids) or '无')} |\n"
        for attempt in snapshot.test_attempts
    )
    failure_sections = []
    for failure in snapshot.failures:
        recoveries = [
            recovery
            for recovery in snapshot.recoveries
            if recovery.failure_id == failure.id
        ]
        recovery_line = (
            "、".join(f"{recovery.id}（{recovery.decision}）" for recovery in recoveries)
            or "无"
        )
        failure_sections.append(
            f"### {_cell(failure.id)}\n\n"
            f"- 来源测试：{_cell(failure.test_attempt_id)}\n"
            f"- 失败分类：{_cell(failure.category)}\n"
            f"- 失败现象：{_cell(failure.summary)}\n"
            f"- 失败用例：{_cell('、'.join(failure.failing_tests) or '无')}\n"
            f"- 修复路径：{_cell(recovery_line)}\n"
        )
    failure_block = "".join(failure_sections) or "- 无\n"
    return (
        "# 测试报告\n\n"
        "## 1. 测试策略\n\n"
        f"- 命令：{_cell('、'.join(commands) or '无')}\n"
        f"- 覆盖需求：{_cell('、'.join(covered) or '无')}\n\n"
        "## 2. 测试尝试\n\n"
        "| ID | 时间 | 结果 | 通过 | 失败 | 对应修改 |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        f"{attempt_rows}\n"
        "## 3. 失败记录\n\n"
        + (failure_block)
    )


def _render_spec_body(
    goal: str,
    snapshot: LearningSnapshot,
    boundaries: Sequence[str],
    constraints: Sequence[str],
    assumptions: Sequence[str],
) -> str:
    rows = "".join(
        f"| {_cell(item.id)} | {_cell(item.source_text)} | "
        f"{_cell(item.student_understanding)} | {_cell(item.acceptance_evidence)} | "
        f"{'核心' if item.is_core else _cell(item.priority)} |\n"
        for item in snapshot.requirements
    )
    return (
        "# 需求理解\n\n"
        "## 1. 任务目标\n\n"
        f"{_cell(goal)}\n\n"
        "## 2. 需求清单\n\n"
        "| ID | 原始要求 | 我的理解 | 验收证据 | 优先级 |\n"
        "| --- | --- | --- | --- | --- |\n"
        f"{rows}\n"
        "## 3. 输入、输出和边界条件\n\n"
        f"{_bullets(boundaries)}\n\n"
        "## 4. 课程约束与禁止事项\n\n"
        f"{_bullets(constraints)}\n\n"
        "## 5. 不确定项与假设\n\n"
        f"{_bullets(assumptions)}\n"
    )


def _render_plan_body(snapshot: LearningSnapshot) -> str:
    decision_lines = []
    for decision in snapshot.decisions:
        rejected = "、".join(decision.rejected_options) or "无"
        decision_lines.append(
            f"### {_cell(decision.id)}：{_cell(decision.chosen_option)}\n\n"
            f"- 理由：{_cell(decision.rationale)}\n"
            f"- 放弃方案：{_cell(rejected)}\n"
            f"- 覆盖需求：{_cell('、'.join(decision.requirement_refs) or '无')}\n"
        )
    step_rows = "".join(
        f"| {_cell(step.id)} | {_cell('、'.join(step.requirement_refs) or '无')} | "
        f"{_cell('、'.join(step.planned_paths) or '无')} | {_cell(step.description)} | "
        f"{_cell(step.verification or '无')} |\n"
        for step in snapshot.plan_steps
    )
    decision_block = "".join(decision_lines) or "（暂无决策记录）\n"
    return (
        "# 实现计划\n\n"
        "## 1. 候选方案与最终选择\n\n"
        f"{decision_block}\n"
        "## 2. 实现步骤\n\n"
        "| 步骤 | 对应需求 | 预计文件 | 修改内容 | 验证方式 |\n"
        "| --- | --- | --- | --- | --- |\n"
        f"{step_rows}\n"
    )


def _render_implementation_body(snapshot: LearningSnapshot) -> str:
    sections = []
    for change in snapshot.changes:
        files = "".join(f"  - `{_cell(path)}`\n" for path in change.changed_paths)
        sections.append(
            f"### {_cell(change.id)}\n\n"
            f"- 对应需求：{_cell('、'.join(change.requirement_refs) or '无')}\n"
            f"- 对应计划：{_cell('、'.join(change.plan_step_refs) or '无')}\n"
            f"- 修改前 Checkpoint：{_cell(change.pre_change_checkpoint_id or '无')}\n"
            f"- Diff 摘要：`{_cell(change.diff_digest)}`\n"
            "- 修改文件：\n"
            f"{files}\n"
            "#### 为什么这样修改\n\n"
            f"{_cell(change.reason)}\n"
        )
    change_block = "".join(sections) or "（暂无修改批次）\n"
    return "# 实现记录\n\n## 修改批次\n\n" + change_block


def _bullets(items: Sequence[str]) -> str:
    if not items:
        return "- 无"
    return "\n".join(f"- {_cell(item)}" for item in items)


def _cell(value: object) -> str:
    from hancode.delivery_support.result import _cell as _delivery_cell

    return _delivery_cell(str(value))


def _write_generated(task_root: Path, filename: str, body: str) -> None:
    target = task_root / filename
    existing = target.read_text(encoding="utf-8") if target.is_file() else ""
    rendered = replace_generated_region(existing, body)
    _write_artifact(task_root, filename, rendered)


# ----------------------------------------------------------------------
# input helpers
# ----------------------------------------------------------------------


def _text(raw: Mapping[str, object], key: str, *, default: str | None = None) -> str:
    value = raw.get(key, default)
    if not isinstance(value, str) or (not value and default is None):
        raise _invalid_input(f"Field {key!r} must be a non-empty string.")
    return value


def _as_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _invalid_input("Expected an integer value.")
    return value


def _str_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        raise _invalid_input("Expected a list of strings, not a single string.")
    if not isinstance(value, Sequence):
        raise _invalid_input("Expected a list of strings.")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            raise _invalid_input("List entries must be non-empty strings.")
        result.append(item)
    return tuple(result)


def _require_refs(refs: Sequence[str], known: set[str]) -> None:
    for ref in refs:
        if ref not in known:
            raise _reference_invalid(f"Unknown evidence reference: {ref!r}.")


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _invalid_input(message: str) -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code="learning_input_invalid",
            message=message,
            phase="spec",
            denied_rule="valid_learning_input_required",
            suggested_fix="Provide well-formed structured learning input.",
        )
    )


def _reference_invalid(message: str) -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code="learning_reference_invalid",
            message=message,
            phase="plan",
            denied_rule="learning_reference_must_exist",
            suggested_fix="Reference only evidence IDs that exist in this task.",
        )
    )


__all__ = ["LearningService"]
