from __future__ import annotations

from pathlib import Path

from hancode.app.learning_service import LearningService
from hancode.delivery_support.collector import collect_learning_delivery
from hancode.delivery_support.validator import validate_learning_delivery
from hancode.storage.workspace import init_project_workspace, init_task_workspace


def _full_task(tmp_path: Path) -> Path:
    init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )
    init_task_workspace(tmp_path, "task-001")
    service = LearningService()
    service.record_requirements(
        tmp_path,
        "task-001",
        goal="parser",
        requirements=[
            {
                "source_text": "reject empty",
                "student_understanding": "empty raises",
                "acceptance_evidence": "T-000001",
                "priority": "core",
                "is_core": True,
            }
        ],
    )
    service.record_change(
        tmp_path,
        "task-001",
        pre_change_checkpoint_id="ckpt-001",
        action_id="evt-000001",
        changed_paths=["src/parser.py"],
        diff_digest="a" * 64,
        reason="add guard",
        requirement_refs=["R-0001"],
        plan_step_refs=[],
    )
    service.record_test_attempt(
        tmp_path,
        "task-001",
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
        tested_change_ids=["C-0001"],
        requirement_refs=["R-0001"],
    )
    return tmp_path


def test_collect_returns_snapshot_and_matrix(tmp_path: Path) -> None:
    project_root = _full_task(tmp_path)

    collected = collect_learning_delivery(project_root, "task-001")

    assert collected.snapshot.task_id == "task-001"
    assert collected.matrix.coverage["R-0001"] == "covered"
    assert len(collected.snapshot.changes) == 1


def test_validate_passes_for_covered_core_requirement(tmp_path: Path) -> None:
    project_root = _full_task(tmp_path)
    collected = collect_learning_delivery(project_root, "task-001")

    validation = validate_learning_delivery(collected)

    assert validation.blockers == ()
    assert validation.learning_contract_status == "verified"


def test_validate_blocks_when_core_requirement_uncovered(tmp_path: Path) -> None:
    init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )
    init_task_workspace(tmp_path, "task-001")
    LearningService().record_requirements(
        tmp_path,
        "task-001",
        goal="parser",
        requirements=[
            {
                "source_text": "reject empty",
                "student_understanding": "empty raises",
                "acceptance_evidence": "T-000001",
                "priority": "core",
                "is_core": True,
            }
        ],
    )

    collected = collect_learning_delivery(tmp_path, "task-001")
    validation = validate_learning_delivery(collected)

    assert any("R-0001" in blocker for blocker in validation.blockers)
    assert validation.learning_contract_status != "verified"


def test_validate_warns_when_no_knowledge_card(tmp_path: Path) -> None:
    project_root = _full_task(tmp_path)
    collected = collect_learning_delivery(project_root, "task-001")

    validation = validate_learning_delivery(collected)

    assert any("知识" in warning or "KnowledgeCard" in warning for warning in validation.warnings)
