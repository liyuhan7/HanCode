from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class StructuredError:
    error_code: str
    message: str
    phase: str
    denied_rule: str | None
    suggested_fix: str

    def to_dict(self) -> dict[str, object]:
        return {
            "error_code": self.error_code,
            "message": self.message,
            "phase": _serialize_value(self.phase),
            "denied_rule": self.denied_rule,
            "suggested_fix": self.suggested_fix,
        }


class HanCodeError(Exception):
    def __init__(self, structured_error: StructuredError) -> None:
        self.structured_error = structured_error
        super().__init__(f"{structured_error.error_code}: {structured_error.message}")

    def to_dict(self) -> dict[str, object]:
        return self.structured_error.to_dict()


def _serialize_value(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    return value
