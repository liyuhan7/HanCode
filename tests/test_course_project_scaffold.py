from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_course_project_positioning_is_documented() -> None:
    readme = read_text("README.md")
    spec = read_text("docs/SPEC.md")
    plan = read_text("docs/PLAN.md")

    assert "Coding Agent Harness" in readme
    assert "Coding Agent Harness" in spec
    assert "Coding Agent Harness" in plan


def test_hancode_template_contains_course_project_workspace_files() -> None:
    required_paths = [
        "examples/.hancode-template/project.json",
        "examples/.hancode-template/project_memory.md",
        "examples/.hancode-template/course_context.md",
        "examples/.hancode-template/experience.md",
        "examples/.hancode-template/tasks/task-001/SPEC.md",
        "examples/.hancode-template/tasks/task-001/PLAN.md",
        "examples/.hancode-template/tasks/task-001/REVIEW.md",
        "examples/.hancode-template/tasks/task-001/TEST_REPORT.md",
        "examples/.hancode-template/tasks/task-001/KNOWLEDGE.md",
        "examples/.hancode-template/tasks/task-001/DELIVERABLES.md",
        "examples/.hancode-template/tasks/task-001/state.json",
        "examples/.hancode-template/tasks/task-001/trace.jsonl",
        "examples/.hancode-template/tasks/task-001/history.jsonl",
        "examples/.hancode-template/tasks/task-001/checkpoints/ckpt-001/manifest.json",
    ]

    for relative_path in required_paths:
        assert (ROOT / relative_path).exists(), relative_path


def test_project_json_contains_course_assignment_metadata() -> None:
    data = json.loads(read_text("examples/.hancode-template/project.json"))

    assert data["project_id"] == "hancode-course-demo"
    assert data["course_name"] == "AI4SE"
    assert data["assignment_name"] == "Student Grade Statistics CLI"
    assert "Python 3.11" in data["stack"]
    assert data["test_command"] == "python -m pytest"


def test_context_builder_includes_course_context() -> None:
    spec = read_text("docs/SPEC.md")
    course_context = read_text("examples/.hancode-template/course_context.md")

    assert "ContextBuilder" in spec
    assert "course_context.md" in spec
    assert "grading rubric" in course_context.lower()
    assert "submission" in course_context.lower()


def test_spec_phase_rejects_edit_file() -> None:
    spec = read_text("docs/SPEC.md")

    assert "spec phase 上下文包含课程目标" in spec
    assert "不得修改业务代码" in spec
    assert "在非 code phase 修改业务代码" in spec


def test_plan_required_before_code_phase() -> None:
    spec = read_text("docs/SPEC.md")
    plan = read_text("docs/PLAN.md")

    assert "缺少 `PLAN.md` 标志时不能进入 code phase" in spec
    assert "test_missing_plan_routes_to_plan" in plan
    assert "不能进入 code phase" in plan or "路由到 plan" in plan

def test_code_phase_allows_edit_file() -> None:
    readme = read_text("README.md")
    plan = read_text("docs/PLAN.md")

    assert "`code`：按 `PLAN.md` 修改代码" in readme
    assert "test_code_phase_allows_source_write_when_prerequisites_ready" in plan
    assert "edit_file" in plan or "source write" in plan

def test_edit_file_requires_reason() -> None:
    spec = read_text("docs/SPEC.md")
    plan = read_text("docs/PLAN.md")

    assert "`edit_file` / `write_file` 必须提供 reason" in spec
    assert "test_edit_file_requires_reason" in plan


def test_edit_file_creates_checkpoint() -> None:
    spec = read_text("docs/SPEC.md")
    plan = read_text("docs/PLAN.md")

    assert "修改业务代码前经过 checkpoint" in spec
    assert "test_edit_file_creates_checkpoint" in plan


def test_rollback_last_checkpoint_restores_file() -> None:
    spec = read_text("docs/SPEC.md")
    plan = read_text("docs/PLAN.md")
    manifest = json.loads(read_text("examples/.hancode-template/tasks/task-001/checkpoints/ckpt-001/manifest.json"))

    assert "`rollback_last_checkpoint`" in spec
    assert "test_rollback_last_checkpoint_restores_file" in plan
    assert manifest["checkpoint_id"] == "ckpt-001"


def test_workspace_has_separate_history() -> None:
    plan = read_text("docs/PLAN.md")

    assert (ROOT / "examples/.hancode-template/tasks/task-001/history.jsonl").exists()
    assert (ROOT / "examples/.hancode-template/tasks/task-001/trace.jsonl").exists()
    assert "test_workspace_has_separate_history" in plan


def test_tool_not_allowed_in_workspace_is_denied() -> None:
    spec = read_text("docs/SPEC.md")
    plan = read_text("docs/PLAN.md")

    assert "ToolPolicy" in spec
    assert "策略拒绝时不得执行工具" in spec
    assert "test_disabled_tool_is_denied" in plan
    assert "未注册工具" in plan or "disabled tool" in plan or "工具是否允许" in plan

def test_code_change_requires_test_or_risk_note() -> None:
    spec = read_text("docs/SPEC.md")
    plan = read_text("docs/PLAN.md")

    assert "未测试风险记录到 `TEST_REPORT.md`" in spec
    assert "缺少测试或审查记录时必须在 `risks[]` 中说明" in spec
    assert "test_code_change_requires_test_or_risk_note" in plan


def test_max_steps_prevents_infinite_loop() -> None:
    spec = read_text("docs/SPEC.md")
    plan = read_text("docs/PLAN.md")

    assert "test_max_steps_prevents_infinite_loop" in plan
    assert "`max_steps` 必须限制 AgentLoop 最大执行步数" in spec


def test_deliver_requires_knowledge_file() -> None:
    spec = read_text("docs/SPEC.md")
    plan = read_text("docs/PLAN.md")

    assert "`KNOWLEDGE.md`" in spec
    assert "test_deliver_requires_knowledge_file" in plan


def test_deliver_requires_deliverables_file() -> None:
    spec = read_text("docs/SPEC.md")
    plan = read_text("docs/PLAN.md")

    assert "`DELIVERABLES.md`" in spec
    assert "test_deliver_requires_deliverables_file" in plan


def test_policy_protects_assignment_files() -> None:
    spec = read_text("docs/SPEC.md")
    plan = read_text("docs/PLAN.md")

    assert "修改或删除课程作业说明" in spec
    assert "test_policy_protects_assignment_files" in plan


def test_policy_protects_teacher_tests_or_grading_scripts() -> None:
    spec = read_text("docs/SPEC.md")
    plan = read_text("docs/PLAN.md")

    assert "老师提供的测试文件、评分脚本或样例数据" in spec
    assert "test_policy_protects_teacher_tests_or_grading_scripts" in plan
