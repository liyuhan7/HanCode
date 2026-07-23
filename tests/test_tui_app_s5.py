"""S5-R0: Textual app boundary checks."""

from __future__ import annotations

from pathlib import Path

from hancode.core.models import Phase, TaskStatus
from hancode.core.state import TaskState
from hancode.app.task_models import TaskSummary
from hancode.interfaces.tui.messages import OperationFailed, OperationFinished
from hancode.interfaces.tui.operations import (
    TuiOperation,
    TuiOperationError,
    TuiOperationKind,
    TuiOperationResult,
)
from hancode.interfaces.tui.app import HanCodeTuiApp
from hancode.runtime.agent_loop import AgentRunResult
import hancode.interfaces.tui.app as tui_app_module


def test_app_does_not_call_application_services_directly() -> None:
    app_path = Path(__file__).parents[1] / "src" / "hancode" / "interfaces" / "tui" / "app.py"
    source = app_path.read_text(encoding="utf-8")

    for service_attribute in (
        "self._task_service.",
        "self._interaction_service.",
        "self._approval_service.",
        "self._inspection_service.",
        "self._recovery_service.",
    ):
        assert service_attribute not in source

    assert "def _execute_sync" not in source


def test_run_worker_uses_request_scoped_operation_messages() -> None:
    app_path = Path(__file__).parents[1] / "src" / "hancode" / "interfaces" / "tui" / "app.py"
    source = app_path.read_text(encoding="utf-8")
    worker_start = source.index("    def _run_operation_worker(")
    message_handlers_start = source.index("    # -- message handlers", worker_start)
    worker_source = source[worker_start:message_handlers_start]

    assert "OperationFinished(result)" in worker_source
    assert "OperationFailed(" in worker_source
    assert "RunFinished(" not in worker_source
    assert "RunFailed(" not in worker_source


def test_run_worker_posts_complete_operation_result(tmp_path: Path, monkeypatch) -> None:
    app = HanCodeTuiApp(project_root=tmp_path)
    operation = TuiOperation(
        request_id="req-worker-001",
        kind=TuiOperationKind.RUN_TASK,
        task_id="task-001",
    )
    result = TuiOperationResult(
        request_id=operation.request_id,
        kind=operation.kind,
        task_id=operation.task_id,
        value={},
    )
    posted: list[object] = []

    class _Worker:
        is_cancelled = False

    app.controller.begin_operation(operation)
    monkeypatch.setattr(tui_app_module, "get_current_worker", lambda: _Worker())
    monkeypatch.setattr(app, "run_worker", lambda body, **_: body())
    monkeypatch.setattr(
        app,
        "call_from_thread",
        lambda _callback, message: posted.append(message),
    )
    monkeypatch.setattr(
        app.controller,
        "execute",
        lambda _operation, trace_observer=None: result,
    )

    app._run_worker(operation)

    assert len(posted) == 1
    assert isinstance(posted[0], OperationFinished)
    assert posted[0].result is result
    assert posted[0].result.request_id == operation.request_id


def test_run_worker_posts_complete_operation_error(tmp_path: Path, monkeypatch) -> None:
    app = HanCodeTuiApp(project_root=tmp_path)
    operation = TuiOperation(
        request_id="req-worker-002",
        kind=TuiOperationKind.RUN_TASK,
        task_id="task-001",
    )
    from hancode.core.errors import StructuredError

    error = TuiOperationError(
        operation.request_id,
        operation.kind,
        operation.task_id,
        StructuredError(
            error_code="run_failed",
            message="运行失败。",
            phase="code",
            denied_rule="run_failed",
            suggested_fix="检查任务状态。",
        ),
    )
    posted: list[object] = []

    class _Worker:
        is_cancelled = False

    app.controller.begin_operation(operation)
    monkeypatch.setattr(tui_app_module, "get_current_worker", lambda: _Worker())
    monkeypatch.setattr(app, "run_worker", lambda body, **_: body())
    monkeypatch.setattr(
        app,
        "call_from_thread",
        lambda _callback, message: posted.append(message),
    )
    monkeypatch.setattr(
        app.controller,
        "execute",
        lambda _operation, trace_observer=None: (_ for _ in ()).throw(error),
    )

    app._run_worker(operation)

    assert len(posted) == 1
    assert isinstance(posted[0], OperationFailed)
    assert posted[0].error is error
    assert posted[0].error.request_id == operation.request_id


