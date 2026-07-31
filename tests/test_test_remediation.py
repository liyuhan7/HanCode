from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from hancode.core.test_remediation import (
    FailureCategory,
    RemediationDecision,
    RemediationKind,
    TestFailureRecord,
    digest_remediation,
    digest_test_failure,
)
from hancode.storage.test_remediations import TestRemediationStore
from hancode.core.errors import HanCodeError
from hancode.runtime.test_remediation import build_test_failure_record


def test_failure_record_round_trips_with_canonical_digest() -> None:
    record = TestFailureRecord(
        schema_version=1,
        task_id="task-001",
        attempt_id="test-000001",
        strategy_digest="a" * 64,
        command_digest="b" * 64,
        category=FailureCategory.ASSERTION_FAILURE,
        exit_code=1,
        timed_out=False,
        passed_count=2,
        failed_count=1,
        failed_tests=("tests/test_widget.py::test_widget",),
        diagnostic_excerpt="AssertionError: expected widget",
        fingerprint="c" * 64,
        repeat_count=0,
        diagnostic_rerun_count=0,
        legacy_evidence=False,
        created_at="2026-07-31T00:00:00+00:00",
        digest="pending",
    )
    record = replace(record, digest=digest_test_failure(record))

    assert TestFailureRecord.from_dict(record.to_dict()) == record


def test_remediation_decision_round_trips_with_canonical_digest() -> None:
    decision = RemediationDecision(
        schema_version=1,
        task_id="task-001",
        failure_digest="a" * 64,
        kind=RemediationKind.MODIFY_SOURCE,
        diagnosis="The implementation violates the asserted behavior.",
        planned_paths=("src/widget.py",),
        question=None,
        created_at="2026-07-31T00:01:00+00:00",
        digest="pending",
    )
    decision = replace(decision, digest=digest_remediation(decision))

    assert RemediationDecision.from_dict(decision.to_dict()) == decision


def test_store_atomically_round_trips_latest_failure(tmp_path: Path) -> None:
    task_root = tmp_path / ".hancode" / "tasks" / "task-001"
    task_root.mkdir(parents=True)
    record = TestFailureRecord(
        schema_version=1,
        task_id="task-001",
        attempt_id="test-000001",
        strategy_digest=None,
        command_digest=None,
        category=FailureCategory.ENVIRONMENT_ERROR,
        exit_code=1,
        timed_out=False,
        passed_count=0,
        failed_count=0,
        failed_tests=(),
        diagnostic_excerpt="Bash/Service/CreateInstance/E_ACCESSDENIED",
        fingerprint="c" * 64,
        repeat_count=0,
        diagnostic_rerun_count=0,
        legacy_evidence=False,
        created_at="2026-07-31T00:02:00+00:00",
        digest="pending",
    )
    record = replace(record, digest=digest_test_failure(record))
    store = TestRemediationStore(tmp_path)

    store.save_failure(record)

    assert store.load_failure("task-001") == record


def test_store_atomically_round_trips_latest_remediation(tmp_path: Path) -> None:
    task_root = tmp_path / ".hancode" / "tasks" / "task-001"
    task_root.mkdir(parents=True)
    decision = RemediationDecision(
        schema_version=1,
        task_id="task-001",
        failure_digest="a" * 64,
        kind=RemediationKind.REPLACE_TEST_STRATEGY,
        diagnosis="The registered shell runner cannot start on Windows.",
        planned_paths=(),
        question=None,
        created_at="2026-07-31T00:03:00+00:00",
        digest="pending",
    )
    decision = replace(decision, digest=digest_remediation(decision))
    store = TestRemediationStore(tmp_path)

    store.save_remediation(decision)

    assert store.load_remediation("task-001") == decision


def test_failure_builder_normalizes_project_paths_and_line_endings(
    tmp_path: Path,
) -> None:
    first = build_test_failure_record(
        task_id="task-001",
        attempt_seq=1,
        strategy_digest="a" * 64,
        command_argv=("pytest", "-q"),
        category=FailureCategory.ASSERTION_FAILURE,
        exit_code=1,
        timed_out=False,
        passed_count=2,
        failed_count=1,
        output=f"FAILED {tmp_path}\\tests\\test_widget.py::test_widget\r\nAssertionError\r\n",
        project_root=tmp_path,
        created_at="2026-07-31T00:04:00+00:00",
    )
    second = build_test_failure_record(
        task_id="task-001",
        attempt_seq=2,
        strategy_digest="a" * 64,
        command_argv=("pytest", "-q"),
        category=FailureCategory.ASSERTION_FAILURE,
        exit_code=1,
        timed_out=False,
        passed_count=2,
        failed_count=1,
        output="FAILED <PROJECT_ROOT>/tests/test_widget.py::test_widget\nAssertionError\n",
        project_root=tmp_path,
        previous=first,
        created_at="2026-07-31T00:05:00+00:00",
    )

    assert first.fingerprint == second.fingerprint
    assert second.repeat_count == 1
    assert second.failed_tests == ("<PROJECT_ROOT>/tests/test_widget.py::test_widget",)


def test_failure_fingerprint_ignores_dynamic_duration(tmp_path: Path) -> None:
    common = {
        "task_id": "task-001",
        "strategy_digest": None,
        "command_argv": None,
        "category": FailureCategory.ASSERTION_FAILURE,
        "exit_code": 1,
        "timed_out": False,
        "passed_count": 0,
        "failed_count": 1,
        "project_root": tmp_path,
    }

    first = build_test_failure_record(
        **common,
        attempt_seq=1,
        output="FAILED tests/test_app.py::test_app\n1 failed in 0.12s",
    )
    second = build_test_failure_record(
        **common,
        attempt_seq=2,
        output="FAILED tests/test_app.py::test_app\n1 failed in 9.87s",
    )

    assert first.fingerprint == second.fingerprint


def test_diagnostic_rerun_increments_only_for_same_fingerprint(tmp_path: Path) -> None:
    common = {
        "task_id": "task-001",
        "strategy_digest": None,
        "command_argv": None,
        "category": FailureCategory.UNKNOWN,
        "exit_code": 1,
        "timed_out": False,
        "passed_count": 0,
        "failed_count": 1,
        "project_root": tmp_path,
        "output": "runner output is incomplete",
    }
    first = build_test_failure_record(**common, attempt_seq=1)
    repeated = build_test_failure_record(
        **common,
        attempt_seq=2,
        previous=first,
        diagnostic_rerun_applied=True,
    )
    changed = build_test_failure_record(
        **{**common, "output": "runner output changed"},
        attempt_seq=3,
        previous=repeated,
        diagnostic_rerun_applied=True,
    )

    assert repeated.diagnostic_rerun_count == 1
    assert changed.diagnostic_rerun_count == 0


def test_store_rejects_invalid_digest_before_replacing_file(tmp_path: Path) -> None:
    task_root = tmp_path / ".hancode" / "tasks" / "task-001"
    task_root.mkdir(parents=True)
    store = TestRemediationStore(tmp_path)
    valid = build_test_failure_record(
        task_id="task-001",
        attempt_seq=1,
        strategy_digest=None,
        command_argv=None,
        category=FailureCategory.UNKNOWN,
        exit_code=1,
        timed_out=False,
        passed_count=0,
        failed_count=1,
        output="unknown runner output",
        project_root=tmp_path,
    )
    store.save_failure(valid)
    original = (task_root / "test_failure.json").read_bytes()

    with pytest.raises(HanCodeError):
        store.save_failure(replace(valid, digest="0" * 64))

    assert (task_root / "test_failure.json").read_bytes() == original
