from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Literal, Mapping

from hancode.config import load_config
from hancode.errors import HanCodeError, StructuredError
from hancode.models import Phase
from hancode.path_policy import PathClassifier, PathZone
from hancode.state import TaskState, load_state, save_state
from hancode.trace import append_trace
from hancode.workspace import load_project_metadata


_MANIFEST_SCHEMA_VERSION = 1
_PENDING: Literal["pending"] = "pending"
_COMMITTED: Literal["committed"] = "committed"
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
    status: Literal["pending", "committed"]
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


def _normalise_targets(
    files: list[Path], project_root: Path, classifier: PathClassifier, phase: Phase
) -> list[tuple[str, Path]]:
    targets: dict[str, Path] = {}
    for file in files:
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
    temporary_path = path.with_suffix(".json.tmp")
    try:
        temporary_path.write_text(content, encoding="utf-8")
        temporary_path.replace(path)
    except OSError:
        temporary_path.unlink(missing_ok=True)
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
        if raw_status not in {_PENDING, _COMMITTED}:
            raise ValueError
        status: Literal["pending", "committed"] = (
            _PENDING if raw_status == _PENDING else _COMMITTED
        )
        rollback_available = _required_bool(payload, "rollback_available")
        if not parsed_files or (status == _PENDING and rollback_available):
            raise ValueError
        if status == _PENDING and any(file.after_sha256 is not None for file in parsed_files):
            raise ValueError
        if status == _COMMITTED and (
            not rollback_available or any(file.after_sha256 is None for file in parsed_files)
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
            snapshot_path = (checkpoint_dir / file.before_snapshot).resolve()
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
    return bool(re.fullmatch(r"ckpt-[0-9]{3,}", checkpoint_id))


def _validate_manifest_path(checkpoint_dir: Path, manifest_path: Path, phase: Phase) -> None:
    try:
        if _is_link(manifest_path) or manifest_path.resolve().parent != checkpoint_dir.resolve():
            raise ValueError
    except (OSError, RuntimeError, ValueError):
        raise _checkpoint_manifest_error(phase) from None


def _is_link(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or bool(is_junction and is_junction())


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
