"""Deterministic workspace path classification for writable actions."""

from __future__ import annotations

from enum import Enum
from fnmatch import fnmatchcase
from pathlib import Path, PureWindowsPath

from hancode.config import HanCodeConfig


class PathZone(str, Enum):
    """The single authoritative classification for a workspace path."""

    PROTECTED = "protected"
    ARTIFACT = "artifact"
    SOURCE = "source"
    OUT_OF_SCOPE = "out_of_scope"


_ARTIFACT_NAMES = frozenset(
    {
        "SPEC.md",
        "PLAN.md",
        "TEST_REPORT.md",
        "REVIEW.md",
        "KNOWLEDGE.md",
        "DELIVERABLES.md",
    }
)
_MACHINE_FILE_NAMES = frozenset({"state.json", "history.jsonl", "trace.jsonl"})


class PathClassifier:
    """Classify project-relative targets using the configured workspace policy."""

    def __init__(self, config: HanCodeConfig) -> None:
        self._config = config

    def classify(self, target: str) -> PathZone:
        """Return a fail-closed zone for *target* without performing any writes."""
        if not target.strip() or self._is_absolute(target):
            return PathZone.OUT_OF_SCOPE

        try:
            workspace_root = self._config.allowed_workspace_root.resolve()
            lexical_candidate = workspace_root / Path(target)
            lexical_relative = lexical_candidate.relative_to(workspace_root).as_posix()
            canonical_candidate = lexical_candidate.resolve()
            canonical_relative = canonical_candidate.relative_to(workspace_root).as_posix()
        except (OSError, RuntimeError, ValueError):
            return PathZone.OUT_OF_SCOPE

        task_root = self._resolve_task_root(workspace_root)
        if self._matches_protected(lexical_relative, canonical_relative) or self._is_machine_file(
            task_root, canonical_candidate
        ):
            return PathZone.PROTECTED
        if self._is_artifact(task_root, canonical_candidate):
            return PathZone.ARTIFACT
        if self._is_task_file(task_root, canonical_candidate):
            return PathZone.OUT_OF_SCOPE
        if self._is_source(workspace_root, canonical_candidate):
            return PathZone.SOURCE
        return PathZone.OUT_OF_SCOPE

    @staticmethod
    def _is_absolute(target: str) -> bool:
        windows_path = PureWindowsPath(target)
        return Path(target).is_absolute() or windows_path.is_absolute() or bool(windows_path.drive)

    def _matches_protected(self, *relative_paths: str) -> bool:
        patterns = tuple(self._normalise(pattern) for pattern in self._config.protected_patterns)
        return any(
            fnmatchcase(self._normalise(relative_path), pattern)
            for relative_path in relative_paths
            for pattern in patterns
        )

    def _resolve_task_root(self, workspace_root: Path) -> Path | None:
        task_root = self._config.task_root
        if task_root is None:
            return None
        try:
            resolved_task_root = task_root.resolve()
            resolved_task_root.relative_to(workspace_root)
        except (OSError, RuntimeError, ValueError):
            return None
        return resolved_task_root

    @staticmethod
    def _is_machine_file(task_root: Path | None, candidate: Path) -> bool:
        if task_root is None:
            return False
        try:
            relative_path = candidate.relative_to(task_root).as_posix().casefold()
        except ValueError:
            return False
        return relative_path in _MACHINE_FILE_NAMES or relative_path.startswith("checkpoints/")

    @staticmethod
    def _is_artifact(task_root: Path | None, candidate: Path) -> bool:
        if task_root is None:
            return False
        try:
            relative_path = candidate.relative_to(task_root)
        except ValueError:
            return False
        return len(relative_path.parts) == 1 and relative_path.name in _ARTIFACT_NAMES

    @staticmethod
    def _is_task_file(task_root: Path | None, candidate: Path) -> bool:
        if task_root is None:
            return False
        try:
            candidate.relative_to(task_root)
        except ValueError:
            return False
        return True

    def _is_source(self, workspace_root: Path, candidate: Path) -> bool:
        for writable_root in self._config.writable_roots:
            try:
                resolved_writable_root = writable_root.resolve()
                resolved_writable_root.relative_to(workspace_root)
                candidate.relative_to(resolved_writable_root)
            except (OSError, RuntimeError, ValueError):
                continue
            return True
        return False

    @staticmethod
    def _normalise(relative_path: str) -> str:
        return relative_path.replace("\\", "/").removeprefix("./").casefold()
