"""Task-scoped mutation locks shared by all state-changing services."""

from __future__ import annotations

from contextlib import AbstractContextManager, contextmanager
from collections.abc import Callable
import os
from pathlib import Path
from typing import Iterator, Protocol
import uuid

from hancode.core.errors import HanCodeError, StructuredError
from hancode.core.models import Phase
from hancode.storage.workspace import task_path


class TaskMutationGuard(Protocol):
    def acquire(self, task_id: str, phase: Phase) -> AbstractContextManager[None]: ...


class FilesystemTaskMutationGuard:
    """Create an exclusive lock file inside one task workspace."""

    def __init__(
        self,
        project_root: Path,
        *,
        task_path_resolver: Callable[[Path, str], Path] = task_path,
    ) -> None:
        self._project_root = project_root.resolve()
        self._task_path_resolver = task_path_resolver

    @contextmanager
    def acquire(self, task_id: str, phase: Phase) -> Iterator[None]:
        lock_path = self._task_path_resolver(self._project_root, task_id) / ".agent-loop.lock"
        owner_token = uuid.uuid4().hex
        try:
            file_descriptor = os.open(
                lock_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
        except FileExistsError as exc:
            raise HanCodeError(
                StructuredError(
                    error_code="mutation_lock_busy",
                    message="Another agent run holds the task mutation lock.",
                    phase=phase.value,
                    denied_rule="single_task_mutator_required",
                    suggested_fix="Wait for the active task run to finish before retrying.",
                )
            ) from exc
        except OSError as exc:
            raise HanCodeError(
                StructuredError(
                    error_code="mutation_lock_unavailable",
                    message="The task mutation lock could not be acquired.",
                    phase=phase.value,
                    denied_rule="mutation_lock_required",
                    suggested_fix="Restore task workspace lock-file access before retrying.",
                )
            ) from exc

        cleanup_failed = False
        owner_changed = False
        try:
            os.write(
                file_descriptor,
                f"owner={owner_token};pid={os.getpid()}\n".encode("ascii"),
            )
            yield
        finally:
            try:
                os.close(file_descriptor)
            except OSError:
                cleanup_failed = True
            try:
                current_owner = lock_path.read_text(encoding="ascii").strip()
                if current_owner != f"owner={owner_token};pid={os.getpid()}".strip():
                    owner_changed = True
                else:
                    lock_path.unlink()
            except (OSError, UnicodeError):
                cleanup_failed = True
            if cleanup_failed or owner_changed:
                raise HanCodeError(
                    StructuredError(
                        error_code=(
                            "mutation_lock_owner_changed"
                            if owner_changed
                            else "mutation_lock_release_failed"
                        ),
                        message="The task mutation lock could not be released.",
                        phase=phase.value,
                        denied_rule="mutation_lock_release_required",
                        suggested_fix="Restore task workspace lock-file access.",
                    )
                )


__all__ = ["FilesystemTaskMutationGuard", "TaskMutationGuard"]
