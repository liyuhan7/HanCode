"""S5-R0: Textual-independent TUI operation contract tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from hancode.app.task_models import TaskSummary
from hancode.app.build_service import BuildSummary
from hancode.core.errors import HanCodeError, StructuredError
from hancode.core.models import Phase, TaskStatus
from hancode.interfaces.tui.operations import (
    TuiIntent,
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


def test_operation_carries_reserved_diff_and_export_parameters(tmp_path: Path) -> None:
    diff_intent = TuiIntent(
        kind=TuiOperationKind.DIFF,
        task_id="task-001",
        diff_scope="task",
        diff_path="src/main.py",
    )
    diff_operation = TuiOperation.from_intent(
        diff_intent,
        request_id="req-diff-001",
    )

    export_dir = tmp_path / "deliverables"
    export_intent = TuiIntent(
        kind=TuiOperationKind.EXPORT,
        task_id="task-001",
        export_output_dir=export_dir,
    )
    export_operation = TuiOperation.from_intent(
        export_intent,
        request_id="req-export-001",
    )

    assert diff_operation.diff_scope == "task"
    assert diff_operation.diff_path == "src/main.py"
    assert export_operation.export_output_dir == export_dir


def test_executor_routes_read_only_inspection_operations_without_finalize(
    tmp_path: Path,
) -> None:
    diff = object()
    report = object()
    checkpoints = object()
    evidence = object()
    calls: list[str] = []

    class _Changes:
        def get_diff(self, project_root, task_id, *, scope, path):  # type: ignore[no-untyped-def]
            calls.append(f"diff:{scope.value}:{path}")
            return diff

    class _Reports:
        def read_test_report(self, project_root, task_id):  # type: ignore[no-untyped-def]
            calls.append("test-report")
            return report

        def read_delivery_summary(self, project_root, task_id):  # type: ignore[no-untyped-def]
            calls.append("delivery-evidence")
            return evidence

    class _Checkpoints:
        def list_checkpoints(self, project_root, task_id):  # type: ignore[no-untyped-def]
            calls.append("checkpoints")
            return checkpoints

    class _Inspection:
        def read_trace(self, project_root, task_id, *, after_seq, limit):  # type: ignore[no-untyped-def]
            calls.append(f"trace:{after_seq}:{limit}")
            return SimpleNamespace(events=(), next_seq=None, has_more=False)

    class _Delivery:
        def get_result(self, project_root, task_id):  # type: ignore[no-untyped-def]
            raise AssertionError("delivery inspection must not finalize")

    services = TuiServices(
        task=object(),  # type: ignore[arg-type]
        interaction=object(),  # type: ignore[arg-type]
        approval=object(),  # type: ignore[arg-type]
        inspection=_Inspection(),  # type: ignore[arg-type]
        changes=_Changes(),  # type: ignore[arg-type]
        test_reports=_Reports(),  # type: ignore[arg-type]
        checkpoints=_Checkpoints(),  # type: ignore[arg-type]
        recovery=object(),  # type: ignore[arg-type]
        delivery=_Delivery(),  # type: ignore[arg-type]
    )
    executor = TuiOperationExecutor(tmp_path, services)

    operations = (
        (TuiOperationKind.DIFF, diff, "diff:latest:src/main.py"),
        (TuiOperationKind.TEST_REPORT, report, "test-report"),
        (TuiOperationKind.CHECKPOINTS, checkpoints, "checkpoints"),
        (TuiOperationKind.DELIVERY, evidence, "delivery-evidence"),
    )
    for index, (kind, expected, expected_call) in enumerate(operations):
        operation = TuiOperation(
            request_id=f"req-query-{index}",
            kind=kind,
            task_id="task-001",
            diff_scope="latest" if kind is TuiOperationKind.DIFF else None,
            diff_path="src/main.py" if kind is TuiOperationKind.DIFF else None,
        )
        result = executor.execute(operation)
        assert result.value is expected
        assert calls[-1] == expected_call

    trace_result = executor.execute(
        TuiOperation(request_id="req-trace", kind=TuiOperationKind.TRACE, task_id="task-001")
    )
    assert trace_result.value.events == ()
    assert calls[-1] == "trace:0:500"


def test_executor_routes_export_to_delivery_service(tmp_path: Path) -> None:
    output_dir = tmp_path / "delivery"
    calls: list[tuple[str, str, Path]] = []

    class _Delivery:
        def export(self, project_root, task_id, directory):  # type: ignore[no-untyped-def]
            calls.append(("export", task_id, directory))
            return "export-result"

    services = TuiServices(
        task=object(),  # type: ignore[arg-type]
        interaction=object(),  # type: ignore[arg-type]
        approval=object(),  # type: ignore[arg-type]
        inspection=object(),  # type: ignore[arg-type]
        changes=object(),  # type: ignore[arg-type]
        test_reports=object(),  # type: ignore[arg-type]
        checkpoints=object(),  # type: ignore[arg-type]
        recovery=object(),  # type: ignore[arg-type]
        delivery=_Delivery(),  # type: ignore[arg-type]
    )
    executor = TuiOperationExecutor(tmp_path, services)

    result = executor.execute(
        TuiOperation(
            request_id="req-export-001",
            kind=TuiOperationKind.EXPORT,
            task_id="task-001",
            export_output_dir=output_dir,
        )
    )

    assert result.value == "export-result"
    assert calls == [("export", "task-001", output_dir)]


def test_executor_routes_build_to_build_service(tmp_path: Path) -> None:
    calls: list[tuple[Path, str]] = []

    class _Build:
        def run(self, project_root: Path, task_id: str) -> BuildSummary:
            calls.append((project_root, task_id))
            return BuildSummary("python -m build", "passed", 0, None, None, False)

    services = TuiServices(
        task=object(),  # type: ignore[arg-type]
        interaction=object(),  # type: ignore[arg-type]
        approval=object(),  # type: ignore[arg-type]
        inspection=object(),  # type: ignore[arg-type]
        changes=object(),  # type: ignore[arg-type]
        test_reports=object(),  # type: ignore[arg-type]
        checkpoints=object(),  # type: ignore[arg-type]
        recovery=object(),  # type: ignore[arg-type]
        delivery=object(),  # type: ignore[arg-type]
        build=_Build(),  # type: ignore[arg-type]
    )
    result = TuiOperationExecutor(tmp_path, services).execute(
        TuiOperation(
            request_id="req-build-001",
            kind=TuiOperationKind.BUILD,
            task_id="task-001",
        )
    )

    assert isinstance(result.value, BuildSummary)
    assert calls == [(tmp_path, "task-001")]
