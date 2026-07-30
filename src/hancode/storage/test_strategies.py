"""Atomic persistence for task-scoped test strategies."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import shlex
from tempfile import mkstemp
from typing import Iterable

from hancode.core.errors import HanCodeError, StructuredError
from hancode.core.test_strategy import (
    TestCoverageItem,
    TestFileEvidence,
    TestStrategy,
    digest_argv,
    digest_strategy,
)
from hancode.storage.workspace import task_path


_SHELL_OPERATOR_CHARS = frozenset("&|;<>$`\r\n")
_SENSITIVE_COMMAND_MARKERS = (
    "api_key",
    "apikey",
    "authorization",
    "bearer ",
    "password",
    "private_key",
    "secret",
    "token",
)


class TestStrategyStore:
    __test__ = False

    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root.resolve()

    def record(
        self,
        task_id: str,
        *,
        command: str,
        framework: str,
        test_files: Iterable[str],
        coverage: Iterable[TestCoverageItem],
    ) -> TestStrategy:
        argv = _parse_command(command)
        normalized_framework = framework.strip()
        coverage_items = tuple(coverage)
        if not normalized_framework or not coverage_items:
            raise _invalid(
                "Test framework and coverage evidence are required.",
                "Provide a framework and at least one requirement mapping.",
            )

        file_evidence = tuple(self._file_evidence(path) for path in test_files)
        if not file_evidence:
            raise _invalid(
                "At least one test file is required.",
                "Create or select a project test file before recording the strategy.",
            )

        created_at = datetime.now(timezone.utc).isoformat()
        strategy = TestStrategy(
            schema_version=1,
            task_id=task_id,
            framework=normalized_framework,
            command=command.strip(),
            command_argv=argv,
            command_digest=digest_argv(argv),
            test_files=file_evidence,
            coverage=coverage_items,
            created_at=created_at,
            digest="pending",
        )
        strategy = replace(strategy, digest=digest_strategy(strategy))
        _atomic_write_json(self._path(task_id), strategy.to_dict())
        return strategy

    def load(self, task_id: str) -> TestStrategy:
        path = self._path(task_id)
        if path.is_symlink() or not path.is_file():
            raise _invalid(
                "Test strategy is missing or unsafe.",
                "Record a valid test strategy during the code phase.",
            )
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Not a JSON object.")
            strategy = TestStrategy.from_dict(data)
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            raise _invalid(
                "Test strategy could not be loaded.",
                "Record the test strategy again during the code phase.",
            ) from exc
        if strategy.task_id != task_id:
            raise _invalid(
                "Test strategy task binding does not match.",
                "Record the test strategy again for this task.",
            )
        return strategy

    def validate(
        self,
        task_id: str,
        *,
        expected_digest: str | None,
        command: str,
    ) -> TestStrategy:
        strategy = self.load(task_id)
        if expected_digest is None or strategy.digest != expected_digest:
            raise _strategy_error(
                "test_strategy_stale",
                "Persisted test strategy does not match task state.",
                "Record the test strategy again during the code phase.",
            )
        try:
            argv = _parse_command(command)
        except HanCodeError as exc:
            raise _strategy_error(
                "test_command_mismatch",
                "Test command does not match the registered strategy.",
                "Run the exact command recorded by record_test_strategy.",
            ) from exc
        if digest_argv(argv) != strategy.command_digest:
            raise _strategy_error(
                "test_command_mismatch",
                "Test command does not match the registered strategy.",
                "Run the exact command recorded by record_test_strategy.",
            )
        for expected in strategy.test_files:
            try:
                current = self._file_evidence(expected.path)
            except HanCodeError as exc:
                raise _strategy_error(
                    "test_strategy_stale",
                    "A registered test file is missing or unsafe.",
                    "Repair the test file and record the strategy again.",
                ) from exc
            if current != expected:
                raise _strategy_error(
                    "test_strategy_stale",
                    "A registered test file changed after strategy recording.",
                    "Record the test strategy again after editing its test files.",
                )
        return strategy

    def _path(self, task_id: str) -> Path:
        return task_path(self._project_root, task_id) / "test_strategy.json"

    def _file_evidence(self, relative_path: str) -> TestFileEvidence:
        if (
            not isinstance(relative_path, str)
            or not relative_path.strip()
            or PurePosixPath(relative_path).is_absolute()
            or PureWindowsPath(relative_path).is_absolute()
        ):
            raise _invalid(
                "Test file path must be project-relative.",
                "Use a relative path inside the project root.",
            )
        candidate = self._project_root / Path(relative_path)
        if candidate.is_symlink():
            raise _invalid(
                "Linked test files cannot be registered.",
                "Use a regular test file inside the project root.",
            )
        resolved = candidate.resolve()
        if not resolved.is_relative_to(self._project_root) or not resolved.is_file():
            raise _invalid(
                "Test file is missing or outside the project root.",
                "Create a regular test file inside the project root.",
            )
        normalized = resolved.relative_to(self._project_root).as_posix()
        return TestFileEvidence(
            path=normalized,
            sha256=hashlib.sha256(resolved.read_bytes()).hexdigest(),
        )


def _parse_command(command: str) -> tuple[str, ...]:
    if not isinstance(command, str) or not command.strip():
        raise _invalid(
            "Test command is required.",
            "Provide one executable command without shell composition.",
        )
    if any(character in command for character in _SHELL_OPERATOR_CHARS):
        raise _invalid(
            "Shell syntax is not supported for test commands.",
            "Provide one argv-style test command.",
        )
    normalized_command = command.casefold()
    if any(marker in normalized_command for marker in _SENSITIVE_COMMAND_MARKERS):
        raise _invalid(
            "Test commands cannot contain credentials or secrets.",
            "Use credential-free test configuration and environment indirection.",
        )
    try:
        argv = tuple(shlex.split(command))
    except ValueError as exc:
        raise _invalid(
            "Test command is invalid.",
            "Provide one argv-style test command.",
        ) from exc
    if not argv:
        raise _invalid(
            "Test command is required.",
            "Provide one argv-style test command.",
        )
    return argv


def _atomic_write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise _invalid(
            "Linked test strategy files cannot be replaced.",
            "Remove the link and record the strategy again.",
        )
    file_descriptor, temporary_path = mkstemp(
        dir=str(path.parent),
        prefix=".test_strategy_",
        suffix=".json",
    )
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except Exception:
        try:
            os.unlink(temporary_path)
        except OSError:
            pass
        raise


def _invalid(message: str, suggested_fix: str) -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code="test_strategy_invalid",
            message=message,
            phase="code",
            denied_rule="valid_test_strategy_required",
            suggested_fix=suggested_fix,
        )
    )


def _strategy_error(
    error_code: str,
    message: str,
    suggested_fix: str,
) -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code=error_code,
            message=message,
            phase="test",
            denied_rule="registered_test_strategy_required",
            suggested_fix=suggested_fix,
        )
    )
