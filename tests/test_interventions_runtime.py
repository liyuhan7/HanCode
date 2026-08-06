"""Run identity + AgentLoop steering integration tests (S17-R1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from hancode.app.task_service import TaskService
from hancode.core.errors import HanCodeError
from hancode.core.models import TaskStatus
from hancode.core.state import load_state
from hancode.runtime.agent_loop import AgentRunResult
from hancode.storage.interventions import InterventionStore
from hancode.storage.workspace import (
    init_project_workspace,
    init_task_workspace,
    task_path,
)


def _make_project(tmp_path: Path) -> Path:
    init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Harness",
    )
    return tmp_path


def _run_result(status: TaskStatus, state: object) -> AgentRunResult:
    return AgentRunResult(
        status=status,
        steps=0,
        tool_calls=(),
        risks=(),
        final_observation=None,
        error=None,
        final_state=state,  # type: ignore[arg-type]
        retry_budget_remaining=0,
        trace_events=(),
    )


def test_run_creates_and_persists_run_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _make_project(tmp_path)
    service = TaskService()
    service.create(tmp_path, "goal")
    captured: dict[str, str | None] = {}

    def fake_run_task(project_root: Path, task_id: str, **kwargs: object) -> object:
        captured["run_id"] = load_state(task_path(project_root, task_id)).active_run_id
        return object()

    monkeypatch.setattr("hancode.app.task_service.run_task", fake_run_task)
    service.run(tmp_path, "task-001", provider=object())  # type: ignore[arg-type]

    persisted = load_state(task_path(tmp_path, "task-001")).active_run_id
    assert captured["run_id"] is not None
    assert persisted == captured["run_id"]


def test_resume_reuses_existing_run_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _make_project(tmp_path)
    service = TaskService()
    service.create(tmp_path, "goal")
    seen: list[str | None] = []

    def fake_run_task(project_root: Path, task_id: str, **kwargs: object) -> object:
        seen.append(load_state(task_path(project_root, task_id)).active_run_id)
        return object()

    monkeypatch.setattr("hancode.app.task_service.run_task", fake_run_task)
    service.run(tmp_path, "task-001", provider=object())  # type: ignore[arg-type]
    service.resume(tmp_path, "task-001", provider=object())  # type: ignore[arg-type]

    assert seen[0] is not None
    assert seen[0] == seen[1]


def test_run_rejected_when_active_run_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _make_project(tmp_path)
    service = TaskService()
    service.create(tmp_path, "goal")

    def fake_run_task(project_root: Path, task_id: str, **kwargs: object) -> object:
        return object()

    monkeypatch.setattr("hancode.app.task_service.run_task", fake_run_task)
    service.run(tmp_path, "task-001", provider=object())  # type: ignore[arg-type]

    with pytest.raises(HanCodeError) as exc:
        service.run(tmp_path, "task-001", provider=object())  # type: ignore[arg-type]
    assert exc.value.structured_error.error_code == "task_run_already_active"


def test_terminal_status_clears_run_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _make_project(tmp_path)
    service = TaskService()
    service.create(tmp_path, "goal")

    def fake_run_task(project_root: Path, task_id: str, **kwargs: object) -> object:
        state = load_state(task_path(project_root, task_id))
        return _run_result(TaskStatus.COMPLETED, state)

    monkeypatch.setattr("hancode.app.task_service.run_task", fake_run_task)
    service.run(tmp_path, "task-001", provider=object())  # type: ignore[arg-type]

    assert load_state(task_path(tmp_path, "task-001")).active_run_id is None


class _RecordingContextBuilder:
    """Wraps the real ContextBuilder shape enough to capture steering."""

    def __init__(self) -> None:
        self.revisions: list[int] = []
        self.effective_counts: list[int] = []

    def build(
        self,
        *,
        task_id: str,
        phase: object,
        state: object,
        observation: object | None = None,
        user_interventions: tuple[object, ...] = (),
        intervention_revision: int = 0,
    ) -> dict[str, object]:
        self.revisions.append(intervention_revision)
        self.effective_counts.append(len(user_interventions))
        return {"task_id": task_id, "user_interventions": {"revision": intervention_revision}}


def test_agent_loop_snapshot_none_without_store(tmp_path: Path) -> None:
    from hancode.runtime.agent_loop import AgentLoop

    # A minimal AgentLoop with no store returns None snapshot, preserving old
    # behaviour: _prepare_steering_snapshot short-circuits.
    loop = AgentLoop.__new__(AgentLoop)
    loop._intervention_store = None  # type: ignore[attr-defined]
    assert loop._prepare_steering_snapshot("task-001", object()) is None  # type: ignore[arg-type]


def test_agent_loop_snapshot_uses_active_run(tmp_path: Path) -> None:
    from dataclasses import replace

    from hancode.runtime.agent_loop import AgentLoop

    _make_project(tmp_path)
    init_task_workspace(tmp_path, "task-050", goal="Steer.")
    store = InterventionStore(tmp_path)
    store.submit("task-050", "run-x", "Only touch API validation.")

    loop = AgentLoop.__new__(AgentLoop)
    loop._intervention_store = store  # type: ignore[attr-defined]

    state = load_state(task_path(tmp_path, "task-050"))
    with_run = replace(state, active_run_id="run-x")
    snapshot = loop._prepare_steering_snapshot("task-050", with_run)  # type: ignore[arg-type]

    assert snapshot is not None
    assert snapshot.revision == 1
    assert snapshot.effective_records[0].content == "Only touch API validation."

    # A task with no active run yields no snapshot.
    assert loop._prepare_steering_snapshot("task-050", state) is None  # type: ignore[arg-type]


# =========================================================================
# S17-R2: revision linearization wiring in AgentLoop
# =========================================================================


def _snapshot(revision: int, sequences: tuple[int, ...]) -> object:
    from hancode.core.interventions import SteeringSnapshot

    return SteeringSnapshot(
        task_id="task-001",
        run_id="run-a",
        revision=revision,
        effective_records=(),
        delivery_sequences=sequences,
    )


class _FakeStore:
    def __init__(
        self,
        *,
        delivered_status: object,
        current: int,
        commit_status: object,
    ) -> None:
        from hancode.core.interventions import (
            ActionCommitResult,
            DeliveryResult,
        )

        self._delivered = DeliveryResult(
            status=delivered_status, current_revision=current  # type: ignore[arg-type]
        )
        self._current = current
        self._commit = ActionCommitResult(
            status=commit_status, current_revision=current  # type: ignore[arg-type]
        )
        self.commit_calls: list[tuple[str, bool]] = []

    def mark_delivered(self, *a: object, **k: object) -> object:
        return self._delivered

    def current_revision(self, task_id: str) -> int:
        return self._current

    def commit_action(
        self,
        task_id: str,
        run_id: str,
        expected_revision: int,
        delivery_sequences: tuple[int, ...],
        action_digest: str,
        commit_key: str,
        acknowledge: bool,
    ) -> object:
        self.commit_calls.append((commit_key, acknowledge))
        return self._commit


def _loop_with(store: object) -> object:
    from hancode.runtime.agent_loop import AgentLoop

    loop = AgentLoop.__new__(AgentLoop)
    loop._intervention_store = store  # type: ignore[attr-defined]
    return loop


def test_mark_delivered_stale_signals_replan() -> None:
    from hancode.core.interventions import ActionCommitStatus, DeliveryStatus

    store = _FakeStore(
        delivered_status=DeliveryStatus.STALE,
        current=5,
        commit_status=ActionCommitStatus.COMMITTED,
    )
    loop = _loop_with(store)
    assert loop._mark_steering_delivered("task-001", _snapshot(3, (1,))) is True  # type: ignore[attr-defined]


def test_mark_delivered_ok_not_stale() -> None:
    from hancode.core.interventions import ActionCommitStatus, DeliveryStatus

    store = _FakeStore(
        delivered_status=DeliveryStatus.DELIVERED,
        current=3,
        commit_status=ActionCommitStatus.COMMITTED,
    )
    loop = _loop_with(store)
    assert loop._mark_steering_delivered("task-001", _snapshot(3, (1,))) is False  # type: ignore[attr-defined]


def test_revision_changed_detects_provider_window_steering() -> None:
    from hancode.core.interventions import ActionCommitStatus, DeliveryStatus

    store = _FakeStore(
        delivered_status=DeliveryStatus.DELIVERED,
        current=7,
        commit_status=ActionCommitStatus.COMMITTED,
    )
    loop = _loop_with(store)
    assert loop._steering_revision_changed("task-001", _snapshot(3, ())) is True  # type: ignore[attr-defined]
    assert loop._steering_revision_changed("task-001", _snapshot(7, ())) is False  # type: ignore[attr-defined]


def test_commit_gate_replan_when_store_returns_replan() -> None:
    from hancode.core.interventions import ActionCommitStatus, DeliveryStatus

    store = _FakeStore(
        delivered_status=DeliveryStatus.DELIVERED,
        current=4,
        commit_status=ActionCommitStatus.REPLAN,
    )
    loop = _loop_with(store)
    replan = loop._commit_steering_action(  # type: ignore[attr-defined]
        "task-001",
        _snapshot(3, (1,)),
        action_digest="d",
        commit_key="run-a:step-1:d",
        acknowledge=False,
    )
    assert replan is True
    assert store.commit_calls == [("run-a:step-1:d", False)]


def test_commit_gate_proceeds_without_store() -> None:
    loop = _loop_with(None)
    assert (
        loop._commit_steering_action(  # type: ignore[attr-defined]
            "task-001",
            _snapshot(3, (1,)),
            action_digest="d",
            commit_key="k",
            acknowledge=False,
        )
        is False
    )
