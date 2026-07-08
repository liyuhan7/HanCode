from __future__ import annotations

import json

import pytest

from hancode.errors import StructuredError
from hancode.models import OperationResult, OperationStatus, Phase, Risk, TaskStatus


def test_phase_allows_only_six_project_phases() -> None:
    assert [phase.value for phase in Phase] == [
        "spec",
        "plan",
        "code",
        "test",
        "review",
        "deliver",
    ]

    with pytest.raises(ValueError):
        Phase("deploy")


def test_task_status_allows_only_defined_values() -> None:
    assert [status.value for status in TaskStatus] == [
        "created",
        "running",
        "blocked",
        "failed",
        "completed",
        "inconsistent",
    ]

    with pytest.raises(ValueError):
        TaskStatus("ok")


def test_operation_result_serializes_to_dict() -> None:
    result = OperationResult(
        status=OperationStatus.BLOCKED,
        message="PLAN.md is missing before code phase.",
        error=StructuredError(
            code="missing_plan",
            message="Cannot enter code phase without PLAN.md.",
            hint="Create the task plan before editing source files.",
            details={"phase": Phase.CODE.value},
        ),
        data={"phase": Phase.CODE},
        risks=[Risk(level="medium", message="Implementation has not started.")],
    )

    payload = result.to_dict()

    assert payload == {
        "status": "blocked",
        "message": "PLAN.md is missing before code phase.",
        "error": {
            "code": "missing_plan",
            "message": "Cannot enter code phase without PLAN.md.",
            "hint": "Create the task plan before editing source files.",
            "details": {"phase": "code"},
        },
        "data": {"phase": "code"},
        "risks": [
            {
                "level": "medium",
                "message": "Implementation has not started.",
                "mitigation": None,
            }
        ],
    }
    assert json.loads(json.dumps(payload)) == payload


def test_operation_result_rejects_unknown_status() -> None:
    with pytest.raises(ValueError, match="Unsupported operation status"):
        OperationResult.from_values(status="ok", message="done")


def test_operation_result_accepts_declared_status_string() -> None:
    result = OperationResult.from_values(status="succeeded", message="done")

    assert result.status is OperationStatus.SUCCEEDED
    assert result.to_dict()["status"] == "succeeded"
