from __future__ import annotations

from pathlib import Path

import pytest

from hancode.app.learning_service import LearningService
from hancode.app.reflection_service import (
    ReflectionConflictError,
    ReflectionSection,
    ReflectionService,
)
from hancode.storage.workspace import init_project_workspace, init_task_workspace


def _task_with_spec(tmp_path: Path) -> Path:
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
    return tmp_path


def test_save_reflection_persists_and_projects_to_markdown(tmp_path: Path) -> None:
    project_root = _task_with_spec(tmp_path)
    service = ReflectionService()

    result = service.save_reflection(
        project_root,
        "task-001",
        artifact="SPEC.md",
        section=ReflectionSection.MY_UNDERSTANDING,
        content="我理解这是一个输入边界校验任务。",
        expected_reflection_revision=0,
    )

    assert result.revision == 1
    spec = (project_root / ".hancode" / "tasks" / "task-001" / "SPEC.md").read_text(
        encoding="utf-8"
    )
    assert "我理解这是一个输入边界校验任务。" in spec
    # generated region is preserved
    assert "# 需求理解" in spec


def test_reflection_revision_conflict_is_rejected(tmp_path: Path) -> None:
    project_root = _task_with_spec(tmp_path)
    service = ReflectionService()
    service.save_reflection(
        project_root,
        "task-001",
        artifact="SPEC.md",
        section=ReflectionSection.MY_UNDERSTANDING,
        content="first",
        expected_reflection_revision=0,
    )

    with pytest.raises(ReflectionConflictError):
        service.save_reflection(
            project_root,
            "task-001",
            artifact="SPEC.md",
            section=ReflectionSection.OPEN_QUESTIONS,
            content="stale write",
            expected_reflection_revision=0,
        )


def test_reflection_read_returns_saved_sections(tmp_path: Path) -> None:
    project_root = _task_with_spec(tmp_path)
    service = ReflectionService()
    service.save_reflection(
        project_root,
        "task-001",
        artifact="SPEC.md",
        section=ReflectionSection.PEER_FEEDBACK,
        content="同伴建议补充大输入测试。",
        expected_reflection_revision=0,
    )

    reflection = service.read_reflections(project_root, "task-001")

    assert reflection.sections["SPEC.md"]["peer_feedback"] == "同伴建议补充大输入测试。"


def test_reflection_rejects_secret_content(tmp_path: Path) -> None:
    project_root = _task_with_spec(tmp_path)
    service = ReflectionService()

    with pytest.raises(Exception):
        service.save_reflection(
            project_root,
            "task-001",
            artifact="SPEC.md",
            section=ReflectionSection.MY_UNDERSTANDING,
            content='api_key = "sk-1234567890abcdef1234"',
            expected_reflection_revision=0,
        )
