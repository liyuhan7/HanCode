from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Sequence

from hancode.errors import StructuredError


class Phase(str, Enum):
    SPEC = "spec"
    PLAN = "plan"
    CODE = "code"
    TEST = "test"
    REVIEW = "review"
    DELIVER = "deliver"


class TaskStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    BLOCKED = "blocked"
    FAILED = "failed"
    COMPLETED = "completed"
    INCONSISTENT = "inconsistent"


class OperationStatus(str, Enum):
    SUCCEEDED = "succeeded"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass(frozen=True)
class Risk:
    level: str
    message: str
    mitigation: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "level": self.level,
            "message": self.message,
            "mitigation": self.mitigation,
        }


@dataclass(frozen=True)
class OperationResult:
    status: OperationStatus
    message: str
    error: StructuredError | None = None
    data: Mapping[str, object] | None = None
    risks: Sequence[Risk] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.status, OperationStatus):
            raise ValueError(f"Unsupported operation status: {self.status!r}")

    @classmethod
    def from_values(
        cls,
        *,
        status: OperationStatus | str,
        message: str,
        error: StructuredError | None = None,
        data: Mapping[str, object] | None = None,
        risks: Sequence[Risk] = (),
    ) -> OperationResult:
        try:
            operation_status = status if isinstance(status, OperationStatus) else OperationStatus(status)
        except ValueError as exc:
            raise ValueError(f"Unsupported operation status: {status!r}") from exc

        return cls(
            status=operation_status,
            message=message,
            error=error,
            data=data,
            risks=risks,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "message": self.message,
            "error": None if self.error is None else self.error.to_dict(),
            "data": None if self.data is None else _serialize_mapping(self.data),
            "risks": [risk.to_dict() for risk in self.risks],
        }


def _serialize_mapping(values: Mapping[str, object]) -> dict[str, object]:
    return {key: _serialize_value(value) for key, value in values.items()}


def _serialize_value(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    if isinstance(value, Mapping):
        return {str(key): _serialize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    if isinstance(value, tuple):
        return [_serialize_value(item) for item in value]
    return value
