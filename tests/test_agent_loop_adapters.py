from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from hancode import agent_loop as agent_loop_module
from hancode.agent_loop import (
    FilesystemAgentLoopPorts,
    FilesystemCheckpointManager,
    FilesystemMutationGuard,
    FilesystemRollbackManager,
    FilesystemStateStore,
    FilesystemTraceAppender,
)
from hancode.checkpoints import CheckpointManifest, RollbackResult
from hancode.errors import HanCodeError
from hancode.models import Phase
from hancode.state import TaskState
from hancode.trace import TraceEvent


def test_filesystem_adapters_delegate_against_one_task_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    task_root = tmp_path / ".hancode" / "tasks" / "task-001"
    calls: list[tuple[str, object]] = []
    state = cast(TaskState, object())
    manifest = cast(CheckpointManifest, object())
    rollback = cast(RollbackResult, object())
    trace_event = cast(TraceEvent, object())

    def fake_task_path(project_root: Path, task_id: str) -> Path:
        calls.append(("task_path", (project_root, task_id)))
        return task_root

    def fake_load_state(root: Path) -> TaskState:
        calls.append(("load_state", root))
        return state

    def fake_save_state(root: Path, value: TaskState) -> None:
        calls.append(("save_state", (root, value)))

    def fake_create_checkpoint(
        root: Path, files: list[Path], reason: str
    ) -> CheckpointManifest:
        calls.append(("create_checkpoint", (root, files, reason)))
        return manifest

    def fake_commit_checkpoint(root: Path, checkpoint_id: str) -> CheckpointManifest:
        calls.append(("commit_checkpoint", (root, checkpoint_id)))
        return manifest

    def fake_rollback_last_checkpoint(
        root: Path, *, record_trace: bool = True
    ) -> RollbackResult:
        calls.append(("rollback_last_checkpoint", (root, record_trace)))
        return rollback

    def fake_append_trace(root: Path, **kwargs: object) -> TraceEvent:
        calls.append(("append_trace", (root, kwargs)))
        return trace_event

    monkeypatch.setattr(agent_loop_module, "task_path", fake_task_path)
    monkeypatch.setattr(agent_loop_module, "load_state", fake_load_state)
    monkeypatch.setattr(agent_loop_module, "save_state", fake_save_state)
    monkeypatch.setattr(agent_loop_module, "create_checkpoint", fake_create_checkpoint)
    monkeypatch.setattr(agent_loop_module, "commit_checkpoint", fake_commit_checkpoint)
    monkeypatch.setattr(
        agent_loop_module, "rollback_last_checkpoint", fake_rollback_last_checkpoint
    )
    monkeypatch.setattr(agent_loop_module, "append_trace", fake_append_trace)

    state_adapter = FilesystemStateStore(tmp_path)
    checkpoint_adapter = FilesystemCheckpointManager(tmp_path)
    rollback_adapter = FilesystemRollbackManager(tmp_path)
    trace_adapter = FilesystemTraceAppender(tmp_path)
    ports = FilesystemAgentLoopPorts.from_project_root(tmp_path)

    assert isinstance(ports.state_store, FilesystemStateStore)
    assert isinstance(ports.trace_appender, FilesystemTraceAppender)
    assert isinstance(ports.checkpoint_manager, FilesystemCheckpointManager)
    assert isinstance(ports.rollback_manager, FilesystemRollbackManager)
    assert isinstance(ports.mutation_guard, FilesystemMutationGuard)

    assert state_adapter.load("task-001") is state
    state_adapter.save("task-001", state)
    assert checkpoint_adapter.create("task-001", [Path("src/main.py")], "fix") is manifest
    assert checkpoint_adapter.commit("task-001", "ckpt-001") is manifest
    assert rollback_adapter.rollback_last("task-001") is rollback
    assert (
        trace_adapter.append(
            "task-001",
            event_type="phase_started",
            phase=Phase.CODE,
            status="running",
            action=None,
            observation={"step": 1},
            error_summary=None,
            state_transition=None,
        )
        is trace_event
    )

    assert [name for name, _ in calls] == [
        "task_path",
        "load_state",
        "task_path",
        "save_state",
        "task_path",
        "create_checkpoint",
        "task_path",
        "commit_checkpoint",
        "task_path",
        "rollback_last_checkpoint",
        "task_path",
        "append_trace",
    ]


def test_filesystem_mutation_guard_is_exclusive(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    task_root = tmp_path / "task-001"
    task_root.mkdir()
    monkeypatch.setattr(agent_loop_module, "task_path", lambda root, task_id: task_root)
    guard = FilesystemMutationGuard(tmp_path)

    with guard.acquire("task-001", Phase.CODE):
        with pytest.raises(HanCodeError) as error:
            with guard.acquire("task-001", Phase.CODE):
                pass
        assert error.value.structured_error.error_code == "mutation_lock_busy"

    assert not (task_root / ".agent-loop.lock").exists()
