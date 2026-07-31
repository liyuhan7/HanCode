"""Tool adapter for recording deterministic test-remediation decisions."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime, timezone

from hancode.core.config import HanCodeConfig
from hancode.core.errors import HanCodeError
from hancode.core.test_remediation import (
    RemediationDecision,
    RemediationKind,
    digest_remediation,
)
from hancode.policy.path_policy import (
    PathClassifier,
    PathZone,
    normalize_project_relative_path,
)
from hancode.storage.test_remediations import TestRemediationStore
from hancode.core.state import load_state
from hancode.tooling.file_tools import redact_text
from hancode.tooling.registry import ToolResult


def record_remediation(
    config: HanCodeConfig,
    *,
    failure_digest: str,
    kind: str,
    diagnosis: str,
    planned_paths: Sequence[str],
    question: str | None,
) -> ToolResult:
    if config.task_root is None:
        return _failed("A task workspace is required.")
    try:
        state = load_state(config.task_root)
        store = TestRemediationStore(config.project_root)
        failure = store.load_failure(config.task_root.name)
        remediation_kind = RemediationKind(kind)
    except (HanCodeError, TypeError, ValueError):
        return _failed("The active test failure is invalid.")

    if (
        state.latest_test_status != "failed"
        or state.latest_test_failure_digest is None
        or failure.digest != state.latest_test_failure_digest
        or failure_digest != failure.digest
    ):
        return _failed("The remediation decision is stale.")

    try:
        paths = tuple(dict.fromkeys(normalize_project_relative_path(path) for path in planned_paths))
    except ValueError:
        return _failed("Remediation paths must be clean project-relative paths.")
    if remediation_kind in {
        RemediationKind.MODIFY_SOURCE,
        RemediationKind.MODIFY_TEST,
    }:
        if not paths:
            return _failed("A modifying remediation requires planned paths.")
        classifier = PathClassifier(config)
        if any(classifier.classify(path) is not PathZone.SOURCE for path in paths):
            return _failed("Remediation paths must be writable, project-relative source paths.")
    elif paths:
        return _failed("This remediation kind does not accept planned paths.")

    if remediation_kind is RemediationKind.MODIFY_TEST and any(
        not _looks_like_test_path(path) for path in paths
    ):
        return _failed("modify_test may target only unprotected test files.")
    if failure.category.value == "environment_error" and remediation_kind in {
        RemediationKind.MODIFY_SOURCE,
        RemediationKind.MODIFY_TEST,
        RemediationKind.RERUN_FOR_DIAGNOSIS,
    }:
        return _failed("Environment failures require a runner replacement, input, or rollback.")
    if remediation_kind is RemediationKind.REQUEST_INPUT:
        if question is None or not question.strip() or len(question) > 1000:
            return _failed("request_input requires one bounded question.")
        if config.interaction_mode != "ask_user":
            return _failed("Human interaction is disabled for this task.")
    elif question is not None:
        return _failed("Only request_input may contain a question.")
    if remediation_kind is RemediationKind.RERUN_FOR_DIAGNOSIS and not (
        failure.category.value == "unknown"
        or failure.legacy_evidence
        or failure.diagnostic_excerpt == "No diagnostic output was captured."
    ):
        return _failed("The current failure already has actionable diagnostics.")
    if (
        remediation_kind is RemediationKind.RERUN_FOR_DIAGNOSIS
        and failure.diagnostic_rerun_count >= 1
    ):
        return _failed("The diagnostic rerun limit has been reached.")
    if remediation_kind is RemediationKind.ROLLBACK and state.latest_checkpoint is None:
        return _failed("No checkpoint is available for rollback.")

    safe_diagnosis = redact_text(diagnosis.strip())[:2000]
    safe_question = None if question is None else redact_text(question.strip())[:1000]
    if not safe_diagnosis:
        return _failed("A remediation diagnosis is required.")
    decision = RemediationDecision(
        schema_version=1,
        task_id=state.task_id,
        failure_digest=failure.digest,
        kind=remediation_kind,
        diagnosis=safe_diagnosis,
        planned_paths=paths,
        question=safe_question,
        created_at=datetime.now(timezone.utc).isoformat(),
        digest="pending",
    )
    decision = replace(decision, digest=digest_remediation(decision))
    try:
        store.save_remediation(decision)
    except (HanCodeError, OSError, UnicodeError):
        return _failed("The remediation decision could not be persisted.")
    return ToolResult(
        success=True,
        action_name="record_remediation",
        output={
            "remediation_digest": decision.digest,
            "failure_digest": decision.failure_digest,
            "kind": decision.kind.value,
            "planned_paths": list(decision.planned_paths),
        },
        mutation_applied=True,
    )


def _looks_like_test_path(path: str) -> bool:
    normalized = path.replace("\\", "/").casefold()
    name = normalized.rsplit("/", 1)[-1]
    return (
        "/test" in f"/{normalized}"
        or name.startswith("test_")
        or name.endswith(("_test.py", ".test.js", ".test.ts", ".spec.js", ".spec.ts"))
    )


def _failed(message: str) -> ToolResult:
    return ToolResult(
        success=False,
        action_name="record_remediation",
        error_summary=message,
        mutation_applied=False,
    )
