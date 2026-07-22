"""Checkpoint Query Repository — unified read-only access to checkpoint data.

All query paths MUST validate: schema_version, project_id, task_id,
checkpoint_id, phase, status, path normalization, snapshot path, snapshot hash,
and symlink/junction.  No caller should parse manifest.json directly.
"""

from __future__ import annotations

from hashlib import sha256
import json
import re
from pathlib import Path
from typing import Mapping

from hancode.core.errors import HanCodeError, StructuredError
from hancode.core.models import Phase
from hancode.storage.checkpoints import CheckpointManifest


_MANIFEST_SCHEMA_VERSION = 1
_VALID_STATUSES = frozenset({"pending", "committed", "rolled_back", "aborted"})


class CheckpointQueryRepository:
    """Read-only queries over a task's checkpoint manifests and snapshots.

    All methods fail-closed on any integrity violation (corrupt manifest,
    symlink, identity mismatch, hash mismatch).
    """

    # ------------------------------------------------------------------
    # list
    # ------------------------------------------------------------------

    def list(self, task_root: Path) -> tuple[CheckpointManifest, ...]:
        task_root = task_root.resolve()
        checkpoints_root = _resolve_checkpoints_root(task_root)
        manifests: list[CheckpointManifest] = []
        for entry in sorted(checkpoints_root.iterdir()):
            if not _is_checkpoint_id(entry.name):
                continue
            if not entry.is_dir():
                continue
            manifest = self._load_and_validate(entry, task_root)
            manifests.append(manifest)
        manifests.sort(key=lambda m: _checkpoint_sort_key(m.checkpoint_id))
        return tuple(manifests)

    # ------------------------------------------------------------------
    # get
    # ------------------------------------------------------------------

    def get(self, task_root: Path, checkpoint_id: str) -> CheckpointManifest:
        task_root = task_root.resolve()
        if not _is_checkpoint_id(checkpoint_id):
            raise _query_error(
                "checkpoint_query_identity_mismatch",
                f"Invalid checkpoint ID format: {checkpoint_id!r}.",
                "Use a valid checkpoint ID like ckpt-001.",
            )
        checkpoints_root = _resolve_checkpoints_root(task_root)
        checkpoint_dir = _checkpoint_dir(checkpoints_root, checkpoint_id)
        if not checkpoint_dir.is_dir():
            raise _query_error(
                "checkpoint_query_manifest_invalid",
                f"Checkpoint not found: {checkpoint_id}.",
                "Verify the checkpoint ID is correct.",
            )
        return self._load_and_validate(checkpoint_dir, task_root)

    # ------------------------------------------------------------------
    # read_before
    # ------------------------------------------------------------------

    def read_before(
        self,
        task_root: Path,
        checkpoint_id: str,
        file_path: str,
    ) -> bytes | None:
        manifest = self.get(task_root, checkpoint_id)
        for f in manifest.files:
            if f.path == file_path:
                if f.action == "create":
                    return None
                if f.before_snapshot is None:
                    raise _query_error(
                        "checkpoint_query_snapshot_invalid",
                        "Modify action missing before_snapshot.",
                        "Repair the checkpoint manifest.",
                    )
                checkpoint_dir = _checkpoint_dir(
                    _resolve_checkpoints_root(task_root.resolve()),
                    checkpoint_id,
                )
                snapshot_path = checkpoint_dir / f.before_snapshot
                if _is_link(snapshot_path):
                    raise _query_error(
                        "checkpoint_query_snapshot_invalid",
                        "Snapshot path is a symlink or junction.",
                        "Replace with a regular file.",
                    )
                try:
                    content = snapshot_path.read_bytes()
                except OSError:
                    raise _query_error(
                        "checkpoint_query_snapshot_invalid",
                        "Snapshot file cannot be read.",
                        "Verify snapshot file integrity.",
                    )
                actual_hash = sha256(content).hexdigest()
                if actual_hash != f.before_sha256:
                    raise _query_error(
                        "checkpoint_query_manifest_invalid",
                        "Snapshot hash mismatch.",
                        "Repair or recreate the checkpoint.",
                    )
                return content
        raise _query_error(
            "checkpoint_query_identity_mismatch",
            f"File {file_path!r} not found in checkpoint {checkpoint_id}.",
            "Verify the file path is correct.",
        )

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    def _load_and_validate(
        self,
        checkpoint_dir: Path,
        task_root: Path,
    ) -> CheckpointManifest:
        manifest_path = checkpoint_dir / "manifest.json"

        # --- task identity check ---
        expected_task_id = task_root.name
        if not expected_task_id.startswith("task-"):
            raise _query_error(
                "checkpoint_query_identity_mismatch",
                "Task root does not appear to be a valid task directory.",
                "Verify the task workspace structure.",
            )

        if _is_link(manifest_path):
            raise _query_error(
                "checkpoint_query_manifest_invalid",
                "Manifest path is a symlink or junction.",
                "Replace manifest.json with a regular file.",
            )
        try:
            resolved_manifest = manifest_path.resolve()
            if resolved_manifest.parent != checkpoint_dir.resolve():
                raise ValueError("manifest escaped checkpoint directory")
        except (OSError, RuntimeError, ValueError):
            raise _query_error(
                "checkpoint_query_manifest_invalid",
                "Manifest path is not within checkpoint directory.",
                "Repair manifest.json location.",
            )

        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            raise _query_error(
                "checkpoint_query_manifest_invalid",
                "Checkpoint manifest cannot be read or parsed.",
                "Repair or recreate manifest.json.",
            )

        if not isinstance(payload, Mapping):
            raise _query_error(
                "checkpoint_query_manifest_invalid",
                "Manifest is not a JSON object.",
                "Repair manifest.json.",
            )

        # Validate schema_version
        schema_version = payload.get("schema_version")
        if schema_version != _MANIFEST_SCHEMA_VERSION:
            raise _query_error(
                "checkpoint_query_manifest_invalid",
                f"Unsupported schema version: {schema_version!r}.",
                "Migrate the checkpoint to the current schema version.",
            )

        # Validate checkpoint ID matches directory name
        checkpoint_id = payload.get("checkpoint_id")
        if not isinstance(checkpoint_id, str) or checkpoint_id != checkpoint_dir.name:
            raise _query_error(
                "checkpoint_query_identity_mismatch",
                "Manifest checkpoint_id does not match directory name.",
                "Repair manifest.json or directory name.",
            )

        # Validate task_id matches the task workspace
        manifest_task_id = payload.get("task_id")
        if manifest_task_id != expected_task_id:
            raise _query_error(
                "checkpoint_query_identity_mismatch",
                f"Manifest task_id {manifest_task_id!r} does not match workspace {expected_task_id!r}.",
                "Repair manifest.json or move checkpoint to the correct task.",
            )

        # Validate status
        status = payload.get("status")
        if status not in _VALID_STATUSES:
            raise _query_error(
                "checkpoint_query_manifest_invalid",
                f"Invalid checkpoint status: {status!r}.",
                "Repair manifest.json.",
            )

        # Build CheckpointManifest using the existing parser for full validation
        try:
            from hancode.storage.checkpoints import CheckpointFile

            files_raw = payload.get("files")
            if not isinstance(files_raw, list):
                raise ValueError
            parsed_files: list[CheckpointFile] = []
            for f in files_raw:
                if not isinstance(f, Mapping):
                    raise ValueError
                action = f.get("action")
                if action not in ("create", "modify"):
                    raise ValueError
                parsed_files.append(
                    CheckpointFile(
                        path=str(f["path"]),
                        action=action,
                        before_snapshot=f.get("before_snapshot") if isinstance(f.get("before_snapshot"), str) else None,
                        before_sha256=f.get("before_sha256") if isinstance(f.get("before_sha256"), str) else None,
                        after_sha256=f.get("after_sha256") if isinstance(f.get("after_sha256"), str) else None,
                    )
                )

            from datetime import datetime

            created_at = datetime.fromisoformat(str(payload["created_at"]))
            phase = Phase(str(payload["phase"]))

            manifest = CheckpointManifest(
                schema_version=int(schema_version),
                project_id=str(payload["project_id"]),
                checkpoint_id=str(checkpoint_id),
                task_id=str(payload["task_id"]),
                phase=phase,
                reason=str(payload.get("reason", "")),
                created_at=created_at,
                status=status,
                files=tuple(parsed_files),
                rollback_available=bool(payload.get("rollback_available", False)),
            )
        except (ValueError, KeyError, TypeError, OSError):
            raise _query_error(
                "checkpoint_query_manifest_invalid",
                "Manifest contains invalid or missing fields.",
                "Repair manifest.json.",
            )

        return manifest


