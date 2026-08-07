from __future__ import annotations

from pathlib import Path

from hancode.app.delivery_service import DeliveryService
from hancode.app.learning_service import LearningService
from hancode.core.actions import Action, ActionType
from hancode.core.test_remediation import FailureCategory
from hancode.core.models import Phase
from hancode.core.state import load_state
from hancode.core.config import load_config
from hancode.runtime.agent_loop import AgentLoop, _trace_action
from hancode.runtime.context import _add_learning_evidence_catalog
from hancode.runtime.test_remediation import build_test_failure_record
from hancode.storage.workspace import init_project_workspace, init_task_workspace
from hancode.storage.test_remediations import TestRemediationStore
from hancode.tooling.factory import build_default_tool_registry
from hancode.tooling.learning_tools import guarded_record_knowledge
from hancode.tooling.registry import ToolResult


def _setup_learning_task(tmp_path: Path) -> Path:
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
                "acceptance_evidence": "pytest",
                "priority": "core",
                "is_core": True,
            }
        ],
    )
    service.record_change(
        tmp_path,
        "task-001",
        pre_change_checkpoint_id=None,
        action_id="write_file:parser",
        changed_paths=["src/parser.py"],
        diff_digest="a" * 64,
        reason="add empty-input guard",
        requirement_refs=["R-0001"],
        plan_step_refs=[],
    )
    return tmp_path


def test_structured_spec_and_plan_tools_accept_omitted_optional_lists(
    tmp_path: Path,
) -> None:
    init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )
    init_task_workspace(tmp_path, "task-001")
    registry = build_default_tool_registry(load_config(tmp_path, "task-001"))

    requirements = registry.dispatch(
        Action(
            ActionType.TOOL_CALL,
            Phase.SPEC,
            "record_requirements",
            {
                "goal": "parser",
                "requirements": [
                    {
                        "source_text": "reject empty",
                        "student_understanding": "empty raises",
                        "acceptance_evidence": "pytest",
                        "is_core": True,
                    }
                ],
            },
            None,
        )
    )
    plan = registry.dispatch(
        Action(
            ActionType.TOOL_CALL,
            Phase.PLAN,
            "record_plan",
            {
                "decisions": [],
                "plan_steps": [{"description": "add the guard"}],
            },
            None,
        )
    )

    assert requirements.success is True
    assert plan.success is True


def test_s14_record_knowledge_rejects_legacy_items_with_guidance(
    tmp_path: Path,
) -> None:
    project_root = _setup_learning_task(tmp_path)
    registry = build_default_tool_registry(load_config(project_root, "task-001"))

    result = registry.dispatch(
        Action(
            ActionType.TOOL_CALL,
            Phase.DELIVER,
            "record_knowledge",
            {
                "items": [
                    {
                        "category": "design_decision",
                        "summary": "placed under src",
                        "detail": "kept the layout",
                    }
                ]
            },
            None,
        )
    )

    assert result.success is False
    assert "cards" in (result.error_summary or "")
    assert "items" in (result.error_summary or "")


def test_s14_record_review_rejects_legacy_requirements_with_guidance(
    tmp_path: Path,
) -> None:
    project_root = _setup_learning_task(tmp_path)
    registry = build_default_tool_registry(load_config(project_root, "task-001"))

    result = registry.dispatch(
        Action(
            ActionType.TOOL_CALL,
            Phase.REVIEW,
            "record_review",
            {"requirements": [], "risks": []},
            None,
        )
    )

    assert result.success is False
    assert "requirement_reviews" in (result.error_summary or "")


def test_learning_evidence_catalog_exposes_authoritative_details(tmp_path: Path) -> None:
    project_root = _setup_learning_task(tmp_path)
    sections: dict[str, object] = {}

    _add_learning_evidence_catalog(sections, project_root, "task-001")

    assert sections["learning_evidence"] == {
        "requirements": [
            {
                "id": "R-0001",
                "source_text": "reject empty",
                "student_understanding": "empty raises",
                "acceptance_evidence": "pytest",
                "priority": "core",
                "is_core": True,
            }
        ],
        "decisions": [],
        "plan_steps": [],
        "changes": [
            {
                "id": "C-0001",
                "changed_paths": ["src/parser.py"],
                "reason": "add empty-input guard",
                "requirement_refs": ["R-0001"],
                "plan_step_refs": [],
            }
        ],
        "test_attempts": [],
        "failures": [],
        "recoveries": [],
    }


