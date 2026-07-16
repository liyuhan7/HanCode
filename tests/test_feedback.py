from __future__ import annotations

import json
from datetime import UTC, datetime
import pytest

from hancode.actions import ParseError
from hancode.checkpoints import CheckpointFile, CheckpointManifest, RollbackResult
from hancode.errors import HanCodeError, StructuredError
from hancode.feedback import (
    FailureCategory,
    FeedbackBuilder,
    Observation,
    ObservationKind,
    build_observation,
    classify_test_output,
)
from hancode.models import OperationStatus, Phase
from hancode.tool_policy import PolicyDecision
from hancode.tools import ToolResult


@pytest.mark.parametrize(
    ("output", "exit_code", "timed_out", "expected"),
    [
        ("", 0, False, FailureCategory.NONE),
        ("SyntaxError: invalid syntax", 1, False, FailureCategory.SYNTAX_ERROR),
        ("ModuleNotFoundError: No module named 'demo'", 1, False, FailureCategory.IMPORT_ERROR),
        ("E   AssertionError: expected 1", 1, False, FailureCategory.ASSERTION_FAILURE),
        ("KeyError: 'name'", 1, False, FailureCategory.ERROR_EXCEPTION),
        ("process hung", 1, True, FailureCategory.TIMEOUT_OR_CRASH),
        ("unexpected test runner output", 2, False, FailureCategory.UNKNOWN),
    ],
)
def test_classify_test_output_returns_stable_category(
    output: str,
    exit_code: int,
    timed_out: bool,
    expected: FailureCategory,
) -> None:
    report = classify_test_output(output, exit_code, timed_out)

    assert report.failure_category is expected
    assert report.passed is (expected is FailureCategory.NONE)
    assert report.next_action_hint


def test_classify_test_output_uses_documented_precedence_and_pytest_counts() -> None:
    output = """\
E   AssertionError: stale assertion
SyntaxError: invalid syntax
2 failed, 7 passed in 0.12s
"""

    report = classify_test_output(output, exit_code=1)

    assert report.failure_category is FailureCategory.SYNTAX_ERROR
    assert report.failed_count == 2
    assert report.passed_count == 7
    assert report.raw_size_bytes == len(output.encode("utf-8"))


def test_classification_prioritizes_timeout_over_exception_and_success_exit_code() -> None:
    report = classify_test_output("KeyError: stale output", exit_code=0, timed_out=True)

    assert report.failure_category is FailureCategory.TIMEOUT_OR_CRASH


def test_classification_keeps_higher_priority_syntax_over_timeout() -> None:
    report = classify_test_output("SyntaxError: invalid syntax", exit_code=1, timed_out=True)

    assert report.failure_category is FailureCategory.SYNTAX_ERROR


def test_policy_denial_becomes_immutable_observation() -> None:
    decision = PolicyDecision(
        allowed=False,
        reason="Target path is protected.",
        phase=Phase.CODE,
        denied_rule="protected_path",
        suggested_fix="Modify an allowed source file.",
    )

    observation = FeedbackBuilder().from_policy_denial(decision)

    assert observation.kind is ObservationKind.POLICY_DENIAL
    assert observation.success is False
    assert observation.phase is Phase.CODE
    assert observation.summary == "Target path is protected."
    assert observation.next_action_hint == "Modify an allowed source file."
    assert observation.details == {"denied_rule": "protected_path"}
    with pytest.raises(TypeError):
        observation.details["denied_rule"] = "changed"  # type: ignore[index]


def test_policy_and_parse_feedback_redact_untrusted_text() -> None:
    decision = PolicyDecision(
        allowed=False,
        reason="Rejected HANCODE_API_KEY=live-secret",
        phase=Phase.CODE,
        denied_rule="protected_path",
        suggested_fix="Do not expose Bearer token-value.",
    )
    parse_error = ParseError(
        error_code="invalid_action",
        message='Bad action: {"secret":"json-secret"}',
        phase="code",
        denied_rule="action_schema",
        suggested_fix="Remove sk-live-secret.",
    )

    observations = (
        FeedbackBuilder().from_policy_denial(decision),
        FeedbackBuilder().from_parse_error(parse_error),
    )
    serialized = json.dumps(
        [observation.to_dict() for observation in observations],
        ensure_ascii=False,
        sort_keys=True,
    )

    assert "live-secret" not in serialized
    assert "token-value" not in serialized
    assert "json-secret" not in serialized
    assert "sk-live-secret" not in serialized
    assert "[REDACTED]" in serialized


