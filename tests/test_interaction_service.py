from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Iterator

import pytest

from hancode.app.interaction_service import InteractionService
from hancode.app.task_models import TaskSummary
from hancode.core.errors import HanCodeError, StructuredError
from hancode.core.interactions import InteractionRecord, InteractionStatus
from hancode.core.models import Phase, TaskStatus
from hancode.core.state import load_state, save_state
from hancode.storage.workspace import init_project_workspace, init_task_workspace, task_path


class _RecordingGuard:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Phase]] = []

    @contextmanager
    def acquire(self, task_id: str, phase: Phase) -> Iterator[None]:
        self.calls.append((task_id, phase))
        yield


class _BusyGuard:
    @contextmanager
    def acquire(self, task_id: str, phase: Phase) -> Iterator[None]:
        raise HanCodeError(
            StructuredError(
                error_code="mutation_lock_busy",
                message="Task lock is busy.",
                phase=phase.value,
                denied_rule="single_task_mutator_required",
                suggested_fix="Retry after the active task run finishes.",
            )
        )
        yield


def _make_waiting_task(tmp_path: Path) -> tuple[Path, str]:
    init_project_workspace(tmp_path, "project-001", "Course", "Assignment")
    task_id = "task-001"
    init_task_workspace(tmp_path, task_id, goal="Choose a target.")
    root = task_path(tmp_path, task_id)
    state = load_state(root)
    interaction = InteractionRecord(
        interaction_id="ask-000001",
        phase=Phase.SPEC,
        question="Which target should be used?",
        answer=None,
        status=InteractionStatus.WAITING,
    )
    save_state(
        root,
        replace(
            state,
            status=TaskStatus.WAITING_INPUT,
            interaction_seq=1,
            interactions=(interaction,),
            pending_interaction_id=interaction.interaction_id,
        ),
    )
    return tmp_path, task_id


def test_get_pending_returns_waiting_interaction(tmp_path: Path) -> None:
    project_root, task_id = _make_waiting_task(tmp_path)

    pending = InteractionService().get_pending(project_root, task_id)

    assert pending is not None
    assert pending.interaction_id == "ask-000001"
    assert pending.question == "Which target should be used?"
    assert pending.answer is None


def test_task_summary_exposes_pending_interaction_without_answer(tmp_path: Path) -> None:
    project_root, task_id = _make_waiting_task(tmp_path)

    from hancode.app.task_models import TaskSummary

    summary = TaskSummary.from_state(load_state(task_path(project_root, task_id)))

    assert summary.requires_input is True
    assert summary.resumable is False
    assert summary.pending_interaction == {
        "interaction_id": "ask-000001",
        "phase": "spec",
        "question": "Which target should be used?",
        "answer_received": False,
    }


def test_answer_updates_pending_interaction(tmp_path: Path) -> None:
    project_root, task_id = _make_waiting_task(tmp_path)

    summary = InteractionService().answer(
        project_root, task_id, "src/main.py", interaction_id="ask-000001"
    )

    assert isinstance(summary, TaskSummary)
    assert summary.status is TaskStatus.WAITING_INPUT
    state = load_state(task_path(project_root, task_id))
    assert state.interactions[0].status is InteractionStatus.ANSWERED
    assert state.interactions[0].answer == "src/main.py"
    assert state.pending_interaction_id == "ask-000001"
    trace = (task_path(project_root, task_id) / "trace.jsonl").read_text(
        encoding="utf-8"
    )
    assert "interaction_answered" in trace
    assert "src/main.py" not in trace


def test_same_answer_is_idempotent(tmp_path: Path) -> None:
    project_root, task_id = _make_waiting_task(tmp_path)
    service = InteractionService()

    service.answer(project_root, task_id, "src/main.py")
    summary = service.answer(project_root, task_id, "src/main.py")

    assert summary.status is TaskStatus.WAITING_INPUT


def test_different_answer_conflicts(tmp_path: Path) -> None:
    project_root, task_id = _make_waiting_task(tmp_path)
    service = InteractionService()
    service.answer(project_root, task_id, "src/main.py")

    with pytest.raises(HanCodeError) as exc_info:
        service.answer(project_root, task_id, "src/other.py")

    assert exc_info.value.structured_error.error_code == "interaction_answer_conflict"


