from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Mapping

from hancode.config import load_config
from hancode.errors import HanCodeError, StructuredError
from hancode.file_tools import redact_text
from hancode.models import Phase
from hancode.workspace import load_project_metadata


_SENSITIVE_FIELD_MARKERS = (
    "awsaccesskeyid",
    "awssecretaccesskey",
    "apikey",
    "authorization",
    "cookie",
    "credential",
    "password",
    "privatekey",
    "secret",
    "token",
)
_MAX_TRACE_STRING_CHARS = 4096
_SENSITIVE_TEXT_PATTERN = re.compile(
    r"(authorization|api[_-]?key|token|secret|password|private[_-]?key|credential|"
    r"cookie|aws[_-]?access[_-]?key[_-]?id|aws[_-]?secret[_-]?access[_-]?key)"
    r"\s*[:=]\s*(?:bearer\s+)?[^\s,;]+",
    re.IGNORECASE,
)
_BEARER_TOKEN_PATTERN = re.compile(r"\bbearer\s+[^\s,;]+", re.IGNORECASE)
_TOOL_EVENT_TYPES = frozenset({"tool_called", "tool_completed", "tool_failed"})
_TOOL_EVENT_STATUSES = {
    "tool_called": "running",
    "tool_completed": "succeeded",
    "tool_failed": "failed",
}
_CONTENT_FIELD_MARKERS = frozenset({"body", "content", "output", "stderr", "stdout", "text"})


@dataclass(frozen=True, slots=True)
class TraceEvent:
    event_id: str
    seq: int
    event_type: str
    task_id: str
    phase: Phase
    timestamp: datetime
    status: str
    action: Mapping[str, object] | None = None
    observation: Mapping[str, object] | None = None
    error_summary: str | None = None
    state_transition: Mapping[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "seq": self.seq,
            "event_type": self.event_type,
            "task_id": self.task_id,
            "phase": self.phase.value,
            "timestamp": self.timestamp.isoformat(),
            "status": self.status,
            "action": self.action,
            "observation": self.observation,
            "error_summary": self.error_summary,
            "state_transition": self.state_transition,
        }


def append_trace(
    task_root: Path,
    *,
    event_type: str,
    task_id: str,
    phase: Phase,
    status: str,
    action: Mapping[str, object] | None = None,
    observation: Mapping[str, object] | None = None,
    error_summary: str | None = None,
    state_transition: Mapping[str, object] | None = None,
    timestamp: datetime | None = None,
) -> TraceEvent:
    event_timestamp = datetime.now(UTC) if timestamp is None else timestamp
    _validate_event(
        task_root,
        task_id,
        event_type,
        phase,
        status,
        action,
        observation,
        state_transition,
        error_summary,
        event_timestamp,
    )
    trace_path = task_root / "trace.jsonl"
    if _is_link(trace_path):
        raise _trace_path_link_error(phase)
    seq = _next_sequence(trace_path, phase, task_id)
    resolved_task_root = task_root.resolve()
    project_root = resolved_task_root.parent.parent.parent
    config = load_config(project_root, task_id)
    if seq > config.max_trace_events:
        raise _trace_limit_error(phase)
    event = TraceEvent(
        event_id=f"evt-{seq:06d}",
        seq=seq,
        event_type=event_type,
        task_id=task_id,
        phase=phase,
        timestamp=event_timestamp,
        status=status,
        action=None if action is None else _sanitize_mapping(action),
        observation=None if observation is None else _sanitize_mapping(observation),
        error_summary=None if error_summary is None else _sanitize_string(error_summary),
        state_transition=(
            None if state_transition is None else _sanitize_mapping(state_transition)
        ),
    )
    try:
        if _is_link(trace_path):
            raise _trace_path_link_error(phase)
        serialized_event = json.dumps(event.to_dict(), ensure_ascii=False)
        with trace_path.open("a", encoding="utf-8") as trace_file:
            trace_file.write(serialized_event + "\n")
    except (OSError, TypeError, ValueError) as exc:
        raise _trace_write_error(phase) from exc
    return event


def _next_sequence(trace_path: Path, phase: Phase, task_id: str) -> int:
    if _is_link(trace_path):
        raise _trace_path_link_error(phase)
    try:
        lines = trace_path.read_text(encoding="utf-8").splitlines()
        for expected_seq, line in enumerate(lines, start=1):
            event = json.loads(line)
            if (
                not isinstance(event, dict)
                or event.get("seq") != expected_seq
                or isinstance(event.get("seq"), bool)
                or event.get("event_id") != f"evt-{expected_seq:06d}"
                or event.get("task_id") != task_id
            ):
                raise ValueError("Invalid trace sequence.")
        return len(lines) + 1
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise _trace_parse_error(phase) from exc


def _sanitize_mapping(values: Mapping[str, object]) -> dict[str, object]:
    return {
        str(key): "[REDACTED]"
        if _is_sensitive_field(str(key))
        else _content_summary(value)
        if _is_content_field(str(key))
        else _sanitize_value(value)
        for key, value in values.items()
    }


def _sanitize_value(value: object) -> object:
    if isinstance(value, Mapping):
        return _sanitize_mapping(value)
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, str):
        return _sanitize_string(value)
    return value


def _sanitize_string(value: str) -> str:
    value = redact_text(value)
    value = _SENSITIVE_TEXT_PATTERN.sub(_redacted_text, value)
    value = _BEARER_TOKEN_PATTERN.sub("Bearer [REDACTED]", value)
    if len(value) <= _MAX_TRACE_STRING_CHARS:
        return value
    return value[:_MAX_TRACE_STRING_CHARS] + "...[TRUNCATED]"


def _content_summary(value: object) -> dict[str, object]:
    if isinstance(value, str):
        return {"summary": "[CONTENT_OMITTED]", "char_count": len(value)}
    return {"summary": "[CONTENT_OMITTED]"}


