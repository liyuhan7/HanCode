from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from hancode.core.models import Phase
from hancode.core.tool_specs import ALL_TOOL_NAMES as _TOOL_NAMES


class ActionType(str, Enum):
    TOOL_CALL = "tool_call"
    FINISH_PHASE = "finish_phase"
    ASK_USER = "ask_user"
    FINAL = "final"


@dataclass(frozen=True, slots=True)
class ParseError:
    error_code: str
    message: str
    phase: str
    denied_rule: str | None
    suggested_fix: str

    def to_dict(self) -> dict[str, object]:
        return {
            "error_code": self.error_code,
            "message": self.message,
            "phase": self.phase,
            "denied_rule": self.denied_rule,
            "suggested_fix": self.suggested_fix,
        }


@dataclass(frozen=True, slots=True)
class Action:
    type: ActionType
    phase: Phase
    tool_name: str | None
    args: Mapping[str, object]
    reason: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.type, ActionType) or not isinstance(self.phase, Phase):
            raise ValueError("invalid Action schema")
        if not isinstance(self.args, Mapping):
            raise ValueError("invalid Action schema")
        if self.reason is not None and not isinstance(self.reason, str):
            raise ValueError("invalid Action schema")
        if not _has_valid_schema(self.type, self.tool_name, self.args, self.reason):
            raise ValueError("invalid Action schema")
        object.__setattr__(self, "args", MappingProxyType(dict(self.args)))

    @classmethod
    def from_values(
        cls,
        *,
        type: ActionType | str | object,
        phase: Phase | str | object,
        tool_name: str | object | None,
        args: Mapping[str, object] | object,
        reason: str | object | None,
    ) -> Action | ParseError:
        action_type = _parse_action_type(type)
        if action_type is None:
            return _parse_error("invalid_action_type", "Use a supported action type.", "unknown")

        action_phase = _parse_phase(phase)
        if action_phase is None:
            return _parse_error("invalid_phase", "Use a supported phase.", "unknown")

        if action_type is ActionType.TOOL_CALL and (not isinstance(tool_name, str) or not tool_name):
            return _parse_error(
                "missing_tool_name",
                "Tool calls require a tool name.",
                action_phase.value,
            )
        if action_type is ActionType.TOOL_CALL and tool_name not in _TOOL_NAMES:
            return _parse_error("unknown_tool", "Use a registered tool.", action_phase.value)
        if action_type is not ActionType.TOOL_CALL and tool_name is not None:
            return _parse_error(
                "unexpected_tool_name",
                "Control actions cannot name a tool.",
                action_phase.value,
            )

        if not isinstance(args, Mapping):
            return _parse_error("invalid_action_args", "Action arguments must be an object.", action_phase.value)

        if reason is not None and not isinstance(reason, str):
            return _parse_error("invalid_reason", "Reason must be text.", action_phase.value)

        if tool_name in {"write_file", "edit_file"} and (
            not isinstance(reason, str) or not reason.strip()
        ):
            return _parse_error("missing_reason", "Write actions require a reason.", action_phase.value)

        if tool_name == "run_tests" and args:
            return _parse_error(
                "invalid_action_args",
                "The test command is selected by configuration.",
                action_phase.value,
            )

        if not _has_valid_schema(
            action_type,
            tool_name if isinstance(tool_name, str) else None,
            args,
            reason if isinstance(reason, str) else None,
        ):
            return _parse_error(
                "invalid_action_args",
                "Arguments do not match the action schema.",
                action_phase.value,
            )

        return cls(
            type=action_type,
            phase=action_phase,
            tool_name=tool_name if isinstance(tool_name, str) else None,
            args=args,
            reason=reason if isinstance(reason, str) else None,
        )


_NO_ARGUMENT_TOOLS = frozenset({"run_tests", "rollback_last_checkpoint", "run_build", "read_test_report", "list_checkpoints"})