def test_answer_requires_pending_question(tmp_path: Path) -> None:
    init_project_workspace(tmp_path, "project-001", "Course", "Assignment")
    init_task_workspace(tmp_path, "task-001")

    with pytest.raises(HanCodeError) as exc_info:
        InteractionService().answer(tmp_path, "task-001", "answer")

    assert exc_info.value.structured_error.error_code == "interaction_not_pending"


def test_answer_rejects_mismatched_interaction_id(tmp_path: Path) -> None:
    project_root, task_id = _make_waiting_task(tmp_path)

    with pytest.raises(HanCodeError) as exc_info:
        InteractionService().answer(
            project_root, task_id, "src/main.py", interaction_id="ask-000002"
        )

    assert exc_info.value.structured_error.error_code == "interaction_id_mismatch"


def test_answer_rejects_blank_or_overlong_answer(tmp_path: Path) -> None:
    project_root, task_id = _make_waiting_task(tmp_path)
    service = InteractionService()

    with pytest.raises(HanCodeError) as blank_error:
        service.answer(project_root, task_id, "   ")
    assert blank_error.value.structured_error.error_code == "interaction_answer_required"

    with pytest.raises(HanCodeError) as long_error:
        service.answer(project_root, task_id, "x" * 8193)
    assert long_error.value.structured_error.error_code == "interaction_answer_too_long"


def test_answer_redacts_secret_before_persisting(tmp_path: Path) -> None:
    project_root, task_id = _make_waiting_task(tmp_path)

    InteractionService().answer(project_root, task_id, "api_key=sk-secret-value")

    state = load_state(task_path(project_root, task_id))
    assert state.interactions[0].answer == "api_key=[REDACTED]"
    assert "sk-secret-value" not in state.interactions[0].answer


def test_answer_rejects_answer_containing_only_sensitive_content(tmp_path: Path) -> None:
    project_root, task_id = _make_waiting_task(tmp_path)

    with pytest.raises(HanCodeError) as exc_info:
        InteractionService().answer(project_root, task_id, "sk-secret-value")

    assert (
        exc_info.value.structured_error.error_code
        == "interaction_answer_contains_only_sensitive_content"
    )
    assert "sk-secret-value" not in str(exc_info.value)


def test_answer_uses_task_mutation_lock(tmp_path: Path) -> None:
    project_root, task_id = _make_waiting_task(tmp_path)
    guard = _RecordingGuard()

    InteractionService(guard_factory=lambda _: guard).answer(
        project_root, task_id, "src/main.py"
    )

    assert guard.calls == [(task_id, Phase.SPEC)]


def test_answer_propagates_busy_task_mutation_lock(tmp_path: Path) -> None:
    project_root, task_id = _make_waiting_task(tmp_path)

    with pytest.raises(HanCodeError) as exc_info:
        InteractionService(guard_factory=lambda _: _BusyGuard()).answer(
            project_root, task_id, "src/main.py"
        )

    assert exc_info.value.structured_error.error_code == "mutation_lock_busy"


def test_answer_trace_failure_restores_waiting_interaction(tmp_path: Path) -> None:
    project_root, task_id = _make_waiting_task(tmp_path)

    import hancode.app.interaction_service as svc

    original_append = svc.append_trace
    call_count = 0

    def _failing_append(*args: object, **kwargs: object) -> object:
        nonlocal call_count
        call_count += 1
        raise HanCodeError(
            StructuredError(
                error_code="trace_write_error",
                message="Simulated trace write failure.",
                phase="spec",
                denied_rule="trace_write_required",
                suggested_fix="Restore trace storage.",
            )
        )

    svc.append_trace = _failing_append
    try:
        with pytest.raises(HanCodeError) as exc_info:
            InteractionService().answer(project_root, task_id, "src/main.py")
        assert exc_info.value.structured_error.error_code == "trace_write_error"
    finally:
        svc.append_trace = original_append

    state = load_state(task_path(project_root, task_id))
    assert state.interactions[0].status is InteractionStatus.WAITING
    assert state.interactions[0].answer is None
    assert state.status is TaskStatus.WAITING_INPUT
