from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from tempfile import mkstemp
from typing import Literal, Mapping

from hancode.config import load_config
from hancode.errors import HanCodeError, StructuredError
from hancode.models import OperationStatus, Phase, TaskStatus
from hancode.path_policy import PathClassifier, PathZone
from hancode.state import TaskState, load_state, save_state
from hancode.trace import append_trace
from hancode.workspace import load_project_metadata


_MANIFEST_SCHEMA_VERSION = 1
_PENDING: Literal["pending"] = "pending"
_COMMITTED: Literal["committed"] = "committed"
_ROLLED_BACK: Literal["rolled_back"] = "rolled_back"
_ABORTED: Literal["aborted"] = "aborted"
_SENSITIVE_REASON_PATTERN = re.compile(
    r"(authorization|api[_-]?key|token|secret|password|private[_-]?key|credential|"
    r"cookie|aws[_-]?access[_-]?key[_-]?id|aws[_-]?secret[_-]?access[_-]?key)"
    r"\s*[:=]\s*(?:bearer\s+)?[^\s,;]+",
    re.IGNORECASE,
)
_BEARER_TOKEN_PATTERN = re.compile(r"\bbearer\s+[^\s,;]+", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class CheckpointFile:
    path: str
    action: Literal["create", "modify"]
    before_snapshot: str | None
    before_sha256: str | None
    after_sha256: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "action": self.action,
            "before_snapshot": self.before_snapshot,
            "before_sha256": self.before_sha256,
            "after_sha256": self.after_sha256,
        }


@dataclass(frozen=True, slots=True)
class CheckpointManifest:
    schema_version: int
    project_id: str
    checkpoint_id: str
    task_id: str
    phase: Phase
    reason: str
    created_at: datetime
    status: Literal["pending", "committed", "rolled_back", "aborted"]
    files: tuple[CheckpointFile, ...]
    rollback_available: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "task_id": self.task_id,
            "phase": self.phase.value,
            "checkpoint_id": self.checkpoint_id,
            "reason": self.reason,
            "created_at": self.created_at.isoformat(),
            "status": self.status,
            "files": [file.to_dict() for file in self.files],
            "rollback_available": self.rollback_available,
        }


@dataclass(frozen=True, slots=True)
class RollbackResult:
    status: OperationStatus
    checkpoint_id: str | None
    restored_files: tuple[str, ...]
    failed_files: tuple[str, ...]
    error: StructuredError | None

    @property
    def error_summary(self) -> str | None:
        return None if self.error is None else self.error.message

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "checkpoint_id": self.checkpoint_id,
            "restored_files": list(self.restored_files),
            "failed_files": list(self.failed_files),
            "error": None if self.error is None else self.error.to_dict(),
            "error_summary": self.error_summary,
        }


@dataclass(frozen=True, slots=True)
class _RollbackTarget:
    file: CheckpointFile
    target: Path
    before_content: bytes | None
    current_content: bytes


@dataclass(frozen=True, slots=True)
class _PendingRecoveryTarget:
    file: CheckpointFile
    target: Path
    before_content: bytes | None
    current_content: bytes | None


def create_checkpoint(
    task_root: Path,
    files: list[Path],
    reason: str,
    *,
    created_at: datetime | None = None,
) -> CheckpointManifest:
    state, project_root, project_metadata = _load_checkpoint_context(task_root)
    task_root = task_root.resolve()
    if state.current_phase is not Phase.CODE:
        raise _checkpoint_error(
            "checkpoint_requires_code_phase",
            "Checkpoint creation is only allowed during the code phase.",
            state.current_phase,
            "checkpoint_code_phase_required",
            "Create checkpoints only before a code-phase source write.",
        )
    if not files:
        raise _checkpoint_error(
            "checkpoint_files_required",
            "Checkpoint creation requires at least one source file.",
            state.current_phase,
            "checkpoint_files_required",
            "Provide the source files that will be modified.",
        )
    if not isinstance(reason, str) or not reason.strip():
        raise _checkpoint_error(
            "checkpoint_reason_required",
            "Checkpoint creation requires a reason.",
            state.current_phase,
            "checkpoint_reason_required",
            "Provide a non-empty reason before modifying source code.",
        )

    config = load_config(project_root, state.task_id)
    if state.checkpoint_seq >= config.max_checkpoints_per_task:
        raise _checkpoint_error(
            "checkpoint_limit_exceeded",
            "The task checkpoint limit has been reached.",
            state.current_phase,
            "max_checkpoints_per_task",
            "Review or rollback an existing checkpoint before creating another.",
        )
    classifier = PathClassifier(config)
    targets = _normalise_targets(files, project_root, classifier, state.current_phase)
    checkpoint_id = f"ckpt-{state.checkpoint_seq + 1:03d}"
    checkpoints_root = _checkpoints_root(task_root, state.current_phase)
    checkpoint_dir = _checkpoint_directory(
        checkpoints_root, checkpoint_id, state.current_phase
    )
    temporary_checkpoint_dir = _checkpoint_directory(
        checkpoints_root, f".{checkpoint_id}.tmp", state.current_phase
    )
    if checkpoint_dir.exists():
        raise _checkpoint_error(
            "checkpoint_snapshot_failed",
            "Checkpoint ID already exists.",
            state.current_phase,
            "checkpoint_id_must_be_unique",
            "Repair checkpoint state before creating another checkpoint.",
        )

    snapshots: list[tuple[str, bytes]] = []
    checkpoint_files: list[CheckpointFile] = []
    for index, (relative_path, target) in enumerate(targets, start=1):
        if target.exists() and target.is_dir():
            raise _checkpoint_error(
                "checkpoint_target_is_directory",
                "Checkpoint target must be a file, not a directory.",
                state.current_phase,
                "checkpoint_file_target_required",
                "Provide a source file path instead of a directory.",
            )
        if target.exists():
            try:
                content = target.read_bytes()
            except OSError as exc:
                raise _checkpoint_error(
                    "checkpoint_snapshot_failed",
                    "Checkpoint snapshot could not be created.",
                    state.current_phase,
                    "checkpoint_snapshot_required",
                    "Restore source file read access before continuing.",
                ) from exc
            snapshot_path = f"files/{index:03d}-{sha256(relative_path.encode()).hexdigest()[:12]}.before"
            snapshots.append((snapshot_path, content))
            checkpoint_files.append(
                CheckpointFile(
                    path=relative_path,
                    action="modify",
                    before_snapshot=snapshot_path,
                    before_sha256=sha256(content).hexdigest(),
                    after_sha256=None,
                )
            )
        else:
            checkpoint_files.append(
                CheckpointFile(
                    path=relative_path,
                    action="create",
                    before_snapshot=None,
                    before_sha256=None,
                    after_sha256=None,
                )
            )

    manifest = CheckpointManifest(
        schema_version=_MANIFEST_SCHEMA_VERSION,
        project_id=_required_project_id(project_metadata, state.current_phase),
        checkpoint_id=checkpoint_id,
        task_id=state.task_id,
        phase=state.current_phase,
        reason=_sanitize_reason(reason.strip()),
        created_at=datetime.now(UTC) if created_at is None else created_at,
        status=_PENDING,
        files=tuple(checkpoint_files),
        rollback_available=False,
    )
    try:
        if temporary_checkpoint_dir.exists():
            raise OSError("Checkpoint temporary directory already exists.")
        temporary_checkpoint_dir.mkdir(parents=True)
        (temporary_checkpoint_dir / "files").mkdir()
        for snapshot_path, content in snapshots:
            (temporary_checkpoint_dir / snapshot_path).parent.mkdir(parents=True, exist_ok=True)
            (temporary_checkpoint_dir / snapshot_path).write_bytes(content)
        _write_manifest(temporary_checkpoint_dir / "manifest.json", manifest, atomic=False)
        temporary_checkpoint_dir.replace(checkpoint_dir)
    except OSError as exc:
        if not _remove_checkpoint(temporary_checkpoint_dir):
            raise _checkpoint_compensation_error(state.current_phase) from exc
        raise _checkpoint_error(
            "checkpoint_snapshot_failed",
            "Checkpoint snapshot could not be persisted.",
            state.current_phase,
            "checkpoint_persistence_required",
            "Restore task workspace write access before continuing.",
        ) from exc

    try:
        save_state(
            task_root,
            replace(
                state,
                checkpoint_seq=state.checkpoint_seq + 1,
                latest_checkpoint=checkpoint_id,
            ),
        )
    except HanCodeError as exc:
        if not _remove_checkpoint(checkpoint_dir):
            raise _checkpoint_compensation_error(state.current_phase) from exc
        raise _checkpoint_error(
            "checkpoint_state_update_failed",
            "Checkpoint state could not be updated.",
            state.current_phase,
            "checkpoint_state_update_required",
            "Restore task state write access before continuing.",
        ) from exc
    try:
        append_trace(
            task_root,
            event_type="checkpoint_created",
            task_id=state.task_id,
            phase=state.current_phase,
            status="succeeded",
            observation={"checkpoint_id": checkpoint_id, "reason": manifest.reason},
            state_transition={"latest_checkpoint": [state.latest_checkpoint, checkpoint_id]},
            timestamp=manifest.created_at,
        )
    except HanCodeError as exc:
        try:
            save_state(task_root, state)
            if not _remove_checkpoint(checkpoint_dir):
                raise OSError("Checkpoint directory could not be removed.")
        except HanCodeError as compensation_error:
            raise _checkpoint_compensation_error(state.current_phase) from compensation_error
        except OSError as compensation_error:
            raise _checkpoint_compensation_error(state.current_phase) from compensation_error
        raise _checkpoint_error(
            "checkpoint_trace_failed",
            "Checkpoint trace event could not be persisted.",
            state.current_phase,
            "checkpoint_trace_required",
            "Restore trace write access before continuing with source changes.",
        ) from exc
    return manifest


