"""Small deterministic recovery coordinator for Action and file-tool failures."""

from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import json
from typing import Mapping, Protocol

from hancode.core.actions import Action, ParseError
from hancode.core.failures import (
    FailureCategory,
    FailureRecord,
    FailureSource,
    RecoveryMode,
)
from hancode.core.models import Phase, TaskStatus
from hancode.core.state import TaskState
from hancode.policy.path_policy import PathZone, normalize_project_relative_path
from hancode.runtime.feedback import FeedbackBuilder, Observation
from hancode.tooling.file_tools import redact_text
from hancode.tooling.registry import ToolResult


class PolicyDecisionLike(Protocol):
    allowed: bool
    reason: str
    target_zone: PathZone | None
    denied_rule: str | None
    suggested_fix: str


_PARSE_CATEGORY_BY_CODE = {
    "invalid_action_payload": FailureCategory.INVALID_ACTION,
    "missing_action_fields": FailureCategory.INVALID_ACTION,
    "unexpected_action_fields": FailureCategory.INVALID_ACTION,
    "invalid_action_type": FailureCategory.INVALID_ACTION,
    "missing_tool_name": FailureCategory.INVALID_ACTION,
    "unexpected_tool_name": FailureCategory.INVALID_ACTION,
    "unknown_tool": FailureCategory.UNKNOWN_TOOL,
    "invalid_action_args": FailureCategory.INVALID_ARGUMENT,
    "invalid_reason": FailureCategory.INVALID_ARGUMENT,
    "missing_reason": FailureCategory.INVALID_ARGUMENT,
    "invalid_phase": FailureCategory.PHASE_MISMATCH,
    "phase_mismatch": FailureCategory.PHASE_MISMATCH,
}
_POLICY_CATEGORY_BY_RULE = {
    "path_out_of_scope": FailureCategory.PATH_OUT_OF_SCOPE,
    "protected_path": FailureCategory.PROTECTED_RESOURCE,
    "deterministic_delivery_artifact": FailureCategory.PROTECTED_RESOURCE,
    "action_phase_mismatch": FailureCategory.PHASE_MISMATCH,
    "tool_not_allowed_in_phase": FailureCategory.PHASE_MISMATCH,
    "artifact_not_allowed_in_phase": FailureCategory.PHASE_MISMATCH,
    "source_write_requires_code_phase": FailureCategory.PHASE_MISMATCH,
    "spec_required_before_source_write": FailureCategory.PHASE_MISMATCH,
    "plan_required_before_source_write": FailureCategory.PHASE_MISMATCH,
    "unsupported_action": FailureCategory.INVALID_ACTION,
    "final_not_model_selectable": FailureCategory.INVALID_ACTION,
    "reason_required_for_write": FailureCategory.INVALID_ARGUMENT,
    "write_path_required": FailureCategory.INVALID_ARGUMENT,
}
_FILE_TOOLS = frozenset(
    {"read_file", "list_files", "search_text", "write_file", "edit_file"}
)
_WRITE_FILE_TOOLS = frozenset({"write_file", "edit_file"})
_TOOL_FALLBACK_CODE = {
    "read_file": "read_failed",
    "list_files": "list_failed",
    "search_text": "search_failed",
    "write_file": "write_failed",
    "edit_file": "edit_failed",
}


@dataclass(frozen=True, slots=True)
class RecoveryUpdate:
    state: TaskState
    observation: Observation
    should_block: bool


