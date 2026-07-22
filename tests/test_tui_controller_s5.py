"""S5-R0: Controller operation lifecycle and stale-result guards."""

from __future__ import annotations

from pathlib import Path

from hancode.app.task_models import TaskSummary
from hancode.core.models import Phase, TaskStatus
from hancode.interfaces.tui.controller import TuiSessionController
from hancode.interfaces.tui.operations import (
    TuiIntent,
    TuiOperationKind,
    TuiOperationResult,
)


def _summary(task_id: str = "task-001") -> TaskSummary:
    return TaskSummary(
        task_id=task_id,
        goal="Build it",
        status=TaskStatus.RUNNING,
        current_phase=Phase.CODE,
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
    def get(self, project_root: Path, task_id: str) -> TaskSummary:
        return _summary(task_id)

    def list_tasks(self, project_root: Path) -> tuple[TaskSummary, ...]:
        return (_summary(),)


def test_controller_rejects_second_mutation_while_busy() -> None:
    controller = TuiSessionController(
        Path("/tmp/project"),
        task_service=_FakeTaskService(),  # type: ignore[arg-type]
    )
    controller.set_active_summary(_summary())
    first = controller.dispatch(TuiIntent(kind=TuiOperationKind.RUN_TASK, task_id="task-001"))

    assert first is not None
    controller.begin_operation(first)

    second = controller.dispatch(TuiIntent(kind=TuiOperationKind.RUN_TASK, task_id="task-001"))

    assert second is None
    assert controller.state.busy is True


def test_controller_ignores_result_from_previous_request() -> None:
    controller = TuiSessionController(
        Path("/tmp/project"),
        task_service=_FakeTaskService(),  # type: ignore[arg-type]
    )
    controller.set_active_summary(_summary())
    first = controller.dispatch(TuiIntent(kind=TuiOperationKind.GET_STATUS, task_id="task-001"))
    assert first is not None
    controller.begin_operation(first)

    controller.apply_result(
        TuiOperationResult(
            request_id="other-request",
            kind=TuiOperationKind.GET_STATUS,
            task_id="task-001",
            value=_summary("task-old"),
        )
    )

    assert controller.state.active_task_id == "task-001"
    assert controller.state.active_task is not None
    assert controller.state.active_task.task_id == "task-001"


def test_controller_allows_list_tasks_without_active_task() -> None:
    controller = TuiSessionController(
        Path("/tmp/project"),
        task_service=_FakeTaskService(),  # type: ignore[arg-type]
    )
    operation = controller.dispatch(TuiIntent(kind=TuiOperationKind.LIST_TASKS))

    assert operation is not None
