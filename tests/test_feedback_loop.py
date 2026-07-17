from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Literal, Mapping, cast

from hancode.actions import Action
from hancode.agent_loop import AgentLoop, CheckpointManager, Policy
from hancode.checkpoints import CheckpointFile, CheckpointManifest, RollbackResult
from hancode.errors import HanCodeError, StructuredError
from hancode.llm import MockLLM
from hancode.models import OperationStatus, Phase, TaskStatus
from hancode.path_policy import PathZone
from hancode.state import TaskState
from hancode.tools import ToolResult
from hancode.trace import TraceEvent


@dataclass(frozen=True)
class AllowedDecision:
    allowed: bool = True
    reason: str = "Action is allowed."
    requires_checkpoint: bool = False
    denied_rule: str | None = None
    suggested_fix: str = "Continue."
    target_zone: PathZone | None = None


class AllowMutationGuard:
    def __init__(self) -> None:
        self.acquisitions = 0
        self.active = 0

    @contextmanager
    def acquire(self, task_id: str, phase: Phase) -> Iterator[None]:
        self.acquisitions += 1
        self.active += 1
        try:
            yield
        finally:
            self.active -= 1


class MemoryStateStore:
    def __init__(self, state: TaskState) -> None:
        self.state = state
        self.saves: list[TaskState] = []

    def load(self, task_id: str) -> TaskState:
        assert task_id == self.state.task_id
        return self.state

    def save(self, task_id: str, state: TaskState) -> None:
        assert task_id == state.task_id
        self.state = state
        self.saves.append(state)


class FailingSaveAfterFirstSaveStore(MemoryStateStore):
    def __init__(self, state: TaskState) -> None:
        super().__init__(state)
        self._save_calls = 0

    def save(self, task_id: str, state: TaskState) -> None:
        self._save_calls += 1
        if self._save_calls == 3:
            raise HanCodeError(
                StructuredError(
                    error_code="state_write_error",
                    message="Task state could not be persisted.",
                    phase=Phase.CODE.value,
                    denied_rule="state_write_required",
                    suggested_fix="Restore task state storage.",
                )
            )
        super().save(task_id, state)


class PersistentFailureAfterCheckpointStore(MemoryStateStore):
    def __init__(self, state: TaskState) -> None:
        super().__init__(state)
        self._save_calls = 0

    def save(self, task_id: str, state: TaskState) -> None:
        self._save_calls += 1
        if self._save_calls >= 3:
            raise OSError("state storage unavailable")
        super().save(task_id, state)


class ReloadFailureAfterCheckpointStore(MemoryStateStore):
    def __init__(self, state: TaskState) -> None:
        super().__init__(state)
        self._load_calls = 0

    def load(self, task_id: str) -> TaskState:
        self._load_calls += 1
        if self._load_calls >= 3:
            raise HanCodeError(
                StructuredError(
                    error_code="state_reload_failed",
                    message="Task state could not be reloaded.",
                    phase=Phase.CODE.value,
                    denied_rule="state_read_required",
                    suggested_fix="Restore task state storage.",
                )
            )
        return super().load(task_id)


class FailingRollbackStateStore(MemoryStateStore):
    def __init__(self, state: TaskState) -> None:
        super().__init__(state)
        self._save_calls = 0

    def save(self, task_id: str, state: TaskState) -> None:
        self._save_calls += 1
        if self._save_calls >= 2:
            raise HanCodeError(
                StructuredError(
                    error_code="state_write_error",
                    message="Task state could not be persisted.",
                    phase=Phase.REVIEW.value,
                    denied_rule="state_write_required",
                    suggested_fix="Restore task state storage.",
                )
            )
        super().save(task_id, state)


class AllowedPolicy:
    def __init__(self, *, requires_checkpoint: bool = False) -> None:
        self._requires_checkpoint = requires_checkpoint

    def evaluate(
        self, *, action: Action, phase: Phase, state: TaskState
    ) -> AllowedDecision:
        assert action.phase is phase
        assert state.current_phase is phase
        return AllowedDecision(
            requires_checkpoint=(
                self._requires_checkpoint
                and action.tool_name in {"write_file", "edit_file"}
            ),
            target_zone=(
                PathZone.ARTIFACT
                if action.tool_name in {"write_file", "edit_file"}
                and str(action.args.get("path", "")).replace("\\", "/")
                in {"SPEC.md", "PLAN.md", "TEST_REPORT.md", "REVIEW.md", "KNOWLEDGE.md", "DELIVERABLES.md"}
                else PathZone.SOURCE
                if action.tool_name in {"write_file", "edit_file"}
                else None
            ),
        )


class ScriptedTools:
    def __init__(
        self,
        *,
        events: list[str] | None = None,
        write_success: bool = True,
    ) -> None:
        self.actions: list[Action] = []
        self.events = events
        self.write_success = write_success

    def dispatch(self, action: Action) -> ToolResult:
        if self.events is not None:
            self.events.append("dispatch")
        self.actions.append(action)
        if action.tool_name == "run_tests":
            return ToolResult(
                success=False,
                action_name="run_tests",
                exit_code=1,
                stderr="E   AssertionError: expected retry\n1 failed",
            )
        if action.tool_name == "write_file" and not self.write_success:
            return ToolResult(
                success=False,
                action_name="write_file",
                error_summary="Source write failed.",
            )
        return ToolResult(success=True, action_name=action.tool_name or "unknown")


class RecordingFeedback:
    def from_parse_error(self, error: object) -> object:
        return {"kind": "parse"}

    def from_policy_denial(self, decision: object) -> object:
        return {"kind": "policy"}

    def from_tool_result(self, result: ToolResult, *, phase: Phase) -> object:
        return {"kind": "test_failure", "phase": phase.value, "result": result}

    def from_checkpoint_manifest(self, manifest: CheckpointManifest) -> object:
        return {"kind": "checkpoint"}

    def from_rollback_result(self, result: RollbackResult, *, phase: Phase) -> object:
        return {"kind": "rollback"}


class FailingFeedback(RecordingFeedback):
    def from_tool_result(self, result: ToolResult, *, phase: Phase) -> object:
        raise HanCodeError(
            StructuredError(
                error_code="feedback_input_invalid",
                message="Feedback cannot be built.",
                phase=phase.value,
                denied_rule="feedback_test_double",
                suggested_fix="Repair the feedback builder.",
            )
        )