def test_rollback_feedback_redacts_structured_error_text() -> None:
    result = RollbackResult(
        status=OperationStatus.FAILED,
        checkpoint_id="ckpt-001",
        restored_files=(),
        failed_files=("src/main.py",),
        error=StructuredError(
            error_code="rollback_failed",
            message="Restore failed: HANCODE_API_KEY=live-secret",
            phase="code",
            denied_rule="rollback_restore",
            suggested_fix="Remove Bearer token-value.",
        ),
    )

    observation = FeedbackBuilder().from_rollback_result(result, phase=Phase.CODE)
    serialized = json.dumps(observation.to_dict(), ensure_ascii=False, sort_keys=True)

    assert "live-secret" not in serialized
    assert "token-value" not in serialized
    assert "[REDACTED]" in serialized


def test_tool_observation_redacts_and_truncates_to_total_byte_budget() -> None:
    result = ToolResult(
        success=True,
        action_name="read_file",
        output={
            "content": "HEAD\nHANCODE_API_KEY=live-secret\n" + "middle\n" * 80 + "TAIL\n",
            "secret": "json-secret",
            "cookie": "cookie-secret",
        },
    )

    observation = FeedbackBuilder(max_observation_bytes=420).from_tool_result(
        result, phase=Phase.CODE
    )
    serialized = json.dumps(
        observation.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )

    assert observation.kind is ObservationKind.TOOL_FEEDBACK
    assert observation.phase is Phase.CODE
    assert "HEAD" in observation.summary
    assert "TAIL" in observation.summary
    assert "[TRUNCATED]" in observation.summary
    assert "live-secret" not in serialized
    assert "json-secret" not in serialized
    assert "cookie-secret" not in serialized
    assert "[REDACTED]" in serialized
    assert len(serialized.encode("utf-8")) <= 420


def test_parse_error_becomes_observation() -> None:
    error = ParseError(
        error_code="missing_action_fields",
        message="Action payload is missing required fields.",
        phase="code",
        denied_rule=None,
        suggested_fix="Provide all required action fields.",
    )

    observation = FeedbackBuilder().from_parse_error(error)

    assert observation.kind is ObservationKind.PARSE_ERROR
    assert observation.success is False
    assert observation.phase is Phase.CODE
    assert observation.details == {
        "denied_rule": None,
        "error_code": "missing_action_fields",
    }


def test_run_tests_result_becomes_categorized_observation() -> None:
    result = ToolResult(
        success=False,
        action_name="run_tests",
        exit_code=1,
        stderr="E   AssertionError: expected 1\n1 failed, 2 passed",
    )

    observation = FeedbackBuilder().from_tool_result(result, phase=Phase.TEST)

    assert observation.kind is ObservationKind.TEST_FEEDBACK
    assert observation.failure_category is FailureCategory.ASSERTION_FAILURE
    assert observation.details["failed_count"] == 1
    assert observation.details["passed_count"] == 2


def test_checkpoint_manifest_becomes_observation() -> None:
    manifest = _manifest()

    observation = FeedbackBuilder().from_checkpoint_manifest(manifest)

    assert observation.kind is ObservationKind.CHECKPOINT_FEEDBACK
    assert observation.success is True
    assert observation.phase is Phase.CODE
    assert observation.details["checkpoint_id"] == "ckpt-001"
    assert observation.details["files"] == ("src/main.py",)


def test_rollback_result_becomes_observation() -> None:
    result = RollbackResult(
        status=OperationStatus.SUCCEEDED,
        checkpoint_id="ckpt-001",
        restored_files=("src/main.py",),
        failed_files=(),
        error=None,
    )

    observation = FeedbackBuilder().from_rollback_result(result, phase=Phase.REVIEW)

    assert observation.kind is ObservationKind.ROLLBACK_FEEDBACK
    assert observation.success is True
    assert observation.phase is Phase.REVIEW
    assert observation.details["checkpoint_id"] == "ckpt-001"
    assert observation.details["restored_files"] == ("src/main.py",)


def test_build_observation_dispatches_to_policy_feedback() -> None:
    decision = PolicyDecision(
        allowed=False,
        reason="Source is protected.",
        phase=Phase.CODE,
        denied_rule="protected_path",
        suggested_fix="Choose a source path.",
    )

    observation = build_observation(decision)

    assert observation.kind is ObservationKind.POLICY_DENIAL
    assert observation.details["denied_rule"] == "protected_path"


def test_timed_out_test_result_uses_timeout_category() -> None:
    result = ToolResult(
        success=False,
        action_name="run_tests",
        exit_code=1,
        timed_out=True,
        stderr="runner stopped",
    )

    observation = FeedbackBuilder().from_tool_result(result, phase=Phase.TEST)

    assert observation.failure_category is FailureCategory.TIMEOUT_OR_CRASH