def commit_checkpoint(task_root: Path, checkpoint_id: str) -> CheckpointManifest:
    state, project_root, project_metadata = _load_checkpoint_context(task_root)
    task_root = task_root.resolve()
    if not _is_checkpoint_id(checkpoint_id):
        raise _checkpoint_not_found_error(state.current_phase)
    checkpoint_dir = _checkpoint_directory(
        _checkpoints_root(task_root, state.current_phase), checkpoint_id, state.current_phase
    )
    manifest_path = checkpoint_dir / "manifest.json"
    if not manifest_path.is_file():
        raise _checkpoint_not_found_error(state.current_phase)
    _validate_manifest_path(checkpoint_dir, manifest_path, state.current_phase)
    manifest = _load_manifest(manifest_path, state.current_phase)
    _validate_manifest_identity(
        manifest,
        checkpoint_id,
        state,
        _required_project_id(project_metadata, state.current_phase),
    )
    config = load_config(project_root, state.task_id)
    classifier = PathClassifier(config)
    _validate_before_snapshots(manifest_path.parent, manifest.files, state.current_phase)
    if manifest.status != _PENDING:
        raise _checkpoint_error(
            "checkpoint_not_pending",
            "Checkpoint is not pending.",
            state.current_phase,
            "pending_checkpoint_required",
            "Commit each checkpoint only once after its source write.",
        )
    committed_files: list[CheckpointFile] = []
    for file in manifest.files:
        relative_path, target = _normalise_targets(
            [Path(file.path)], project_root, classifier, state.current_phase
        )[0]
        if relative_path != file.path:
            raise _checkpoint_error(
                "checkpoint_manifest_invalid",
                "Checkpoint manifest path is not normalized.",
                state.current_phase,
                "normalized_checkpoint_path_required",
                "Repair manifest.json with project-relative source paths.",
            )
        if not target.is_file():
            raise _checkpoint_error(
                "checkpoint_target_missing",
                "Checkpoint target is missing after the source write.",
                state.current_phase,
                "checkpoint_target_must_exist_for_commit",
                "Restore or create every checkpoint target before committing.",
            )
        try:
            after_sha256 = sha256(target.read_bytes()).hexdigest()
        except OSError as exc:
            raise _checkpoint_error(
                "checkpoint_commit_failed",
                "Checkpoint after hash could not be recorded.",
                state.current_phase,
                "checkpoint_after_hash_required",
                "Restore source file read access before committing.",
            ) from exc
        committed_files.append(replace(file, after_sha256=after_sha256))

    committed = replace(
        manifest,
        status=_COMMITTED,
        files=tuple(committed_files),
        rollback_available=True,
    )
    try:
        _write_manifest(manifest_path, committed, atomic=True)
    except OSError as exc:
        raise _checkpoint_error(
            "checkpoint_commit_failed",
            "Checkpoint manifest could not be committed.",
            state.current_phase,
            "checkpoint_manifest_commit_required",
            "Restore task workspace write access before committing.",
        ) from exc
    try:
        append_trace(
            task_root,
            event_type="checkpoint_committed",
            task_id=state.task_id,
            phase=manifest.phase,
            status="succeeded",
            observation={"checkpoint_id": checkpoint_id},
            state_transition={"checkpoint_status": [_PENDING, _COMMITTED]},
        )
    except HanCodeError as exc:
        try:
            _write_manifest(manifest_path, manifest, atomic=True)
        except OSError as compensation_error:
            raise _checkpoint_error(
                "checkpoint_compensation_failed",
                "Checkpoint trace failed and manifest could not be restored.",
                state.current_phase,
                "checkpoint_compensation_required",
                "Repair manifest.json before continuing.",
            ) from compensation_error
        raise _checkpoint_error(
            "checkpoint_trace_failed",
            "Checkpoint trace event could not be persisted.",
            state.current_phase,
            "checkpoint_trace_required",
            "Restore trace write access before continuing with source changes.",
        ) from exc
    return committed


