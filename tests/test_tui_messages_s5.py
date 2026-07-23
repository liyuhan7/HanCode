"""S5-R2: request-scoped Textual operation messages."""

from __future__ import annotations

from hancode.core.errors import StructuredError
from hancode.interfaces.tui.messages import OperationFailed, OperationFinished
from hancode.interfaces.tui.operations import (
    TuiOperationError,
    TuiOperationKind,
    TuiOperationResult,
)


def test_operation_finished_preserves_result_request_context() -> None:
    result = TuiOperationResult(
        request_id="req-001",
        kind=TuiOperationKind.GET_STATUS,
        task_id="task-001",
        value={"status": "running"},
    )

    message = OperationFinished(result)

    assert message.result is result
    assert message.result.request_id == "req-001"


def test_operation_failed_preserves_structured_error_request_context() -> None:
    error = TuiOperationError(
        "req-002",
        TuiOperationKind.READ_ARTIFACT,
        "task-001",
        StructuredError(
            error_code="artifact_missing",
            message="Artifact is unavailable.",
            phase="deliver",
            denied_rule="artifact_missing",
            suggested_fix="Run delivery first.",
        ),
    )

    message = OperationFailed(error)

    assert message.error is error
    assert message.error.request_id == "req-002"
    assert message.error.task_id == "task-001"
