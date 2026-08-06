"""Domain model for Runtime Steering interventions (S17).

An intervention is a user requirement submitted while the agent is running.
The persisted fact source is an append-only event log; ``InterventionRecord``
is the projection replayed from those events, and ``SteeringSnapshot`` is the
immutable view the AgentLoop hands to the ContextBuilder for one turn.

S17-R1 scope: STEER only. Concurrency linearization (``commit_action``),
Prepare-Commit-Apply and Approval revision binding are intentionally excluded
and land in later S17 sub-cards.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re


_INTERVENTION_ID_PATTERN = re.compile(r"iv-\d{6}")
_EVENT_ID_PATTERN = re.compile(r"ive-\d{6}")


class InterventionKind(str, Enum):
    STEER = "steer"


class InterventionStatus(str, Enum):
    PENDING = "pending"
    DELIVERED = "delivered"
    CONSUMED = "consumed"


class InterventionEventType(str, Enum):
    SUBMITTED = "submitted"
    DELIVERED = "delivered"
    CONSUMED = "consumed"


class DeliveryStatus(str, Enum):
    DELIVERED = "delivered"
    STALE = "stale"


class ActionCommitStatus(str, Enum):
    COMMITTED = "committed"
    REPLAN = "replan"


def format_intervention_id(sequence: int) -> str:
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
        raise ValueError("intervention sequence must be a positive integer")
    if sequence > 999999:
        raise ValueError("intervention sequence exceeds the supported range")
    return f"iv-{sequence:06d}"


def is_valid_intervention_id(intervention_id: str) -> bool:
    return bool(_INTERVENTION_ID_PATTERN.fullmatch(intervention_id))


@dataclass(frozen=True, slots=True)
class InterventionEvent:
    """A single fact event stored in ``interventions.jsonl``."""

    schema_version: int
    event_id: str
    event_type: InterventionEventType
    intervention_id: str
    task_id: str
    run_id: str
    sequence: int
    created_at: str
    content: str | None

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("intervention event schema_version must be 1")
        if not _EVENT_ID_PATTERN.fullmatch(self.event_id):
            raise ValueError("event_id must match ive-XXXXXX")
        if not isinstance(self.event_type, InterventionEventType):
            raise ValueError("event_type must be an InterventionEventType")
        if not is_valid_intervention_id(self.intervention_id):
            raise ValueError("intervention_id must match iv-XXXXXX")
        if not isinstance(self.task_id, str) or not self.task_id:
            raise ValueError("intervention event task_id must be non-empty")
        if not isinstance(self.run_id, str) or not self.run_id:
            raise ValueError("intervention event run_id must be non-empty")
        if (
            not isinstance(self.sequence, int)
            or isinstance(self.sequence, bool)
            or self.sequence < 1
        ):
            raise ValueError("intervention event sequence must be a positive integer")
        if not isinstance(self.created_at, str) or not self.created_at:
            raise ValueError("intervention event created_at must be non-empty")
        if self.event_type is InterventionEventType.SUBMITTED:
            if not isinstance(self.content, str) or not self.content:
                raise ValueError("submitted intervention event requires content")
        elif self.content is not None:
            raise ValueError("only submitted events may carry content")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "intervention_id": self.intervention_id,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "sequence": self.sequence,
            "created_at": self.created_at,
            "content": self.content,
        }

    @classmethod
    def from_dict(cls, data: object) -> InterventionEvent:
        if not isinstance(data, dict):
            raise ValueError("intervention event must be a JSON object")
        try:
            event_type = InterventionEventType(data["event_type"])
        except (KeyError, ValueError) as exc:
            raise ValueError("invalid intervention event_type") from exc
        raw_content = data.get("content")
        if raw_content is not None and not isinstance(raw_content, str):
            raise ValueError("intervention content must be a string or null")
        return cls(
            schema_version=_require_int(data, "schema_version"),
            event_id=_require_str(data, "event_id"),
            event_type=event_type,
            intervention_id=_require_str(data, "intervention_id"),
            task_id=_require_str(data, "task_id"),
            run_id=_require_str(data, "run_id"),
            sequence=_require_int(data, "sequence"),
            created_at=_require_str(data, "created_at"),
            content=raw_content,
        )


@dataclass(frozen=True, slots=True)
class InterventionRecord:
    """Projection of an intervention replayed from its event stream."""

    intervention_id: str
    task_id: str
    run_id: str
    sequence: int
    kind: InterventionKind
    status: InterventionStatus
    content: str
    submitted_at: str
    delivered_at: str | None
    consumed_at: str | None

    def __post_init__(self) -> None:
        if not is_valid_intervention_id(self.intervention_id):
            raise ValueError("intervention_id must match iv-XXXXXX")
        if not isinstance(self.task_id, str) or not self.task_id:
            raise ValueError("intervention record task_id must be non-empty")
        if not isinstance(self.run_id, str) or not self.run_id:
            raise ValueError("intervention record run_id must be non-empty")
        if (
            not isinstance(self.sequence, int)
            or isinstance(self.sequence, bool)
            or self.sequence < 1
        ):
            raise ValueError("intervention record sequence must be a positive integer")
        if not isinstance(self.kind, InterventionKind):
            raise ValueError("intervention kind must be an InterventionKind")
        if not isinstance(self.status, InterventionStatus):
            raise ValueError("intervention status must be an InterventionStatus")
        if not isinstance(self.content, str) or not self.content:
            raise ValueError("intervention record content must be non-empty")

    def to_dict(self) -> dict[str, object]:
        return {
            "intervention_id": self.intervention_id,
            "sequence": self.sequence,
            "status": self.status.value,
            "content": self.content,
        }


@dataclass(frozen=True, slots=True)
class SteeringSnapshot:
    """Immutable steering view for one AgentLoop turn."""

    task_id: str
    run_id: str
    revision: int
    effective_records: tuple[InterventionRecord, ...]
    delivery_sequences: tuple[int, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.task_id, str) or not self.task_id:
            raise ValueError("snapshot task_id must be non-empty")
        if not isinstance(self.run_id, str) or not self.run_id:
            raise ValueError("snapshot run_id must be non-empty")
        if (
            not isinstance(self.revision, int)
            or isinstance(self.revision, bool)
            or self.revision < 0
        ):
            raise ValueError("snapshot revision must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    status: DeliveryStatus
    current_revision: int


@dataclass(frozen=True, slots=True)
class ActionCommitResult:
    status: ActionCommitStatus
    current_revision: int


def _require_str(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"intervention event field {key!r} must be a non-empty string")
    return value


def _require_int(data: dict[str, object], key: str) -> int:
    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"intervention event field {key!r} must be an integer")
    return value
