"""Checkpoint-based diff tool — S4-R1.

get_diff produces a unified diff by comparing checkpoint before-snapshots
against current workspace files.  It does NOT depend on Git.
"""

from __future__ import annotations

import difflib
from hashlib import sha256
from pathlib import Path

from hancode.core.change_models import ChangeType, DiffScope, FileDiff, TaskDiff
from hancode.core.errors import HanCodeError
from hancode.core.state import load_state
from hancode.storage.checkpoint_queries import CheckpointQueryRepository
from hancode.tooling.file_tools import redact_text
from hancode.tooling.registry import ToolResult


# Default bounds (see §8.7 of S4-R design)
_DEFAULT_MAX_DIFF_FILES = 100
_DEFAULT_MAX_DIFF_CHARS = 30_000
_DEFAULT_MAX_DIFF_FILE_BYTES = 524_288
_DEFAULT_DIFF_CONTEXT_LINES = 3

# Hard caps
_HARD_MAX_DIFF_FILES = 500
_HARD_MAX_DIFF_CHARS = 100_000
_HARD_MAX_DIFF_FILE_BYTES = 2 * 1024 * 1024  # 2 MiB

# Binary detection: look for null bytes in first 8KB
_BINARY_CHECK_BYTES = 8192


def get_diff(
    project_root: Path,
    task_root: Path,
    *,
    scope: str = "task",
    path: str | None = None,
    max_diff_files: int = _DEFAULT_MAX_DIFF_FILES,
    max_diff_chars: int = _DEFAULT_MAX_DIFF_CHARS,
    max_diff_file_bytes: int = _DEFAULT_MAX_DIFF_FILE_BYTES,
    context_lines: int = _DEFAULT_DIFF_CONTEXT_LINES,
) -> ToolResult:
    # --- clamp bounds ---
    max_diff_files = min(max(max_diff_files, 1), _HARD_MAX_DIFF_FILES)
    max_diff_chars = min(max(max_diff_chars, 1), _HARD_MAX_DIFF_CHARS)
    max_diff_file_bytes = min(max(max_diff_file_bytes, 1), _HARD_MAX_DIFF_FILE_BYTES)

    # --- parse scope ---
    try:
        diff_scope = DiffScope(scope)
    except ValueError:
        return ToolResult(
            success=False,
            action_name="get_diff",
            error_summary=f"Invalid diff scope: {scope!r}. Use 'task' or 'latest'.",
        )

    project_root = project_root.resolve()
    task_root = task_root.resolve()
    task_id = task_root.name

    repo = CheckpointQueryRepository()
    try:
        all_manifests = repo.list(task_root)
    except (HanCodeError, OSError):
        return _diff_failure("Checkpoint manifest or snapshot validation failed.")

    # Filter to trusted statuses
    trusted = [
        m for m in all_manifests
        if m.status in ("committed", "rolled_back")
    ]

    if diff_scope is DiffScope.LATEST:
        state = load_state(task_root)
        latest_id = state.latest_checkpoint
        if latest_id is None:
            return _empty_diff(task_id, diff_scope, "no_latest_checkpoint")
        trusted = [m for m in trusted if m.checkpoint_id == latest_id]
        if not trusted:
            return _empty_diff(task_id, diff_scope, "latest_checkpoint_not_committed")

    if not trusted:
        return _empty_diff(task_id, diff_scope, "no_trusted_checkpoints")

    # --- Find the earliest checkpoint per file (task scope) ---
    # For task scope, for each file, find the earliest checkpoint that includes it.
    # The baseline is the before_snapshot in that earliest checkpoint.
    file_baselines: dict[str, tuple[str, bytes]] = {}  # path -> (checkpoint_id, before_content)
    file_actions: dict[str, str] = {}
    file_after_hashes: dict[str, str | None] = {}

    for manifest in trusted:
        for f in manifest.files:
            if f.path not in file_baselines:
                if f.action == "create":
                    file_baselines[f.path] = (manifest.checkpoint_id, b"")
                    file_actions[f.path] = "create"
                else:
                    try:
                        content = repo.read_before(
                            task_root,
                            manifest.checkpoint_id,
                            f.path,
                            max_bytes=max_diff_file_bytes,
                        )
                    except (HanCodeError, OSError):
                        return _diff_failure(
                            "Checkpoint snapshot could not be read safely."
                        )
                    if content is not None:
                        file_baselines[f.path] = (manifest.checkpoint_id, content)
                        file_actions[f.path] = "modify"
            file_after_hashes[f.path] = f.after_sha256

    # --- Filter by path if requested ---
    if path is not None:
        file_baselines = {k: v for k, v in file_baselines.items() if k == path}
        if not file_baselines:
            return _empty_diff(task_id, diff_scope, "path_not_in_checkpoints")

    # --- Build FileDiffs ---
    truncated = False
    total_chars = 0
    file_diffs: list[FileDiff] = []
    checkpoint_ids: list[str] = []

    for file_path, (ckpt_id, before_bytes) in sorted(file_baselines.items()):
        if len(file_diffs) >= max_diff_files:
            truncated = True
            break

        if ckpt_id not in checkpoint_ids:
            checkpoint_ids.append(ckpt_id)

        workspace_file = project_root / file_path
        action = file_actions.get(file_path, "modify")

        if len(before_bytes) > max_diff_file_bytes:
            return _diff_failure("Checkpoint file exceeds the configured diff size limit.")

        # Determine change type
        if action == "create":
            change_type = ChangeType.CREATED
            before_sha = None
        elif not workspace_file.exists():
            change_type = ChangeType.DELETED
            before_sha = sha256(before_bytes).hexdigest() if before_bytes else None
        else:
            change_type = ChangeType.MODIFIED
            before_sha = sha256(before_bytes).hexdigest() if before_bytes else None

        current_sha: str | None = None
        current_bytes: bytes | None = None
        binary = False

        try:
            resolved_workspace_file = workspace_file.resolve()
            resolved_workspace_file.relative_to(project_root)
        except (OSError, RuntimeError, ValueError):
            return _diff_failure("Workspace file is outside the project root.")

        if workspace_file.exists():
            try:
                if workspace_file.stat().st_size > max_diff_file_bytes:
                    return _diff_failure(
                        "Workspace file exceeds the configured diff size limit."
                    )
                # Keep bounded raw bytes for binary hashing; only text diff
                # generation is disabled for binary content.
                with open(workspace_file, "rb") as fh:
                    raw_bytes = fh.read(max_diff_file_bytes)
                if b"\x00" in raw_bytes[:_BINARY_CHECK_BYTES]:
                    binary = True
                    current_bytes = raw_bytes
                else:
                    try:
                        current_text = raw_bytes.decode("utf-8")
                        current_bytes = current_text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
                    except UnicodeDecodeError:
                        binary = True
                        current_bytes = raw_bytes
            except OSError:
                return _diff_failure("Workspace file could not be read safely.")
            if current_bytes is not None:
                current_sha = sha256(current_bytes).hexdigest()
        elif change_type is ChangeType.DELETED:
            current_bytes = b""
            current_sha = sha256(current_bytes).hexdigest()

        # Drift detection: compare after_sha256 (from last checkpoint) to current workspace
        drifted = False
        last_after = file_after_hashes.get(file_path)
        if last_after is not None and current_sha is not None and last_after != current_sha:
            drifted = True

        # Generate unified diff
        unified_diff: str | None = None
        if (
            not binary
            and change_type in {ChangeType.CREATED, ChangeType.MODIFIED, ChangeType.DELETED}
            and before_bytes is not None
            and current_bytes is not None
        ):
            before_text = _safe_decode(before_bytes)
            current_text = _safe_decode(current_bytes)
            before_lines = before_text.splitlines(keepends=True)
            current_lines = current_text.splitlines(keepends=True)

            diff_lines = list(
                difflib.unified_diff(
                    before_lines,
                    current_lines,
                    fromfile=f"before/{file_path}",
                    tofile=f"current/{file_path}",
                    n=context_lines,
                )
            )
            raw_diff = "".join(diff_lines)
            # Truncate diff
            if total_chars + len(raw_diff) > max_diff_chars:
                # Truncate at hunk boundary
                available = max_diff_chars - total_chars
                raw_diff = _truncate_at_hunk_boundary(raw_diff, available)
                truncated = True

            total_chars += len(raw_diff)
            # Redact secrets from diff
            unified_diff = redact_text(raw_diff)

        file_diffs.append(
            FileDiff(
                path=file_path,
                change_type=change_type,
                before_sha256=before_sha,
                current_sha256=current_sha,
                binary=binary,
                drifted=drifted,
                unified_diff=unified_diff,
                truncated=truncated,
            )
        )

    risks: list[str] = []
    if truncated:
        risks.append("diff_output_truncated")
    if any(f.drifted for f in file_diffs):
        risks.append("workspace_changed_after_checkpoint")

    task_diff = TaskDiff(
        task_id=task_id,
        scope=diff_scope,
        checkpoint_ids=tuple(checkpoint_ids),
        files=tuple(file_diffs),
        truncated=truncated,
        risks=tuple(risks),
    )

    return ToolResult(
        success=True,
        action_name="get_diff",
        output=_task_diff_to_dict(task_diff),
    )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _task_diff_to_dict(td: TaskDiff) -> dict[str, object]:
    return {
        "task_id": td.task_id,
        "scope": td.scope.value,
        "checkpoint_ids": list(td.checkpoint_ids),
        "files": [
            {
                "path": f.path,
                "change_type": f.change_type.value,
                "before_sha256": f.before_sha256,
                "current_sha256": f.current_sha256,
                "binary": f.binary,
                "drifted": f.drifted,
                "unified_diff": f.unified_diff,
                "truncated": f.truncated,
            }
            for f in td.files
        ],
        "truncated": td.truncated,
        "risks": list(td.risks),
    }


def _empty_diff(task_id: str, scope: DiffScope, risk: str) -> ToolResult:
    return ToolResult(
        success=True,
        action_name="get_diff",
        output={
            "task_id": task_id,
            "scope": scope.value,
            "checkpoint_ids": [],
            "files": [],
            "truncated": False,
            "risks": [risk],
        },
    )


def _diff_failure(message: str) -> ToolResult:
    return ToolResult(success=False, action_name="get_diff", error_summary=message)


def _safe_decode(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def _truncate_at_hunk_boundary(text: str, max_chars: int) -> str:
    """Truncate text at the last complete hunk boundary within max_chars."""
    if len(text) <= max_chars:
        return text
    # Find last @@ line
    truncated = text[:max_chars]
    last_hunk = truncated.rfind("\n@@")
    if last_hunk > 0:
        return truncated[:last_hunk] + "\n"
    return truncated
