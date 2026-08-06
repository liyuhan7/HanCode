from __future__ import annotations

from pathlib import Path

from hancode.app.learning_inspection_service import LearningInspectionService
from hancode.app.learning_service import LearningService
from hancode.storage.workspace import init_project_workspace, init_task_workspace


def _task(tmp_path: Path) -> Path:
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
        reason="add empty-input guard",
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
    service.record_knowledge(
        tmp_path,
        "task-001",
        cards=[
            {
                "category": "reusable_pattern",
                "problem": "empty input crashes",
                "context": "cli parser",
                "principle": "validate at boundary",
                "solution": "guard in parse_input",
                "evidence_refs": ["R-0001", "C-0001"],
                "applicable_when": "external input",
                "not_applicable_when": "trusted internal",
                "common_mistake": "only fix symptom",
                "transfer_example": "json schema layer",
            }
        ],
    )
    return tmp_path


def test_overview_reports_counts_cards_and_coverage(tmp_path: Path) -> None:
    project_root = _task(tmp_path)

    overview = LearningInspectionService().overview(project_root, "task-001")

    assert overview.requirement_count == 1
    assert overview.change_count == 1
    assert overview.test_attempt_count == 1
    assert overview.knowledge_cards[0].id == "K-0001"
    assert overview.coverage[0].coverage == "covered"
