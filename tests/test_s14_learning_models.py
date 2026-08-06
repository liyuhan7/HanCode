from __future__ import annotations

import dataclasses

import pytest

from hancode.core.learning_evidence import (
    ChangeEvidence,
    DecisionEvidence,
    EvidenceKind,
    FailureEvidence,
    KnowledgeCard,
    PlanStepEvidence,
    RecoveryEvidence,
    RequirementEvidence,
    TestAttemptEvidence,
    TraceabilityLink,
    format_evidence_id,
    is_valid_evidence_id,
    parse_evidence_kind,
)


@pytest.mark.parametrize(
    ("kind", "seq", "expected"),
    [
        (EvidenceKind.REQUIREMENT, 1, "R-0001"),
        (EvidenceKind.DECISION, 12, "D-0012"),
        (EvidenceKind.PLAN_STEP, 7, "P-0007"),
        (EvidenceKind.CHANGE, 3, "C-0003"),
        (EvidenceKind.KNOWLEDGE, 99, "K-0099"),
        (EvidenceKind.TEST_ATTEMPT, 1, "T-000001"),
        (EvidenceKind.FAILURE, 42, "F-000042"),
        (EvidenceKind.RECOVERY, 5, "REC-0005"),
    ],
)
def test_format_evidence_id(kind: EvidenceKind, seq: int, expected: str) -> None:
    assert format_evidence_id(kind, seq) == expected


@pytest.mark.parametrize(
    ("evidence_id", "kind"),
    [
        ("R-0001", EvidenceKind.REQUIREMENT),
        ("T-000001", EvidenceKind.TEST_ATTEMPT),
        ("REC-0005", EvidenceKind.RECOVERY),
    ],
)
def test_parse_evidence_kind(evidence_id: str, kind: EvidenceKind) -> None:
    assert parse_evidence_kind(evidence_id) is kind


@pytest.mark.parametrize(
    "bad_id",
    [
        "",
        "R-1",
        "R-00001",
        "X-0001",
        "T-0001",
        "REC-00001",
        "R0001",
        "r-0001",
        "C-0001 ",
    ],
)
def test_is_valid_evidence_id_rejects_malformed(bad_id: str) -> None:
    assert is_valid_evidence_id(bad_id) is False


def test_format_evidence_id_rejects_nonpositive_sequence() -> None:
    with pytest.raises(ValueError):
        format_evidence_id(EvidenceKind.REQUIREMENT, 0)


def test_requirement_evidence_is_frozen_and_validates_id() -> None:
    requirement = RequirementEvidence(
        id="R-0001",
        task_id="task-001",
        source_text="original",
        student_understanding="my words",
        acceptance_evidence="T-000001",
        priority="core",
        is_core=True,
    )
    assert requirement.schema_version == 1
    with pytest.raises(dataclasses.FrozenInstanceError):
        requirement.is_core = False  # type: ignore[misc]


def test_requirement_evidence_rejects_wrong_id_prefix() -> None:
    with pytest.raises(ValueError):
        RequirementEvidence(
            id="C-0001",
            task_id="task-001",
            source_text="x",
            student_understanding="y",
            acceptance_evidence="z",
            priority="core",
            is_core=True,
        )


def test_change_evidence_requires_change_id() -> None:
    change = ChangeEvidence(
        id="C-0001",
        task_id="task-001",
        pre_change_checkpoint_id="ckpt-001",
        action_id="evt-000001",
        changed_paths=("src/main.py",),
        diff_digest="a" * 64,
        reason="add validation",
        requirement_refs=("R-0001",),
        plan_step_refs=("P-0001",),
    )
    assert change.changed_paths == ("src/main.py",)
    with pytest.raises(ValueError):
        ChangeEvidence(
            id="T-000001",
            task_id="task-001",
            pre_change_checkpoint_id="ckpt-001",
            action_id="evt-000001",
            changed_paths=("src/main.py",),
            diff_digest="a" * 64,
            reason="add validation",
            requirement_refs=(),
            plan_step_refs=(),
        )


def test_test_attempt_and_failure_and_recovery_ids() -> None:
    attempt = TestAttemptEvidence(
        id="T-000001",
        task_id="task-001",
        command="pytest",
        started_at="2026-08-06T00:00:00Z",
        finished_at="2026-08-06T00:00:01Z",
        exit_code=1,
        status="failed",
        passed_count=5,
        failed_count=2,
        failure_category="assertion",
        summary="2 failed",
        output_digest="b" * 64,
        tested_change_ids=("C-0001",),
        requirement_refs=("R-0001",),
    )
    failure = FailureEvidence(
        id="F-000001",
        task_id="task-001",
        test_attempt_id="T-000001",
        failure_digest="c" * 64,
        category="assertion",
        summary="index error",
        failing_tests=("tests/test_x.py::test_y",),
        affected_paths=("src/main.py",),
    )
    recovery = RecoveryEvidence(
        id="REC-0001",
        task_id="task-001",
        failure_id="F-000001",
        decision="modify_source",
        planned_paths=("src/main.py",),
        reason="fix boundary",
        rollback_required=False,
    )
    assert (attempt.id, failure.id, recovery.id) == ("T-000001", "F-000001", "REC-0001")


def test_decision_and_plan_step_ids() -> None:
    decision = DecisionEvidence(
        id="D-0001",
        task_id="task-001",
        chosen_option="A",
        rejected_options=("B",),
        rationale="simpler",
        requirement_refs=("R-0001",),
    )
    plan_step = PlanStepEvidence(
        id="P-0001",
        task_id="task-001",
        description="parse input",
        requirement_refs=("R-0001",),
        planned_paths=("src/parser.py",),
        verification="T-000001",
        decision_ref="D-0001",
    )
    assert (decision.id, plan_step.id) == ("D-0001", "P-0001")


def test_knowledge_card_requires_k_id_and_holds_transfer_example() -> None:
    card = KnowledgeCard(
        id="K-0001",
        task_id="task-001",
        category="reusable_pattern",
        problem="p",
        context="c",
        principle="pr",
        solution="s",
        evidence_refs=("R-0001", "C-0001"),
        applicable_when="cli input",
        not_applicable_when="trusted internal",
        common_mistake="only fix symptom",
        transfer_example="json schema layer",
    )
    assert card.transfer_example == "json schema layer"
    with pytest.raises(ValueError):
        dataclasses.replace(card, id="R-0001")


def test_traceability_link_rejects_unknown_relation() -> None:
    link = TraceabilityLink(
        source_id="R-0001",
        target_id="D-0001",
        relation="REQUIREMENT_DECISION",
    )
    assert link.relation == "REQUIREMENT_DECISION"
    with pytest.raises(ValueError):
        TraceabilityLink(
            source_id="R-0001",
            target_id="D-0001",
            relation="NOT_A_RELATION",
        )
