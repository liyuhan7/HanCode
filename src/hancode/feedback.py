"""Deterministic feedback classification and observation construction."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
import json
import re
from types import MappingProxyType
from typing import Mapping

from hancode.actions import ParseError
from hancode.checkpoints import CheckpointManifest, RollbackResult
from hancode.errors import HanCodeError, StructuredError
from hancode.models import Phase
from hancode.file_tools import redact_text
from hancode.tool_policy import PolicyDecision
from hancode.tools import ToolResult


class FailureCategory(str, Enum):
    NONE = "none"
    SYNTAX_ERROR = "syntax_error"
    IMPORT_ERROR = "import_error"
    ASSERTION_FAILURE = "assertion_failure"
    ERROR_EXCEPTION = "error_exception"
    TIMEOUT_OR_CRASH = "timeout_or_crash"
    UNKNOWN = "unknown"


class ObservationKind(str, Enum):
    TEST_FEEDBACK = "test_feedback"
    TOOL_FEEDBACK = "tool_feedback"
    POLICY_DENIAL = "policy_denial"
    PARSE_ERROR = "parse_error"
    CHECKPOINT_FEEDBACK = "checkpoint_feedback"
    ROLLBACK_FEEDBACK = "rollback_feedback"


@dataclass(frozen=True, slots=True)
class FeedbackReport:
    passed: bool
    failure_category: FailureCategory
    summary: str
    next_action_hint: str
    failed_count: int = 0
    passed_count: int = 0
    raw_size_bytes: int = 0


@dataclass(frozen=True, slots=True)
class Observation:
    kind: ObservationKind
    success: bool
    phase: Phase
    summary: str
    next_action_hint: str
    failure_category: FailureCategory | None = None
    details: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "details",
            MappingProxyType(
                {
                    str(key): _freeze_value(
                        "[REDACTED]"
                        if _is_sensitive_key(str(key))
                        else _sanitize_value(value)
                    )
                    for key, value in self.details.items()
                }
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "success": self.success,
            "phase": self.phase.value,
            "summary": self.summary,
            "next_action_hint": self.next_action_hint,
            "failure_category": (
                None if self.failure_category is None else self.failure_category.value
            ),
            "details": _thaw_value(self.details),
        }


class FeedbackBuilder:
    """Build deterministic observations without state or trace side effects."""

    def __init__(self, max_observation_bytes: int = 8192) -> None:
        if (
            not isinstance(max_observation_bytes, int)
            or isinstance(max_observation_bytes, bool)
            or max_observation_bytes <= 0
        ):
            raise _feedback_input_error(
                "positive_observation_budget_required",
                "Provide a positive integer max_observation_bytes value.",
            )
        self._max_observation_bytes = max_observation_bytes

    def from_policy_denial(self, decision: PolicyDecision) -> Observation:
        return self._fit(
            Observation(
            kind=ObservationKind.POLICY_DENIAL,
            success=False,
            phase=_require_phase(decision.phase),
            summary=redact_text(decision.reason),
            next_action_hint=redact_text(decision.suggested_fix),
            details={"denied_rule": decision.denied_rule},
            )
        )

    def from_tool_result(self, result: ToolResult, *, phase: Phase) -> Observation:
        phase = _require_phase(phase)
        if result.action_name == "run_tests":
            return self._test_observation(result, phase)
        try:
            summary = _tool_summary(result)
        except (TypeError, ValueError) as error:
            raise _feedback_input_error(
                "feedback_json_compatible_output_required",
                "Provide JSON-compatible ToolResult output values.",
            ) from error
        return self._fit(
            Observation(
                kind=ObservationKind.TOOL_FEEDBACK,
                success=result.success,
                phase=phase,
                summary=summary,
                next_action_hint=(
                    "Continue with the next planned step."
                    if result.success
                    else "Inspect the tool failure before retrying."
                ),
                details={
                    "action_name": result.action_name,
                    "exit_code": result.exit_code,
                    "timed_out": result.timed_out,
                },
            )
        )

    def from_parse_error(self, error: ParseError) -> Observation:
        try:
            phase = Phase(error.phase)
        except ValueError as phase_error:
            raise _feedback_input_error(
                "valid_parse_error_phase_required",
                "Provide a ParseError phase supported by the harness.",
            ) from phase_error
        return self._fit(
            Observation(
                kind=ObservationKind.PARSE_ERROR,
                success=False,
                phase=phase,
                summary=redact_text(error.message),
                next_action_hint=redact_text(error.suggested_fix),
                details={
                    "denied_rule": error.denied_rule,
                    "error_code": error.error_code,
                },
            )
        )

    def from_checkpoint_manifest(self, manifest: CheckpointManifest) -> Observation:
        return self._fit(
            Observation(
                kind=ObservationKind.CHECKPOINT_FEEDBACK,
                success=True,
                phase=_require_phase(manifest.phase),
                summary=redact_text(
                    f"Checkpoint {manifest.checkpoint_id} is {manifest.status}."
                ),
                next_action_hint="Use the checkpoint before making the next source change.",
                details={
                    "checkpoint_id": manifest.checkpoint_id,
                    "files": tuple(sorted(file.path for file in manifest.files)),
                    "rollback_available": manifest.rollback_available,
                    "status": manifest.status,
                },
            )
        )

    def from_rollback_result(
        self, result: RollbackResult, *, phase: Phase
    ) -> Observation:
        phase = _require_phase(phase)
        success = result.status.value == "succeeded"
        error = result.error
        summary = (
            "Rollback restored the latest checkpoint."
            if success
            else "Rollback did not complete."
            if error is None
            else error.message
        )
        next_action_hint = (
            "Review the restored files before making another change."
            if success
            else "Repair rollback prerequisites before continuing."
            if error is None
            else error.suggested_fix
        )
        return self._fit(
            Observation(
                kind=ObservationKind.ROLLBACK_FEEDBACK,
                success=success,
                phase=phase,
                summary=redact_text(summary),
                next_action_hint=redact_text(next_action_hint),
                details={
                    "checkpoint_id": result.checkpoint_id,
                    "failed_files": tuple(sorted(result.failed_files)),
                    "restored_files": tuple(sorted(result.restored_files)),
                    "rollback_status": result.status.value,
                    "error_code": None if error is None else error.error_code,
                },
            )
        )

    def _test_observation(self, result: ToolResult, phase: Phase) -> Observation:
        output = "\n".join(
            value
            for value in (result.error_summary, result.stdout, result.stderr)
            if value
        )
        report = classify_test_output(
            output,
            result.exit_code if result.exit_code is not None else (0 if result.success else 1),
            result.timed_out,
        )
        return self._fit(
            Observation(
                kind=ObservationKind.TEST_FEEDBACK,
                success=report.passed,
                phase=phase,
                summary=report.summary,
                next_action_hint=report.next_action_hint,
                failure_category=report.failure_category,
                details={
                    "action_name": result.action_name,
                    "exit_code": result.exit_code,
                    "timed_out": result.timed_out,
                    "failed_count": report.failed_count,
                    "passed_count": report.passed_count,
                    "raw_size_bytes": report.raw_size_bytes,
                },
            )
        )

    def _fit(self, observation: Observation) -> Observation:
        if _byte_len(observation.to_dict()) <= self._max_observation_bytes:
            return observation
        skeleton = replace(observation, summary="")
        if _byte_len(skeleton.to_dict()) > self._max_observation_bytes:
            raise _feedback_budget_error(observation.phase)

        low, high = len("[TRUNCATED]".encode("utf-8")), len(observation.summary.encode("utf-8"))
        best = "[TRUNCATED]"
        while low <= high:
            middle = (low + high) // 2
            candidate = _truncate_text(observation.summary, middle)
            if _byte_len(replace(observation, summary=candidate).to_dict()) <= self._max_observation_bytes:
                best = candidate
                low = middle + 1
            else:
                high = middle - 1
        return replace(observation, summary=best)


def build_observation(
    result: ToolResult | PolicyDecision | ParseError | CheckpointManifest | RollbackResult,
    *,
    phase: Phase | None = None,
    max_observation_bytes: int = 8192,
) -> Observation:
    """Dispatch one supported deterministic result into an observation."""
    if phase is not None:
        phase = _require_phase(phase)
    builder = FeedbackBuilder(max_observation_bytes)
    if isinstance(result, PolicyDecision):
        return builder.from_policy_denial(result)
    if isinstance(result, ParseError):
        return builder.from_parse_error(result)
    if isinstance(result, CheckpointManifest):
        return builder.from_checkpoint_manifest(result)
    if isinstance(result, (ToolResult, RollbackResult)):
        if phase is None:
            raise _feedback_input_error(
                "feedback_phase_required",
                "Provide the current phase for tool or rollback feedback.",
            )
        if isinstance(result, ToolResult):
            return builder.from_tool_result(result, phase=phase)
        return builder.from_rollback_result(result, phase=phase)
    raise _feedback_input_error(
        "supported_feedback_input_required",
        "Provide a supported deterministic feedback input.",
    )


_HINTS = {
    FailureCategory.NONE: "Tests passed; continue with the next planned step.",
    FailureCategory.SYNTAX_ERROR: "Fix syntax or indentation before changing business logic.",
    FailureCategory.IMPORT_ERROR: "Record the dependency risk; do not install dependencies automatically.",
    FailureCategory.ASSERTION_FAILURE: "Compare the implementation with the PLAN verification expectation.",
    FailureCategory.ERROR_EXCEPTION: "Use the exception type to narrow the changed code path.",
    FailureCategory.TIMEOUT_OR_CRASH: "Reduce the change scope and inspect the latest checkpoint.",
    FailureCategory.UNKNOWN: "Inspect the retained test output before making another change.",
}


def classify_test_output(
    output: str,
    exit_code: int,
    timed_out: bool = False,
    *,
    max_observation_bytes: int = 8192,
) -> FeedbackReport:
    """Classify a complete test output with a fixed, documented precedence."""
    category = _classify(output, exit_code, timed_out)
    failed_count = _pytest_count(output, "failed")
    passed_count = _pytest_count(output, "passed")
    return FeedbackReport(
        passed=category is FailureCategory.NONE,
        failure_category=category,
        summary=_truncate_text(redact_text(output), max_observation_bytes),
        next_action_hint=_HINTS[category],
        failed_count=failed_count,
        passed_count=passed_count,
        raw_size_bytes=len(output.encode("utf-8")),
    )


def _classify(output: str, exit_code: int, timed_out: bool) -> FailureCategory:
    if any(marker in output for marker in ("SyntaxError", "IndentationError", "errors during collection")):
        return FailureCategory.SYNTAX_ERROR
    if any(marker in output for marker in ("ModuleNotFoundError", "ImportError")):
        return FailureCategory.IMPORT_ERROR
    if "AssertionError" in output or ("assert" in output and "E   " in output):
        return FailureCategory.ASSERTION_FAILURE
    if timed_out or exit_code < 0:
        return FailureCategory.TIMEOUT_OR_CRASH
    if "Error" in output or "Exception" in output:
        return FailureCategory.ERROR_EXCEPTION
    if exit_code == 0:
        return FailureCategory.NONE
    return FailureCategory.UNKNOWN


def _pytest_count(output: str, label: str) -> int:
    matches = re.findall(rf"\b(\d+) {label}\b", output)
    return 0 if not matches else int(matches[-1])


def _tool_summary(result: ToolResult) -> str:
    if result.error_summary is not None:
        return redact_text(result.error_summary)
    return json.dumps(_sanitize_value(result.output), ensure_ascii=False, sort_keys=True)


def _sanitize_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if _is_sensitive_key(str(key)) else _sanitize_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return [_sanitize_value(item) for item in sorted(value, key=repr)]
    if isinstance(value, str):
        return redact_text(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    raise ValueError("ToolResult output contains an unsupported value type")


def _is_sensitive_key(key: str) -> bool:
    normalized = "".join(character for character in key.casefold() if character.isalnum())
    return any(marker in normalized for marker in ("apikey", "authorization", "password", "secret", "token"))


def _freeze_value(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze_value(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return tuple(_freeze_value(item) for item in sorted(value, key=repr))
    return value


def _thaw_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _thaw_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_value(item) for item in value]
    return value


def _byte_len(value: object) -> int:
    serialized = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return len(serialized.encode("utf-8"))


def _truncate_text(text: str, max_bytes: int) -> str:
    if len(text.encode("utf-8")) <= max_bytes:
        return text
    marker = "[TRUNCATED]"
    if max_bytes <= len(marker.encode("utf-8")):
        return marker[:max(0, max_bytes)]
    retained_bytes = max_bytes - len(marker.encode("utf-8"))
    head = _utf8_prefix(text, retained_bytes // 2)
    tail = _utf8_suffix(text, retained_bytes - len(head.encode("utf-8")))
    return head + marker + tail


def _utf8_prefix(text: str, max_bytes: int) -> str:
    result: list[str] = []
    used = 0
    for character in text:
        size = len(character.encode("utf-8"))
        if used + size > max_bytes:
            break
        result.append(character)
        used += size
    return "".join(result)


def _utf8_suffix(text: str, max_bytes: int) -> str:
    result: list[str] = []
    used = 0
    for character in reversed(text):
        size = len(character.encode("utf-8"))
        if used + size > max_bytes:
            break
        result.append(character)
        used += size
    return "".join(reversed(result))


def _feedback_input_error(denied_rule: str, suggested_fix: str) -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code="feedback_input_invalid",
            message="Feedback input cannot be converted into an observation.",
            phase="unknown",
            denied_rule=denied_rule,
            suggested_fix=suggested_fix,
        )
    )


def _require_phase(phase: object) -> Phase:
    if isinstance(phase, Phase):
        return phase
    raise _feedback_input_error(
        "valid_feedback_phase_required",
        "Provide a phase from the harness Phase enum.",
    )


def _feedback_budget_error(phase: Phase) -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code="feedback_budget_too_small",
            message="The configured observation budget cannot contain feedback metadata.",
            phase=phase.value,
            denied_rule="observation_budget_sufficient",
            suggested_fix="Increase max_observation_bytes before building feedback.",
        )
    )
