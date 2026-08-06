from __future__ import annotations

from hancode.core.learning_evidence import (
    ChangeEvidence,
    FailureEvidence,
    LearningSnapshot,
    RecoveryEvidence,
    RequirementEvidence,
    TestAttemptEvidence,
)
from hancode.runtime.traceability_builder import build_traceability


def _requirement(is_core: bool = True) -> RequirementEvidence:
    return RequirementEvidence(
        id="R-0001",
        task_id="task-001",
        source_text="reject empty",
        student_understanding="empty raises",
        acceptance_evidence="T-000001",
        priority="core",
        is_core=is_core,
    )


def _change() -> ChangeEvidence:
    return ChangeEvidence(
        id="C-0001",
        task_id="task-001",
        pre_change_checkpoint_id="ckpt-001",
        action_id="evt-000001",
        changed_paths=("src/parser.py",),
        diff_digest="a" * 64,
        reason="add guard",
        requirement_refs=("R-0001",),
        plan_step_refs=(),
    )


def _passing_attempt() -> TestAttemptEvidence:
    return TestAttemptEvidence(
        id="T-000001",
        task_id="task-001",
        command="pytest",
        started_at="2026-08-06T00:01:00Z",
        finished_at="2026-08-06T00:01:01Z",
        exit_code=0,
        status="passed",
        passed_count=7,
        failed_count=0,
        failure_category=None,
        summary="ok",
        output_digest="b" * 64,
        tested_change_ids=("C-0001",),
        requirement_refs=("R-0001",),
    )


def test_core_requirement_covered_with_full_chain() -> None:
    snapshot = LearningSnapshot(
        task_id="task-001",
        requirements=(_requirement(),),
        changes=(_change(),),
        test_attempts=(_passing_attempt(),),
    )

    matrix = build_traceability(snapshot)

    assert matrix.coverage["R-0001"] == "covered"
    relations = {(link.source_id, link.target_id, link.relation) for link in matrix.links}
    assert ("C-0001", "T-000001", "CHANGE_TEST") in relations
    assert ("R-0001", "C-0001", "PLAN_STEP_CHANGE") not in relations  # no plan step


def test_core_requirement_without_passing_test_is_not_covered() -> None:
    snapshot = LearningSnapshot(
        task_id="task-001",
        requirements=(_requirement(),),
        changes=(_change(),),
        test_attempts=(),
    )

    matrix = build_traceability(snapshot)

    assert matrix.coverage["R-0001"] != "covered"


def test_overall_pass_does_not_cover_unlinked_requirement() -> None:
    other_requirement = RequirementEvidence(
        id="R-0002",
        task_id="task-001",
        source_text="utf8",
        student_understanding="handle non-ascii",
        acceptance_evidence="manual",
        priority="normal",
        is_core=True,
    )
    snapshot = LearningSnapshot(
        task_id="task-001",
        requirements=(_requirement(), other_requirement),
        changes=(_change(),),
        test_attempts=(_passing_attempt(),),
    )

    matrix = build_traceability(snapshot)

    assert matrix.coverage["R-0001"] == "covered"
    assert matrix.coverage["R-0002"] != "covered"


def test_failure_recovery_change_links() -> None:
    failure = FailureEvidence(
        id="F-000001",
        task_id="task-001",
        test_attempt_id="T-000001",
        failure_digest="c" * 64,
        category="assertion",
        summary="boom",
        failing_tests=(),
        affected_paths=(),
    )
    recovery = RecoveryEvidence(
        id="REC-0001",
        task_id="task-001",
        failure_id="F-000001",
        decision="modify_source",
        planned_paths=("src/parser.py",),
        reason="fix",
        rollback_required=False,
    )
    snapshot = LearningSnapshot(
        task_id="task-001",
        requirements=(_requirement(),),
        changes=(_change(),),
        test_attempts=(_passing_attempt(),),
        failures=(failure,),
        recoveries=(recovery,),
    )

    matrix = build_traceability(snapshot)
    relations = {(link.source_id, link.target_id, link.relation) for link in matrix.links}
    assert ("T-000001", "F-000001", "TEST_FAILURE") in relations
    assert ("F-000001", "REC-0001", "FAILURE_RECOVERY") in relations
