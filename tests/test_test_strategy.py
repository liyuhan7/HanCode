from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from hancode.core.errors import HanCodeError
from hancode.core.test_strategy import TestCoverageItem
from hancode.storage.test_strategies import TestStrategyStore
from hancode.storage.workspace import init_project_workspace, init_task_workspace


def _workspace(tmp_path: Path) -> tuple[Path, Path]:
    init_project_workspace(tmp_path, "project-001", "SE", "Harness")
    task_root = init_task_workspace(tmp_path, "task-001", goal="Add behavior.")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text(
        "def test_app():\n    assert True\n",
        encoding="utf-8",
    )
    return tmp_path, task_root


def _record(store: TestStrategyStore):
    return store.record(
        "task-001",
        command="python -m pytest tests/test_app.py -q",
        framework="pytest",
        test_files=("tests/test_app.py",),
        coverage=(
            TestCoverageItem(
                requirement="REQ-001",
                verification="test_app exercises the requested behavior",
            ),
        ),
    )


def test_record_and_load_binds_command_files_and_digest(tmp_path: Path) -> None:
    project_root, _task_root = _workspace(tmp_path)
    store = TestStrategyStore(project_root)

    strategy = _record(store)
    loaded = store.load("task-001")

    assert loaded == strategy
    assert strategy.command_argv == (
        "python",
        "-m",
        "pytest",
        "tests/test_app.py",
        "-q",
    )
    assert strategy.test_files[0].sha256 == hashlib.sha256(
        (project_root / "tests" / "test_app.py").read_bytes()
    ).hexdigest()
    assert len(strategy.digest) == 64
    assert store.validate(
        "task-001",
        expected_digest=strategy.digest,
        command=strategy.command,
    ) == strategy


def test_validate_rejects_test_file_drift(tmp_path: Path) -> None:
    project_root, _task_root = _workspace(tmp_path)
    store = TestStrategyStore(project_root)
    strategy = _record(store)
    (project_root / "tests" / "test_app.py").write_text(
        "def test_app():\n    assert False\n",
        encoding="utf-8",
    )

    with pytest.raises(HanCodeError) as error:
        store.validate(
            "task-001",
            expected_digest=strategy.digest,
            command=strategy.command,
        )

    assert error.value.structured_error.error_code == "test_strategy_stale"


def test_record_rejects_secret_bearing_command(tmp_path: Path) -> None:
    project_root, _task_root = _workspace(tmp_path)

    with pytest.raises(HanCodeError) as error:
        TestStrategyStore(project_root).record(
            "task-001",
            command="pytest --token live-secret",
            framework="pytest",
            test_files=("tests/test_app.py",),
            coverage=(
                TestCoverageItem(
                    requirement="REQ-001",
                    verification="test_app",
                ),
            ),
        )

    assert error.value.structured_error.error_code == "test_strategy_invalid"


def test_record_rejects_unavailable_test_command_executable(tmp_path: Path) -> None:
    project_root, _task_root = _workspace(tmp_path)

    with pytest.raises(HanCodeError) as error:
        TestStrategyStore(project_root).record(
            "task-001",
            command="missing-hancode-test-runner -q",
            framework="custom",
            test_files=("tests/test_app.py",),
            coverage=(
                TestCoverageItem(
                    requirement="REQ-001",
                    verification="test_app",
                ),
            ),
        )

    assert error.value.structured_error.error_code == "test_strategy_invalid"


def test_atomic_replace_failure_preserves_existing_strategy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root, task_root = _workspace(tmp_path)
    store = TestStrategyStore(project_root)
    _record(store)
    strategy_path = task_root / "test_strategy.json"
    original = strategy_path.read_bytes()

    def fail_replace(source: str | bytes | os.PathLike[str], target: str | bytes | os.PathLike[str]) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(OSError):
        _record(store)

    assert strategy_path.read_bytes() == original
    assert list(task_root.glob(".test_strategy_*.json")) == []