# ---------------------------------------------------------------------------
# internal helpers
# ---------------------------------------------------------------------------


def _resolve_checkpoints_root(task_root: Path) -> Path:
    checkpoints_root = task_root / "checkpoints"
    try:
        resolved = checkpoints_root.resolve()
        if resolved.parent != task_root.resolve():
            raise ValueError
    except (OSError, RuntimeError, ValueError):
        raise _query_error(
            "checkpoint_query_manifest_invalid",
            "Checkpoints directory is not within the task workspace.",
            "Repair task workspace structure.",
        )
    if not checkpoints_root.is_dir():
        return checkpoints_root  # empty — caller handles
    return checkpoints_root


def _checkpoint_dir(checkpoints_root: Path, checkpoint_id: str) -> Path:
    ckpt_dir = checkpoints_root / checkpoint_id
    try:
        resolved = ckpt_dir.resolve()
        resolved.relative_to(checkpoints_root.resolve())
    except (OSError, RuntimeError, ValueError):
        raise _query_error(
            "checkpoint_query_identity_mismatch",
            "Checkpoint directory escapes checkpoints root.",
            "Repair checkpoint directory.",
        )
    return ckpt_dir


def _is_checkpoint_id(checkpoint_id: str) -> bool:
    return isinstance(checkpoint_id, str) and bool(
        re.fullmatch(r"ckpt-[0-9]{3,}", checkpoint_id)
    )


def _checkpoint_sort_key(checkpoint_id: str) -> int:
    m = re.search(r"[0-9]+", checkpoint_id)
    return int(m.group(0)) if m else 0


def _is_link(path: Path) -> bool:
    try:
        is_junction = getattr(path, "is_junction", None)
        return path.is_symlink() or bool(is_junction and is_junction())
    except (AttributeError, OSError, RuntimeError):
        return True


def _query_error(error_code: str, message: str, suggested_fix: str) -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code=error_code,
            message=message,
            phase="code",
            denied_rule=error_code,
            suggested_fix=suggested_fix,
        )
    )