class RecoveryCoordinator:
    def __init__(self, feedback_builder: FeedbackBuilder | None = None) -> None:
        self._feedback_builder = feedback_builder or FeedbackBuilder()

    def record_parse_failure(
        self,
        *,
        state: TaskState,
        raw_action: object,
        parse_error: ParseError,
        phase: Phase,
    ) -> RecoveryUpdate:
        action_digest = _raw_action_digest(raw_action, parse_error.error_code)
        tool_name, target = _raw_action_identity(raw_action)
        category = _PARSE_CATEGORY_BY_CODE.get(
            parse_error.error_code, FailureCategory.UNKNOWN
        )
        fingerprint = _digest(
            {
                "source": FailureSource.ACTION_PARSE.value,
                "category": category.value,
                "phase": phase.value,
                "error_code": parse_error.error_code,
                "action_digest": action_digest,
            }
        )
        failure = FailureRecord(
            failure_id=f"fail-{fingerprint[:12]}",
            source=FailureSource.ACTION_PARSE,
            category=category,
            fingerprint=fingerprint,
            action_digest=action_digest,
            phase=phase,
            tool_name=tool_name,
            target=target,
            error_code=parse_error.error_code,
            safe_message=redact_text(parse_error.message),
            suggested_fix=redact_text(parse_error.suggested_fix),
            safe_details={"denied_rule": parse_error.denied_rule},
            repeat_count=1,
            recovery_mode=RecoveryMode.RETRY,
        )
        return self._record_failure(state, failure)

    def supports_policy_denial(self, decision: PolicyDecisionLike) -> bool:
        return decision.denied_rule in _POLICY_CATEGORY_BY_RULE

    def supports_tool_failure(self, action: Action, result: ToolResult) -> bool:
        return (
            action.tool_name in _FILE_TOOLS
            and not result.success
            and result.action_name == action.tool_name
            and (
                action.tool_name not in _WRITE_FILE_TOOLS
                or result.mutation_applied is False
            )
        )

    def record_policy_failure(
        self,
        *,
        state: TaskState,
        action: Action,
        decision: PolicyDecisionLike,
        phase: Phase,
    ) -> RecoveryUpdate:
        denied_rule = decision.denied_rule
        if denied_rule not in _POLICY_CATEGORY_BY_RULE:
            raise ValueError("policy denial is outside S11 recovery scope")
        action_digest = _action_digest(action)
        target = _action_target(action)
        category = _POLICY_CATEGORY_BY_RULE[denied_rule]
        fingerprint = _digest(
            {
                "source": FailureSource.POLICY_DENIAL.value,
                "category": category.value,
                "phase": phase.value,
                "tool_name": action.tool_name,
                "target": target,
                "denied_rule": denied_rule,
            }
        )
        failure = FailureRecord(
            failure_id=f"fail-{fingerprint[:12]}",
            source=FailureSource.POLICY_DENIAL,
            category=category,
            fingerprint=fingerprint,
            action_digest=action_digest,
            phase=phase,
            tool_name=action.tool_name,
            target=target,
            error_code=denied_rule,
            safe_message=redact_text(decision.reason),
            suggested_fix=redact_text(decision.suggested_fix),
            safe_details={
                "denied_rule": denied_rule,
                "target_zone": (
                    None if decision.target_zone is None else decision.target_zone.value
                ),
            },
            repeat_count=1,
            recovery_mode=RecoveryMode.RETRY,
        )
        return self._record_failure(state, failure)

    def record_tool_failure(
        self,
        *,
        state: TaskState,
        action: Action,
        result: ToolResult,
        phase: Phase,
    ) -> RecoveryUpdate:
        if not self.supports_tool_failure(action, result):
            raise ValueError("tool failure is outside S11 recovery scope")
        assert action.tool_name is not None
        error_code = result.error_code or _TOOL_FALLBACK_CODE[action.tool_name]
        category = (
            FailureCategory.PATH_OUT_OF_SCOPE
            if error_code == "path_out_of_scope"
            else FailureCategory.PROTECTED_RESOURCE
            if error_code == "protected_resource"
            else FailureCategory.TOOL_FAILED
        )
        action_digest = _action_digest(action)
        target = _action_target(action)
        fingerprint = _digest(
            {
                "source": FailureSource.TOOL_EXECUTION.value,
                "category": category.value,
                "phase": phase.value,
                "tool_name": action.tool_name,
                "target": target,
                "error_code": error_code,
            }
        )
        failure = FailureRecord(
            failure_id=f"fail-{fingerprint[:12]}",
            source=FailureSource.TOOL_EXECUTION,
            category=category,
            fingerprint=fingerprint,
            action_digest=action_digest,
            phase=phase,
            tool_name=action.tool_name,
            target=target,
            error_code=error_code,
            safe_message=redact_text(result.error_summary or "Tool execution failed."),
            suggested_fix=_tool_failure_hint(error_code),
            safe_details={"mutation_applied": result.mutation_applied},
            repeat_count=1,
            recovery_mode=RecoveryMode.RETRY,
        )
        return self._record_failure(state, failure)

    def observation_from_state(self, state: TaskState) -> Observation | None:
        if state.active_failure is None:
            return None
        return self._feedback_builder.from_failure_record(state.active_failure)

    def guard_action(
        self, *, state: TaskState, action: Action
    ) -> RecoveryUpdate | None:
        active = state.active_failure
        if active is None or active.action_digest != _action_digest(action):
            return None
        repeat_count = min(3, active.repeat_count + 1)
        repeated = replace(
            active,
            repeat_count=repeat_count,
            recovery_mode=_mode_for_count(repeat_count),
        )
        updated_state = replace(
            state,
            active_failure=repeated,
            status=(
                TaskStatus.BLOCKED
                if repeated.recovery_mode is RecoveryMode.BLOCKED
                else state.status
            ),
        )
        return RecoveryUpdate(
            state=updated_state,
            observation=self._feedback_builder.from_failure_record(repeated),
            should_block=repeated.recovery_mode is RecoveryMode.BLOCKED,
        )

    def resolve_after_success(self, *, state: TaskState, action: Action) -> TaskState:
        active = state.active_failure
        if active is None:
            return state
        current_digest = _action_digest(action)
        current_target = _action_target(action)
        clear = False
        if active.source is FailureSource.ACTION_PARSE:
            clear = current_digest != active.action_digest
        elif active.category in {
            FailureCategory.PATH_OUT_OF_SCOPE,
            FailureCategory.PROTECTED_RESOURCE,
        }:
            clear = (
                active.tool_name == action.tool_name
                and current_target is not None
                and current_target != active.target
            )
        elif active.category is FailureCategory.PHASE_MISMATCH:
            clear = action.phase is state.current_phase and current_digest != active.action_digest
        else:
            clear = active.tool_name == action.tool_name and current_digest != active.action_digest
        return replace(state, active_failure=None) if clear else state

    def _record_failure(self, state: TaskState, failure: FailureRecord) -> RecoveryUpdate:
        active = state.active_failure
        if active is not None and active.fingerprint == failure.fingerprint:
            failure = replace(
                failure,
                action_digest=failure.action_digest,
                repeat_count=min(3, active.repeat_count + 1),
                recovery_mode=_mode_for_count(min(3, active.repeat_count + 1)),
            )
        updated_state = replace(
            state,
            active_failure=failure,
            status=(
                TaskStatus.BLOCKED
                if failure.recovery_mode is RecoveryMode.BLOCKED
                else state.status
            ),
        )
        return RecoveryUpdate(
            state=updated_state,
            observation=self._feedback_builder.from_failure_record(failure),
            should_block=failure.recovery_mode is RecoveryMode.BLOCKED,
        )


