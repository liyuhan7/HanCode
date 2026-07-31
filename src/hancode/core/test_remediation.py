"""Immutable records for test failures and their remediation decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
from typing import Mapping


_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_ATTEMPT_ID_RE = re.compile(r"test-\d{6}")


class FailureCategory(str, Enum):
    NONE = "none"
    NO_TESTS = "no_tests"
    SYNTAX_ERROR = "syntax_error"
    IMPORT_ERROR = "import_error"
    ASSERTION_FAILURE = "assertion_failure"
    ERROR_EXCEPTION = "error_exception"
    ENVIRONMENT_ERROR = "environment_error"
    TIMEOUT_OR_CRASH = "timeout_or_crash"
    UNKNOWN = "unknown"


class RemediationKind(str, Enum):
    MODIFY_SOURCE = "modify_source"
    MODIFY_TEST = "modify_test"
    REPLACE_TEST_STRATEGY = "replace_test_strategy"
    RERUN_FOR_DIAGNOSIS = "rerun_for_diagnosis"
    REQUEST_INPUT = "request_input"
    ROLLBACK = "rollback"


@dataclass(frozen=True, slots=True)
class TestFailureRecord:
    __test__ = False

    schema_version: int
    task_id: str
    attempt_id: str
    strategy_digest: str | None
    command_digest: str | None
    category: FailureCategory
    exit_code: int | None
    timed_out: bool
    passed_count: int
    failed_count: int
    failed_tests: tuple[str, ...]
    diagnostic_excerpt: str
    fingerprint: str
    repeat_count: int
    diagnostic_rerun_count: int
    legacy_evidence: bool
    created_at: str
    digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "attempt_id": self.attempt_id,
            "strategy_digest": self.strategy_digest,
            "command_digest": self.command_digest,
            "category": self.category.value,
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "failed_tests": list(self.failed_tests),
            "diagnostic_excerpt": self.diagnostic_excerpt,
            "fingerprint": self.fingerprint,
            "repeat_count": self.repeat_count,
            "diagnostic_rerun_count": self.diagnostic_rerun_count,
            "legacy_evidence": self.legacy_evidence,
            "created_at": self.created_at,
            "digest": self.digest,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> TestFailureRecord:
        if frozenset(data) != frozenset(cls.__dataclass_fields__):
            raise ValueError("Test failure fields do not match schema.")
        failed_tests = data.get("failed_tests")
        if not isinstance(failed_tests, list) or not all(
            isinstance(item, str) and item for item in failed_tests
        ):
            raise ValueError("Invalid failed test identifiers.")
        record = cls(
            schema_version=_required_int(data, "schema_version"),
            task_id=_required_text(data, "task_id"),
            attempt_id=_required_text(data, "attempt_id"),
            strategy_digest=_optional_sha256(data, "strategy_digest"),
            command_digest=_optional_sha256(data, "command_digest"),
            category=FailureCategory(_required_text(data, "category")),
            exit_code=_optional_int(data, "exit_code"),
            timed_out=_required_bool(data, "timed_out"),
            passed_count=_required_nonnegative_int(data, "passed_count"),
            failed_count=_required_nonnegative_int(data, "failed_count"),
            failed_tests=tuple(failed_tests),
            diagnostic_excerpt=_required_text(data, "diagnostic_excerpt"),
            fingerprint=_required_sha256(data, "fingerprint"),
            repeat_count=_required_nonnegative_int(data, "repeat_count"),
            diagnostic_rerun_count=_required_nonnegative_int(
                data, "diagnostic_rerun_count"
            ),
            legacy_evidence=_required_bool(data, "legacy_evidence"),
            created_at=_required_text(data, "created_at"),
            digest=_required_sha256(data, "digest"),
        )
        if record.schema_version != 1:
            raise ValueError("Unsupported test failure schema version.")
        if _ATTEMPT_ID_RE.fullmatch(record.attempt_id) is None:
            raise ValueError("Invalid test attempt identifier.")
        if digest_test_failure(record) != record.digest:
            raise ValueError("Test failure digest does not match.")
        return record


@dataclass(frozen=True, slots=True)
class RemediationDecision:
    schema_version: int
    task_id: str
    failure_digest: str
    kind: RemediationKind
    diagnosis: str
    planned_paths: tuple[str, ...]
    question: str | None
    created_at: str
    digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "failure_digest": self.failure_digest,
            "kind": self.kind.value,
            "diagnosis": self.diagnosis,
            "planned_paths": list(self.planned_paths),
            "question": self.question,
            "created_at": self.created_at,
            "digest": self.digest,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> RemediationDecision:
        if frozenset(data) != frozenset(cls.__dataclass_fields__):
            raise ValueError("Remediation fields do not match schema.")
        planned_paths = data.get("planned_paths")
        if not isinstance(planned_paths, list) or not all(
            isinstance(item, str) and item for item in planned_paths
        ):
            raise ValueError("Invalid remediation paths.")
        question = data.get("question")
        if question is not None and (
            not isinstance(question, str) or not question.strip()
        ):
            raise ValueError("Invalid remediation question.")
        decision = cls(
            schema_version=_required_int(data, "schema_version"),
            task_id=_required_text(data, "task_id"),
            failure_digest=_required_sha256(data, "failure_digest"),
            kind=RemediationKind(_required_text(data, "kind")),
            diagnosis=_required_text(data, "diagnosis"),
            planned_paths=tuple(planned_paths),
            question=question,
            created_at=_required_text(data, "created_at"),
            digest=_required_sha256(data, "digest"),
        )
        if decision.schema_version != 1:
            raise ValueError("Unsupported remediation schema version.")
        if digest_remediation(decision) != decision.digest:
            raise ValueError("Remediation digest does not match.")
        return decision


def digest_test_failure(record: TestFailureRecord) -> str:
    data = record.to_dict()
    data.pop("digest", None)
    payload = json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def digest_remediation(decision: RemediationDecision) -> str:
    data = decision.to_dict()
    data.pop("digest", None)
    payload = json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _required_text(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Invalid test failure field: {key}.")
    return value


def _required_int(data: Mapping[str, object], key: str) -> int:
    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"Invalid test failure field: {key}.")
    return value


def _required_nonnegative_int(data: Mapping[str, object], key: str) -> int:
    value = _required_int(data, key)
    if value < 0:
        raise ValueError(f"Invalid test failure field: {key}.")
    return value


def _optional_int(data: Mapping[str, object], key: str) -> int | None:
    value = data.get(key)
    if value is None:
        return None
    return _required_int(data, key)


def _required_bool(data: Mapping[str, object], key: str) -> bool:
    value = data.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"Invalid test failure field: {key}.")
    return value


def _required_sha256(data: Mapping[str, object], key: str) -> str:
    value = _required_text(data, key)
    if _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"Invalid test failure field: {key}.")
    return value


def _optional_sha256(data: Mapping[str, object], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    return _required_sha256(data, key)