def reconcile_pending_checkpoint(
    task_root: Path, state: TaskState, *, recover: bool
) -> TaskState:
    persisted_state, project_root, project_metadata = _load_checkpoint_context(task_root)
    if not isinstance(state, TaskState) or state.task_id != persisted_state.task_id:
        raise _checkpoint_manifest_error(persisted_state.current_phase)
    if persisted_state.latest_checkpoint is None:
        return persisted_state
    if not _is_checkpoint_id(persisted_state.latest_checkpoint):
        raise _checkpoint_manifest_error(persisted_state.current_phase)

    task_root = task_root.resolve()
    checkpoint_id = persisted_state.latest_checkpoint
    checkpoint_dir = _checkpoint_directory(
        _checkpoints_root(task_root, persisted_state.current_phase),
        checkpoint_id,
        persisted_state.current_phase,
    )
    manifest_path = checkpoint_dir / "manifest.json"
    try:
        if not manifest_path.is_file():
            raise _checkpoint_not_found_error(persisted_state.current_phase)
        _validate_manifest_path(checkpoint_dir, manifest_path, persisted_state.current_phase)
        manifest = _load_manifest(manifest_path, persisted_state.current_phase)
        _validate_manifest_identity(
            manifest,
            checkpoint_id,
            persisted_state,
            _required_project_id(project_metadata, persisted_state.current_phase),
        )
    except HanCodeError as exc:
        _record_pending_recovery_failure(
            task_root,
            persisted_state,
            checkpoint_id,
            persisted_state.current_phase,
            exc.structured_error,
        )
        raise
    if manifest.status != _PENDING:
        return persisted_state

    config = load_config(project_root, persisted_state.task_id)
    classifier = PathClassifier(config)
    try:
        _validate_before_snapshots(checkpoint_dir, manifest.files, persisted_state.current_phase)
        recovery_targets = _pending_recovery_targets(
            manifest,
            checkpoint_dir,
            project_root,
            classifier,
            persisted_state.current_phase,
        )
    except HanCodeError as exc:
        _record_pending_recovery_failure(
            task_root,
            persisted_state,
            checkpoint_id,
            manifest.phase,
            exc.structured_error,
        )
        raise
    has_source_change = any(
        target.current_content is None
        if target.file.action == "modify"
        else target.current_content is not None
        or target.target.is_dir()
        for target in recovery_targets
    ) or any(
        target.file.action == "modify"
        and target.current_content is not None
        and sha256(target.current_content).hexdigest() != target.file.before_sha256
        for target in recovery_targets
    )
    if has_source_change and not recover:
        inconsistent_state = replace(
            persisted_state,
            status=TaskStatus.INCONSISTENT,
            inconsistent=True,
            rollback_required=True,
            pending_checkpoint_recovery_id=checkpoint_id,
        )
        try:
            save_state(task_root, inconsistent_state)
        except HanCodeError as exc:
            raise _checkpoint_error(
                "pending_checkpoint_state_update_failed",
                "Pending checkpoint recovery state could not be saved.",
                persisted_state.current_phase,
                "pending_checkpoint_state_persistence_required",
                "Restore state.json write access before resuming the task.",
            ) from exc
        try:
            append_trace(
                task_root,
                event_type="checkpoint_recovery_required",
                task_id=persisted_state.task_id,
                phase=manifest.phase,
                status="blocked",
                observation={"checkpoint_id": checkpoint_id},
                error_summary="Pending checkpoint recovery requires explicit resume.",
            )
        except HanCodeError as exc:
            _mark_rollback_inconsistent(task_root, inconsistent_state)
            raise _checkpoint_error(
                "pending_checkpoint_trace_failed",
                "Pending checkpoint recovery trace could not be persisted.",
                persisted_state.current_phase,
                "checkpoint_trace_required",
                "Restore trace storage before retrying pending checkpoint recovery.",
            ) from exc
        raise _checkpoint_error(
            "pending_checkpoint_recovery_required",
            "A pending checkpoint may have changed source files.",
            persisted_state.current_phase,
            "explicit_pending_checkpoint_recovery_required",
            "Resume with explicit recovery to restore verified before snapshots.",
        )

    latest_checkpoint = _latest_rollbackable_checkpoint(
        task_root,
        persisted_state,
        _required_project_id(project_metadata, persisted_state.current_phase),
    )
    aborted = replace(manifest, status=_ABORTED, rollback_available=False)
    recovery_id = persisted_state.pending_checkpoint_recovery_id
    recovery_lock_matches = recovery_id is None or recovery_id == checkpoint_id
    resolved_pending_recovery = recovery_lock_matches and (
        (recover and has_source_change)
        or (recovery_id == checkpoint_id and (not has_source_change or recover))
    )
    reconciled_state = replace(
        persisted_state,
        status=(
            TaskStatus.BLOCKED
            if resolved_pending_recovery
            else persisted_state.status
        ),
        latest_checkpoint=latest_checkpoint,
        inconsistent=False if resolved_pending_recovery else persisted_state.inconsistent,
        rollback_required=(
            False if resolved_pending_recovery else persisted_state.rollback_required
        ),
        pending_checkpoint_recovery_id=(
            None
            if persisted_state.pending_checkpoint_recovery_id == checkpoint_id
            else persisted_state.pending_checkpoint_recovery_id
        ),
    )
    restored: list[_PendingRecoveryTarget] = []
    if has_source_change:
        try:
            for recovery_target in recovery_targets:
                _restore_pending_recovery_target(recovery_target)
                restored.append(recovery_target)
        except OSError as exc:
            try:
                append_trace(
                    task_root,
                    event_type="checkpoint_recovery_failed",
                    task_id=persisted_state.task_id,
                    phase=manifest.phase,
                    status="failed",
                    observation={"checkpoint_id": checkpoint_id},
                    error_summary="Pending checkpoint source files could not be restored.",
                )
            except HanCodeError as trace_exc:
                _mark_rollback_inconsistent(task_root, persisted_state)
                raise _checkpoint_error(
                    "pending_checkpoint_trace_failed",
                    "Pending checkpoint recovery trace could not be persisted.",
                    persisted_state.current_phase,
                    "checkpoint_trace_required",
                    "Restore trace storage before retrying pending checkpoint recovery.",
                ) from trace_exc
            if not _compensate_pending_recovery_targets(restored):
                _mark_rollback_inconsistent(task_root, persisted_state)
                raise _checkpoint_compensation_error(persisted_state.current_phase) from exc
            raise _checkpoint_error(
                "pending_checkpoint_restore_failed",
                "Pending checkpoint source files could not be restored.",
                persisted_state.current_phase,
                "pending_checkpoint_restore_required",
                "Restore source file write access before retrying explicit recovery.",
            ) from exc

    try:
        _write_manifest(manifest_path, aborted, atomic=True)
        save_state(task_root, reconciled_state)
        append_trace(
            task_root,
            event_type="checkpoint_aborted",
            task_id=persisted_state.task_id,
            phase=manifest.phase,
            status="succeeded",
            observation={"checkpoint_id": checkpoint_id},
            state_transition={
                "latest_checkpoint": [
                    persisted_state.latest_checkpoint,
                    latest_checkpoint,
                ]
            },
        )
    except (HanCodeError, OSError) as exc:
        compensated = _compensate_pending_abort(
            task_root,
            persisted_state,
            manifest_path,
            manifest,
            restored,
        )
        try:
            append_trace(
                task_root,
                event_type="checkpoint_abort_failed",
                task_id=persisted_state.task_id,
                phase=manifest.phase,
                status="failed",
                observation={"checkpoint_id": checkpoint_id},
                error_summary="Pending checkpoint abort could not be persisted.",
            )
        except HanCodeError as trace_exc:
            _mark_rollback_inconsistent(task_root, persisted_state)
            raise _checkpoint_error(
                "pending_checkpoint_trace_failed",
                "Pending checkpoint abort trace could not be persisted.",
                persisted_state.current_phase,
                "checkpoint_trace_required",
                "Restore trace storage before retrying pending checkpoint recovery.",
            ) from trace_exc
        if not compensated:
            _mark_rollback_inconsistent(task_root, persisted_state)
            raise _checkpoint_compensation_error(persisted_state.current_phase) from exc
        raise _checkpoint_error(
            "pending_checkpoint_abort_failed",
            "Pending checkpoint could not be safely aborted.",
            persisted_state.current_phase,
            "pending_checkpoint_abort_persistence_required",
            "Restore task workspace write access before retrying recovery.",
        ) from exc
    return reconciled_state