class NoopTraceAppender:
    def append(
        self,
        task_id: str,
        *,
        event_type: str,
        phase: Phase,
        status: str,
        action: Mapping[str, object] | None = None,
        observation: Mapping[str, object] | None = None,
        error_summary: str | None = None,
        state_transition: Mapping[str, object] | None = None,
    ) -> TraceEvent:
        raise AssertionError("Task 2 must not append trace events.")


class RecordingTraceAppender:
    def __init__(self) -> None:
        self.events: list[TraceEvent] = []

    def append(
        self,
        task_id: str,
        *,
        event_type: str,
        phase: Phase,
        status: str,
        action: Mapping[str, object] | None = None,
        observation: Mapping[str, object] | None = None,
        error_summary: str | None = None,
        state_transition: Mapping[str, object] | None = None,
    ) -> TraceEvent:
        event = TraceEvent(
            event_id=f"evt-{len(self.events) + 1:06d}",
            seq=len(self.events) + 1,
            event_type=event_type,
            task_id=task_id,
            phase=phase,
            timestamp=datetime.now(UTC),
            status=status,
            action=action,
            observation=observation,
            error_summary=error_summary,
            state_transition=state_transition,
        )
        self.events.append(event)
        return event


class FailingTraceAppender:
    def append(
        self,
        task_id: str,
        *,
        event_type: str,
        phase: Phase,
        status: str,
        action: Mapping[str, object] | None = None,
        observation: Mapping[str, object] | None = None,
        error_summary: str | None = None,
        state_transition: Mapping[str, object] | None = None,
    ) -> TraceEvent:
        raise HanCodeError(
            StructuredError(
                error_code="trace_write_error",
                message="Trace storage is unavailable.",
                phase=phase.value,
                denied_rule="trace_write_required",
                suggested_fix="Restore trace storage.",
            )
        )


class NoopCheckpointManager:
    def create(self, task_id: str, files: list[object], reason: str) -> CheckpointManifest:
        raise AssertionError("Task 2 must not create checkpoints.")

    def commit(self, task_id: str, checkpoint_id: str) -> CheckpointManifest:
        raise AssertionError("Task 2 must not commit checkpoints.")


class RecordingCheckpointManager:
    def __init__(
        self,
        events: list[str],
        *,
        create_error: HanCodeError | None = None,
        commit_error: HanCodeError | None = None,
    ) -> None:
        self.events = events
        self.create_error = create_error
        self.commit_error = commit_error
        self.files: list[Path] | None = None
        self.reason: str | None = None
        self._state_store: MemoryStateStore | None = None
        self._pending_manifest: CheckpointManifest | None = None

    def bind_state_store(self, state_store: MemoryStateStore) -> None:
        self._state_store = state_store

    def create(self, task_id: str, files: list[Path], reason: str) -> CheckpointManifest:
        self.events.append("create")
        self.files = files
        self.reason = reason
        if self.create_error is not None:
            raise self.create_error
        manifest = _checkpoint_manifest(task_id)
        if self._state_store is not None:
            self._state_store.save(
                task_id,
                replace(
                    self._state_store.state,
                    latest_checkpoint=manifest.checkpoint_id,
                    checkpoint_seq=self._state_store.state.checkpoint_seq + 1,
                ),
            )
        self._pending_manifest = manifest
        return manifest

    def commit(self, task_id: str, checkpoint_id: str) -> CheckpointManifest:
        self.events.append("commit")
        assert checkpoint_id == "ckpt-001"
        if self.commit_error is not None:
            raise self.commit_error
        pending = self._pending_manifest or _checkpoint_manifest(task_id)
        return replace(pending, status="committed", rollback_available=True, files=tuple(
            replace(file, after_sha256="a" * 64) for file in pending.files
        ))


class StatePersistingCheckpointManager(RecordingCheckpointManager):
    def __init__(self, events: list[str], state_store: MemoryStateStore) -> None:
        super().__init__(events)
        self.bind_state_store(state_store)

    def create(self, task_id: str, files: list[Path], reason: str) -> CheckpointManifest:
        return super().create(task_id, files, reason)


class InvalidCheckpointManager(RecordingCheckpointManager):
    def create(self, task_id: str, files: list[Path], reason: str) -> CheckpointManifest:
        return replace(super().create(task_id, files, reason), task_id="other-task")


class MalformedCheckpointIdManager(RecordingCheckpointManager):
    def create(self, task_id: str, files: list[Path], reason: str) -> CheckpointManifest:
        return replace(super().create(task_id, files, reason), checkpoint_id="../outside")


class InconsistentCheckpointStateManager(StatePersistingCheckpointManager):
    def create(self, task_id: str, files: list[Path], reason: str) -> CheckpointManifest:
        manifest = super().create(task_id, files, reason)
        state_store = self._state_store
        assert state_store is not None
        state_store.save(
            task_id,
            replace(state_store.state, status=TaskStatus.INCONSISTENT, inconsistent=True),
        )
        return manifest


class InvalidCommitCheckpointManager(RecordingCheckpointManager):
    def commit(self, task_id: str, checkpoint_id: str) -> CheckpointManifest:
        committed = super().commit(task_id, checkpoint_id)
        return replace(committed, status="pending", rollback_available=False)


class NoPersistCheckpointManager:
    def create(self, task_id: str, files: list[Path], reason: str) -> CheckpointManifest:
        return _checkpoint_manifest(task_id)

    def commit(self, task_id: str, checkpoint_id: str) -> CheckpointManifest:
        return _checkpoint_manifest(task_id, status="committed", rollback_available=True)


class TamperedCommitCheckpointManager(RecordingCheckpointManager):
    def commit(self, task_id: str, checkpoint_id: str) -> CheckpointManifest:
        committed = super().commit(task_id, checkpoint_id)
        return replace(
            committed,
            files=(*committed.files, CheckpointFile(
                path="src/victim.py",
                action="create",
                before_snapshot=None,
                before_sha256=None,
                after_sha256="c" * 64,
            )),
        )


class NoopRollbackManager:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def rollback_last(self, task_id: str) -> RollbackResult:
        self.calls.append(task_id)
        raise AssertionError("Task 2 must not roll back checkpoints.")


class FailingRollbackManager:
    def rollback_last(self, task_id: str) -> RollbackResult:
        return RollbackResult(
            status=OperationStatus.FAILED,
            checkpoint_id="ckpt-001",
            restored_files=(),
            failed_files=("src/main.py",),
            error=StructuredError(
                error_code="rollback_restore_failed",
                message="Rollback could not restore the source file.",
                phase=Phase.REVIEW.value,
                denied_rule="rollback_restore_required",
                suggested_fix="Restore source file access.",
            ),
        )


