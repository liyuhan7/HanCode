"""Deterministic MockLLM action sequences used by the packaged Demo."""

from __future__ import annotations

from hancode.core.models import Phase


TASK_ID = "task-001"


def build_first_actions() -> tuple[dict[str, object], ...]:
    return (
        _write_artifact(Phase.SPEC, "SPEC.md", "# SPEC\n\n实现整数加法。\n"),
        _write_artifact(Phase.PLAN, "PLAN.md", "# PLAN\n\n先写测试，再实现加法。\n"),
        _write(Phase.CODE, "assignment.md", "篡改课程要求\n"),
        _write(Phase.CODE, "src/calculator.py", _source("return left - right")),
        _record_test_strategy(),
        _finish(Phase.CODE),
        _run_tests(),
    )


def build_retry_actions() -> tuple[dict[str, object], ...]:
    return (
        _record_remediation(
            diagnosis="The subtraction implementation violates the addition assertion.",
            planned_paths=["src/calculator.py"],
        ),
        _write(Phase.CODE, "src/calculator.py", _source("return 0")),
        _finish(Phase.CODE),
        _run_tests(),
    )


def build_recovery_actions() -> tuple[dict[str, object], ...]:
    return (
        _record_remediation(
            diagnosis="The constant result still violates the addition assertion.",
            planned_paths=["src/calculator.py"],
        ),
        _write(Phase.CODE, "src/calculator.py", _source("return left + right")),
        _finish(Phase.CODE),
        _run_tests(),
    )


def build_post_rollback_actions() -> tuple[dict[str, object], ...]:
    """Apply the final source repair after the retry-budget rollback."""
    return (
        _write(Phase.CODE, "src/calculator.py", _source("return left + right")),
        _finish(Phase.CODE),
        _run_tests(),
    )


def build_finish_actions() -> tuple[dict[str, object], ...]:
    return (
        _finish(Phase.TEST),
        _get_diff(),
        _record_review(
            [
                {
                    "requirement_id": "REQ-ADD-001",
                    "status": "covered",
                    "evidence": "tests/test_calculator.py::CalculatorTests.test_add_returns_the_sum_of_two_integers",
                    "risk": None,
                    "is_core": True,
                }
            ],
            [],
        ),
    )


def build_delivery_actions() -> tuple[dict[str, object], ...]:
    return (
        _record_knowledge(
            [
                {
                    "category": "requirement_understanding",
                    "summary": "课程要求不可修改",
                    "detail": "assignment.md 受保护，策略拒绝了写入请求。",
                },
                {
                    "category": "design_decision",
                    "summary": "业务写入必须先 checkpoint",
                    "detail": "每次 source write 在执行前创建可恢复快照。",
                },
                {
                    "category": "testing_experience",
                    "summary": "失败测试应被分类后回灌",
                    "detail": "真实 unittest 失败被分类为 assertion_failure。",
                },
                {
                    "category": "error_fix",
                    "summary": "耗尽重试预算后回退",
                    "detail": "第二次失败后恢复最新 checkpoint，再进行最小正确修复。",
                },
                {
                    "category": "reusable_pattern",
                    "summary": "受限离线测试器",
                    "detail": "Demo 以固定 argv 和 shell=False 运行本地 unittest。",
                },
            ]
        ),
        _finish(Phase.DELIVER),
    )


def _write_artifact(phase: Phase, artifact: str, content: str) -> dict[str, object]:
    return _write(phase, _artifact_path(artifact), content)


def _write(phase: Phase, path: str, content: str) -> dict[str, object]:
    return {
        "type": "tool_call",
        "phase": phase.value,
        "tool_name": "write_file",
        "args": {"path": path, "content": content},
        "reason": "Execute the deterministic mock demo step.",
    }


def _finish(phase: Phase) -> dict[str, object]:
    return {
        "type": "finish_phase",
        "phase": phase.value,
        "tool_name": None,
        "args": {},
        "reason": None,
    }


def _run_tests(command: str = "python -m unittest discover -s tests -q") -> dict[str, object]:
    return {
        "type": "tool_call",
        "phase": Phase.TEST.value,
        "tool_name": "run_tests",
        "args": {"command": command},
        "reason": None,
    }


def _record_test_strategy() -> dict[str, object]:
    return {
        "type": "tool_call",
        "phase": Phase.CODE.value,
        "tool_name": "record_test_strategy",
        "args": {
            "command": "python -m unittest discover -s tests -q",
            "framework": "unittest",
            "test_files": ["tests/test_calculator.py"],
            "coverage": [
                {
                    "requirement": "REQ-ADD-001",
                    "verification": (
                        "CalculatorTests.test_add_returns_the_sum_of_two_integers"
                    ),
                }
            ],
        },
        "reason": "Bind the demo task to its existing behavioral unittest.",
    }


def _get_diff() -> dict[str, object]:
    return {
        "type": "tool_call",
        "phase": Phase.REVIEW.value,
        "tool_name": "get_diff",
        "args": {"scope": "task"},
        "reason": None,
    }


def _record_review(
    requirements: list[dict[str, object]], risks: list[str]
) -> dict[str, object]:
    return {
        "type": "tool_call",
        "phase": Phase.REVIEW.value,
        "tool_name": "record_review",
        "args": {"requirements": requirements, "risks": risks},
        "reason": None,
    }


def _record_remediation(
    *, diagnosis: str, planned_paths: list[str]
) -> dict[str, object]:
    return {
        "type": "tool_call",
        "phase": Phase.REVIEW.value,
        "tool_name": "record_remediation",
        "args": {
            "kind": "modify_source",
            "diagnosis": diagnosis,
            "planned_paths": planned_paths,
            "question": None,
        },
        "reason": None,
    }


def _record_knowledge(items: list[dict[str, object]]) -> dict[str, object]:
    return {
        "type": "tool_call",
        "phase": Phase.DELIVER.value,
        "tool_name": "record_knowledge",
        "args": {"items": items},
        "reason": None,
    }


def _source(statement: str) -> str:
    return f"def add(left: int, right: int) -> int:\n    {statement}\n"


def _artifact_path(artifact: str) -> str:
    return f".hancode/tasks/{TASK_ID}/{artifact}"