def abort_pending_checkpoint(
    task_root: Path,
    checkpoint_id: str,
    *,
    restore_files: bool,
) -> CheckpointManifest:
    """Abort one pending checkpoint after applying its selected recovery policy."""
    state, _project_root, project_metadata = _load_checkpoint_context(task_root)
    if not isinstance(restore_files, bool):
        raise _checkpoint_manifest_error(state.current_phase)
    if not _is_checkpoint_id(checkpoint_id) or state.latest_checkpoint != checkpoint_id:
        raise _checkpoint_not_found_error(state.current_phase)

    task_root = task_root.resolve()
    checkpoint_dir = _checkpoint_directory(
        _checkpoints_root(task_root, state.current_phase),
        checkpoint_id,
        state.current_phase,
    )
    manifest_path = checkpoint_dir / "manifest.json"
    if not manifest_path.is_file():
        raise _checkpoint_not_found_error(state.current_phase)
    _validate_manifest_path(checkpoint_dir, manifest_path, state.current_phase)
    manifest = _load_manifest(manifest_path, state.current_phase)
    _validate_manifest_identity(
        manifest,
        checkpoint_id,
        state,
        _required_project_id(project_metadata, state.current_phase),
    )
    if manifest.status != _PENDING:
        raise _checkpoint_error(
            "checkpoint_not_pending",
            "Checkpoint is not pending.",
            state.current_phase,
            "pending_checkpoint_required",
            "Abort each pending checkpoint only once before continuing.",
        )

    reconcile_pending_checkpoint(task_root, state, recover=restore_files)
    final_state = load_state(task_root)
    final_manifest = _load_manifest(manifest_path, final_state.current_phase)
    if final_manifest.status != _ABORTED:
        raise _checkpoint_error(
            "pending_checkpoint_abort_failed",
            "Pending checkpoint did not reach the aborted state.",
            final_state.current_phase,
            "pending_checkpoint_abort_persistence_required",
            "Repair the checkpoint manifest and task state before continuing.",
        )
    return final_manifest


