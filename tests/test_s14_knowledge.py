from __future__ import annotations

from pathlib import Path

import pytest

from hancode.app.learning_service import LearningService
from hancode.core.errors import HanCodeError
from hancode.storage.workspace import init_project_workspace, init_task_workspace


def _setup(tmp_path: Path) -> tuple[LearningService, Path]:
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
    return service, tmp_path


def test_record_review_renders_matrix(tmp_path: Path) -> None:
    service, project_root = _setup(tmp_path)

    service.record_review(
        project_root,
        "task-001",
        requirement_reviews=[
            {
                "requirement_id": "R-0001",
                "change_refs": ["C-0001"],
                "test_refs": [],
                "status": "covered",
                "risk": None,
            }
        ],
        quality_findings=["clear boundary"],
        untested_risks=["large input"],
        plan_deviations=[],
        delivery_recommendation="ship",
    )

    review = (project_root / ".hancode" / "tasks" / "task-001" / "REVIEW.md").read_text(
        encoding="utf-8"
    )
    assert "# 最终审查" in review
    assert "R-0001" in review
    assert "C-0001" in review


def test_record_review_rejects_unknown_reference(tmp_path: Path) -> None:
    service, project_root = _setup(tmp_path)

    with pytest.raises(HanCodeError) as exc_info:
        service.record_review(
            project_root,
            "task-001",
            requirement_reviews=[
                {
                    "requirement_id": "R-0001",
                    "change_refs": ["C-9999"],
                    "test_refs": [],
                    "status": "covered",
                    "risk": None,
                }
            ],
            quality_findings=[],
            untested_risks=[],
            plan_deviations=[],
            delivery_recommendation="ship",
        )

    assert exc_info.value.to_dict()["error_code"] == "learning_reference_invalid"


def test_record_knowledge_card_renders_and_assigns_k_id(tmp_path: Path) -> None:
    service, project_root = _setup(tmp_path)

    cards = service.record_knowledge(
        project_root,
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

    assert cards[0].id == "K-0001"
    knowledge = (
        project_root / ".hancode" / "tasks" / "task-001" / "KNOWLEDGE.md"
    ).read_text(encoding="utf-8")
    assert "K-0001" in knowledge
    assert "validate at boundary" in knowledge
    assert "json schema layer" in knowledge


def test_record_knowledge_accepts_test_attempt_reference(tmp_path: Path) -> None:
    service, project_root = _setup(tmp_path)
    service.record_test_attempt(
        project_root,
        "task-001",
        command="pytest",
        started_at="2026-08-07T00:00:00Z",
        finished_at="2026-08-07T00:00:01Z",
        exit_code=0,
        status="passed",
        passed_count=1,
        failed_count=0,
        failure_category=None,
        summary="1 passed",
        output_digest="b" * 64,
        tested_change_ids=["C-0001"],
        requirement_refs=["R-0001"],
    )

    cards = service.record_knowledge(
        project_root,
        "task-001",
        cards=[
            {
                "category": "testing_experience",
                "problem": "A behavior needs verification.",
                "context": "The parser boundary.",
                "principle": "Keep executable evidence linked.",
                "solution": "Reference the test attempt directly.",
                "evidence_refs": ["T-000001"],
                "applicable_when": "A test attempt is the key evidence.",
                "not_applicable_when": "No executable test exists.",
                "common_mistake": "Using a file path as evidence.",
                "transfer_example": "Link a regression test in another parser.",
            }
        ],
    )

    assert cards[0].evidence_refs == ("T-000001",)


def test_record_knowledge_requires_grounded_evidence(tmp_path: Path) -> None:
    service, project_root = _setup(tmp_path)

    with pytest.raises(HanCodeError) as exc_info:
        service.record_knowledge(
            project_root,
            "task-001",
            cards=[
                {
                    "category": "reusable_pattern",
                    "problem": "p",
                    "context": "c",
                    "principle": "pr",
                    "solution": "s",
                    "evidence_refs": ["R-9999"],
                    "applicable_when": "a",
                    "not_applicable_when": "n",
                    "common_mistake": "m",
                    "transfer_example": "t",
                }
            ],
        )

    assert exc_info.value.to_dict()["error_code"] == "learning_reference_invalid"


def test_record_knowledge_requires_transfer_example(tmp_path: Path) -> None:
    service, project_root = _setup(tmp_path)

    with pytest.raises(HanCodeError):
        service.record_knowledge(
            project_root,
            "task-001",
            cards=[
                {
                    "category": "reusable_pattern",
                    "problem": "p",
                    "context": "c",
                    "principle": "pr",
                    "solution": "s",
                    "evidence_refs": ["R-0001", "C-0001"],
                    "applicable_when": "a",
                    "not_applicable_when": "n",
                    "common_mistake": "m",
                    "transfer_example": "",
                }
            ],
        )
