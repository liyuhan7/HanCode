from __future__ import annotations

import json
from pathlib import Path

from hancode.app.delivery_service import DeliveryService
from hancode.app.learning_service import LearningService
from hancode.core.models import TaskStatus
from hancode.storage.workspace import init_project_workspace, init_task_workspace


def _covered_task(tmp_path: Path) -> Path:
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
    return tmp_path


def test_evaluate_learning_reports_submission_eligible(tmp_path: Path) -> None:
    project_root = _covered_task(tmp_path)

    result = DeliveryService().evaluate_learning(project_root, "task-001")

    assert result.status is TaskStatus.COMPLETED
    assert result.submission_eligible is True
    assert result.learning_contract_status == "verified"
    assert result.blockers == ()


def test_evaluate_learning_marks_legacy_task_unverified(tmp_path: Path) -> None:
    project_root = _covered_task(tmp_path)
    state_file = project_root / ".hancode" / "tasks" / "task-001" / "state.json"
    data = json.loads(state_file.read_text(encoding="utf-8"))
    data.pop("learning_contract_version", None)
    state_file.write_text(json.dumps(data), encoding="utf-8")

    result = DeliveryService().evaluate_learning(project_root, "task-001")

    assert result.submission_eligible is False
    assert result.learning_contract_status == "legacy_unverified"
