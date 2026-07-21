"""Task-scoped mutation locks shared by all state-changing services."""

from __future__ import annotations

from contextlib import AbstractContextManager, contextmanager
from collections.abc import Callable
import os
from pathlib import Path
import sys
from typing import Iterator, Protocol
import uuid

from hancode.core.errors import HanCodeError, StructuredError
from hancode.core.models import Phase
from hancode.storage.workspace import task_path


def _is_process_alive(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        SYNCHRONIZE = 0x00100000
        handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _read_owner_pid(lock_path: Path) -> int | None:
    try:
        content = lock_path.read_text(encoding="ascii").strip()
        pid_part = content.split(";pid=")[-1] if ";pid=" in content else ""
        return int(pid_part) if pid_part else None
    except (OSError, UnicodeError, ValueError, IndexError):
        return None


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
            owner_pid = _read_owner_pid(lock_path)
            if owner_pid is not None and not _is_process_alive(owner_pid):
                try:
                    lock_path.unlink()
                except OSError:
                    pass
                else:
                    try:
                        file_descriptor = os.open(
                            lock_path,
                            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                            0o600,
                        )
                    except OSError:
                        pass
                    else:
                        yield from self._locked(
                            file_descriptor, lock_path, owner_token, phase
                        )
                        return
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

        yield from self._locked(
            file_descriptor, lock_path, owner_token, phase
        )

    def _locked(
        self,
        file_descriptor: int,
        lock_path: Path,
        owner_token: str,
        phase: Phase,
    ) -> Iterator[None]:
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
