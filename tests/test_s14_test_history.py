from __future__ import annotations

from pathlib import Path

from hancode.app.learning_service import LearningService
from hancode.storage.workspace import init_project_workspace, init_task_workspace


def _project(tmp_path: Path) -> Path:
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
        goal="Build a parser",
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
    return tmp_path


def _attempt(
    service: LearningService,
    project_root: Path,
    *,
    status: str,
    passed: int,
    failed: int,
    started: str,
):
    return service.record_test_attempt(
        project_root,
        "task-001",
        command="pytest",
        started_at=started,
        finished_at=started,
        exit_code=0 if status == "passed" else 1,
        status=status,
        passed_count=passed,
        failed_count=failed,
        failure_category="assertion" if status == "failed" else None,
        summary=f"{passed} passed {failed} failed",
        output_digest="a" * 64,
        tested_change_ids=(),
        requirement_refs=("R-0001",),
    )


def test_failed_attempt_survives_later_pass(tmp_path: Path) -> None:
    project_root = _project(tmp_path)
    service = LearningService()

    first = _attempt(
        service, project_root, status="failed", passed=5, failed=2,
        started="2026-08-06T00:00:00Z",
    )
    second = _attempt(
        service, project_root, status="passed", passed=7, failed=0,
        started="2026-08-06T00:01:00Z",
    )

    assert first.id == "T-000001"
    assert second.id == "T-000002"
    report = (tmp_path / ".hancode" / "tasks" / "task-001" / "TEST_REPORT.md").read_text(
        encoding="utf-8"
    )
    # both attempts remain visible; failed history not overwritten by later pass
    assert "T-000001" in report
    assert "T-000002" in report
    assert "failed" in report
    assert "passed" in report


def test_test_report_has_strategy_and_attempts_sections(tmp_path: Path) -> None:
    project_root = _project(tmp_path)
    service = LearningService()
    _attempt(
        service, project_root, status="passed", passed=3, failed=0,
        started="2026-08-06T00:00:00Z",
    )

    report = (tmp_path / ".hancode" / "tasks" / "task-001" / "TEST_REPORT.md").read_text(
        encoding="utf-8"
    )
    assert "# 测试报告" in report
    assert "## 1. 测试策略" in report
    assert "## 2. 测试尝试" in report


def test_failure_and_recovery_chain(tmp_path: Path) -> None:
    project_root = _project(tmp_path)
    service = LearningService()

    attempt = _attempt(
        service, project_root, status="failed", passed=5, failed=2,
        started="2026-08-06T00:00:00Z",
    )
    failure = service.record_failure(
        project_root,
        "task-001",
        test_attempt_id=attempt.id,
        failure_digest="c" * 64,
        category="assertion",
        summary="IndexError on empty input",
        failing_tests=("tests/test_parser.py::test_empty",),
        affected_paths=("src/parser.py",),
    )
    recovery = service.record_recovery(
        project_root,
        "task-001",
        failure_id=failure.id,
        decision="modify_source",
        planned_paths=("src/parser.py",),
        reason="add empty-input guard",
        rollback_required=False,
    )

    assert failure.id == "F-000001"
    assert recovery.id == "REC-0001"
    report = (tmp_path / ".hancode" / "tasks" / "task-001" / "TEST_REPORT.md").read_text(
        encoding="utf-8"
    )
    assert "F-000001" in report
    assert "REC-0001" in report
    assert "IndexError on empty input" in report


def test_failure_rejects_unknown_attempt(tmp_path: Path) -> None:
    project_root = _project(tmp_path)
    service = LearningService()

    import pytest

    from hancode.core.errors import HanCodeError

    with pytest.raises(HanCodeError) as exc_info:
        service.record_failure(
            project_root,
            "task-001",
            test_attempt_id="T-000099",
            failure_digest="c" * 64,
            category="assertion",
            summary="x",
            failing_tests=(),
            affected_paths=(),
        )

    assert exc_info.value.to_dict()["error_code"] == "learning_reference_invalid"