def rollback_last_checkpoint(
    task_root: Path, *, record_trace: bool = True
) -> RollbackResult:
    def _record_rollback_outcome(
        outcome_root: Path, outcome_state: TaskState, result: RollbackResult
    ) -> RollbackResult:
        return _persist_rollback_outcome(
            outcome_root,
            outcome_state,
            result,
            record_trace=record_trace,
        )

    try:
        state, project_root, project_metadata = _load_checkpoint_context(task_root)
    except HanCodeError as exc:
        return RollbackResult(
            status=OperationStatus.BLOCKED,
            checkpoint_id=None,
            restored_files=(),
            failed_files=(),
            error=exc.structured_error,
        )
    if state.inconsistent or state.status is TaskStatus.INCONSISTENT:
        return _record_rollback_outcome(
            task_root,
            state,
            _rollback_blocked(
                state.latest_checkpoint,
                _rollback_error(
                    "rollback_inconsistent_state",
                    "Rollback is blocked while task state is inconsistent.",
                    state.current_phase,
                    "consistent_task_state_required",
                    "Repair and reconcile task state before requesting rollback.",
                ).structured_error,
            ),
        )
    if state.current_phase is not Phase.REVIEW:
        return _record_rollback_outcome(
            task_root,
            state,
            _rollback_blocked(
                state.latest_checkpoint,
                _rollback_error(
                    "rollback_requires_review_phase",
                    "Rollback is only allowed during the review phase.",
                    state.current_phase,
                    "rollback_review_phase_required",
                    "Enter the review phase before restoring a checkpoint.",
                ).structured_error,
            ),
        )
    if state.latest_checkpoint is None or not _is_checkpoint_id(state.latest_checkpoint):
        return _record_rollback_outcome(
            task_root,
            state,
            _rollback_blocked(
                state.latest_checkpoint,
                _rollback_error(
                    "rollback_checkpoint_required",
                    "Rollback requires the latest committed checkpoint.",
                    state.current_phase,
                    "latest_checkpoint_required",
                    "Create and commit a checkpoint before requesting rollback.",
                ).structured_error,
            ),
        )

    checkpoint_id = state.latest_checkpoint
    try:
        task_root = task_root.resolve()
        checkpoint_dir = _checkpoint_directory(
            _checkpoints_root(task_root, state.current_phase),
            checkpoint_id,
            state.current_phase,
        )
        manifest_path = checkpoint_dir / "manifest.json"
        if not manifest_path.is_file():
            raise _checkpoint_not_found_error(state.current_phase)
        _validate_manifest_path(checkpoint_dir, manifest_path, state.current_phase)
        manifest = _load_manifest(manifest_path, state.current_phase)
        _validate_manifest_identity(
            manifest,
            checkpoint_id,
            state,
            _required_project_id(project_metadata, state.current_phase),
        )
        if manifest.status != _COMMITTED or not manifest.rollback_available:
            raise _rollback_error(
                "rollback_not_available",
                "The latest checkpoint is not available for rollback.",
                state.current_phase,
                "committed_checkpoint_required",
                "Commit an available checkpoint before requesting rollback.",
            )
        config = load_config(project_root, state.task_id)
        classifier = PathClassifier(config)
        _validate_before_snapshots(checkpoint_dir, manifest.files, state.current_phase)
        restore_targets: list[_RollbackTarget] = []
        for file in manifest.files:
            relative_path, target = _normalise_targets(
                [Path(file.path)], project_root, classifier, state.current_phase
            )[0]
            if relative_path != file.path or not target.is_file():
                raise _checkpoint_manifest_error(state.current_phase)
            current_content = target.read_bytes()
            if sha256(current_content).hexdigest() != file.after_sha256:
                raise _rollback_error(
                    "rollback_conflict",
                    "A source file changed after its checkpoint was committed.",
                    state.current_phase,
                    "checkpoint_after_hash_required",
                    "Resolve the source conflict before requesting rollback again.",
                )
            before_content = (
                None
                if file.before_snapshot is None
                else (checkpoint_dir / file.before_snapshot).read_bytes()
            )
            restore_targets.append(
                _RollbackTarget(
                    file=file,
                    target=target,
                    before_content=before_content,
                    current_content=current_content,
                )
            )
    except HanCodeError as exc:
        return _record_rollback_outcome(
            task_root,
            state,
            _rollback_blocked(checkpoint_id, exc.structured_error),
        )
    except OSError:
        return _record_rollback_outcome(
            task_root,
            state,
            _rollback_blocked(
                checkpoint_id,
                _rollback_error(
                    "rollback_conflict",
                    "Current source files could not be verified for rollback.",
                    state.current_phase,
                    "checkpoint_after_hash_required",
                    "Restore source file read access before requesting rollback again.",
                ).structured_error,
            ),
        )

    if record_trace:
        try:
            append_trace(
                task_root,
                event_type="rollback_started",
                task_id=state.task_id,
                phase=state.current_phase,
                status="running",
                observation={"checkpoint_id": checkpoint_id},
            )
        except HanCodeError:
            return RollbackResult(
                status=OperationStatus.FAILED,
                checkpoint_id=checkpoint_id,
                restored_files=(),
                failed_files=(),
                error=_rollback_error(
                    "rollback_trace_failed",
                    "Rollback start trace could not be persisted.",
                    state.current_phase,
                    "rollback_trace_required",
                    "Restore trace write access before retrying rollback.",
                ).structured_error,
            )

    restored_files: list[str] = []
    for restore_target in restore_targets:
        try:
            _restore_rollback_target(restore_target)
            restored_files.append(restore_target.file.path)
        except OSError:
            if not _compensate_rollback_files(restore_targets, restored_files):
                _mark_rollback_inconsistent(task_root, state)
                return _record_rollback_outcome(
                    task_root,
                    state,
                    RollbackResult(
                    status=OperationStatus.FAILED,
                    checkpoint_id=checkpoint_id,
                    restored_files=tuple(restored_files),
                    failed_files=(restore_target.file.path,),
                    error=_rollback_error(
                        "rollback_compensation_failed",
                        "Rollback could not restore its original source state.",
                        state.current_phase,
                        "rollback_compensation_required",
                        "Repair source files before continuing.",
                    ).structured_error,
                    ),
                )
            return _record_rollback_outcome(
                task_root,
                state,
                RollbackResult(
                status=OperationStatus.FAILED,
                checkpoint_id=checkpoint_id,
                restored_files=(),
                failed_files=(restore_target.file.path,),
                error=_rollback_error(
                    "rollback_restore_failed",
                    "Rollback could not restore all source files.",
                    state.current_phase,
                    "rollback_restore_required",
                    "Restore source file write access before retrying rollback.",
                ).structured_error,
                ),
            )
    rolled_back = replace(
        manifest,
        status=_ROLLED_BACK,
        rollback_available=False,
    )
    try:
        _write_manifest(manifest_path, rolled_back, atomic=True)
    except OSError:
        if not _compensate_rollback_files(restore_targets, restored_files):
            _mark_rollback_inconsistent(task_root, state)
            return _record_rollback_outcome(
                task_root,
                state,
                RollbackResult(
                status=OperationStatus.FAILED,
                checkpoint_id=checkpoint_id,
                restored_files=tuple(restored_files),
                failed_files=(),
                error=_rollback_error(
                    "rollback_compensation_failed",
                    "Rollback could not restore its original source state.",
                    state.current_phase,
                    "rollback_compensation_required",
                    "Repair source files before continuing.",
                ).structured_error,
                ),
            )
        return _record_rollback_outcome(
            task_root,
            state,
            RollbackResult(
            status=OperationStatus.FAILED,
            checkpoint_id=checkpoint_id,
            restored_files=(),
            failed_files=(),
            error=_rollback_error(
                "rollback_manifest_update_failed",
                "Rollback manifest could not be updated.",
                state.current_phase,
                "rollback_manifest_update_required",
                "Restore task workspace write access before retrying rollback.",
            ).structured_error,
            ),
        )
    phase_completed = dict(state.phase_completed)
    phase_completed.update({"code": False, "test": False, "review": False})
    rolled_back_state = replace(
        state,
        latest_test_status="none",
        test_status_consumed=False,
        source_edits_this_phase=0,
        rollback_required=False,
        rollback_done=True,
        phase_completed=phase_completed,
    )
    try:
        save_state(task_root, rolled_back_state)
    except HanCodeError:
        if not _compensate_rollback(
            task_root,
            state,
            manifest_path,
            manifest,
            restore_targets,
            restored_files,
        ):
            _mark_rollback_inconsistent(task_root, state)
            return _record_rollback_outcome(
                task_root,
                state,
                RollbackResult(
                status=OperationStatus.FAILED,
                checkpoint_id=checkpoint_id,
                restored_files=tuple(restored_files),
                failed_files=(),
                error=_rollback_error(
                    "rollback_compensation_failed",
                    "Rollback could not restore its original state after a state failure.",
                    state.current_phase,
                    "rollback_compensation_required",
                    "Repair state.json, manifest.json, and source files before continuing.",
                ).structured_error,
                ),
            )
        return _record_rollback_outcome(
            task_root,
            state,
            RollbackResult(
            status=OperationStatus.FAILED,
            checkpoint_id=checkpoint_id,
            restored_files=(),
            failed_files=(),
            error=_rollback_error(
                "rollback_state_update_failed",
                "Rollback state could not be updated.",
                state.current_phase,
                "rollback_state_update_required",
                "Restore task state write access before retrying rollback.",
            ).structured_error,
            ),
        )
    if not record_trace:
        return RollbackResult(
            status=OperationStatus.SUCCEEDED,
            checkpoint_id=checkpoint_id,
            restored_files=tuple(restored_files),
            failed_files=(),
            error=None,
        )
    try:
        append_trace(
            task_root,
            event_type="rollback_performed",
            task_id=state.task_id,
            phase=state.current_phase,
            status="succeeded",
            observation={
                "checkpoint_id": checkpoint_id,
                "restored_files": list(restored_files),
            },
            state_transition={
                "rollback_done": [state.rollback_done, True],
                "rollback_required": [state.rollback_required, False],
            },
        )
    except HanCodeError:
        if not _compensate_rollback(
            task_root,
            state,
            manifest_path,
            manifest,
            restore_targets,
            restored_files,
        ):
            _mark_rollback_inconsistent(task_root, state)
            return RollbackResult(
                status=OperationStatus.FAILED,
                checkpoint_id=checkpoint_id,
                restored_files=tuple(restored_files),
                failed_files=(),
                error=_rollback_error(
                    "rollback_compensation_failed",
                    "Rollback could not restore its original state after a trace failure.",
                    state.current_phase,
                    "rollback_compensation_required",
                    "Repair state.json, manifest.json, and source files before continuing.",
                ).structured_error,
            )
        return RollbackResult(
            status=OperationStatus.FAILED,
            checkpoint_id=checkpoint_id,
            restored_files=(),
            failed_files=(),
            error=_rollback_error(
                "rollback_trace_failed",
                "Rollback trace could not be persisted.",
                state.current_phase,
                "rollback_trace_required",
                "Restore trace write access before retrying rollback.",
            ).structured_error,
        )
    return RollbackResult(
        status=OperationStatus.SUCCEEDED,
        checkpoint_id=checkpoint_id,
        restored_files=tuple(restored_files),
        failed_files=(),
        error=None,
    )