def test_record_knowledge_invalid_reference_returns_candidates(
    tmp_path: Path,
) -> None:
    project_root = _setup_learning_task(tmp_path)
    result = guarded_record_knowledge(
        project_root,
        "task-001",
        cards=[
            {
                "category": "reusable_pattern",
                "problem": "empty input crashes",
                "context": "parser boundary",
                "principle": "validate at the boundary",
                "solution": "reject empty input",
                "evidence_refs": ["src/parser.py"],
                "applicable_when": "external input",
                "not_applicable_when": "trusted internal data",
                "common_mistake": "using a path as evidence",
                "transfer_example": "schema validation layer",
            }
        ],
    )

    assert result.success is False
    assert result.error_code == "learning_reference_invalid"
    assert "Available IDs: C-0001, R-0001" in (result.error_summary or "")
    assert "File paths" in (result.error_summary or "")


def test_record_knowledge_trace_keeps_only_safe_reference_summary() -> None:
    action = Action(
        ActionType.TOOL_CALL,
        Phase.DELIVER,
        "record_knowledge",
        {
            "cards": [
                    {
                        "category": "reusable_pattern",
                        "problem": "sensitive detail",
                        "context": "parser boundary",
                        "principle": "validate inputs",
                        "solution": "reject empty input",
                        "evidence_refs": ["R-0001", "C-0001"],
                        "applicable_when": "external input",
                        "not_applicable_when": "trusted data",
                        "common_mistake": "late validation",
                        "transfer_example": "schema boundary",
                    }
            ]
        },
        "record grounded knowledge",
    )

    traced = _trace_action(action, None, include_path=False)

    assert traced["args"] == {
        "cards": [
            {
                "category": "reusable_pattern",
                "evidence_refs": ["R-0001", "C-0001"],
            }
        ]
    }
    assert "sensitive detail" not in str(traced)


def test_active_task_routes_record_review_to_s14(tmp_path: Path) -> None:
    project_root = _setup_learning_task(tmp_path)
    config = load_config(project_root, "task-001")
    registry = build_default_tool_registry(config)

    result = registry.dispatch(
        Action(
            ActionType.TOOL_CALL,
            Phase.REVIEW,
            "record_review",
            {
                "requirement_reviews": [
                    {
                        "requirement_id": "R-0001",
                        "change_refs": ["C-0001"],
                        "test_refs": [],
                        "status": "covered",
                        "risk": None,
                    }
                ],
                "quality_findings": [],
                "untested_risks": [],
                "plan_deviations": [],
                "delivery_recommendation": "ship",
            },
            None,
        )
    )

    assert result.success is True
    review = (
        project_root / ".hancode" / "tasks" / "task-001" / "REVIEW.md"
    ).read_text(encoding="utf-8")
    assert "# 最终审查" in review
    assert "C-0001" in review


def test_active_task_routes_record_knowledge_to_s14(tmp_path: Path) -> None:
    project_root = _setup_learning_task(tmp_path)
    config = load_config(project_root, "task-001")
    registry = build_default_tool_registry(config)

    result = registry.dispatch(
        Action(
            ActionType.TOOL_CALL,
            Phase.DELIVER,
            "record_knowledge",
            {
                "cards": [
                    {
                        "category": "reusable_pattern",
                        "problem": "empty input crashes",
                        "context": "parser boundary",
                        "principle": "validate at the boundary",
                        "solution": "reject empty input",
                        "evidence_refs": ["R-0001", "C-0001"],
                        "applicable_when": "external input",
                        "not_applicable_when": "trusted internal data",
                        "common_mistake": "fix only the symptom",
                        "transfer_example": "schema validation layer",
                    }
                ]
            },
            None,
        )
    )

    assert result.success is True
    assert result.output == {"artifact": "KNOWLEDGE.md", "format": "structured", "count": 1}
    knowledge = (
        project_root / ".hancode" / "tasks" / "task-001" / "KNOWLEDGE.md"
    ).read_text(encoding="utf-8")
    assert "# 知识复盘" in knowledge
    assert "K-0001" in knowledge


def test_task_without_learning_evidence_keeps_legacy_route(
    tmp_path: Path,
    monkeypatch,
) -> None:
    init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )
    task_root = init_task_workspace(tmp_path, "task-001")
    calls: list[dict[str, object]] = []

    def legacy_record_review(
        project_root: Path,
        task_id: str,
        requirements: object,
        risks: object = (),
    ):
        calls.append(
            {
                "project_root": project_root,
                "task_id": task_id,
                "requirements": requirements,
                "risks": risks,
            }
        )
        from hancode.tooling.registry import ToolResult

        return ToolResult(success=True, action_name="record_review")

    monkeypatch.setattr(
        "hancode.tooling.delivery_tools.record_review",
        legacy_record_review,
    )
    config = load_config(tmp_path, task_root.name)
    registry = build_default_tool_registry(config)

    result = registry.dispatch(
        Action(
            ActionType.TOOL_CALL,
            Phase.REVIEW,
            "record_review",
            {"requirements": [], "risks": ["legacy-risk"]},
            None,
        )
    )

    assert result.success is True
    assert calls == [
        {
            "project_root": tmp_path,
            "task_id": "task-001",
            "requirements": [],
            "risks": ["legacy-risk"],
        }
    ]
    assert load_state(task_root).learning_contract_version == 1


