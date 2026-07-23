"""S5-R2: shared Textual Worker lifecycle contracts."""

from __future__ import annotations

from pathlib import Path

import hancode.interfaces.tui.app as tui_app_module
from hancode.core.errors import StructuredError
from hancode.interfaces.tui.app import HanCodeTuiApp
from hancode.interfaces.tui.messages import OperationFailed, OperationFinished
from hancode.interfaces.tui.operations import (
    TuiOperation,
    TuiOperationError,
    TuiOperationKind,
    TuiOperationResult,
)


class _Worker:
    is_cancelled = False


def _run_worker_inline(app: HanCodeTuiApp, monkeypatch, posted: list[object]) -> dict[str, object]:
    captured: dict[str, object] = {}

    def run_worker(body, **kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        body()

    monkeypatch.setattr(tui_app_module, "get_current_worker", lambda: _Worker())
    monkeypatch.setattr(app, "run_worker", run_worker)
    monkeypatch.setattr(
        app,
        "call_from_thread",
        lambda _callback, message: posted.append(message),
    )
    return captured


def test_query_worker_uses_shared_query_group_and_preserves_result(
    tmp_path: Path, monkeypatch
) -> None:
    app = HanCodeTuiApp(project_root=tmp_path)
    operation = TuiOperation(
        request_id="req-query-001",
        kind=TuiOperationKind.GET_STATUS,
        task_id="task-001",
    )
    result = TuiOperationResult(
        request_id=operation.request_id,
        kind=operation.kind,
        task_id=operation.task_id,
        value={},
    )
    posted: list[object] = []
    captured = _run_worker_inline(app, monkeypatch, posted)
    monkeypatch.setattr(
        app.controller,
        "execute",
        lambda _operation, trace_observer=None: result,
    )

    app.controller.begin_operation(operation)
    app._run_query_worker(operation)

    assert captured["group"] == "task-query"
    assert captured["exclusive"] is False
    assert isinstance(posted[0], OperationFinished)
    assert posted[0].result.request_id == operation.request_id


def test_mutation_worker_uses_shared_mutation_group(tmp_path: Path, monkeypatch) -> None:
    app = HanCodeTuiApp(project_root=tmp_path)
    operation = TuiOperation(
        request_id="req-mutation-001",
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
    captured = _run_worker_inline(app, monkeypatch, posted)
    monkeypatch.setattr(
        app.controller,
        "execute",
        lambda _operation, trace_observer=None: result,
    )

    app.controller.begin_operation(operation)
    app._run_worker(operation)

    assert captured["group"] == "task-mutation"
    assert captured["exclusive"] is True
    assert isinstance(posted[0], OperationFinished)


def test_query_worker_error_clears_request_through_operation_failed(
    tmp_path: Path, monkeypatch
) -> None:
    app = HanCodeTuiApp(project_root=tmp_path)
    operation = TuiOperation(
        request_id="req-query-error-001",
        kind=TuiOperationKind.GET_STATUS,
        task_id="task-001",
    )
    error = TuiOperationError(
        operation.request_id,
        operation.kind,
        operation.task_id,
        StructuredError(
            error_code="query_failed",
            message="查询失败。",
            phase="spec",
            denied_rule="query_failed",
            suggested_fix="重试查询。",
        ),
    )
    posted: list[object] = []
    _run_worker_inline(app, monkeypatch, posted)
    monkeypatch.setattr(
        app.controller,
        "execute",
        lambda _operation, trace_observer=None: (_ for _ in ()).throw(error),
    )

    app.controller.begin_operation(operation)
    app._run_query_worker(operation)
    assert isinstance(posted[0], OperationFailed)

    app.on_operation_failed(posted[0])

    assert app.controller.state.current_request_id is None
    assert app.controller.state.active_query is None
    assert app.controller.state.last_error == error.structured_error