def _load_checkpoint_context(
    task_root: Path,
) -> tuple[TaskState, Path, dict[str, object]]:
    resolved_task_root = task_root.resolve()
    if (
        resolved_task_root.parent.name != "tasks"
        or resolved_task_root.parent.parent.name != ".hancode"
    ):
        raise _checkpoint_error(
            "invalid_checkpoint_task_root",
            "Checkpoint task root is outside the task workspace layout.",
            Phase.CODE,
            "task_workspace_checkpoint_root_required",
            "Use a task root inside .hancode/tasks/<task_id>.",
        )
    state = load_state(resolved_task_root)
    if state.task_id != resolved_task_root.name:
        raise _invalid_checkpoint_task_root_error(state.current_phase)
    project_root = resolved_task_root.parent.parent.parent
    project_metadata = load_project_metadata(resolved_task_root.parent.parent / "project.json")
    return state, project_root, project_metadata


def _restore_rollback_target(restore_target: _RollbackTarget) -> None:
    if restore_target.file.action == "create":
        restore_target.target.unlink()
        return
    if restore_target.before_content is None:
        raise OSError("Missing before snapshot.")
    _replace_file_contents(
        restore_target.target,
        restore_target.before_content,
        ".rollback.tmp",
    )


def _pending_recovery_targets(
    manifest: CheckpointManifest,
    checkpoint_dir: Path,
    project_root: Path,
    classifier: PathClassifier,
    phase: Phase,
) -> list[_PendingRecoveryTarget]:
    targets: list[_PendingRecoveryTarget] = []
    for file in manifest.files:
        relative_path, target = _normalise_targets(
            [Path(file.path)], project_root, classifier, phase
        )[0]
        if relative_path != file.path:
            raise _checkpoint_manifest_error(phase)
        try:
            current_content = None if not target.is_file() else target.read_bytes()
            before_content = (
                None
                if file.before_snapshot is None
                else (checkpoint_dir / file.before_snapshot).read_bytes()
            )
        except OSError:
            raise _checkpoint_manifest_error(phase) from None
        targets.append(
            _PendingRecoveryTarget(
                file=file,
                target=target,
                before_content=before_content,
                current_content=current_content,
            )
        )
    return targets


def _restore_pending_recovery_target(target: _PendingRecoveryTarget) -> None:
    if target.file.action == "create":
        if target.target.is_dir():
            raise OSError("Pending checkpoint create target is a directory.")
        target.target.unlink(missing_ok=True)
        return
    if target.before_content is None or target.target.is_dir():
        raise OSError("Pending checkpoint modify target is invalid.")
    _replace_file_contents(
        target.target,
        target.before_content,
        ".pending-recovery.tmp",
    )


def _compensate_pending_recovery_targets(
    restored: list[_PendingRecoveryTarget],
) -> bool:
    try:
        for target in reversed(restored):
            if target.current_content is None:
                target.target.unlink(missing_ok=True)
            else:
                _replace_file_contents(
                    target.target,
                    target.current_content,
                    ".pending-recovery-compensate.tmp",
                )
    except OSError:
        return False
    return True


def _compensate_pending_abort(
    task_root: Path,
    state: TaskState,
    manifest_path: Path,
    manifest: CheckpointManifest,
    restored: list[_PendingRecoveryTarget],
) -> bool:
    try:
        save_state(task_root, state)
        _write_manifest(manifest_path, manifest, atomic=True)
    except (HanCodeError, OSError):
        return False
    return _compensate_pending_recovery_targets(restored)


def _latest_rollbackable_checkpoint(
    task_root: Path,
    state: TaskState,
    project_id: str,
) -> str | None:
    checkpoints_root = _checkpoints_root(task_root, state.current_phase)
    candidates: list[str] = []
    try:
        checkpoint_dirs = tuple(checkpoints_root.iterdir())
    except OSError:
        raise _checkpoint_manifest_error(state.current_phase) from None
    for checkpoint_dir in checkpoint_dirs:
        checkpoint_id = checkpoint_dir.name
        if not _is_checkpoint_id(checkpoint_id):
            continue
        if _is_link(checkpoint_dir) or not checkpoint_dir.is_dir():
            raise _checkpoint_manifest_error(state.current_phase)
        manifest_path = checkpoint_dir / "manifest.json"
        if not manifest_path.is_file():
            raise _checkpoint_manifest_error(state.current_phase)
        _validate_manifest_path(checkpoint_dir, manifest_path, state.current_phase)
        manifest = _load_manifest(manifest_path, state.current_phase)
        _validate_manifest_identity(manifest, checkpoint_id, state, project_id)
        _validate_before_snapshots(checkpoint_dir, manifest.files, state.current_phase)
        if manifest.status == _COMMITTED and manifest.rollback_available:
            candidates.append(checkpoint_id)
    return max(candidates, key=lambda checkpoint_id: int(checkpoint_id.removeprefix("ckpt-")), default=None)


def _compensate_rollback_files(
    restore_targets: list[_RollbackTarget], restored_files: list[str]
) -> bool:
    restored = set(restored_files)
    try:
        for restore_target in reversed(restore_targets):
            if restore_target.file.path not in restored:
                continue
            _replace_file_contents(
                restore_target.target,
                restore_target.current_content,
                ".rollback-compensate.tmp",
            )
    except OSError:
        return False
    return True


def _compensate_rollback(
    task_root: Path,
    state: TaskState,
    manifest_path: Path,
    manifest: CheckpointManifest,
    restore_targets: list[_RollbackTarget],
    restored_files: list[str],
) -> bool:
    try:
        save_state(task_root, state)
        _write_manifest(manifest_path, manifest, atomic=True)
    except (HanCodeError, OSError):
        return False
    return _compensate_rollback_files(restore_targets, restored_files)


def _mark_rollback_inconsistent(task_root: Path, state: TaskState) -> None:
    try:
        save_state(
            task_root,
            replace(state, status=TaskStatus.INCONSISTENT, inconsistent=True),
        )
    except HanCodeError:
        pass


def _record_pending_recovery_failure(
    task_root: Path,
    state: TaskState,
    checkpoint_id: str,
    phase: Phase,
    error: StructuredError,
) -> None:
    try:
        append_trace(
            task_root,
            event_type="checkpoint_recovery_failed",
            task_id=state.task_id,
            phase=phase,
            status="failed",
            observation={"checkpoint_id": checkpoint_id},
            error_summary=error.message,
        )
    except HanCodeError as trace_exc:
        _mark_rollback_inconsistent(task_root, state)
        raise _checkpoint_error(
            "pending_checkpoint_trace_failed",
            "Pending checkpoint recovery trace could not be persisted.",
            phase,
            "checkpoint_trace_required",
            "Restore trace storage before retrying pending checkpoint recovery.",
        ) from trace_exc


