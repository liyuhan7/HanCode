"""S5-R0: Controller operation lifecycle and stale-result guards."""

from __future__ import annotations

from pathlib import Path

from hancode.app.task_models import TaskSummary
from hancode.core.change_models import ChangeType, DiffScope, FileDiff, TaskDiff
from hancode.core.models import Phase, TaskStatus
from hancode.interfaces.tui.controller import TuiSessionController
from hancode.interfaces.tui.operations import (
    TuiIntent,
    TuiOperationKind,
    TuiOperationResult,
)
from hancode.interfaces.tui.presenters import DetailKind, DiffView


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


def test_query_operation_tracks_loading_without_marking_mutation_busy() -> None:
    controller = TuiSessionController(
        Path("/tmp/project"),
        task_service=_FakeTaskService(),  # type: ignore[arg-type]
    )
    operation = controller.dispatch(TuiIntent(kind=TuiOperationKind.GET_STATUS, task_id="task-001"))

    assert operation is not None
    controller.begin_operation(operation)

    assert controller.state.busy is False
    assert controller.state.active_query == TuiOperationKind.GET_STATUS.value
    assert controller.state.active_mutation is None
    assert controller.state.current_request_id == operation.request_id


def test_controller_discards_query_result_after_newer_request_begins() -> None:
    controller = TuiSessionController(
        Path("/tmp/project"),
        task_service=_FakeTaskService(),  # type: ignore[arg-type]
    )
    controller.set_active_summary(_summary("task-001"))
    first = controller.dispatch(TuiIntent(kind=TuiOperationKind.GET_STATUS, task_id="task-001"))
    second = controller.dispatch(TuiIntent(kind=TuiOperationKind.SELECT_TASK, task_id="task-001"))

    assert first is not None
    assert second is not None
    controller.begin_operation(first)
    controller.begin_operation(second)
    controller.apply_result(
        TuiOperationResult(
            request_id=first.request_id,
            kind=TuiOperationKind.GET_STATUS,
            task_id="task-001",
            value=_summary("task-old"),
        )
    )

    assert controller.state.current_request_id == second.request_id
    assert controller.state.active_query == TuiOperationKind.SELECT_TASK.value
    assert controller.state.active_task is not None
    assert controller.state.active_task.task_id == "task-001"


def test_controller_discards_task_query_after_active_task_changes() -> None:
    controller = TuiSessionController(
        Path("/tmp/project"),
        task_service=_FakeTaskService(),  # type: ignore[arg-type]
    )
    controller.set_active_summary(_summary("task-001"))
    operation = controller.dispatch(
        TuiIntent(kind=TuiOperationKind.GET_STATUS, task_id="task-001")
    )
    assert operation is not None
    controller.begin_operation(operation)
    controller.set_active_summary(_summary("task-002"))

    accepted = controller.apply_result(
        TuiOperationResult(
            request_id=operation.request_id,
            kind=TuiOperationKind.GET_STATUS,
            task_id="task-001",
            value=_summary("task-001"),
        )
    )

    assert accepted is False
    assert controller.state.current_request_id == operation.request_id
    assert controller.state.active_task_id == "task-002"


def test_controller_routes_diff_result_to_diff_detail_view() -> None:
    controller = TuiSessionController(
        Path("/tmp/project"),
        task_service=_FakeTaskService(),  # type: ignore[arg-type]
    )
    controller.set_active_summary(_summary("task-001"))
    operation = controller.dispatch(
        TuiIntent(kind=TuiOperationKind.DIFF, task_id="task-001")
    )
    assert operation is not None
    controller.begin_operation(operation)
    accepted = controller.apply_result(
        TuiOperationResult(
            request_id=operation.request_id,
            kind=operation.kind,
            task_id=operation.task_id,
            value=TaskDiff(
                task_id="task-001",
                scope=DiffScope.TASK,
                checkpoint_ids=(),
                files=(
                    FileDiff(
                        path="src/main.py",
                        change_type=ChangeType.MODIFIED,
                        before_sha256=None,
                        current_sha256=None,
                        binary=False,
                        drifted=False,
                        unified_diff="@@",
                        truncated=False,
                    ),
                ),
                truncated=False,
                risks=(),
            ),
        )
    )

    assert accepted is True
    assert controller.state.detail_kind is DetailKind.DIFF
    assert isinstance(controller.state.detail, DiffView)


def test_controller_exposes_single_sync_operation_entrypoint() -> None:
    controller = TuiSessionController(
        Path("/tmp/project"),
        task_service=_FakeTaskService(),  # type: ignore[arg-type]
    )

    value = controller.execute_sync(
        TuiIntent(kind=TuiOperationKind.GET_STATUS, task_id="task-001")
    )

    assert isinstance(value, TaskSummary)
    assert controller.state.current_request_id is None
    assert controller.state.active_query is None