class RaisingRollbackManager:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def rollback_last(self, task_id: str) -> RollbackResult:
        self.calls.append(task_id)
        raise HanCodeError(
            StructuredError(
                error_code="rollback_storage_failed",
                message="Rollback storage is unavailable.",
                phase=Phase.REVIEW.value,
                denied_rule="rollback_execution_required",
                suggested_fix="Restore checkpoint storage before retrying rollback.",
            )
        )


class RaisingTools(ScriptedTools):
    def dispatch(self, action: Action) -> ToolResult:
        raise HanCodeError(
            StructuredError(
                error_code="tool_dispatch_failed",
                message="Tool dispatch failed.",
                phase=action.phase.value,
                denied_rule="tool_dispatch_required",
                suggested_fix="Repair the tool registry.",
            )
        )


class InvalidToolResultTools(ScriptedTools):
    def dispatch(self, action: Action) -> ToolResult:
        return ToolResult(
            success=cast(bool, "yes"),
            action_name=action.tool_name or "unknown",
        )


class RecordingRollbackManager:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self._state_store: MemoryStateStore | None = None

    def bind_state_store(self, state_store: MemoryStateStore) -> None:
        self._state_store = state_store

    def rollback_last(self, task_id: str) -> RollbackResult:
        self.calls.append(task_id)
        if self._state_store is not None:
            phase_completed = dict(self._state_store.state.phase_completed)
            phase_completed.update(
                {
                    Phase.CODE.value: False,
                    Phase.TEST.value: False,
                    Phase.REVIEW.value: False,
                }
            )
            self._state_store.save(
                task_id,
                replace(
                    self._state_store.state,
                    latest_test_status="none",
                    test_status_consumed=False,
                    source_edits_this_phase=0,
                    rollback_required=False,
                    rollback_done=True,
                    phase_completed=phase_completed,
                ),
            )
        return RollbackResult(
            status=OperationStatus.SUCCEEDED,
            checkpoint_id="ckpt-001",
            restored_files=("src/main.py",),
            failed_files=(),
            error=None,
        )


class StatePersistingRollbackManager(RecordingRollbackManager):
    def __init__(self, state_store: MemoryStateStore) -> None:
        super().__init__()
        self._state_store = state_store

    def rollback_last(self, task_id: str) -> RollbackResult:
        result = super().rollback_last(task_id)
        phase_completed = dict(self._state_store.state.phase_completed)
        phase_completed.update(
            {
                Phase.CODE.value: False,
                Phase.TEST.value: False,
                Phase.REVIEW.value: False,
            }
        )
        self._state_store.save(
            task_id,
            replace(
                self._state_store.state,
                latest_test_status="none",
                test_status_consumed=False,
                source_edits_this_phase=0,
                rollback_required=False,
                rollback_done=True,
                phase_completed=phase_completed,
            ),
        )
        return result


class InvalidRollbackResultManager:
    def rollback_last(self, task_id: str) -> RollbackResult:
        return RollbackResult(
            status=OperationStatus.SUCCEEDED,
            checkpoint_id=None,
            restored_files=(),
            failed_files=(),
            error=None,
        )


class InconsistentFailingRollbackManager:
    def __init__(self, state_store: MemoryStateStore) -> None:
        self._state_store = state_store

    def rollback_last(self, task_id: str) -> RollbackResult:
        self._state_store.save(
            task_id,
            replace(self._state_store.state, status=TaskStatus.INCONSISTENT, inconsistent=True),
        )
        return RollbackResult(
            status=OperationStatus.FAILED,
            checkpoint_id="ckpt-001",
            restored_files=(),
            failed_files=("src/main.py",),
            error=StructuredError(
                error_code="rollback_compensation_failed",
                message="Rollback compensation failed.",
                phase=Phase.REVIEW.value,
                denied_rule="rollback_compensation_required",
                suggested_fix="Reconcile source and state before retrying.",
            ),
        )


class FailingRollbackFeedback(RecordingFeedback):
    def from_rollback_result(self, result: RollbackResult, *, phase: Phase) -> object:
        raise HanCodeError(
            StructuredError(
                error_code="rollback_feedback_failed",
                message="Rollback feedback could not be constructed.",
                phase=phase.value,
                denied_rule="rollback_feedback_required",
                suggested_fix="Repair the rollback feedback builder.",
            )
        )


class RecordingContextBuilder:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def build(self, *, task_id: str, phase: Phase, state: TaskState) -> dict[str, object]:
        context: dict[str, object] = {"task_id": task_id, "phase": phase.value}
        self.calls.append(context)
        return context


def test_source_write_checkpoint_orders_create_dispatch_then_commit() -> None:
    events: list[str] = []
    checkpoints = RecordingCheckpointManager(events)
    loop = _loop(
        llm=MockLLM([_retry_write_action()]),
        state_store=MemoryStateStore(_retry_code_state()),
        context_builder=RecordingContextBuilder(),
        feedback=RecordingFeedback(),
        policy=AllowedPolicy(requires_checkpoint=True),
        tools=ScriptedTools(events=events),
        checkpoint_manager=checkpoints,
        max_steps=1,
    )

    loop.run("task-001")

    assert events == ["create", "dispatch", "commit"]
    assert checkpoints.files == [Path("src/main.py")]
    assert checkpoints.reason == "Fix the failed assertion."


def test_checkpointed_write_preserves_checkpoint_metadata_persisted_by_manager() -> None:
    events: list[str] = []
    state_store = MemoryStateStore(_retry_code_state())
    loop = _loop(
        llm=MockLLM([_retry_write_action()]),
        state_store=state_store,
        context_builder=RecordingContextBuilder(),
        feedback=RecordingFeedback(),
        policy=AllowedPolicy(requires_checkpoint=True),
        tools=ScriptedTools(events=events),
        checkpoint_manager=StatePersistingCheckpointManager(events, state_store),
        max_steps=1,
    )

    result = loop.run("task-001")

    assert result.final_state.latest_checkpoint == "ckpt-001"
    assert result.final_state.checkpoint_seq == 1
    assert state_store.state.latest_checkpoint == "ckpt-001"
    assert state_store.state.checkpoint_seq == 1