def _replace_file_contents(target: Path, content: bytes, temporary_suffix: str) -> None:
    descriptor: int | None = None
    temporary_target: Path | None = None
    try:
        descriptor, temporary_name = mkstemp(
            prefix=f".{target.name}{temporary_suffix.removesuffix('.tmp')}-",
            suffix=".tmp",
            dir=target.parent,
        )
        temporary_target = Path(temporary_name)
        if _is_link(temporary_target):
            raise OSError("Rollback temporary file must not be a link.")
        with os.fdopen(descriptor, "wb") as temporary_file:
            descriptor = None
            temporary_file.write(content)
        temporary_target.replace(target)
    except OSError:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        try:
            if temporary_target is not None:
                temporary_target.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _normalise_targets(
    files: list[Path], project_root: Path, classifier: PathClassifier, phase: Phase
) -> list[tuple[str, Path]]:
    targets: dict[str, Path] = {}
    for file in files:
        if not isinstance(file, Path):
            raise _checkpoint_path_error(phase)
        try:
            target = (project_root / file).resolve() if not file.is_absolute() else file.resolve()
            relative_path = target.relative_to(project_root.resolve()).as_posix()
        except (OSError, RuntimeError, ValueError):
            raise _checkpoint_path_error(phase) from None
        if classifier.classify(relative_path) is not PathZone.SOURCE:
            raise _checkpoint_path_error(phase)
        targets[relative_path] = target
    return sorted(targets.items())


def _write_manifest(path: Path, manifest: CheckpointManifest, *, atomic: bool) -> None:
    content = json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2) + "\n"
    if not atomic:
        path.write_text(content, encoding="utf-8")
        return
    descriptor: int | None = None
    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = mkstemp(
            prefix=".manifest-",
            suffix=".tmp",
            dir=path.parent,
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as temporary_file:
            descriptor = None
            temporary_file.write(content)
        temporary_path.replace(path)
    except OSError:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise


def _load_manifest(path: Path, phase: Phase) -> CheckpointManifest:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError
        files = payload["files"]
        if not isinstance(files, list):
            raise ValueError
        parsed_files = tuple(_parse_checkpoint_file(file) for file in files)
        created_at = datetime.fromisoformat(_required_str(payload, "created_at"))
        raw_status = _required_str(payload, "status")
        if raw_status not in {_PENDING, _COMMITTED, _ROLLED_BACK, _ABORTED}:
            raise ValueError
        status: Literal["pending", "committed", "rolled_back", "aborted"] = raw_status
        rollback_available = _required_bool(payload, "rollback_available")
        if not parsed_files or (status == _PENDING and rollback_available):
            raise ValueError
        if status == _PENDING and any(file.after_sha256 is not None for file in parsed_files):
            raise ValueError
        if status == _COMMITTED and (
            not rollback_available or any(file.after_sha256 is None for file in parsed_files)
        ):
            raise ValueError
        if status == _ROLLED_BACK and (
            rollback_available or any(file.after_sha256 is None for file in parsed_files)
        ):
            raise ValueError
        if status == _ABORTED and (
            rollback_available or any(file.after_sha256 is not None for file in parsed_files)
        ):
            raise ValueError
        return CheckpointManifest(
            schema_version=_required_int(payload, "schema_version"),
            project_id=_required_str(payload, "project_id"),
            checkpoint_id=_required_str(payload, "checkpoint_id"),
            task_id=_required_str(payload, "task_id"),
            phase=Phase(_required_str(payload, "phase")),
            reason=_required_str(payload, "reason"),
            created_at=created_at,
            status=status,
            files=parsed_files,
            rollback_available=rollback_available,
        )
    except (OSError, UnicodeError, ValueError, KeyError, TypeError):
        raise _checkpoint_error(
            "checkpoint_manifest_invalid",
            "Checkpoint manifest is invalid.",
            phase,
            "valid_checkpoint_manifest_required",
            "Repair manifest.json before committing or rolling back.",
        ) from None


def _parse_checkpoint_file(value: object) -> CheckpointFile:
    if not isinstance(value, Mapping):
        raise ValueError
    action = _required_str(value, "action")
    if action not in {"create", "modify"}:
        raise ValueError
    before_snapshot = _optional_str(value, "before_snapshot")
    before_sha256 = _optional_str(value, "before_sha256")
    after_sha256 = _optional_str(value, "after_sha256")
    if after_sha256 is not None and not re.fullmatch(r"[0-9a-f]{64}", after_sha256):
        raise ValueError
    if action == "create":
        if before_snapshot is not None or before_sha256 is not None:
            raise ValueError
        return CheckpointFile(
            path=_required_str(value, "path"),
            action="create",
            before_snapshot=before_snapshot,
            before_sha256=before_sha256,
            after_sha256=after_sha256,
        )
    if before_snapshot is None or before_sha256 is None:
        raise ValueError
    return CheckpointFile(
        path=_required_str(value, "path"),
        action="modify",
        before_snapshot=before_snapshot,
        before_sha256=before_sha256,
        after_sha256=after_sha256,
    )


def _required_project_id(metadata: Mapping[str, object], phase: Phase) -> str:
    project_id = metadata.get("project_id")
    if not isinstance(project_id, str) or not project_id:
        raise _checkpoint_error(
            "invalid_checkpoint_task_root",
            "Checkpoint project metadata is invalid.",
            phase,
            "valid_project_metadata_required",
            "Repair project.json before creating a checkpoint.",
        )
    return project_id


def _validate_manifest_identity(
    manifest: CheckpointManifest,
    checkpoint_id: str,
    state: TaskState,
    project_id: str,
) -> None:
    if (
        manifest.schema_version != _MANIFEST_SCHEMA_VERSION
        or manifest.checkpoint_id != checkpoint_id
        or manifest.project_id != project_id
        or manifest.task_id != state.task_id
        or manifest.phase is not Phase.CODE
        or len({file.path for file in manifest.files}) != len(manifest.files)
    ):
        raise _checkpoint_error(
            "checkpoint_manifest_invalid",
            "Checkpoint manifest does not match the active task.",
            state.current_phase,
            "valid_checkpoint_manifest_required",
            "Repair manifest.json before committing or rolling back.",
        )


def _checkpoints_root(task_root: Path, phase: Phase) -> Path:
    try:
        resolved_task_root = task_root.resolve()
        checkpoints_root = task_root / "checkpoints"
        resolved_checkpoints_root = checkpoints_root.resolve()
        if (
            not checkpoints_root.is_dir()
            or resolved_checkpoints_root.parent != resolved_task_root
            or resolved_checkpoints_root.name != "checkpoints"
        ):
            raise ValueError
    except (OSError, RuntimeError, ValueError):
        raise _invalid_checkpoint_task_root_error(phase) from None
    return checkpoints_root


def _checkpoint_directory(
    checkpoints_root: Path, checkpoint_id: str, phase: Phase
) -> Path:
    try:
        checkpoint_dir = checkpoints_root / checkpoint_id
        resolved_checkpoint_dir = checkpoint_dir.resolve()
        resolved_checkpoints_root = checkpoints_root.resolve()
        resolved_checkpoint_dir.relative_to(resolved_checkpoints_root)
        if resolved_checkpoint_dir == resolved_checkpoints_root:
            raise ValueError
    except (OSError, RuntimeError, ValueError):
        raise _invalid_checkpoint_task_root_error(phase) from None
    return checkpoint_dir


def _validate_before_snapshots(
    checkpoint_dir: Path, files: tuple[CheckpointFile, ...], phase: Phase
) -> None:
    try:
        resolved_checkpoint_dir = checkpoint_dir.resolve()
        files_root = checkpoint_dir / "files"
        snapshots_root = files_root.resolve()
        if (
            _is_link(files_root)
            or not files_root.is_dir()
            or snapshots_root.parent != resolved_checkpoint_dir
            or snapshots_root.name != "files"
        ):
            raise ValueError
    except (OSError, RuntimeError, ValueError):
        raise _checkpoint_manifest_error(phase) from None
    for file in files:
        if file.action == "create":
            continue
        if file.before_snapshot is None or file.before_sha256 is None:
            raise _checkpoint_manifest_error(phase)
        try:
            raw_snapshot_path = checkpoint_dir / file.before_snapshot
            if _is_link(raw_snapshot_path):
                raise ValueError
            snapshot_path = raw_snapshot_path.resolve()
            relative_snapshot = snapshot_path.relative_to(checkpoint_dir.resolve()).as_posix()
            snapshot_path.relative_to(snapshots_root)
            if relative_snapshot != file.before_snapshot or not snapshot_path.is_file():
                raise ValueError
            snapshot_hash = sha256(snapshot_path.read_bytes()).hexdigest()
        except (OSError, RuntimeError, ValueError):
            raise _checkpoint_manifest_error(phase) from None
        if not re.fullmatch(r"[0-9a-f]{64}", file.before_sha256) or snapshot_hash != file.before_sha256:
            raise _checkpoint_manifest_error(phase)


def _is_checkpoint_id(checkpoint_id: str) -> bool:
    return isinstance(checkpoint_id, str) and bool(
        re.fullmatch(r"ckpt-[0-9]{3,}", checkpoint_id)
    )


def _validate_manifest_path(checkpoint_dir: Path, manifest_path: Path, phase: Phase) -> None:
    try:
        if _is_link(manifest_path) or manifest_path.resolve().parent != checkpoint_dir.resolve():
            raise ValueError
    except (OSError, RuntimeError, ValueError):
        raise _checkpoint_manifest_error(phase) from None


def _is_link(path: Path) -> bool:
    try:
        is_junction = getattr(path, "is_junction", None)
        return path.is_symlink() or bool(is_junction and is_junction())
    except (AttributeError, OSError, RuntimeError):
        return True


def _sanitize_reason(reason: str) -> str:
    sanitized = _SENSITIVE_REASON_PATTERN.sub(_redact_reason_match, reason)
    return _BEARER_TOKEN_PATTERN.sub("Bearer [REDACTED]", sanitized)


def _redact_reason_match(match: re.Match[str]) -> str:
    separator = ":" if ":" in match.group(0) else "="
    return f"{match.group(1)}{separator}[REDACTED]"


def _checkpoint_not_found_error(phase: Phase) -> HanCodeError:
    return _checkpoint_error(
        "checkpoint_not_found",
        "Checkpoint manifest was not found.",
        phase,
        "checkpoint_must_exist",
        "Use an existing checkpoint ID for this task.",
    )


def _invalid_checkpoint_task_root_error(phase: Phase) -> HanCodeError:
    return _checkpoint_error(
        "invalid_checkpoint_task_root",
        "Checkpoint directory is outside the task workspace.",
        phase,
        "task_workspace_checkpoint_root_required",
        "Repair the task checkpoints directory before continuing.",
    )


def _checkpoint_manifest_error(phase: Phase) -> HanCodeError:
    return _checkpoint_error(
        "checkpoint_manifest_invalid",
        "Checkpoint manifest is invalid.",
        phase,
        "valid_checkpoint_manifest_required",
        "Repair manifest.json and its snapshot files before continuing.",
    )


def _checkpoint_compensation_error(phase: Phase) -> HanCodeError:
    return _checkpoint_error(
        "checkpoint_compensation_failed",
        "Checkpoint failure could not be fully compensated.",
        phase,
        "checkpoint_compensation_required",
        "Repair state.json and the checkpoint directory before continuing.",
    )


def _required_str(values: Mapping[str, object], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError
    return value


def _optional_str(values: Mapping[str, object], key: str) -> str | None:
    value = values.get(key)
    if value is not None and (not isinstance(value, str) or not value):
        raise ValueError
    return value


def _required_int(values: Mapping[str, object], key: str) -> int:
    value = values.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError
    return value


def _required_bool(values: Mapping[str, object], key: str) -> bool:
    value = values.get(key)
    if not isinstance(value, bool):
        raise ValueError
    return value


def _checkpoint_path_error(phase: Phase) -> HanCodeError:
    return _checkpoint_error(
        "checkpoint_path_not_source",
        "Checkpoint targets must be writable source files.",
        phase,
        "checkpoint_source_path_required",
        "Use a source path inside a configured writable root.",
    )


def _checkpoint_error(
    error_code: str,
    message: str,
    phase: Phase,
    denied_rule: str,
    suggested_fix: str,
) -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code=error_code,
            message=message,
            phase=phase.value,
            denied_rule=denied_rule,
            suggested_fix=suggested_fix,
        )
    )