def _is_sensitive_field(name: str) -> bool:
    normalized_name = "".join(character for character in name.lower() if character.isalnum())
    return any(marker in normalized_name for marker in _SENSITIVE_FIELD_MARKERS)


def _is_content_field(name: str) -> bool:
    normalized_name = "".join(character for character in name.lower() if character.isalnum())
    return any(
        normalized_name.startswith(marker) or normalized_name.endswith(marker)
        for marker in _CONTENT_FIELD_MARKERS
    )


def _is_link(path: Path) -> bool:
    try:
        is_junction = getattr(path, "is_junction", None)
        return path.is_symlink() or bool(is_junction and is_junction())
    except (OSError, RuntimeError):
        return True


def _redacted_text(match: re.Match[str]) -> str:
    separator = ":" if ":" in match.group(0) else "="
    return f"{match.group(1)}{separator}[REDACTED]"


def _validate_event(
    task_root: Path,
    task_id: str,
    event_type: str,
    phase: Phase,
    status: str,
    action: Mapping[str, object] | None,
    observation: Mapping[str, object] | None,
    state_transition: Mapping[str, object] | None,
    error_summary: str | None,
    timestamp: datetime,
) -> None:
    if not isinstance(phase, Phase):
        raise _invalid_trace_payload_error(Phase.SPEC)
    if not isinstance(timestamp, datetime):
        raise _invalid_trace_payload_error(phase)
    resolved_task_root = task_root.resolve()
    if (
        resolved_task_root.parent.name != "tasks"
        or resolved_task_root.parent.parent.name != ".hancode"
    ):
        raise _invalid_trace_task_root_error(phase)
    if resolved_task_root.name != task_id:
        raise _trace_task_identity_error(phase)
    try:
        load_project_metadata(resolved_task_root.parent.parent / "project.json")
    except HanCodeError as exc:
        raise _invalid_trace_task_root_error(phase) from exc
    if any(
        value is not None and not isinstance(value, Mapping)
        for value in (action, observation, state_transition)
    ):
        raise _invalid_trace_payload_error(phase)
    if error_summary is not None and not isinstance(error_summary, str):
        raise _invalid_trace_payload_error(phase)
    if event_type not in _TOOL_EVENT_TYPES:
        return
    tool_name = None if action is None else action.get("tool_name")
    args = None if action is None else action.get("args")
    reason = None if action is None else action.get("reason")
    policy_decision = None if action is None else action.get("policy_decision")
    if (
        not isinstance(action, Mapping)
        or not isinstance(tool_name, str)
        or not tool_name.strip()
        or not isinstance(args, Mapping)
        or not isinstance(reason, str)
        or not reason.strip()
        or not isinstance(policy_decision, Mapping)
        or not isinstance(policy_decision.get("allowed"), bool)
        or not isinstance(policy_decision.get("message"), str)
        or not isinstance(policy_decision.get("phase"), str)
        or policy_decision.get("phase") != phase.value
        or "denied_rule" not in policy_decision
        or (
            policy_decision.get("denied_rule") is not None
            and not isinstance(policy_decision.get("denied_rule"), str)
        )
        or not isinstance(policy_decision.get("suggested_fix"), str)
        or status != _TOOL_EVENT_STATUSES[event_type]
        or (event_type == "tool_failed" and not error_summary)
    ):
        raise _invalid_tool_event_error(phase)


def _trace_parse_error(phase: Phase) -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code="trace_parse_error",
            message="Existing task trace is invalid.",
            phase=phase.value,
            denied_rule="valid_trace_required",
            suggested_fix="Repair or restore trace.jsonl before continuing.",
        )
    )


def _trace_write_error(phase: Phase) -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code="trace_write_error",
            message="Trace event could not be persisted.",
            phase=phase.value,
            denied_rule="trace_persistence_required",
            suggested_fix=(
                "Restore task trace write access before continuing with high-risk actions."
            ),
        )
    )


def _invalid_tool_event_error(phase: Phase) -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code="invalid_trace_event",
            message="Trace event is invalid.",
            phase=phase.value,
            denied_rule="auditable_tool_event_required",
            suggested_fix="Record tool name, arguments, reason, and policy decision.",
        )
    )


def _trace_task_identity_error(phase: Phase) -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code="trace_task_identity_mismatch",
            message="Trace task ID does not match the task workspace.",
            phase=phase.value,
            denied_rule="trace_task_identity_match_required",
            suggested_fix="Use the task ID that matches the task trace directory.",
        )
    )


def _invalid_trace_task_root_error(phase: Phase) -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code="invalid_trace_task_root",
            message="Trace task root is outside the task workspace layout.",
            phase=phase.value,
            denied_rule="task_workspace_trace_root_required",
            suggested_fix="Use a task root inside .hancode/tasks/<task_id>.",
        )
    )


def _invalid_trace_payload_error(phase: Phase) -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code="invalid_trace_payload",
            message="Trace event payload is invalid.",
            phase=phase.value,
            denied_rule="valid_trace_payload_required",
            suggested_fix="Use JSON-compatible payload values and a string error summary.",
        )
    )


def _trace_limit_error(phase: Phase) -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code="trace_event_limit_exceeded",
            message="The task trace event limit has been reached.",
            phase=phase.value,
            denied_rule="max_trace_events",
            suggested_fix="Review the existing trace before appending another event.",
        )
    )


def _trace_path_link_error(phase: Phase) -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code="trace_path_link_not_allowed",
            message="Task trace path must not be a symbolic link or junction.",
            phase=phase.value,
            denied_rule="canonical_trace_path_required",
            suggested_fix="Replace trace.jsonl with a regular file inside the task workspace.",
        )
    )