def test_agent_loop_records_source_change_and_passing_test(tmp_path: Path) -> None:
    project_root = _setup_learning_task(tmp_path)
    source = project_root / "src" / "parser.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("def parse():\n    return True\n", encoding="utf-8")
    loop = AgentLoop.__new__(AgentLoop)
    loop._project_root = project_root
    state = load_state(project_root / ".hancode" / "tasks" / "task-001")

    write_action = Action(
        ActionType.TOOL_CALL,
        Phase.CODE,
        "write_file",
        {"path": "src/parser.py", "content": "def parse():\n    return True\n"},
        "Implement the parser guard.",
    )
    loop._record_learning_evidence_after_tool(
        "task-001",
        state,
        write_action,
        ToolResult(success=True, action_name="write_file", mutation_applied=True),
        source_write=True,
    )
    loop._record_learning_evidence_after_tool(
        "task-001",
        state,
        Action(
            ActionType.TOOL_CALL,
            Phase.TEST,
            "run_tests",
            {"command": "pytest -q"},
            None,
        ),
        ToolResult(
            success=True,
            action_name="run_tests",
            command="pytest -q",
            stdout="1 passed in 0.01s",
            exit_code=0,
        ),
        source_write=False,
    )

    snapshot = LearningService().load_snapshot(project_root, "task-001")
    assert [change.id for change in snapshot.changes] == ["C-0001", "C-0002"]
    assert [attempt.id for attempt in snapshot.test_attempts] == ["T-000001"]
    assert snapshot.test_attempts[0].status == "passed"
    implementation = (
        project_root / ".hancode" / "tasks" / "task-001" / "IMPLEMENTATION.md"
    ).read_text(encoding="utf-8")
    assert "C-0002" in implementation


def test_agent_loop_records_failure_after_failed_test(tmp_path: Path) -> None:
    project_root = _setup_learning_task(tmp_path)
    loop = AgentLoop.__new__(AgentLoop)
    loop._project_root = project_root
    failure = build_test_failure_record(
        task_id="task-001",
        attempt_seq=1,
        strategy_digest=None,
        command_argv=("pytest", "-q"),
        category=FailureCategory.ASSERTION_FAILURE,
        exit_code=1,
        timed_out=False,
        passed_count=0,
        failed_count=1,
        output="FAILED tests/test_parser.py - AssertionError",
        project_root=project_root,
    )
    TestRemediationStore(project_root).save_failure(failure)

    loop._record_learning_evidence_after_tool(
        "task-001",
        load_state(project_root / ".hancode" / "tasks" / "task-001"),
        Action(
            ActionType.TOOL_CALL,
            Phase.TEST,
            "run_tests",
            {"command": "pytest -q"},
            None,
        ),
        ToolResult(
            success=False,
            action_name="run_tests",
            command="pytest -q",
            stdout="FAILED tests/test_parser.py - AssertionError",
            exit_code=1,
        ),
        source_write=False,
    )

    snapshot = LearningService().load_snapshot(project_root, "task-001")
    assert [attempt.id for attempt in snapshot.test_attempts] == ["T-000001"]
    assert [item.id for item in snapshot.failures] == ["F-000001"]
    assert snapshot.failures[0].test_attempt_id == "T-000001"


def test_learning_finalize_writes_design_format_deliverables(tmp_path: Path) -> None:
    project_root = _setup_learning_task(tmp_path)
    LearningService().record_test_attempt(
        project_root,
        "task-001",
        command="pytest -q",
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

    result = DeliveryService().finalize(project_root, "task-001")

    assert result.submission_eligible is True
    deliverables = (
        project_root / ".hancode" / "tasks" / "task-001" / "DELIVERABLES.md"
    ).read_text(encoding="utf-8")
    assert "# 项目交付摘要" in deliverables
    assert "## 5. 需求覆盖摘要" in deliverables
    assert "## 8. 审计信息" in deliverables
    assert "核心需求覆盖：1 / 1" in deliverables
