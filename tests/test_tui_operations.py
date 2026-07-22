"""S5-R0: Textual-independent TUI operation contract tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from hancode.app.task_models import TaskSummary
from hancode.core.errors import HanCodeError, StructuredError
from hancode.core.models import Phase, TaskStatus
from hancode.interfaces.tui.operations import (
    TuiOperation,
    TuiOperationError,
    TuiOperationExecutor,
    TuiOperationKind,
    TuiServices,
)


def _summary() -> TaskSummary:
    return TaskSummary(
        task_id="task-001",
        goal="Build it",
        status=TaskStatus.CREATED,
        current_phase=Phase.SPEC,
        retry_budget_remaining=2,
        latest_test_status="none",
        files_changed=(),
        tests_run=(),
        latest_checkpoint=None,
        rollback_required=False,
        inconsistent=False,
        artifacts={},
        resumable=False,
    )


class _FakeTaskService:
    def __init__(self) -> None:
        self.created: list[str] = []

    def create(self, project_root: Path, goal: str) -> TaskSummary:
        self.created.append(goal)
        return _summary()


def _services(task: object) -> TuiServices:
    return TuiServices(
        task=task,  # type: ignore[arg-type]
        interaction=object(),  # type: ignore[arg-type]
        approval=object(),  # type: ignore[arg-type]
        inspection=object(),  # type: ignore[arg-type]
        changes=object(),  # type: ignore[arg-type]
        test_reports=object(),  # type: ignore[arg-type]
        checkpoints=object(),  # type: ignore[arg-type]
        recovery=object(),  # type: ignore[arg-type]
        delivery=object(),  # type: ignore[arg-type]
    )


def test_executor_routes_create_task_to_injected_service(tmp_path: Path) -> None:
    task = _FakeTaskService()
    executor = TuiOperationExecutor(tmp_path, _services(task))
    operation = TuiOperation(
        request_id="req-001",
        kind=TuiOperationKind.CREATE_TASK,
        goal="Build it",
    )

    result = executor.execute(operation)

    assert task.created == ["Build it"]
    assert result.request_id == "req-001"
    assert result.value is not None


def test_executor_converts_service_error_to_structured_operation_error(
    tmp_path: Path,
) -> None:
    error = StructuredError(
        error_code="task_create_failed",
        message="cannot create",
        phase="spec",
        denied_rule=None,
        suggested_fix="retry",
    )

    class _FailingTaskService:
        def create(self, project_root: Path, goal: str) -> TaskSummary:
            raise HanCodeError(error)

    executor = TuiOperationExecutor(tmp_path, _services(_FailingTaskService()))
    operation = TuiOperation(
        request_id="req-002",
        kind=TuiOperationKind.CREATE_TASK,
        goal="Build it",
    )

    with pytest.raises(TuiOperationError) as caught:
        executor.execute(operation)

    assert caught.value.request_id == "req-002"
    assert caught.value.structured_error == error
