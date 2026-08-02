"""Persistent, deterministic failure records used by the S11 recovery loop."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from types import MappingProxyType
from typing import Mapping, TypeVar

from hancode.core.models import Phase


class FailureSource(str, Enum):
    ACTION_PARSE = "action_parse"
    POLICY_DENIAL = "policy_denial"
    TOOL_EXECUTION = "tool_execution"


class FailureCategory(str, Enum):
    INVALID_ACTION = "invalid_action"
    UNKNOWN_TOOL = "unknown_tool"
    INVALID_ARGUMENT = "invalid_argument"
    PHASE_MISMATCH = "phase_mismatch"
    PATH_OUT_OF_SCOPE = "path_out_of_scope"
    PROTECTED_RESOURCE = "protected_resource"
    TOOL_FAILED = "tool_failed"
    UNKNOWN = "unknown"


class RecoveryMode(str, Enum):
    RETRY = "retry"
    CHANGE_ACTION = "change_action"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class FailureRecord:
    """The active failure persisted in ``TaskState``.

    ``failure_id`` is deliberately derived from the stable fingerprint by the
    coordinator.  It identifies the active failure key, rather than a history
    event; audit events remain in the existing trace stream.
    """

    failure_id: str
    source: FailureSource
    category: FailureCategory
    fingerprint: str
    action_digest: str
    phase: Phase
    tool_name: str | None
    target: str | None
    error_code: str
    safe_message: str
    suggested_fix: str
    safe_details: Mapping[str, object]
    repeat_count: int
    recovery_mode: RecoveryMode

    def __post_init__(self) -> None:
        if not _is_nonempty_str(self.failure_id) or not self.failure_id.startswith("fail-"):
            raise ValueError("invalid failure_id")
        if not isinstance(self.source, FailureSource):
            raise ValueError("invalid failure source")
        if not isinstance(self.category, FailureCategory):
            raise ValueError("invalid failure category")
        if not _is_digest(self.fingerprint):
            raise ValueError("invalid failure fingerprint")
        if not _is_digest(self.action_digest):
            raise ValueError("invalid action digest")
        if self.failure_id != f"fail-{self.fingerprint[:12]}":
            raise ValueError("failure_id must be derived from fingerprint")
        if not isinstance(self.phase, Phase):
            raise ValueError("invalid failure phase")
        if self.tool_name is not None and not _is_nonempty_str(self.tool_name):
            raise ValueError("invalid failure tool")
        if self.target is not None and not _is_nonempty_str(self.target):
            raise ValueError("invalid failure target")
        for value in (self.error_code, self.safe_message, self.suggested_fix):
            if not isinstance(value, str):
                raise ValueError("invalid failure text")
        if not isinstance(self.safe_details, Mapping):
            raise ValueError("invalid failure details")
        frozen_details = _freeze_value(self.safe_details)
        if not isinstance(frozen_details, Mapping):
            raise ValueError("invalid failure details")
        if not _is_nonnegative_int(self.repeat_count) or self.repeat_count < 1:
            raise ValueError("invalid failure repeat count")
        if not isinstance(self.recovery_mode, RecoveryMode):
            raise ValueError("invalid recovery mode")
        object.__setattr__(self, "safe_details", frozen_details)

    def to_dict(self) -> dict[str, object]:
        return {
            "failure_id": self.failure_id,
            "source": self.source.value,
            "category": self.category.value,
            "fingerprint": self.fingerprint,
            "action_digest": self.action_digest,
            "phase": self.phase.value,
            "tool_name": self.tool_name,
            "target": self.target,
            "error_code": self.error_code,
            "safe_message": self.safe_message,
            "suggested_fix": self.suggested_fix,
            "safe_details": _thaw_value(self.safe_details),
            "repeat_count": self.repeat_count,
            "recovery_mode": self.recovery_mode.value,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "FailureRecord":
        if not isinstance(data, Mapping):
            raise ValueError("invalid failure record")
        expected = {
            "failure_id",
            "source",
            "category",
            "fingerprint",
            "action_digest",
            "phase",
            "tool_name",
            "target",
            "error_code",
            "safe_message",
            "suggested_fix",
            "safe_details",
            "repeat_count",
            "recovery_mode",
        }
        if set(data) != expected:
            raise ValueError("invalid failure record fields")
        source = _enum_value(FailureSource, data, "source")
        category = _enum_value(FailureCategory, data, "category")
        phase = _enum_value(Phase, data, "phase")
        recovery_mode = _enum_value(RecoveryMode, data, "recovery_mode")
        tool_name = _optional_text(data, "tool_name")
        target = _optional_text(data, "target")
        safe_details = data["safe_details"]
        if not isinstance(safe_details, Mapping):
            raise ValueError("invalid failure details")
        return cls(
            failure_id=_required_text(data, "failure_id"),
            source=source,
            category=category,
            fingerprint=_required_text(data, "fingerprint"),
            action_digest=_required_text(data, "action_digest"),
            phase=phase,
            tool_name=tool_name,
            target=target,
            error_code=_required_text(data, "error_code"),
            safe_message=_required_text(data, "safe_message"),
            suggested_fix=_required_text(data, "suggested_fix"),
            safe_details=safe_details,
            repeat_count=_required_int(data, "repeat_count"),
            recovery_mode=recovery_mode,
        )


EnumT = TypeVar("EnumT", bound=Enum)


def _enum_value(enum_type: type[EnumT], data: Mapping[str, object], field: str) -> EnumT:
    value = data.get(field)
    if not isinstance(value, str):
        raise ValueError(f"invalid failure field: {field}")
    try:
        return enum_type(value)
    except ValueError:
        raise ValueError(f"invalid failure field: {field}") from None


def _required_text(data: Mapping[str, object], field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"invalid failure field: {field}")
    return value


def _optional_text(data: Mapping[str, object], field: str) -> str | None:
    value = data.get(field)
    if value is not None and (not isinstance(value, str) or not value):
        raise ValueError(f"invalid failure field: {field}")
    return value


def _required_int(data: Mapping[str, object], field: str) -> int:
    value = data.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"invalid failure field: {field}")
    return value


def _is_nonempty_str(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _is_nonnegative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _freeze_value(value: object) -> object:
    if isinstance(value, Mapping):
        frozen: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise ValueError("invalid failure detail key")
            frozen[key] = _freeze_value(item)
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise ValueError("invalid failure detail value")


def _thaw_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _thaw_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_value(item) for item in value]
    return value