_PARSER_FIELDS = frozenset({"type", "phase", "tool_name", "args", "reason"})


def parse_action(raw: dict[str, object], current_phase: Phase) -> Action | ParseError:
    if not isinstance(raw, dict):
        return _parser_error(
            "invalid_action_payload",
            "Action payload must be an object.",
            current_phase,
            "Provide an object with the required action fields.",
        )

    fields = set(raw)
    if _PARSER_FIELDS - fields:
        return _parser_error(
            "missing_action_fields",
            "Action payload is missing required fields.",
            current_phase,
            "Provide all required action fields.",
        )
    if fields - _PARSER_FIELDS:
        return _parser_error(
            "unexpected_action_fields",
            "Action payload contains unexpected fields.",
            current_phase,
            "Provide only the required action fields.",
        )

    action = Action.from_values(
        type=raw["type"],
        phase=raw["phase"],
        tool_name=raw["tool_name"],
        args=raw["args"],
        reason=raw["reason"],
    )
    if isinstance(action, ParseError):
        return action
    if action.phase is not current_phase:
        return _parser_error(
            "phase_mismatch",
            "Action phase does not match the current phase.",
            current_phase,
            "Use the current phase.",
        )
    return action


def _parse_action_type(value: object) -> ActionType | None:
    try:
        return value if isinstance(value, ActionType) else ActionType(value)
    except (TypeError, ValueError):
        return None


def _parse_phase(value: object) -> Phase | None:
    try:
        return value if isinstance(value, Phase) else Phase(value)
    except (TypeError, ValueError):
        return None


def _parse_error(error_code: str, message: str, phase: str) -> ParseError:
    return ParseError(
        error_code=error_code,
        message=message,
        phase=phase,
        denied_rule=None,
        suggested_fix="Provide a valid action schema.",
    )


def _parser_error(
    error_code: str, message: str, current_phase: Phase, suggested_fix: str
) -> ParseError:
    return ParseError(
        error_code=error_code,
        message=message,
        phase=current_phase.value,
        denied_rule=None,
        suggested_fix=suggested_fix,
    )


def _has_valid_schema(
    action_type: ActionType,
    tool_name: str | None,
    args: Mapping[str, object],
    reason: str | None,
) -> bool:
    if action_type is ActionType.TOOL_CALL:
        if tool_name not in _TOOL_NAMES:
            return False
        if tool_name in {"write_file", "edit_file"} and (reason is None or not reason.strip()):
            return False
        return _has_valid_tool_args(tool_name, args)
    if tool_name is not None:
        return False
    if action_type is ActionType.ASK_USER:
        question = args.get("question")
        return (
            set(args) == {"question"}
            and isinstance(question, str)
            and bool(question.strip())
            and len(question) <= 2048
        )
    return not args


def _has_valid_tool_args(tool_name: str, args: Mapping[str, object]) -> bool:
    if tool_name == "read_file":
        return _has_exact_nonempty_text_args(args, {"path"})
    if tool_name == "list_files":
        return not args or _has_exact_nonempty_text_args(args, {"path"})
    if tool_name == "search_text":
        return _has_exact_nonempty_text_args(args, {"query"})
    if tool_name == "write_file":
        return _has_path_and_text_args(args, {"path", "content"})
    if tool_name == "edit_file":
        return (
            _has_path_and_text_args(args, {"path", "old_string", "new_string"})
            and _is_nonempty_text(args["old_string"])
        )
    return tool_name in _NO_ARGUMENT_TOOLS and not args


def _has_exact_nonempty_text_args(args: Mapping[str, object], keys: set[str]) -> bool:
    return set(args) == keys and all(_is_nonempty_text(args[key]) for key in keys)


def _has_path_and_text_args(args: Mapping[str, object], keys: set[str]) -> bool:
    return (
        set(args) == keys
        and _is_nonempty_text(args["path"])
        and all(isinstance(args[key], str) for key in keys - {"path"})
    )


def _is_nonempty_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())