def _mode_for_count(count: int) -> RecoveryMode:
    return RecoveryMode.RETRY if count <= 1 else RecoveryMode.CHANGE_ACTION if count == 2 else RecoveryMode.BLOCKED


def _action_digest(action: Action) -> str:
    return _digest(
        {
            "type": action.type.value,
            "phase": action.phase.value,
            "tool_name": action.tool_name,
            "args": _canonical(action.args),
        }
    )


def _raw_action_digest(raw_action: object, error_code: str) -> str:
    if isinstance(raw_action, Mapping):
        payload = {
            "type": _canonical(raw_action.get("type")),
            "phase": _canonical(raw_action.get("phase")),
            "tool_name": _canonical(raw_action.get("tool_name")),
            "args": _canonical(raw_action.get("args")),
        }
        try:
            return _digest(payload)
        except (TypeError, ValueError):
            pass
    return _digest({"payload_type": type(raw_action).__name__, "error_code": error_code})


def _raw_action_identity(raw_action: object) -> tuple[str | None, str | None]:
    if not isinstance(raw_action, Mapping):
        return None, None
    tool_name = raw_action.get("tool_name")
    args = raw_action.get("args")
    if not isinstance(tool_name, str):
        tool_name = None
    target = _target_from_args(args)
    return tool_name, target


def _action_target(action: Action) -> str | None:
    return _target_from_args(action.args)


def _target_from_args(args: object) -> str | None:
    if not isinstance(args, Mapping):
        return None
    value = args.get("path")
    if value is None:
        return "." if "path" not in args else None
    if not isinstance(value, str) or not value:
        return None
    try:
        return normalize_project_relative_path(value)
    except ValueError:
        return value.replace("\\", "/")[:512]


def _canonical(value: object) -> object:
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("action mappings require string keys")
        return {
            key: _canonical(item)
            for key, item in sorted(value.items(), key=lambda pair: pair[0])
        }
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    return {"type": type(value).__name__}


def _digest(value: object) -> str:
    encoded = json.dumps(
        _canonical(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _tool_failure_hint(error_code: str) -> str:
    return {
        "invalid_argument": "根据工具参数 schema 修正参数。",
        "path_out_of_scope": "改用工作区内的项目相对路径。",
        "protected_resource": "选择允许修改的源码或产物目标。",
        "file_not_found": "先读取或搜索现有文件，再提交有效目标。",
        "directory_not_found": "先列出工作区目录，再提交有效目录。",
        "not_a_file": "选择文件目标。",
        "not_a_directory": "选择目录目标。",
        "invalid_utf8": "使用有效 UTF-8 内容。",
        "edit_no_change": "提交确实改变文件的编辑。",
        "edit_target_not_unique": "先读取文件并选择唯一 old_string。",
    }.get(error_code, "检查文件工具失败后更换目标或参数。")
