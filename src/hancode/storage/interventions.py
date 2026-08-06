"""Append-only persistence for Runtime Steering interventions (S17-R1).

The fact source is one JSON line per event under:
    .hancode/tasks/<task-id>/interventions.jsonl

``InterventionRecord`` projections are replayed from the event stream on every
call; the file is never rewritten. A module-level lock keyed by the normalized
log path serializes concurrent access from multiple in-process ``Store``
instances (TUI thread + Agent Worker thread). Cross-process locking is a
non-goal for the S17 MVP.

S17-R1 scope: submit / prepare_context / mark_delivered / mark_consumed /
current_revision. Revision-linearized ``commit_action`` lands in S17-R2.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
from typing import Mapping

from hancode.core.errors import HanCodeError, StructuredError
from hancode.core.interventions import (
    ActionCommitResult,
    ActionCommitStatus,
    DeliveryResult,
    DeliveryStatus,
    InterventionEvent,
    InterventionEventType,
    InterventionKind,
    InterventionRecord,
    InterventionStatus,
    SteeringSnapshot,
    format_intervention_id,
)
from hancode.tooling.file_tools import redact_text
from hancode.storage.workspace import task_path


_LOG_NAME = "interventions.jsonl"
_LEDGER_NAME = "action_commits.jsonl"
_REDACTED_MARKER = "[REDACTED]"

_PATH_LOCKS_GUARD = threading.Lock()
_PATH_LOCKS: dict[str, threading.RLock] = {}


def _lock_for(path: Path) -> threading.RLock:
    key = os.path.normcase(str(path.resolve()))
    with _PATH_LOCKS_GUARD:
        lock = _PATH_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _PATH_LOCKS[key] = lock
        return lock


class InterventionStore:
    """Persist and project Runtime Steering interventions for one project."""

    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root.resolve()

    def _log_path(self, task_id: str) -> Path:
        return task_path(self._project_root, task_id) / _LOG_NAME

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def submit(self, task_id: str, run_id: str, content: str) -> InterventionRecord:
        """Append a SUBMITTED event and return its record projection."""
        if not isinstance(run_id, str) or not run_id:
            raise self._error(
                "intervention_run_invalid",
                "A valid run identity is required to submit steering.",
                "active_run_required",
                "Start or resume the task before submitting steering.",
            )
        if not isinstance(content, str) or not content.strip():
            raise self._error(
                "intervention_content_required",
                "Steering content must be non-empty.",
                "steering_content_required",
                "Provide a concrete steering instruction.",
            )
        safe_content = redact_text(content.strip())
        if not safe_content or safe_content == _REDACTED_MARKER:
            raise self._error(
                "intervention_content_contains_only_sensitive_content",
                "Steering content contained only sensitive material.",
                "steering_content_non_sensitive_required",
                "Do not send credentials through steering; use hancode auth login.",
            )
        path = self._log_path(task_id)
        with _lock_for(path):
            events = self._replay_events(path, task_id)
            sequence = self._max_sequence(events) + 1
            intervention_id = format_intervention_id(sequence)
            event = InterventionEvent(
                schema_version=1,
                event_id=self._next_event_id(events),
                event_type=InterventionEventType.SUBMITTED,
                intervention_id=intervention_id,
                task_id=task_id,
                run_id=run_id,
                sequence=sequence,
                created_at=_now(),
                content=safe_content,
            )
            self._append_event(path, events, event)
            record = self._project(task_id)[intervention_id]
            return record

    def prepare_context(self, task_id: str, run_id: str) -> SteeringSnapshot:
        """Build the immutable steering snapshot for the current run."""
        path = self._log_path(task_id)
        with _lock_for(path):
            events = self._replay_events(path, task_id)
            revision = self._max_sequence(events)
            records = self._project_from(events, task_id)
        effective = tuple(
            record
            for record in sorted(records.values(), key=lambda item: item.sequence)
            if record.run_id == run_id
        )
        delivery = tuple(
            record.sequence
            for record in effective
            if record.status is not InterventionStatus.CONSUMED
        )
        return SteeringSnapshot(
            task_id=task_id,
            run_id=run_id,
            revision=revision,
            effective_records=effective,
            delivery_sequences=delivery,
        )

    def mark_delivered(
        self,
        task_id: str,
        run_id: str,
        expected_revision: int,
        sequences: tuple[int, ...],
    ) -> DeliveryResult:
        """Transition PENDING records to DELIVERED (idempotent)."""
        path = self._log_path(task_id)
        with _lock_for(path):
            events = self._replay_events(path, task_id)
            revision = self._max_sequence(events)
            if revision != expected_revision:
                return DeliveryResult(
                    status=DeliveryStatus.STALE, current_revision=revision
                )
            records = self._project_from(events, task_id)
            for sequence in sequences:
                record = self._record_for_sequence(records, sequence, run_id)
                if record is None or record.status is not InterventionStatus.PENDING:
                    continue
                event = InterventionEvent(
                    schema_version=1,
                    event_id=self._next_event_id(events),
                    event_type=InterventionEventType.DELIVERED,
                    intervention_id=record.intervention_id,
                    task_id=task_id,
                    run_id=run_id,
                    sequence=record.sequence,
                    created_at=_now(),
                    content=None,
                )
                self._append_event(path, events, event)
                records = self._project_from(events, task_id)
            return DeliveryResult(
                status=DeliveryStatus.DELIVERED, current_revision=revision
            )

    def mark_consumed(
        self,
        task_id: str,
        run_id: str,
        sequences: tuple[int, ...],
    ) -> None:
        """Transition DELIVERED records to CONSUMED (idempotent)."""
        path = self._log_path(task_id)
        with _lock_for(path):
            events = self._replay_events(path, task_id)
            records = self._project_from(events, task_id)
            for sequence in sequences:
                record = self._record_for_sequence(records, sequence, run_id)
                if record is None or record.status is not InterventionStatus.DELIVERED:
                    continue
                event = InterventionEvent(
                    schema_version=1,
                    event_id=self._next_event_id(events),
                    event_type=InterventionEventType.CONSUMED,
                    intervention_id=record.intervention_id,
                    task_id=task_id,
                    run_id=run_id,
                    sequence=record.sequence,
                    created_at=_now(),
                    content=None,
                )
                self._append_event(path, events, event)
                records = self._project_from(events, task_id)

    def current_revision(self, task_id: str) -> int:
        path = self._log_path(task_id)
        with _lock_for(path):
            events = self._replay_events(path, task_id)
            return self._max_sequence(events)

    def commit_action(
        self,
        task_id: str,
        run_id: str,
        expected_revision: int,
        delivery_sequences: tuple[int, ...],
        action_digest: str,
        commit_key: str,
        acknowledge: bool,
    ) -> ActionCommitResult:
        """Linearize an Action against steering under the shared log lock.

        Steering ``submit`` and ``commit_action`` contend for the same path
        lock, so exactly one crosses the commit point first:

        * If steering already raised the revision, the stale Action gets
          ``REPLAN`` and produces no side effects.
        * Otherwise the Action commits; when ``acknowledge`` is set, the
          delivered steering it handled is marked ``CONSUMED``.

        The result is recorded in an idempotency ledger keyed by
        ``commit_key`` so a crash-retry with the same key returns the first
        recorded result.
        """
        if not isinstance(commit_key, str) or not commit_key:
            raise self._error(
                "intervention_commit_key_required",
                "A commit key is required to commit an action.",
                "commit_key_required",
                "Provide a deterministic commit key for the action.",
            )
        path = self._log_path(task_id)
        ledger_path = self._ledger_path(task_id)
        with _lock_for(path):
            ledger = self._replay_ledger(ledger_path, task_id)
            existing = ledger.get(commit_key)
            if existing is not None:
                return ActionCommitResult(
                    status=existing.status,
                    current_revision=existing.revision,
                )
            events = self._replay_events(path, task_id)
            revision = self._max_sequence(events)
            if revision != expected_revision:
                self._append_ledger(
                    ledger_path,
                    ledger,
                    task_id=task_id,
                    run_id=run_id,
                    commit_key=commit_key,
                    action_digest=action_digest,
                    status=ActionCommitStatus.REPLAN,
                    revision=revision,
                )
                return ActionCommitResult(
                    status=ActionCommitStatus.REPLAN, current_revision=revision
                )
            if acknowledge:
                records = self._project_from(events, task_id)
                for sequence in delivery_sequences:
                    record = self._record_for_sequence(records, sequence, run_id)
                    if (
                        record is None
                        or record.status is not InterventionStatus.DELIVERED
                    ):
                        continue
                    consume_event = InterventionEvent(
                        schema_version=1,
                        event_id=self._next_event_id(events),
                        event_type=InterventionEventType.CONSUMED,
                        intervention_id=record.intervention_id,
                        task_id=task_id,
                        run_id=run_id,
                        sequence=record.sequence,
                        created_at=_now(),
                        content=None,
                    )
                    self._append_event(path, events, consume_event)
                    records = self._project_from(events, task_id)
            self._append_ledger(
                ledger_path,
                ledger,
                task_id=task_id,
                run_id=run_id,
                commit_key=commit_key,
                action_digest=action_digest,
                status=ActionCommitStatus.COMMITTED,
                revision=revision,
            )
            return ActionCommitResult(
                status=ActionCommitStatus.COMMITTED, current_revision=revision
            )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _ledger_path(self, task_id: str) -> Path:
        return task_path(self._project_root, task_id) / _LEDGER_NAME

    def _replay_ledger(
        self, ledger_path: Path, task_id: str
    ) -> dict[str, _CommitLedgerEntry]:
        if _is_link(ledger_path):
            raise self._ledger_corrupt_error(task_id)
        if not ledger_path.is_file():
            return {}
        entries: dict[str, _CommitLedgerEntry] = {}
        try:
            with ledger_path.open(encoding="utf-8") as handle:
                for line in handle:
                    stripped = line.strip()
                    if not stripped:
                        raise ValueError("empty ledger line")
                    entry = _CommitLedgerEntry.from_dict(json.loads(stripped))
                    if entry.task_id != task_id:
                        raise ValueError("ledger task mismatch")
                    if entry.commit_key in entries:
                        raise ValueError("duplicate commit key")
                    entries[entry.commit_key] = entry
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            raise self._ledger_corrupt_error(task_id) from exc
        return entries

    def _append_ledger(
        self,
        ledger_path: Path,
        ledger: dict[str, _CommitLedgerEntry],
        *,
        task_id: str,
        run_id: str,
        commit_key: str,
        action_digest: str,
        status: ActionCommitStatus,
        revision: int,
    ) -> None:
        entry = _CommitLedgerEntry(
            task_id=task_id,
            run_id=run_id,
            commit_key=commit_key,
            action_digest=action_digest,
            status=status,
            revision=revision,
            created_at=_now(),
        )
        line = json.dumps(
            entry.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        parent = ledger_path.parent
        try:
            parent.mkdir(parents=True, exist_ok=True)
            if _is_link(ledger_path):
                raise OSError("commit ledger is a link")
            with ledger_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as exc:
            raise self._error(
                "intervention_commit_persist_failed",
                "Failed to persist the action commit ledger entry.",
                "commit_ledger_writable_required",
                "Repair the task workspace before committing actions.",
            ) from exc
        ledger[commit_key] = entry

    def _ledger_corrupt_error(self, task_id: str) -> HanCodeError:
        return self._error(
            "intervention_commit_ledger_corrupt",
            f"The action commit ledger for {task_id} is corrupt.",
            "valid_commit_ledger_required",
            "Repair or remove the corrupt action_commits.jsonl before continuing.",
        )

    def _project(self, task_id: str) -> dict[str, InterventionRecord]:
        events = self._replay_events(self._log_path(task_id), task_id)
        return self._project_from(events, task_id)

    def _project_from(
        self, events: list[InterventionEvent], task_id: str
    ) -> dict[str, InterventionRecord]:
        records: dict[str, InterventionRecord] = {}
        for event in events:
            if event.event_type is InterventionEventType.SUBMITTED:
                assert event.content is not None
                records[event.intervention_id] = InterventionRecord(
                    intervention_id=event.intervention_id,
                    task_id=event.task_id,
                    run_id=event.run_id,
                    sequence=event.sequence,
                    kind=InterventionKind.STEER,
                    status=InterventionStatus.PENDING,
                    content=event.content,
                    submitted_at=event.created_at,
                    delivered_at=None,
                    consumed_at=None,
                )
            elif event.event_type is InterventionEventType.DELIVERED:
                existing = records[event.intervention_id]
                if existing.status is InterventionStatus.PENDING:
                    records[event.intervention_id] = _replace_status(
                        existing,
                        InterventionStatus.DELIVERED,
                        delivered_at=event.created_at,
                    )
            elif event.event_type is InterventionEventType.CONSUMED:
                existing = records[event.intervention_id]
                records[event.intervention_id] = _replace_status(
                    existing,
                    InterventionStatus.CONSUMED,
                    delivered_at=existing.delivered_at or event.created_at,
                    consumed_at=event.created_at,
                )
        return records

    @staticmethod
    def _record_for_sequence(
        records: Mapping[str, InterventionRecord], sequence: int, run_id: str
    ) -> InterventionRecord | None:
        for record in records.values():
            if record.sequence == sequence and record.run_id == run_id:
                return record
        return None

    @staticmethod
    def _max_sequence(events: list[InterventionEvent]) -> int:
        maximum = 0
        for event in events:
            if event.sequence > maximum:
                maximum = event.sequence
        return maximum

    @staticmethod
    def _next_event_id(events: list[InterventionEvent]) -> str:
        return f"ive-{len(events) + 1:06d}"

    def _replay_events(
        self, path: Path, task_id: str
    ) -> list[InterventionEvent]:
        if _is_link(path) or not path.is_file():
            if _is_link(path):
                raise self._corrupt_error(task_id)
            return []
        events: list[InterventionEvent] = []
        seen_intervention_ids: set[str] = set()
        state_by_id: dict[str, InterventionStatus] = {}
        run_by_id: dict[str, str] = {}
        max_submitted = 0
        try:
            with path.open(encoding="utf-8") as handle:
                for index, line in enumerate(handle, start=1):
                    stripped = line.strip()
                    if not stripped:
                        raise ValueError("empty intervention log line")
                    event = InterventionEvent.from_dict(json.loads(stripped))
                    if event.event_id != f"ive-{index:06d}":
                        raise ValueError("intervention event_id out of sequence")
                    if event.task_id != task_id:
                        raise ValueError("intervention event task mismatch")
                    self._validate_transition(
                        event, seen_intervention_ids, state_by_id, run_by_id
                    )
                    if event.event_type is InterventionEventType.SUBMITTED:
                        if event.sequence != max_submitted + 1:
                            raise ValueError("submitted sequence not contiguous")
                        max_submitted = event.sequence
                    events.append(event)
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            raise self._corrupt_error(task_id) from exc
        return events

    @staticmethod
    def _validate_transition(
        event: InterventionEvent,
        seen: set[str],
        state_by_id: dict[str, InterventionStatus],
        run_by_id: dict[str, str],
    ) -> None:
        if event.event_type is InterventionEventType.SUBMITTED:
            if event.intervention_id in seen:
                raise ValueError("duplicate intervention id")
            seen.add(event.intervention_id)
            state_by_id[event.intervention_id] = InterventionStatus.PENDING
            run_by_id[event.intervention_id] = event.run_id
            return
        if event.intervention_id not in seen:
            raise ValueError("lifecycle event for unknown intervention")
        if run_by_id[event.intervention_id] != event.run_id:
            raise ValueError("cross-run intervention modification")
        current = state_by_id[event.intervention_id]
        if event.event_type is InterventionEventType.DELIVERED:
            if current not in {InterventionStatus.PENDING, InterventionStatus.DELIVERED}:
                raise ValueError("invalid delivered transition")
            state_by_id[event.intervention_id] = InterventionStatus.DELIVERED
        elif event.event_type is InterventionEventType.CONSUMED:
            if current not in {
                InterventionStatus.DELIVERED,
                InterventionStatus.CONSUMED,
            }:
                raise ValueError("invalid consumed transition")
            state_by_id[event.intervention_id] = InterventionStatus.CONSUMED

    def _append_event(
        self, path: Path, events: list[InterventionEvent], event: InterventionEvent
    ) -> None:
        line = json.dumps(
            event.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        parent = path.parent
        try:
            parent.mkdir(parents=True, exist_ok=True)
            if _is_link(path):
                raise OSError("intervention log is a link")
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as exc:
            raise self._error(
                "intervention_persist_failed",
                "Failed to persist the steering event.",
                "intervention_log_writable_required",
                "Repair the task workspace before submitting steering.",
            ) from exc
        events.append(event)

    def _corrupt_error(self, task_id: str) -> HanCodeError:
        return self._error(
            "intervention_log_corrupt",
            f"The intervention log for {task_id} is corrupt.",
            "valid_intervention_log_required",
            "Repair or remove the corrupt interventions.jsonl before continuing.",
        )

    @staticmethod
    def _error(
        error_code: str, message: str, denied_rule: str, suggested_fix: str
    ) -> HanCodeError:
        return HanCodeError(
            StructuredError(
                error_code=error_code,
                message=message,
                phase="unknown",
                denied_rule=denied_rule,
                suggested_fix=suggested_fix,
            )
        )


def _replace_status(
    record: InterventionRecord,
    status: InterventionStatus,
    *,
    delivered_at: str | None = None,
    consumed_at: str | None = None,
) -> InterventionRecord:
    return InterventionRecord(
        intervention_id=record.intervention_id,
        task_id=record.task_id,
        run_id=record.run_id,
        sequence=record.sequence,
        kind=record.kind,
        status=status,
        content=record.content,
        submitted_at=record.submitted_at,
        delivered_at=delivered_at if delivered_at is not None else record.delivered_at,
        consumed_at=consumed_at if consumed_at is not None else record.consumed_at,
    )


@dataclass(frozen=True, slots=True)
class _CommitLedgerEntry:
    task_id: str
    run_id: str
    commit_key: str
    action_digest: str
    status: ActionCommitStatus
    revision: int
    created_at: str

    def to_dict(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "run_id": self.run_id,
            "commit_key": self.commit_key,
            "action_digest": self.action_digest,
            "status": self.status.value,
            "revision": self.revision,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: object) -> _CommitLedgerEntry:
        if not isinstance(data, dict):
            raise ValueError("commit ledger entry must be a JSON object")
        try:
            status = ActionCommitStatus(data["status"])
        except (KeyError, ValueError) as exc:
            raise ValueError("invalid commit ledger status") from exc
        revision = data.get("revision")
        if not isinstance(revision, int) or isinstance(revision, bool):
            raise ValueError("commit ledger revision must be an integer")
        return cls(
            task_id=_require_ledger_str(data, "task_id"),
            run_id=_require_ledger_str(data, "run_id"),
            commit_key=_require_ledger_str(data, "commit_key"),
            action_digest=_require_ledger_str(data, "action_digest"),
            status=status,
            revision=revision,
            created_at=_require_ledger_str(data, "created_at"),
        )


def _require_ledger_str(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"commit ledger field {key!r} must be a non-empty string")
    return value


def _is_link(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or bool(is_junction and is_junction())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
