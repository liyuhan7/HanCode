"""Domain models for S4 change inspection — diffs, checkpoints, and summaries.

All models are frozen, hashable, and do not expose absolute paths, internal
snapshot directories, or raw file contents.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from hancode.core.models import Phase


class ChangeType(str, Enum):
    CREATED = "created"
    MODIFIED = "modified"
    DELETED = "deleted"


class DiffScope(str, Enum):
    LATEST = "latest"
    TASK = "task"


@dataclass(frozen=True, slots=True)
class FileDiff:
    path: str
    change_type: ChangeType
    before_sha256: str | None
    current_sha256: str | None
    binary: bool
    drifted: bool
    unified_diff: str | None
    truncated: bool


@dataclass(frozen=True, slots=True)
class TaskDiff:
    task_id: str
    scope: DiffScope
    checkpoint_ids: tuple[str, ...]
    files: tuple[FileDiff, ...]
    truncated: bool
    risks: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CheckpointSummary:
    """Public-facing checkpoint summary.

    MUST NOT expose: before_snapshot internal paths, absolute paths, raw file
    contents, or internal temp directories.
    """

    checkpoint_id: str
    phase: Phase
    reason: str
    created_at: str
    status: str
    files: tuple[str, ...]
    rollback_available: bool
