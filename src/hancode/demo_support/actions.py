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
        _finish(Phase.CODE),
        _run_tests(),
    )


def build_retry_actions() -> tuple[dict[str, object], ...]:
    return (
        _finish(Phase.REVIEW),
        _write(Phase.CODE, "src/calculator.py", _source("return 0")),
        _finish(Phase.CODE),
        _run_tests(),
    )


def build_recovery_actions() -> tuple[dict[str, object], ...]:
    return (
        _write(Phase.CODE, "src/calculator.py", _source("return left + right")),
        _finish(Phase.CODE),
        _run_tests(),
    )


def build_finish_actions() -> tuple[dict[str, object], ...]:
    return (_finish(Phase.TEST), _finish(Phase.REVIEW))


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


def _run_tests() -> dict[str, object]:
    return {
        "type": "tool_call",
        "phase": Phase.TEST.value,
        "tool_name": "run_tests",
        "args": {},
        "reason": None,
    }


def _source(statement: str) -> str:
    return f"def add(left: int, right: int) -> int:\n    {statement}\n"


def _artifact_path(artifact: str) -> str:
    return f".hancode/tasks/{TASK_ID}/{artifact}"
