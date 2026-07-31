"""Deterministic construction of bounded test-failure evidence."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from hancode.core.test_remediation import (
    FailureCategory,
    TestFailureRecord,
    digest_test_failure,
)
from hancode.core.test_strategy import digest_argv
from hancode.tooling.file_tools import redact_text


_ANSI_ESCAPE_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")
_FAILED_TEST_RE = re.compile(r"(?m)^FAILED\s+(\S+)")
_DURATION_RE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:ms|s|seconds?)\b", re.I)
_ISO_TIMESTAMP_RE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?\b"
)
_MAX_DIAGNOSTIC_CHARS = 4096


def build_test_failure_record(
    *,
    task_id: str,
    attempt_seq: int,
    strategy_digest: str | None,
    command_argv: tuple[str, ...] | None,
    category: FailureCategory,
    exit_code: int | None,
    timed_out: bool,
    passed_count: int,
    failed_count: int,
    output: str,
    project_root: Path,
    previous: TestFailureRecord | None = None,
    diagnostic_rerun_applied: bool = False,
    legacy_evidence: bool = False,
    created_at: str | None = None,
) -> TestFailureRecord:
    """Build the latest immutable failure record from sanitized runner output."""

    diagnostic = _normalize_diagnostic(output, project_root)
    failed_tests = tuple(dict.fromkeys(_FAILED_TEST_RE.findall(diagnostic)))
    fingerprint = _fingerprint(
        category=category,
        exit_code=exit_code,
        timed_out=timed_out,
        failed_tests=failed_tests,
        diagnostic=diagnostic,
    )
    repeat_count = (
        previous.repeat_count + 1
        if previous is not None and previous.fingerprint == fingerprint
        else 0
    )
    diagnostic_rerun_count = (
        previous.diagnostic_rerun_count + 1
        if (
            diagnostic_rerun_applied
            and previous is not None
            and previous.fingerprint == fingerprint
        )
        else 0
    )
    record = TestFailureRecord(
        schema_version=1,
        task_id=task_id,
        attempt_id=f"test-{attempt_seq:06d}",
        strategy_digest=strategy_digest,
        command_digest=None if command_argv is None else digest_argv(command_argv),
        category=category,
        exit_code=exit_code,
        timed_out=timed_out,
        passed_count=passed_count,
        failed_count=failed_count,
        failed_tests=failed_tests,
        diagnostic_excerpt=diagnostic,
        fingerprint=fingerprint,
        repeat_count=repeat_count,
        diagnostic_rerun_count=diagnostic_rerun_count,
        legacy_evidence=legacy_evidence,
        created_at=created_at or datetime.now(timezone.utc).isoformat(),
        digest="pending",
    )
    return replace(record, digest=digest_test_failure(record))


def _normalize_diagnostic(output: str, project_root: Path) -> str:
    safe = redact_text(_ANSI_ESCAPE_RE.sub("", output))
    normalized = safe.replace("\r\n", "\n").replace("\r", "\n").replace("\\", "/")
    project = project_root.resolve(strict=False).as_posix().rstrip("/")
    if project:
        normalized = re.sub(re.escape(project), "<PROJECT_ROOT>", normalized, flags=re.I)
    normalized = "\n".join(
        re.sub(r"[ \t]+", " ", line).strip() for line in normalized.splitlines()
    ).strip()
    if not normalized:
        normalized = "No diagnostic output was captured."
    return normalized[:_MAX_DIAGNOSTIC_CHARS]


def _fingerprint(
    *,
    category: FailureCategory,
    exit_code: int | None,
    timed_out: bool,
    failed_tests: tuple[str, ...],
    diagnostic: str,
) -> str:
    payload = json.dumps(
        {
            "category": category.value,
            "exit_code": exit_code,
            "timed_out": timed_out,
            "failed_tests": list(failed_tests),
            "diagnostic": _normalize_dynamic_values(diagnostic),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _normalize_dynamic_values(value: str) -> str:
    value = _ISO_TIMESTAMP_RE.sub("<TIMESTAMP>", value)
    return _DURATION_RE.sub("<DURATION>", value)
