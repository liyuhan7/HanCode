"""Append-only learning event store and derived projection — S14-R1.3.

``learning/events.jsonl`` is the single source of truth for learning facts. It
is append-only and hash-chained: each record embeds the digest of the previous
record so tampering or reordering fails closed. ``learning/evidence.json`` is a
derived projection that can always be rebuilt by replaying a valid event prefix;
it is never treated as authoritative.

Event types are the nine names frozen in SPEC 7.3 / architecture S14.3.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import os
from pathlib import Path
from tempfile import mkstemp
from typing import Mapping

from hancode.core.errors import HanCodeError, StructuredError


_EVENT_ID_PREFIX = "LE"
_EVENT_ID_WIDTH = 6
_SCHEMA_VERSION = 1


class LearningEventType(str, Enum):
    REQUIREMENT_UNDERSTOOD = "RequirementUnderstood"
    DECISION_RECORDED = "DecisionRecorded"
    CHANGE_APPLIED = "ChangeApplied"
    TEST_EXECUTED = "TestExecuted"
    FAILURE_DIAGNOSED = "FailureDiagnosed"
    FIX_APPLIED = "FixApplied"
    ROLLBACK_EXECUTED = "RollbackExecuted"
    REQUIREMENT_REVIEWED = "RequirementReviewed"
    KNOWLEDGE_EXTRACTED = "KnowledgeExtracted"


@dataclass(frozen=True, slots=True)
class LearningEvent:
    schema_version: int
    task_id: str
    seq: int
    event_id: str
    event_type: LearningEventType
    occurred_at: str
    payload: Mapping[str, object]
    previous_digest: str | None
    digest: str


class LearningStore:
    """Persist and replay hash-chained learning events for one task."""

    def _events_path(self, task_root: Path) -> Path:
        return task_root / "learning" / "events.jsonl"

    def _projection_path(self, task_root: Path) -> Path:
        return task_root / "learning" / "evidence.json"

    # ------------------------------------------------------------------
    # append
    # ------------------------------------------------------------------

    def append(
        self,
        task_root: Path,
        task_id: str,
        event_type: LearningEventType | str,
        payload: Mapping[str, object],
        *,
        occurred_at: str,
    ) -> LearningEvent:
        resolved_type = _coerce_event_type(event_type)
        if task_root.name != task_id:
            raise _identity_mismatch()
        events = self.read_events(task_root)
        for event in events:
            if event.task_id != task_id:
                raise _identity_mismatch()

        seq = len(events) + 1
        event_id = f"{_EVENT_ID_PREFIX}-{seq:0{_EVENT_ID_WIDTH}d}"
        previous_digest = events[-1].digest if events else None
        record = {
            "schema_version": _SCHEMA_VERSION,
            "task_id": task_id,
            "seq": seq,
            "event_id": event_id,
            "event_type": resolved_type.value,
            "occurred_at": occurred_at,
            "payload": _canonical(payload),
            "previous_digest": previous_digest,
        }
        digest = _digest_record(record)
        record["digest"] = digest

        line = json.dumps(record, ensure_ascii=False, sort_keys=True)
        events_path = self._events_path(task_root)
        events_path.parent.mkdir(parents=True, exist_ok=True)
        if _is_link(events_path):
            raise _store_error(
                "learning_events_corrupt",
                "Learning events log must not be a link.",
                "Replace events.jsonl with a regular file.",
            )
        try:
            with open(events_path, "a", encoding="utf-8", newline="") as handle:
                handle.write(line + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as exc:
            raise _store_error(
                "learning_events_write_failed",
                "Learning event could not be appended.",
                "Restore task workspace write access before continuing.",
            ) from exc

        appended = LearningEvent(
            schema_version=_SCHEMA_VERSION,
            task_id=task_id,
            seq=seq,
            event_id=event_id,
            event_type=resolved_type,
            occurred_at=occurred_at,
            payload=record["payload"],  # type: ignore[arg-type]
            previous_digest=previous_digest,
            digest=digest,
        )
        self._write_projection(task_root, (*events, appended))
        return appended

    # ------------------------------------------------------------------
    # read / replay
    # ------------------------------------------------------------------

    def read_events(self, task_root: Path) -> tuple[LearningEvent, ...]:
        events_path = self._events_path(task_root)
        if not events_path.is_file():
            return ()
        if _is_link(events_path):
            raise _store_error(
                "learning_events_corrupt",
                "Learning events log must not be a link.",
                "Replace events.jsonl with a regular file.",
            )
        try:
            raw = events_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise _store_error(
                "learning_events_corrupt",
                "Learning events log cannot be read.",
                "Repair or restore events.jsonl.",
            ) from exc

        lines = raw.split("\n")
        # A trailing partial write (no terminating newline) is dropped: only the
        # complete newline-terminated prefix is trusted.
        if raw.endswith("\n"):
            complete = [line for line in lines if line != ""]
        else:
            complete = [line for line in lines[:-1] if line != ""]

        events: list[LearningEvent] = []
        previous_digest: str | None = None
        for index, line in enumerate(complete):
            expected_seq = index + 1
            event = _parse_and_verify(line, expected_seq, previous_digest)
            events.append(event)
            previous_digest = event.digest
        return tuple(events)

    def load_projection(self, task_root: Path) -> dict[str, object]:
        events = self.read_events(task_root)
        projection_path = self._projection_path(task_root)
        if not projection_path.is_file():
            self._write_projection(task_root, events)
        return _projection_dict(events)

    def rebuild_projection(self, task_root: Path) -> dict[str, object]:
        events = self.read_events(task_root)
        self._write_projection(task_root, events)
        return _projection_dict(events)

    def _write_projection(
        self, task_root: Path, events: tuple[LearningEvent, ...]
    ) -> None:
        projection = _projection_dict(events)
        path = self._projection_path(task_root)
        path.parent.mkdir(parents=True, exist_ok=True)
        if _is_link(path):
            raise _store_error(
                "learning_projection_invalid",
                "Learning projection must not be a link.",
                "Replace evidence.json with a regular file.",
            )
        temporary_path: Path | None = None
        descriptor: int | None = None
        try:
            descriptor, temporary_name = mkstemp(
                prefix=".evidence-", suffix=".tmp", dir=path.parent
            )
            temporary_path = Path(temporary_name)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
                descriptor = None
                handle.write(json.dumps(projection, ensure_ascii=False, indent=2) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
            temporary_path = None
        except (OSError, UnicodeError) as exc:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            raise _store_error(
                "learning_projection_invalid",
                "Learning projection could not be written.",
                "Restore task workspace write access before continuing.",
            ) from exc
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)


def _projection_dict(events: tuple[LearningEvent, ...]) -> dict[str, object]:
    task_id = events[0].task_id if events else None
    return {
        "schema_version": _SCHEMA_VERSION,
        "task_id": task_id,
        "source_event_seq": len(events),
        "digest": events[-1].digest if events else None,
        "events": [
            {
                "seq": event.seq,
                "event_id": event.event_id,
                "event_type": event.event_type.value,
                "occurred_at": event.occurred_at,
                "payload": dict(event.payload),
            }
            for event in events
        ],
    }


def _coerce_event_type(event_type: LearningEventType | str) -> LearningEventType:
    if isinstance(event_type, LearningEventType):
        return event_type
    return LearningEventType(event_type)


def _canonical(payload: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(payload, Mapping):
        raise ValueError("Learning event payload must be a mapping.")
    # Round-trip through JSON to guarantee only serializable content is stored.
    result = json.loads(json.dumps(dict(payload), ensure_ascii=False, sort_keys=True))
    if not isinstance(result, dict):
        raise ValueError("Learning event payload must be a JSON object.")
    return result


def _digest_record(record: Mapping[str, object]) -> str:
    material = json.dumps(dict(record), ensure_ascii=False, sort_keys=True)
    return sha256(material.encode("utf-8")).hexdigest()


def _parse_and_verify(
    line: str, expected_seq: int, previous_digest: str | None
) -> LearningEvent:
    try:
        record = json.loads(line)
    except json.JSONDecodeError as exc:
        raise _corrupt() from exc
    if not isinstance(record, dict):
        raise _corrupt()
    stored_digest = record.get("digest")
    if not isinstance(stored_digest, str):
        raise _corrupt()
    verifiable = {key: value for key, value in record.items() if key != "digest"}
    if _digest_record(verifiable) != stored_digest:
        raise _corrupt()
    if record.get("seq") != expected_seq:
        raise _corrupt()
    if record.get("previous_digest") != previous_digest:
        raise _corrupt()
    if record.get("schema_version") != _SCHEMA_VERSION:
        raise _corrupt()
    task_id = record.get("task_id")
    event_id = record.get("event_id")
    occurred_at = record.get("occurred_at")
    payload = record.get("payload")
    if (
        not isinstance(task_id, str)
        or not task_id
        or not isinstance(event_id, str)
        or not isinstance(occurred_at, str)
        or not isinstance(payload, dict)
    ):
        raise _corrupt()
    try:
        event_type = LearningEventType(record.get("event_type"))
    except ValueError as exc:
        raise _corrupt() from exc
    return LearningEvent(
        schema_version=_SCHEMA_VERSION,
        task_id=task_id,
        seq=expected_seq,
        event_id=event_id,
        event_type=event_type,
        occurred_at=occurred_at,
        payload=payload,
        previous_digest=previous_digest,
        digest=stored_digest,
    )


def _store_error(error_code: str, message: str, suggested_fix: str) -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code=error_code,
            message=message,
            phase="deliver",
            denied_rule=error_code,
            suggested_fix=suggested_fix,
        )
    )


def _corrupt() -> HanCodeError:
    return _store_error(
        "learning_events_corrupt",
        "Learning events log is corrupt or its digest chain is broken.",
        "Restore events.jsonl from a trusted source; do not edit it by hand.",
    )


def _identity_mismatch() -> HanCodeError:
    return _store_error(
        "learning_task_identity_mismatch",
        "Learning event task identity does not match the events log.",
        "Append events only to the matching task workspace.",
    )


def _is_link(path: Path) -> bool:
    try:
        is_junction = getattr(path, "is_junction", None)
        return path.is_symlink() or bool(is_junction and is_junction())
    except (AttributeError, OSError, RuntimeError):
        return True


__all__ = ["LearningEvent", "LearningEventType", "LearningStore"]