def _run_result() -> AgentRunResult:
    state = TaskState(
        schema_version=1,
        task_id="task-001",
        goal="Build it",
        status=TaskStatus.COMPLETED,
        current_phase=Phase.DELIVER,
        files_changed=(),
        latest_checkpoint=None,
        checkpoint_seq=0,
        tests_run=(),
        latest_test_status="passed",
        test_status_consumed=True,
        retry_budget_remaining=2,
        inconsistent=False,
        source_edits_this_phase=0,
        rollback_required=False,
        rollback_done=False,
        phase_completed={
            "spec": True,
            "plan": True,
            "code": True,
            "test": True,
            "review": True,
            "deliver": True,
        },
        artifacts={
            "SPEC.md": False,
            "PLAN.md": False,
            "TEST_REPORT.md": True,
            "REVIEW.md": False,
            "KNOWLEDGE.md": False,
            "DELIVERABLES.md": False,
        },
    )
    return AgentRunResult(
        status=TaskStatus.COMPLETED,
        steps=1,
        tool_calls=(),
        risks=(),
        final_observation=None,
        error=None,
        final_state=state,
        retry_budget_remaining=2,
        trace_events=(),
    )


def test_run_operation_finished_applies_result_through_controller(tmp_path: Path) -> None:
    app = HanCodeTuiApp(project_root=tmp_path)
    operation = TuiOperation(
        request_id="req-run-001",
        kind=TuiOperationKind.RUN_TASK,
        task_id="task-001",
    )
    app.controller.begin_operation(operation)
    app._refresh_task_list_data_only = lambda: None  # type: ignore[method-assign]

    app.on_operation_finished(
        OperationFinished(
            TuiOperationResult(
                request_id=operation.request_id,
                kind=operation.kind,
                task_id=operation.task_id,
                value=_run_result(),
            )
        )
    )

    assert app.controller.state.busy is False
    assert app.controller.state.active_task is not None
    assert app.controller.state.active_task.status is TaskStatus.COMPLETED


def test_operation_failed_clears_active_request_via_controller(tmp_path: Path) -> None:
    from hancode.core.errors import StructuredError

    app = HanCodeTuiApp(project_root=tmp_path)
    operation = TuiOperation(
        request_id="req-fail-001",
        kind=TuiOperationKind.RUN_TASK,
        task_id="task-001",
    )
    app.controller.begin_operation(operation)
    error = TuiOperationError(
        operation.request_id,
        operation.kind,
        operation.task_id,
        StructuredError(
            error_code="run_failed",
            message="运行失败。",
            phase="code",
            denied_rule="run_failed",
            suggested_fix="检查任务状态。",
        ),
    )

    app.on_operation_failed(OperationFailed(error))

    assert app.controller.state.busy is False
    assert app.controller.state.current_request_id is None
    assert app.controller.state.last_error == error.structured_error


def test_inspection_commands_dispatch_query_intents(tmp_path: Path, monkeypatch) -> None:
    app = HanCodeTuiApp(project_root=tmp_path)
    app.controller.set_active_summary(TaskSummary.from_state(_run_result().final_state))
    intents = []
    monkeypatch.setattr(app, "_start_query", lambda intent: intents.append(intent))

    app.submit_input("/diff latest src/main.py")
    app.submit_input("/test")
    app.submit_input("/checkpoints")
    app.submit_input("/delivery")
    app.submit_input("/trace evt-000001")

    assert [intent.kind for intent in intents] == [
        TuiOperationKind.DIFF,
        TuiOperationKind.TEST_REPORT,
        TuiOperationKind.CHECKPOINTS,
        TuiOperationKind.DELIVERY,
        TuiOperationKind.TRACE,
    ]
    assert intents[0].diff_scope == "latest"
    assert intents[0].diff_path == "src/main.py"
    assert intents[-1].event_id == "evt-000001"
