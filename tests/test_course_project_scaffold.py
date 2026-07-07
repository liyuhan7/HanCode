from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_course_project_positioning_is_documented() -> None:
    readme = read_text("README.md")
    spec = read_text("SPEC.md")
    plan = read_text("PLAN.md")

    required = "面向学生课程项目的轻量级 Coding Agent Harness"
    assert required in readme
    assert required in spec
    assert required in plan


def test_hancode_template_contains_course_project_workspace_files() -> None:
    required_paths = [
        ".hancode/project.json",
        ".hancode/project_memory.md",
        ".hancode/course_context.md",
        ".hancode/experience.md",
        ".hancode/tasks/task-001/SPEC.md",
        ".hancode/tasks/task-001/PLAN.md",
        ".hancode/tasks/task-001/REVIEW.md",
        ".hancode/tasks/task-001/TEST_REPORT.md",
        ".hancode/tasks/task-001/KNOWLEDGE.md",
        ".hancode/tasks/task-001/DELIVERABLES.md",
        ".hancode/tasks/task-001/state.json",
        ".hancode/tasks/task-001/trace.jsonl",
        ".hancode/tasks/task-001/history.jsonl",
        ".hancode/tasks/task-001/checkpoints/ckpt-001/manifest.json",
    ]

    for relative_path in required_paths:
        assert (ROOT / relative_path).exists(), relative_path


def test_project_json_contains_course_assignment_metadata() -> None:
    data = json.loads(read_text(".hancode/project.json"))

    assert data["project_id"] == "hancode-course-demo"
    assert data["course_name"] == "AI4SE"
    assert data["assignment_name"] == "Student Grade Statistics CLI"
    assert "Python 3.11" in data["stack"]
    assert data["test_command"] == "python -m pytest"


def test_context_builder_includes_course_context() -> None:
    spec = read_text("SPEC.md")
    course_context = read_text(".hancode/course_context.md")

    assert "ContextBuilder" in spec
    assert "course_context.md" in spec
    assert "grading rubric" in course_context.lower()
    assert "submission" in course_context.lower()


def test_spec_phase_rejects_edit_file() -> None:
    spec = read_text("SPEC.md")

    assert "`spec` phase 读取课程作业说明" in spec
    assert "不得修改业务代码" in spec
    assert "在非 code phase 修改业务代码" in spec


def test_plan_required_before_code_phase() -> None:
    spec = read_text("SPEC.md")
    plan = read_text("PLAN.md")

    assert "`PLAN.md` 不存在时不能进入 `code`" in spec
    assert "test_plan_required_before_code_phase" in plan


def test_code_phase_allows_edit_file() -> None:
    readme = read_text("README.md")
    plan = read_text("PLAN.md")

    assert "`code`：按 `PLAN.md` 修改代码" in readme
    assert "test_code_phase_allows_edit_file" in plan


def test_edit_file_requires_reason() -> None:
    spec = read_text("SPEC.md")
    plan = read_text("PLAN.md")

    assert "`edit_file` / `write_file` 必须提供 reason" in spec
    assert "test_edit_file_requires_reason" in plan


def test_edit_file_creates_checkpoint() -> None:
    spec = read_text("SPEC.md")
    plan = read_text("PLAN.md")

    assert "修改业务代码前必须 checkpoint" in spec
    assert "test_edit_file_creates_checkpoint" in plan


def test_rollback_last_checkpoint_restores_file() -> None:
    spec = read_text("SPEC.md")
    plan = read_text("PLAN.md")
    manifest = json.loads(read_text(".hancode/tasks/task-001/checkpoints/ckpt-001/manifest.json"))

    assert "`rollback_last_checkpoint`" in spec
    assert "test_rollback_last_checkpoint_restores_file" in plan
    assert manifest["checkpoint_id"] == "ckpt-001"


def test_workspace_has_separate_history() -> None:
    plan = read_text("PLAN.md")

    assert (ROOT / ".hancode/tasks/task-001/history.jsonl").exists()
    assert (ROOT / ".hancode/tasks/task-001/trace.jsonl").exists()
    assert "test_workspace_has_separate_history" in plan


def test_tool_not_allowed_in_workspace_is_denied() -> None:
    spec = read_text("SPEC.md")
    plan = read_text("PLAN.md")

    assert "ToolPolicy" in spec
    assert "被拒绝的工具调用不执行" in spec
    assert "test_tool_not_allowed_in_workspace_is_denied" in plan


def test_code_change_requires_test_or_risk_note() -> None:
    spec = read_text("SPEC.md")
    plan = read_text("PLAN.md")

    assert "`TEST_REPORT.md` 中的测试状态" in spec
    assert "缺少测试报告或 review 时标记风险" in spec
    assert "test_code_change_requires_test_or_risk_note" in plan


def test_max_steps_prevents_infinite_loop() -> None:
    plan = read_text("PLAN.md")

    assert "test_max_steps_prevents_infinite_loop" in plan
    assert "maximum loop iterations" in read_text("docs/agent-guides/harness-boundary.md")


def test_deliver_requires_knowledge_file() -> None:
    spec = read_text("SPEC.md")
    plan = read_text("PLAN.md")

    assert "`KNOWLEDGE.md`" in spec
    assert "test_deliver_requires_knowledge_file" in plan


def test_deliver_requires_deliverables_file() -> None:
    spec = read_text("SPEC.md")
    plan = read_text("PLAN.md")

    assert "`DELIVERABLES.md`" in spec
    assert "test_deliver_requires_deliverables_file" in plan


def test_policy_protects_assignment_files() -> None:
    spec = read_text("SPEC.md")
    plan = read_text("PLAN.md")

    assert "删除或修改作业说明文件" in spec
    assert "test_policy_protects_assignment_files" in plan


def test_policy_protects_teacher_tests_or_grading_scripts() -> None:
    spec = read_text("SPEC.md")
    plan = read_text("PLAN.md")

    assert "老师提供的测试文件、评分脚本或样例数据" in spec
    assert "test_policy_protects_teacher_tests_or_grading_scripts" in plan

