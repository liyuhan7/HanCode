from __future__ import annotations

from pathlib import Path

import pytest

from hancode.app.learning_service import LearningService
from hancode.core.errors import HanCodeError
from hancode.storage.learning_store import LearningStore
from hancode.storage.workspace import init_project_workspace, init_task_workspace


def _project(tmp_path: Path) -> Path:
    init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )
    init_task_workspace(tmp_path, "task-001")
    return tmp_path


def _record_requirements(service: LearningService, project_root: Path) -> None:
    service.record_requirements(
        project_root,
        "task-001",
        goal="Build an input parser",
        requirements=[
            {
                "source_text": "The parser must reject empty input",
                "student_understanding": "Empty strings raise a clear error",
                "acceptance_evidence": "T-000001",
                "priority": "core",
                "is_core": True,
            },
            {
                "source_text": "Support UTF-8",
                "student_understanding": "Handle non-ascii",
                "acceptance_evidence": "manual",
                "priority": "normal",
                "is_core": False,
            },
        ],
        boundaries=["Only single-line input"],
        constraints=["No third-party parser"],
        assumptions=["Input is provided as str"],
    )


def test_record_requirements_generates_stable_spec(tmp_path: Path) -> None:
    project_root = _project(tmp_path)
    service = LearningService()

    _record_requirements(service, project_root)
    spec_path = tmp_path / ".hancode" / "tasks" / "task-001" / "SPEC.md"
    first = spec_path.read_text(encoding="utf-8")

    # student note in the student region survives a re-render
    spec_path.write_text(
        first + "\n补充：这是我的额外理解。\n", encoding="utf-8"
    )
    _record_requirements(service, project_root)
    second = spec_path.read_text(encoding="utf-8")

    assert "# 需求理解" in first
    assert "R-0001" in first
    assert "R-0002" in first
    assert "补充：这是我的额外理解。" in second


def test_record_requirements_persists_events_and_evidence(tmp_path: Path) -> None:
    project_root = _project(tmp_path)
    service = LearningService()

    _record_requirements(service, project_root)

    task_root = tmp_path / ".hancode" / "tasks" / "task-001"
    events = LearningStore().read_events(task_root)
    assert len(events) == 2
    assert all(event.event_type.value == "RequirementUnderstood" for event in events)
    state_artifacts_present = (task_root / "SPEC.md").is_file()
    assert state_artifacts_present


def test_record_plan_rejects_unknown_requirement(tmp_path: Path) -> None:
    project_root = _project(tmp_path)
    service = LearningService()
    _record_requirements(service, project_root)

    with pytest.raises(HanCodeError) as exc_info:
        service.record_plan(
            project_root,
            "task-001",
            decisions=[
                {
                    "chosen_option": "A",
                    "rejected_options": ["B"],
                    "rationale": "simpler",
                    "requirement_refs": ["R-9999"],
                }
            ],
            plan_steps=[
                {
                    "description": "parse",
                    "requirement_refs": ["R-9999"],
                    "planned_paths": ["src/parser.py"],
                    "verification": "T-000001",
                    "decision_ref": "D-0001",
                }
            ],
        )

    assert exc_info.value.to_dict()["error_code"] == "learning_reference_invalid"


def test_record_plan_generates_plan_markdown(tmp_path: Path) -> None:
    project_root = _project(tmp_path)
    service = LearningService()
    _record_requirements(service, project_root)

    service.record_plan(
        project_root,
        "task-001",
        decisions=[
            {
                "chosen_option": "Recursive descent",
                "rejected_options": ["Regex-only"],
                "rationale": "Clearer error handling",
                "requirement_refs": ["R-0001"],
            }
        ],
        plan_steps=[
            {
                "description": "Add empty-input guard",
                "requirement_refs": ["R-0001"],
                "planned_paths": ["src/parser.py"],
                "verification": "T-000001",
                "decision_ref": "D-0001",
            }
        ],
    )

    plan_path = tmp_path / ".hancode" / "tasks" / "task-001" / "PLAN.md"
    content = plan_path.read_text(encoding="utf-8")
    assert "# 实现计划" in content
    assert "D-0001" in content
    assert "P-0001" in content
    assert "Recursive descent" in content


def test_record_change_creates_change_evidence_and_implementation(
    tmp_path: Path,
) -> None:
    project_root = _project(tmp_path)
    service = LearningService()
    _record_requirements(service, project_root)

    change = service.record_change(
        project_root,
        "task-001",
        pre_change_checkpoint_id="ckpt-001",
        action_id="evt-000001",
        changed_paths=["src/parser.py"],
        diff_digest="a" * 64,
        reason="Add empty-input validation",
        requirement_refs=["R-0001"],
        plan_step_refs=[],
    )

    assert change.id == "C-0001"
    impl_path = tmp_path / ".hancode" / "tasks" / "task-001" / "IMPLEMENTATION.md"
    content = impl_path.read_text(encoding="utf-8")
    assert "# 实现记录" in content
    assert "C-0001" in content
    assert "src/parser.py" in content
    assert "ckpt-001" in content


def test_record_change_rejects_unknown_requirement_ref(tmp_path: Path) -> None:
    project_root = _project(tmp_path)
    service = LearningService()
    _record_requirements(service, project_root)

    with pytest.raises(HanCodeError) as exc_info:
        service.record_change(
            project_root,
            "task-001",
            pre_change_checkpoint_id="ckpt-001",
            action_id="evt-000001",
            changed_paths=["src/parser.py"],
            diff_digest="a" * 64,
            reason="x",
            requirement_refs=["R-9999"],
            plan_step_refs=[],
        )

    assert exc_info.value.to_dict()["error_code"] == "learning_reference_invalid"
