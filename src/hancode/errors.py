from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class StructuredError:
    code: str
    message: str
    hint: str
    details: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": self.message,
            "hint": self.hint,
            "details": dict(self.details),
        }


class HanCodeError(Exception):
    def __init__(self, structured_error: StructuredError) -> None:
        self.structured_error = structured_error
        super().__init__(f"{structured_error.code}: {structured_error.message}")

    def to_dict(self) -> dict[str, object]:
        return self.structured_error.to_dict()