def _rollback_blocked(
    checkpoint_id: str | None, error: StructuredError
) -> RollbackResult:
    return RollbackResult(
        status=OperationStatus.BLOCKED,
        checkpoint_id=checkpoint_id,
        restored_files=(),
        failed_files=(),
        error=error,
    )


def _persist_rollback_outcome(
    task_root: Path,
    state: TaskState,
    result: RollbackResult,
    *,
    record_trace: bool = True,
) -> RollbackResult:
    if not record_trace:
        return result
    try:
        append_trace(
            task_root,
            event_type="rollback_performed",
            task_id=state.task_id,
            phase=state.current_phase,
            status=result.status.value,
            observation={
                "checkpoint_id": result.checkpoint_id,
                "restored_files": list(result.restored_files),
                "failed_files": list(result.failed_files),
            },
            error_summary=result.error_summary,
        )
    except HanCodeError:
        return replace(
            result,
            status=OperationStatus.FAILED,
            error=_rollback_error(
                "rollback_trace_failed",
                "Rollback trace could not be persisted.",
                state.current_phase,
                "rollback_trace_required",
                "Restore trace write access before retrying rollback.",
            ).structured_error,
        )
    return result


def _rollback_error(
    error_code: str,
    message: str,
    phase: Phase,
    denied_rule: str,
    suggested_fix: str,
) -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code=error_code,
            message=message,
            phase=phase.value,
            denied_rule=denied_rule,
            suggested_fix=suggested_fix,
        )
    )


def _remove_checkpoint(checkpoint_dir: Path) -> bool:
    try:
        for path in sorted(checkpoint_dir.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            else:
                path.rmdir()
        checkpoint_dir.rmdir()
    except OSError:
        return False
    return True