def test_checkpoint_create_failure_marks_state_inconsistent_before_source_dispatch() -> None:
    events: list[str] = []
    tools = ScriptedTools(events=events)
    checkpoints = RecordingCheckpointManager(
        events,
        create_error=HanCodeError(
            StructuredError(
                error_code="checkpoint_snapshot_failed",
                message="Checkpoint could not be created.",
                phase=Phase.CODE.value,
                denied_rule="checkpoint_persistence_required",
                suggested_fix="Restore checkpoint storage.",
            )
        ),
    )
    loop = _loop(
        llm=MockLLM([_retry_write_action()]),
        state_store=MemoryStateStore(_retry_code_state()),
        context_builder=RecordingContextBuilder(),
        feedback=RecordingFeedback(),
        policy=AllowedPolicy(requires_checkpoint=True),
        tools=tools,
        checkpoint_manager=checkpoints,
        max_steps=1,
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.INCONSISTENT
    assert result.error is not None
    assert result.error.error_code == "checkpoint_snapshot_failed"
    assert result.final_state.inconsistent is True
    assert events == ["create"]
    assert tools.actions == []


def test_invalid_checkpoint_manifest_blocks_before_source_write_dispatch() -> None:
    events: list[str] = []
    tools = ScriptedTools(events=events)
    loop = _loop(
        llm=MockLLM([_retry_write_action()]),
        state_store=MemoryStateStore(_retry_code_state()),
        context_builder=RecordingContextBuilder(),
        feedback=RecordingFeedback(),
        tools=tools,
        checkpoint_manager=InvalidCheckpointManager(events),
        max_steps=1,
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.BLOCKED
    assert result.error is not None
    assert result.error.error_code == "checkpoint_manifest_invalid"
    assert events == ["create"]
    assert tools.actions == []


def test_malformed_checkpoint_id_returns_structured_inconsistent_result() -> None:
    events: list[str] = []
    state_store = MemoryStateStore(_retry_code_state())
    loop = _loop(
        llm=MockLLM([_retry_write_action()]),
        state_store=state_store,
        context_builder=RecordingContextBuilder(),
        feedback=RecordingFeedback(),
        tools=ScriptedTools(events=events),
        checkpoint_manager=MalformedCheckpointIdManager(events),
        max_steps=1,
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.INCONSISTENT
    assert result.error is not None
    assert result.error.error_code == "checkpoint_manifest_invalid"
    assert result.final_state.inconsistent is True
    assert events == ["create"]


def test_inconsistent_state_after_checkpoint_blocks_before_source_dispatch() -> None:
    events: list[str] = []
    tools = ScriptedTools(events=events)
    state_store = MemoryStateStore(_retry_code_state())
    loop = _loop(
        llm=MockLLM([_retry_write_action()]),
        state_store=state_store,
        context_builder=RecordingContextBuilder(),
        feedback=RecordingFeedback(),
        tools=tools,
        checkpoint_manager=InconsistentCheckpointStateManager(events, state_store),
        max_steps=1,
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.BLOCKED
    assert result.error is not None
    assert result.error.error_code == "checkpoint_state_invalid"
    assert events == ["create"]
    assert tools.actions == []


def test_invalid_commit_manifest_marks_state_inconsistent() -> None:
    events: list[str] = []
    state_store = MemoryStateStore(_retry_code_state())
    loop = _loop(
        llm=MockLLM([_retry_write_action()]),
        state_store=state_store,
        context_builder=RecordingContextBuilder(),
        feedback=RecordingFeedback(),
        tools=ScriptedTools(events=events),
        checkpoint_manager=InvalidCommitCheckpointManager(events),
        max_steps=1,
    )

    result = loop.run("task-001")

    assert events == ["create", "dispatch", "commit"]
    assert result.status is TaskStatus.INCONSISTENT
    assert result.error is not None
    assert result.error.error_code == "checkpoint_manifest_invalid"
    assert result.final_state.inconsistent is True


def test_tool_dispatch_failure_after_checkpoint_returns_inconsistent_result() -> None:
    events: list[str] = []
    state_store = MemoryStateStore(_retry_code_state())
    loop = _loop(
        llm=MockLLM([_retry_write_action()]),
        state_store=state_store,
        context_builder=RecordingContextBuilder(),
        feedback=RecordingFeedback(),
        tools=RaisingTools(events=events),
        checkpoint_manager=RecordingCheckpointManager(events),
        max_steps=1,
    )

    result = loop.run("task-001")

    assert events == ["create"]
    assert result.status is TaskStatus.INCONSISTENT
    assert result.error is not None
    assert result.error.error_code == "tool_dispatch_failed"
    assert result.final_state.inconsistent is True


def test_checkpointed_source_write_failure_marks_state_inconsistent_and_stops() -> None:
    events: list[str] = []
    state_store = MemoryStateStore(_retry_code_state())
    loop = _loop(
        llm=MockLLM([_retry_write_action()]),
        state_store=state_store,
        context_builder=RecordingContextBuilder(),
        feedback=RecordingFeedback(),
        policy=AllowedPolicy(requires_checkpoint=True),
        tools=ScriptedTools(events=events, write_success=False),
        checkpoint_manager=RecordingCheckpointManager(events),
        max_steps=1,
    )

    result = loop.run("task-001")

    assert events == ["create", "dispatch"]
    assert result.status is TaskStatus.INCONSISTENT
    assert result.error is not None
    assert result.error.error_code == "checkpointed_write_failed"
    assert result.final_state.inconsistent is True
    assert state_store.state.status is TaskStatus.INCONSISTENT
    assert result.risks[0].level == "high"


def test_checkpoint_commit_failure_marks_state_inconsistent_and_stops() -> None:
    events: list[str] = []
    state_store = MemoryStateStore(_retry_code_state())
    loop = _loop(
        llm=MockLLM([_retry_write_action()]),
        state_store=state_store,
        context_builder=RecordingContextBuilder(),
        feedback=RecordingFeedback(),
        policy=AllowedPolicy(requires_checkpoint=True),
        tools=ScriptedTools(events=events),
        checkpoint_manager=RecordingCheckpointManager(
            events,
            commit_error=HanCodeError(
                StructuredError(
                    error_code="checkpoint_commit_failed",
                    message="Checkpoint could not be committed.",
                    phase=Phase.CODE.value,
                    denied_rule="checkpoint_commit_required",
                    suggested_fix="Reconcile the source file.",
                )
            ),
        ),
        max_steps=1,
    )

    result = loop.run("task-001")

    assert events == ["create", "dispatch", "commit"]
    assert result.status is TaskStatus.INCONSISTENT
    assert result.error is not None
    assert result.error.error_code == "checkpoint_commit_failed"
    assert result.final_state.inconsistent is True
    assert state_store.state.status is TaskStatus.INCONSISTENT
    assert result.risks[0].level == "high"


def test_failed_test_retries_through_review_then_decrements_once_on_retry_write() -> None:
    state_store = MemoryStateStore(_state())
    context_builder = RecordingContextBuilder()
    trace_appender = RecordingTraceAppender()
    llm = MockLLM(
        [
            _run_tests_action(),
            _finish_review_action(),
            _retry_write_action(),
            _retry_write_action(),
        ]
    )
    loop = _loop(
        llm=llm,
        state_store=state_store,
        context_builder=context_builder,
        feedback=RecordingFeedback(),
        policy=AllowedPolicy(requires_checkpoint=True),
        checkpoint_manager=RecordingCheckpointManager([]),
        trace_appender=trace_appender,
        max_steps=4,
    )

    result = loop.run("task-001")

    failed_test_state = next(
        saved
        for saved in state_store.saves
        if saved.latest_test_status == "failed" and not saved.test_status_consumed
    )
    review_state = next(
        saved
        for saved in state_store.saves
        if saved.phase_completed[Phase.REVIEW.value]
    )

    assert failed_test_state.phase_completed[Phase.TEST.value] is False
    assert failed_test_state.tests_run == ("run_tests",)
    assert failed_test_state.retry_budget_remaining == 2
    assert review_state.test_status_consumed is True
    assert review_state.phase_completed[Phase.CODE.value] is False
    assert llm.contexts[2]["phase"] == Phase.CODE.value
    assert llm.contexts[2]["observation"] == {
        "kind": "test_failure",
        "phase": Phase.TEST.value,
        "result": ToolResult(
            success=False,
            action_name="run_tests",
            exit_code=1,
            stderr="E   AssertionError: expected retry\n1 failed",
        ),
    }
    assert result.retry_budget_remaining == 1
    assert result.final_state.source_edits_this_phase == 2
    assert result.status is not TaskStatus.COMPLETED
    assert [event.event_type for event in trace_appender.events] == [
        "phase_started",
        "tool_called",
        "tool_failed",
        "test_failed",
        "phase_started",
        "phase_completed",
        "phase_started",
        "tool_called",
        "source_write_authorized",
        "tool_completed",
        "retry_budget_consumed",
        "tool_called",
        "source_write_authorized",
        "tool_completed",
    ]
    assert result.trace_events == tuple(trace_appender.events)


def test_mutation_guard_is_released_between_two_source_writes() -> None:
    guard = AllowMutationGuard()
    loop = _loop(
        llm=MockLLM([_retry_write_action(), _retry_write_action()]),
        state_store=MemoryStateStore(_retry_code_state()),
        context_builder=RecordingContextBuilder(),
        feedback=RecordingFeedback(),
        policy=AllowedPolicy(requires_checkpoint=True),
        tools=ScriptedTools(),
        checkpoint_manager=RecordingCheckpointManager([]),
        mutation_guard=guard,
        max_steps=2,
    )

    loop.run("task-001")

    assert guard.acquisitions == 1
    assert guard.active == 0


def test_artifact_write_does_not_use_source_checkpoint_or_edit_budget() -> None:
    phase_completed = {phase.value: False for phase in Phase}
    state = replace(
        _state(),
        current_phase=Phase.SPEC,
        phase_completed={**phase_completed, Phase.CODE.value: True},
        artifacts={**_state().artifacts, "SPEC.md": False},
    )
    loop = _loop(
        llm=MockLLM([_artifact_write_action()]),
        state_store=MemoryStateStore(state),
        context_builder=RecordingContextBuilder(),
        feedback=RecordingFeedback(),
        tools=ScriptedTools(),
        max_steps=1,
    )

    result = loop.run("task-001")

    assert result.tool_calls == ("write_file",)
    assert result.final_state.files_changed == ()
    assert result.final_state.source_edits_this_phase == 0
    assert result.final_state.artifacts["SPEC.md"] is True


def test_checkpoint_pointer_mismatch_is_persisted_as_inconsistent() -> None:
    events: list[str] = []
    state_store = MemoryStateStore(_retry_code_state())
    loop = _loop(
        llm=MockLLM([_retry_write_action()]),
        state_store=state_store,
        context_builder=RecordingContextBuilder(),
        feedback=RecordingFeedback(),
        tools=ScriptedTools(events=events),
        checkpoint_manager=cast(CheckpointManager, NoPersistCheckpointManager()),
        max_steps=1,
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.INCONSISTENT
    assert result.error is not None
    assert result.error.error_code == "checkpoint_state_invalid"
    assert state_store.state.inconsistent is True
    assert state_store.state.status is TaskStatus.INCONSISTENT
    assert events == []


def test_checkpoint_state_reload_failure_persists_recovery_pointer() -> None:
    events: list[str] = []
    state_store = ReloadFailureAfterCheckpointStore(_retry_code_state())
    loop = _loop(
        llm=MockLLM([_retry_write_action()]),
        state_store=state_store,
        context_builder=RecordingContextBuilder(),
        feedback=RecordingFeedback(),
        tools=ScriptedTools(events=events),
        checkpoint_manager=RecordingCheckpointManager(events),
        max_steps=1,
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.INCONSISTENT
    assert result.error is not None
    assert result.error.error_code == "checkpoint_state_reload_failed"
    assert state_store.state.latest_checkpoint == "ckpt-001"
    assert state_store.state.inconsistent is True
    assert events == ["create"]


def test_tampered_commit_manifest_is_rejected() -> None:
    events: list[str] = []
    state_store = MemoryStateStore(_retry_code_state())
    loop = _loop(
        llm=MockLLM([_retry_write_action()]),
        state_store=state_store,
        context_builder=RecordingContextBuilder(),
        feedback=RecordingFeedback(),
        tools=ScriptedTools(events=events),
        checkpoint_manager=TamperedCommitCheckpointManager(events),
        max_steps=1,
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.INCONSISTENT
    assert result.error is not None
    assert result.error.error_code == "checkpoint_manifest_invalid"
    assert state_store.state.inconsistent is True


def test_malformed_tool_result_is_fail_closed() -> None:
    state_store = MemoryStateStore(_state())
    loop = _loop(
        llm=MockLLM([_run_tests_action()]),
        state_store=state_store,
        context_builder=RecordingContextBuilder(),
        feedback=RecordingFeedback(),
        tools=InvalidToolResultTools(),
        max_steps=1,
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.INCONSISTENT
    assert result.error is not None
    assert result.error.error_code == "tool_result_invalid"
    assert state_store.state.inconsistent is True


def test_failed_test_trace_uses_previous_test_status_in_state_transition() -> None:
    state = replace(_state(), latest_test_status="passed")
    trace_appender = RecordingTraceAppender()
    loop = _loop(
        llm=MockLLM([_run_tests_action()]),
        state_store=MemoryStateStore(state),
        context_builder=RecordingContextBuilder(),
        feedback=RecordingFeedback(),
        trace_appender=trace_appender,
        max_steps=1,
    )

    loop.run("task-001")

    test_failed = next(event for event in trace_appender.events if event.event_type == "test_failed")
    assert test_failed.state_transition == {"latest_test_status": ["passed", "failed"]}


def test_source_write_without_policy_requirement_still_uses_checkpoint_and_consumes_retry_budget() -> None:
    events: list[str] = []
    state = _retry_code_state()
    loop = _loop(
        llm=MockLLM([_retry_write_action()]),
        state_store=MemoryStateStore(state),
        context_builder=RecordingContextBuilder(),
        feedback=RecordingFeedback(),
        policy=AllowedPolicy(requires_checkpoint=False),
        tools=ScriptedTools(events=events),
        checkpoint_manager=RecordingCheckpointManager(events),
        max_steps=1,
    )

    result = loop.run("task-001")

    assert events == ["create", "dispatch", "commit"]
    assert result.retry_budget_remaining == 1
    assert result.final_state.source_edits_this_phase == 1
    assert result.final_state.files_changed == ("src/main.py",)


def test_trace_failure_blocks_source_write_before_checkpoint_or_dispatch() -> None:
    events: list[str] = []
    tools = ScriptedTools(events=events)
    loop = _loop(
        llm=MockLLM([_retry_write_action()]),
        state_store=MemoryStateStore(_retry_code_state()),
        context_builder=RecordingContextBuilder(),
        feedback=RecordingFeedback(),
        tools=tools,
        checkpoint_manager=RecordingCheckpointManager(events),
        trace_appender=FailingTraceAppender(),
        max_steps=1,
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.BLOCKED
    assert result.error is not None
    assert result.error.error_code == "trace_write_error"
    assert events == []
    assert tools.actions == []


def test_state_persistence_failure_after_source_write_returns_inconsistent_result() -> None:
    events: list[str] = []
    state_store = FailingSaveAfterFirstSaveStore(_retry_code_state())
    loop = _loop(
        llm=MockLLM([_retry_write_action()]),
        state_store=state_store,
        context_builder=RecordingContextBuilder(),
        feedback=RecordingFeedback(),
        tools=ScriptedTools(events=events),
        checkpoint_manager=RecordingCheckpointManager(events),
        max_steps=1,
    )

    result = loop.run("task-001")

    assert events == ["create", "dispatch", "commit"]
    assert result.status is TaskStatus.INCONSISTENT
    assert result.error is not None
    assert result.error.error_code == "state_write_error"
    assert result.final_state.inconsistent is True
    assert result.final_state.rollback_required is True
    assert state_store.state.status is TaskStatus.INCONSISTENT


def test_persistent_state_failure_is_not_swallowed_when_marking_inconsistent() -> None:
    events: list[str] = []
    state_store = PersistentFailureAfterCheckpointStore(_retry_code_state())
    loop = _loop(
        llm=MockLLM([_retry_write_action()]),
        state_store=state_store,
        context_builder=RecordingContextBuilder(),
        feedback=RecordingFeedback(),
        tools=ScriptedTools(events=events),
        checkpoint_manager=RecordingCheckpointManager(events),
        max_steps=1,
    )

    result = loop.run("task-001")

    assert events == ["create", "dispatch", "commit"]
    assert result.status is TaskStatus.INCONSISTENT
    assert result.error is not None
    assert result.error.error_code == "state_persistence_failed"
    assert result.final_state.inconsistent is True


def test_retry_budget_exhaustion_forces_rollback_and_returns_feedback_observation() -> None:
    tools = ScriptedTools()
    rollback_manager = RecordingRollbackManager()
    trace_appender = RecordingTraceAppender()
    loop = _loop(
        llm=MockLLM([]),
        state_store=MemoryStateStore(_retry_budget_exhausted_state()),
        context_builder=RecordingContextBuilder(),
        feedback=RecordingFeedback(),
        tools=tools,
        rollback_manager=rollback_manager,
        trace_appender=trace_appender,
        max_steps=1,
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.RUNNING
    assert result.final_state.current_phase is Phase.REVIEW
    assert result.final_state.rollback_required is False
    assert result.final_state.rollback_done is True
    assert result.final_observation == {"kind": "rollback"}
    assert tools.actions == []
    assert rollback_manager.calls == ["task-001"]
    assert [event.event_type for event in trace_appender.events] == [
        "rollback_started",
        "rollback_performed",
    ]
    assert result.trace_events == tuple(trace_appender.events)


def test_rollback_preserves_state_persisted_by_rollback_manager() -> None:
    state_store = MemoryStateStore(_retry_budget_exhausted_state())
    rollback_manager = StatePersistingRollbackManager(state_store)
    loop = _loop(
        llm=MockLLM([]),
        state_store=state_store,
        context_builder=RecordingContextBuilder(),
        feedback=RecordingFeedback(),
        rollback_manager=rollback_manager,
        max_steps=1,
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.RUNNING
    assert result.final_state.latest_test_status == "none"
    assert result.final_state.test_status_consumed is False
    assert result.final_state.source_edits_this_phase == 0
    assert result.final_state.rollback_required is False
    assert result.final_state.rollback_done is True
    assert result.final_state.phase_completed[Phase.CODE.value] is False
    assert result.final_state.phase_completed[Phase.TEST.value] is False
    assert result.final_state.phase_completed[Phase.REVIEW.value] is False


def test_explicit_rollback_action_is_dispatched_once_and_returns_observation() -> None:
    state_store = MemoryStateStore(
        replace(_review_state(), latest_checkpoint="ckpt-001", checkpoint_seq=1)
    )
    rollback_manager = RecordingRollbackManager()
    guard = AllowMutationGuard()
    loop = _loop(
        llm=MockLLM([_rollback_action()]),
        state_store=state_store,
        context_builder=RecordingContextBuilder(),
        feedback=RecordingFeedback(),
        rollback_manager=rollback_manager,
        mutation_guard=guard,
        max_steps=1,
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.RUNNING
    assert result.tool_calls == ("rollback_last_checkpoint",)
    assert result.final_observation == {"kind": "rollback"}
    assert rollback_manager.calls == ["task-001"]
    assert guard.acquisitions == 1
    assert guard.active == 0


def test_invalid_rollback_result_is_fail_closed() -> None:
    state_store = MemoryStateStore(_retry_budget_exhausted_state())
    loop = _loop(
        llm=MockLLM([]),
        state_store=state_store,
        context_builder=RecordingContextBuilder(),
        feedback=RecordingFeedback(),
        rollback_manager=cast(
            RecordingRollbackManager, InvalidRollbackResultManager()
        ),
        max_steps=1,
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.INCONSISTENT
    assert result.error is not None
    assert result.error.error_code == "rollback_result_invalid"
    assert state_store.state.inconsistent is True


def test_rollback_compensation_inconsistency_is_not_overwritten() -> None:
    state_store = MemoryStateStore(_retry_budget_exhausted_state())
    loop = _loop(
        llm=MockLLM([]),
        state_store=state_store,
        context_builder=RecordingContextBuilder(),
        feedback=RecordingFeedback(),
        rollback_manager=cast(
            RecordingRollbackManager, InconsistentFailingRollbackManager(state_store)
        ),
        max_steps=1,
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.INCONSISTENT
    assert result.final_state.inconsistent is True
    assert state_store.state.inconsistent is True


def test_rollback_feedback_failure_preserves_persisted_success_flags() -> None:
    state_store = MemoryStateStore(_retry_budget_exhausted_state())
    loop = _loop(
        llm=MockLLM([]),
        state_store=state_store,
        context_builder=RecordingContextBuilder(),
        feedback=FailingRollbackFeedback(),
        rollback_manager=StatePersistingRollbackManager(state_store),
        max_steps=1,
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.INCONSISTENT
    assert result.error is not None
    assert result.error.error_code == "rollback_feedback_failed"
    assert result.final_state.inconsistent is True
    assert result.final_state.rollback_done is True
    assert result.final_state.rollback_required is False


def test_budget_exhaustion_on_last_step_still_forces_rollback() -> None:
    state_store = MemoryStateStore(
        replace(
            _retry_code_state(),
            latest_checkpoint="ckpt-001",
            checkpoint_seq=1,
            retry_budget_remaining=1,
        )
    )
    rollback_manager = RecordingRollbackManager()
    loop = _loop(
        llm=MockLLM([_retry_write_action(), _finish_code_action(), _run_tests_action()]),
        state_store=state_store,
        context_builder=RecordingContextBuilder(),
        feedback=RecordingFeedback(),
        policy=AllowedPolicy(requires_checkpoint=True),
        checkpoint_manager=RecordingCheckpointManager([]),
        rollback_manager=rollback_manager,
        max_steps=3,
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.RUNNING
    assert rollback_manager.calls == ["task-001"]
    assert result.final_state.current_phase is Phase.REVIEW


def test_rollback_state_save_failure_returns_structured_inconsistent_result() -> None:
    state_store = FailingRollbackStateStore(_retry_budget_exhausted_state())
    loop = _loop(
        llm=MockLLM([]),
        state_store=state_store,
        context_builder=RecordingContextBuilder(),
        feedback=RecordingFeedback(),
        rollback_manager=FailingRollbackManager(),
        max_steps=1,
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.INCONSISTENT
    assert result.error is not None
    assert result.error.error_code == "state_write_error"
    assert result.final_state.inconsistent is True


def test_rollback_exception_records_rollback_failed_trace_event() -> None:
    trace_appender = RecordingTraceAppender()
    loop = _loop(
        llm=MockLLM([]),
        state_store=MemoryStateStore(_retry_budget_exhausted_state()),
        context_builder=RecordingContextBuilder(),
        feedback=RecordingFeedback(),
        rollback_manager=RaisingRollbackManager(),
        trace_appender=trace_appender,
        max_steps=1,
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.BLOCKED
    assert result.error is not None
    assert result.error.error_code == "rollback_storage_failed"
    assert [event.event_type for event in trace_appender.events] == [
        "rollback_started",
        "rollback_performed",
    ]


def test_resume_after_rollback_failure_retries_rollback_before_llm() -> None:
    state_store = MemoryStateStore(_retry_budget_exhausted_state())
    rollback_manager = RaisingRollbackManager()
    first_loop = _loop(
        llm=MockLLM([]),
        state_store=state_store,
        context_builder=RecordingContextBuilder(),
        feedback=RecordingFeedback(),
        rollback_manager=rollback_manager,
        max_steps=1,
    )

    first = first_loop.run("task-001")
    second_loop = _loop(
        llm=MockLLM([_finish_review_action()]),
        state_store=state_store,
        context_builder=RecordingContextBuilder(),
        feedback=RecordingFeedback(),
        rollback_manager=rollback_manager,
        max_steps=1,
    )

    second = second_loop.run("task-001", resume=True)

    assert first.status is TaskStatus.BLOCKED
    assert second.status is TaskStatus.BLOCKED
    assert second.final_state.rollback_required is True
    assert second.final_state.phase_completed[Phase.REVIEW.value] is False
    assert rollback_manager.calls == ["task-001", "task-001"]


def test_resume_can_recover_inconsistent_state_with_required_checkpoint_rollback() -> None:
    state_store = MemoryStateStore(
        replace(
            _retry_code_state(),
            status=TaskStatus.INCONSISTENT,
            inconsistent=True,
            latest_checkpoint="ckpt-001",
            checkpoint_seq=1,
            rollback_required=True,
        )
    )
    rollback_manager = RecordingRollbackManager()
    loop = _loop(
        llm=MockLLM([]),
        state_store=state_store,
        context_builder=RecordingContextBuilder(),
        feedback=RecordingFeedback(),
        rollback_manager=rollback_manager,
        max_steps=1,
    )

    result = loop.run("task-001", resume=True)

    assert result.status is TaskStatus.RUNNING
    assert result.error is None
    assert result.final_state.inconsistent is False
    assert result.final_state.rollback_required is False
    assert result.final_state.rollback_done is True
    assert rollback_manager.calls == ["task-001"]


def test_final_action_after_failed_test_cannot_bypass_router_completion() -> None:
    state_store = MemoryStateStore(_state())
    loop = _loop(
        llm=MockLLM([_run_tests_action(), _final_review_action()]),
        state_store=state_store,
        context_builder=RecordingContextBuilder(),
        feedback=RecordingFeedback(),
        max_steps=2,
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.BLOCKED
    assert result.error is not None
    assert result.error.error_code == "final_requires_router_completion"


def test_feedback_construction_failure_blocks_with_its_structured_error() -> None:
    loop = _loop(
        llm=MockLLM([_run_tests_action()]),
        state_store=MemoryStateStore(_state()),
        context_builder=RecordingContextBuilder(),
        feedback=FailingFeedback(),
        max_steps=1,
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.BLOCKED
    assert result.error is not None
    assert result.error.error_code == "feedback_input_invalid"
    assert result.error.denied_rule == "feedback_test_double"


def _loop(
    *,
    llm: MockLLM,
    state_store: MemoryStateStore | FailingSaveAfterFirstSaveStore | PersistentFailureAfterCheckpointStore | FailingRollbackStateStore | ReloadFailureAfterCheckpointStore,
    context_builder: RecordingContextBuilder,
    feedback: RecordingFeedback,
    policy: AllowedPolicy | None = None,
    tools: ScriptedTools | None = None,
    checkpoint_manager: (
        RecordingCheckpointManager
        | StatePersistingCheckpointManager
        | InvalidCheckpointManager
        | MalformedCheckpointIdManager
        | InconsistentCheckpointStateManager
        | InvalidCommitCheckpointManager
        | None
    ) = None,
    rollback_manager: (
        NoopRollbackManager
        | RecordingRollbackManager
        | StatePersistingRollbackManager
        | FailingRollbackManager
        | RaisingRollbackManager
        | None
    ) = None,
    trace_appender: NoopTraceAppender | RecordingTraceAppender | FailingTraceAppender | None = None,
    mutation_guard: AllowMutationGuard | None = None,
    max_steps: int,
) -> AgentLoop:
    if isinstance(checkpoint_manager, RecordingCheckpointManager):
        checkpoint_manager.bind_state_store(state_store)
    if isinstance(rollback_manager, RecordingRollbackManager):
        rollback_manager.bind_state_store(state_store)
    return AgentLoop(
        llm=llm,
        context_builder=context_builder,
        policy=cast(Policy, policy or AllowedPolicy()),
        tool_registry=tools or ScriptedTools(),
        feedback_builder=feedback,
        state_store=state_store,
        trace_appender=trace_appender or RecordingTraceAppender(),
        checkpoint_manager=cast(
            CheckpointManager,
            checkpoint_manager or NoopCheckpointManager(),
        ),
        rollback_manager=rollback_manager or NoopRollbackManager(),
        max_steps=max_steps,
        mutation_guard=mutation_guard or AllowMutationGuard(),
    )


def _state() -> TaskState:
    return TaskState(
        schema_version=1,
        task_id="task-001",
        goal="Retry a failed test.",
        status=TaskStatus.CREATED,
        current_phase=Phase.CODE,
        files_changed=(),
        latest_checkpoint=None,
        checkpoint_seq=0,
        tests_run=(),
        latest_test_status="none",
        test_status_consumed=False,
        retry_budget_remaining=2,
        inconsistent=False,
        source_edits_this_phase=0,
        rollback_required=False,
        rollback_done=False,
        phase_completed={
            Phase.SPEC.value: True,
            Phase.PLAN.value: True,
            Phase.CODE.value: True,
            Phase.TEST.value: False,
            Phase.REVIEW.value: False,
            Phase.DELIVER.value: False,
        },
        artifacts={
            "SPEC.md": True,
            "PLAN.md": True,
            "TEST_REPORT.md": False,
            "REVIEW.md": False,
            "KNOWLEDGE.md": False,
            "DELIVERABLES.md": False,
        },
    )


def _retry_code_state() -> TaskState:
    state = _state()
    phase_completed = dict(state.phase_completed)
    phase_completed[Phase.CODE.value] = False
    phase_completed[Phase.TEST.value] = False
    return replace(
        state,
        current_phase=Phase.CODE,
        latest_test_status="failed",
        test_status_consumed=True,
        phase_completed=phase_completed,
    )


def _review_state() -> TaskState:
    state = _state()
    phase_completed = dict(state.phase_completed)
    phase_completed[Phase.TEST.value] = True
    phase_completed[Phase.REVIEW.value] = False
    return replace(
        state,
        current_phase=Phase.REVIEW,
        latest_test_status="passed",
        phase_completed=phase_completed,
    )


def _retry_budget_exhausted_state() -> TaskState:
    state = _state()
    phase_completed = dict(state.phase_completed)
    phase_completed[Phase.TEST.value] = False
    return replace(
        state,
        current_phase=Phase.TEST,
        latest_checkpoint="ckpt-001",
        checkpoint_seq=1,
        latest_test_status="failed",
        retry_budget_remaining=0,
        phase_completed=phase_completed,
    )


def _run_tests_action() -> dict[str, object]:
    return {
        "type": "tool_call",
        "phase": Phase.TEST.value,
        "tool_name": "run_tests",
        "args": {},
        "reason": None,
    }


def _finish_review_action() -> dict[str, object]:
    return {
        "type": "finish_phase",
        "phase": Phase.REVIEW.value,
        "tool_name": None,
        "args": {},
        "reason": None,
    }


def _finish_code_action() -> dict[str, object]:
    return {
        "type": "finish_phase",
        "phase": Phase.CODE.value,
        "tool_name": None,
        "args": {},
        "reason": None,
    }


def _final_review_action() -> dict[str, object]:
    return {
        "type": "final",
        "phase": Phase.REVIEW.value,
        "tool_name": None,
        "args": {},
        "reason": None,
    }


def _retry_write_action() -> dict[str, object]:
    return {
        "type": "tool_call",
        "phase": Phase.CODE.value,
        "tool_name": "write_file",
        "args": {"path": "src/main.py", "content": "fixed\n"},
        "reason": "Fix the failed assertion.",
    }


def _artifact_write_action() -> dict[str, object]:
    return {
        "type": "tool_call",
        "phase": Phase.SPEC.value,
        "tool_name": "write_file",
        "args": {"path": "SPEC.md", "content": "# Spec\n"},
        "reason": "Record the task specification.",
    }


def _rollback_action() -> dict[str, object]:
    return {
        "type": "tool_call",
        "phase": Phase.REVIEW.value,
        "tool_name": "rollback_last_checkpoint",
        "args": {},
        "reason": None,
    }


def _checkpoint_manifest(
    task_id: str,
    *,
    status: Literal["pending", "committed", "rolled_back"] = "pending",
    rollback_available: bool = False,
) -> CheckpointManifest:
    return CheckpointManifest(
        schema_version=1,
        project_id="project-001",
        checkpoint_id="ckpt-001",
        task_id=task_id,
        phase=Phase.CODE,
        reason="Fix the failed assertion.",
        created_at=datetime.now(UTC),
        status=status,
        files=(
            CheckpointFile(
                path="src/main.py",
                action="modify",
                before_snapshot="files/001-main.before",
                before_sha256="b" * 64,
                after_sha256="a" * 64 if status == "committed" else None,
            ),
        ),
        rollback_available=rollback_available,
    )