def test_build_observation_requires_phase_for_tool_result() -> None:
    with pytest.raises(HanCodeError) as error:
        build_observation(ToolResult(success=False, action_name="read_file"))

    assert error.value.structured_error.error_code == "feedback_input_invalid"
    assert error.value.structured_error.denied_rule == "feedback_phase_required"


def test_classification_uses_full_output_before_redacted_summary_truncation() -> None:
    output = "HEAD\nHANCODE_API_KEY=live-secret\n" + "middle\n" * 40 + "TAIL\nSyntaxError\n"

    report = classify_test_output(output, exit_code=1, max_observation_bytes=140)

    assert report.failure_category is FailureCategory.SYNTAX_ERROR
    assert "HEAD" in report.summary
    assert "TAIL" in report.summary
    assert "[TRUNCATED]" in report.summary
    assert "live-secret" not in report.summary
    assert "[REDACTED]" in report.summary
    assert len(report.summary.encode("utf-8")) <= 140


def test_observation_freezes_nested_details() -> None:
    details = {"files": ["src/main.py"]}
    observation = Observation(
        kind=ObservationKind.TOOL_FEEDBACK,
        success=True,
        phase=Phase.CODE,
        summary="ok",
        next_action_hint="continue",
        details=details,
    )
    details["files"].append("src/other.py")

    assert observation.details["files"] == ("src/main.py",)


def test_observation_freezes_nested_sets_as_deterministic_tuples() -> None:
    details = {"files": {"src/b.py", "src/a.py"}}
    observation = Observation(
        kind=ObservationKind.TOOL_FEEDBACK,
        success=True,
        phase=Phase.CODE,
        summary="ok",
        next_action_hint="continue",
        details=details,
    )
    details["files"].add("src/c.py")

    assert observation.details["files"] == ("src/a.py", "src/b.py")
    assert observation.to_dict()["details"] == {"files": ["src/a.py", "src/b.py"]}


def test_observation_redacts_sensitive_top_level_detail_keys() -> None:
    observation = Observation(
        kind=ObservationKind.TOOL_FEEDBACK,
        success=True,
        phase=Phase.CODE,
        summary="ok",
        next_action_hint="continue",
        details={"token": "plain-token"},
    )

    assert observation.to_dict()["details"] == {"token": "[REDACTED]"}


def test_public_feedback_inputs_reject_invalid_values_structurally() -> None:
    parse_error = ParseError(
        error_code="invalid_action",
        message="bad action",
        phase="not-a-phase",
        denied_rule="action_schema",
        suggested_fix="Use a valid phase.",
    )
    invalid_tool = ToolResult(
        success=True,
        action_name="read_file",
        output={"content": bytearray(b"not-json")},
    )

    with pytest.raises(HanCodeError) as budget_error:
        FeedbackBuilder(max_observation_bytes=0)
    with pytest.raises(HanCodeError) as phase_error:
        build_observation(ToolResult(success=True, action_name="read_file"), phase="code")  # type: ignore[arg-type]
    with pytest.raises(HanCodeError) as parse_phase_error:
        FeedbackBuilder().from_parse_error(parse_error)
    with pytest.raises(HanCodeError) as output_error:
        FeedbackBuilder().from_tool_result(invalid_tool, phase=Phase.CODE)

    assert budget_error.value.structured_error.error_code == "feedback_input_invalid"
    assert phase_error.value.structured_error.error_code == "feedback_input_invalid"
    assert parse_phase_error.value.structured_error.error_code == "feedback_input_invalid"
    assert output_error.value.structured_error.error_code == "feedback_input_invalid"


def test_classification_never_exceeds_an_extremely_small_summary_budget() -> None:
    report = classify_test_output("long output", exit_code=1, max_observation_bytes=1)

    assert len(report.summary.encode("utf-8")) <= 1


def test_observation_budget_too_small_is_structured_error() -> None:
    decision = PolicyDecision(
        allowed=False,
        reason="Denied.",
        phase=Phase.CODE,
        denied_rule="protected_path",
        suggested_fix="Choose a source path.",
    )

    with pytest.raises(HanCodeError) as error:
        FeedbackBuilder(max_observation_bytes=1).from_policy_denial(decision)

    assert error.value.structured_error.error_code == "feedback_budget_too_small"


def _manifest() -> CheckpointManifest:
    return CheckpointManifest(
        schema_version=1,
        project_id="project-001",
        checkpoint_id="ckpt-001",
        task_id="task-001",
        phase=Phase.CODE,
        reason="Before edit.",
        created_at=datetime(2026, 7, 13, tzinfo=UTC),
        status="committed",
        files=(
            CheckpointFile(
                path="src/main.py",
                action="modify",
                before_snapshot="files/src/main.py",
                before_sha256="a" * 64,
                after_sha256="b" * 64,
            ),
        ),
        rollback_available=True,
    )
