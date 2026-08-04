"""Filesystem persistence for task-scoped runtime memory."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from tempfile import mkstemp

from hancode.core.errors import HanCodeError, StructuredError
from hancode.core.config import load_config
from hancode.core.actions import Action
from hancode.core.memory import (
    MemoryAppendResult,
    MemoryBlob,
    MemoryIndex,
    MemoryKind,
    MemoryLoadResult,
    MemoryMediaType,
    MemoryQuery,
    MemoryRecord,
    MemoryRecordDraft,
    MemorySearchHit,
    MemorySlice,
    MemorySnapshot,
    digest_memory_index,
    digest_memory_record,
)
from hancode.core.models import OperationStatus, Phase
from hancode.core.state import TaskState, load_state
from hancode.storage.checkpoints import RollbackResult
from hancode.storage.workspace import task_path
from hancode.tooling.registry import ToolResult


class FilesystemMemoryStore:
    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root.resolve()

    def load(self, task_id: str) -> MemoryLoadResult:
        task_root = task_path(self._project_root, task_id)
        state = load_state(task_root)
        config = load_config(self._project_root, task_id)
        if state.task_id != task_id:
            raise _memory_error(
                "memory_task_identity_mismatch",
                "Memory task ID does not match the task workspace.",
                state.current_phase,
                "memory_task_identity_match_required",
                "Use the task ID bound to the task workspace.",
            )
        memory_root = task_root / "memory"
        blobs_root = memory_root / "blobs"
        events_path = memory_root / "events.jsonl"
        index_path = memory_root / "index.json"
        memory_root_existed = memory_root.exists()
        _require_safe_paths((task_root, memory_root, blobs_root, events_path, index_path), state.current_phase)
        try:
            memory_root.mkdir(exist_ok=True)
            _require_safe_paths((memory_root,), state.current_phase)
            blobs_root.mkdir(exist_ok=True)
            _require_safe_paths((blobs_root,), state.current_phase)
            if not events_path.exists():
                if memory_root_existed:
                    raise _memory_corrupt(state.current_phase)
                events_path.touch()
            _require_safe_regular_file(events_path, state.current_phase)
            index_exists = index_path.exists()
            if index_exists:
                _require_safe_regular_file(index_path, state.current_phase)
        except HanCodeError:
            raise
        except OSError as exc:
            raise _memory_write_error(state.current_phase) from exc
        records = _read_records(events_path, task_id, blobs_root, state.current_phase)
        expected_index = _project_index(
            records, task_id, config.max_memory_recent_events
        )
        audit_signals: tuple[str, ...] = ()
        if index_exists:
            persisted_index = _read_index(index_path, state.current_phase)
            if persisted_index.task_id != task_id:
                raise _memory_corrupt(state.current_phase)
            if persisted_index.next_seq > len(records) + 1:
                raise _memory_corrupt(state.current_phase)
            prefix = records[: persisted_index.next_seq - 1]
            if _project_index(prefix, task_id, persisted_index.recent_limit) != persisted_index:
                raise _memory_corrupt(state.current_phase)
            if persisted_index.next_seq < len(records) + 1:
                _atomic_write_json(index_path, expected_index.to_dict(), state.current_phase)
                audit_signals = ("memory_index_recovered",)
            elif persisted_index.recent_limit != config.max_memory_recent_events:
                _atomic_write_json(index_path, expected_index.to_dict(), state.current_phase)
        else:
            _atomic_write_json(index_path, expected_index.to_dict(), state.current_phase)
            if records:
                audit_signals = ("memory_index_recovered",)
        snapshot = _snapshot(records, memory_root, state.current_phase)
        return MemoryLoadResult(
            snapshot=snapshot,
            audit_signals=audit_signals,
        )

    def ensure_capacity(self, task_id: str, *, reserved_bytes: int) -> None:
        state = load_state(task_path(self._project_root, task_id))
        if (
            not isinstance(reserved_bytes, int)
            or isinstance(reserved_bytes, bool)
            or reserved_bytes < 0
        ):
            raise _memory_invalid_record(state.current_phase)
        loaded = self.load(task_id)
        config = load_config(self._project_root, task_id)
        if loaded.snapshot.total_bytes + reserved_bytes > config.max_memory_task_bytes:
            raise _memory_quota_exceeded(state.current_phase)

    def read_blob_bytes(self, task_id: str, memory_id: str) -> bytes:
        """Return one verified blob without exposing the memory filesystem layout."""
        state = load_state(task_path(self._project_root, task_id))
        loaded = self.load(task_id)
        if not isinstance(memory_id, str) or not memory_id:
            raise _memory_invalid_record(state.current_phase)
        record = next(
            (
                candidate
                for candidate in loaded.snapshot.records
                if candidate.memory_id == memory_id
            ),
            None,
        )
        if record is None or record.blob_ref is None:
            raise _memory_invalid_record(state.current_phase)
        blobs_root = task_path(self._project_root, task_id) / "memory" / "blobs"
        _validate_blob(record, blobs_root, state.current_phase)
        try:
            return (blobs_root.parent / record.blob_ref).read_bytes()
        except OSError as exc:
            raise _memory_corrupt(state.current_phase) from exc

    def read(
        self,
        task_id: str,
        memory_id: str,
        *,
        start_line: int,
        end_line: int,
    ) -> MemorySlice:
        state = load_state(task_path(self._project_root, task_id))
        if (
            not isinstance(memory_id, str)
            or not memory_id
            or not isinstance(start_line, int)
            or isinstance(start_line, bool)
            or not isinstance(end_line, int)
            or isinstance(end_line, bool)
            or start_line < 1
            or end_line < start_line
            or end_line - start_line + 1 > 200
        ):
            raise _memory_invalid_record(state.current_phase)
        snapshot = self.load(task_id).snapshot
        records = {record.memory_id: record for record in snapshot.records}
        record = records.get(memory_id)
        if record is None:
            raise _memory_not_found(state.current_phase)
        if record.blob_ref is None or record.media_type is None:
            raise _memory_content_unavailable(state.current_phase)
        content = self.read_blob_bytes(task_id, memory_id)
        try:
            text = content.decode("utf-8")
            if record.media_type is MemoryMediaType.JSON:
                text = json.dumps(
                    json.loads(text), ensure_ascii=False, indent=2, sort_keys=True
                ) + "\n"
        except (UnicodeError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise _memory_corrupt(state.current_phase) from exc
        lines = text.splitlines(keepends=True)
        if start_line > len(lines):
            raise _memory_invalid_record(state.current_phase)
        actual_end = min(end_line, len(lines))
        invalidated_by = dict(snapshot.invalidated_by).get(memory_id)
        stale = invalidated_by is not None
        invalidation_reason = _invalidation_reason(
            records.get(invalidated_by) if invalidated_by is not None else None,
            record.paths,
        )
        authoritative = (
            not stale
            and record.tool_name == "read_file"
            and len(record.paths) == 1
            and dict(snapshot.latest_by_path).get(record.paths[0]) == memory_id
        )
        return MemorySlice(
            memory_id=record.memory_id,
            phase=record.phase,
            kind=record.kind,
            tool_name=record.tool_name,
            media_type=record.media_type,
            paths=record.paths,
            record_generation=record.workspace_generation,
            current_generation=snapshot.workspace_generation,
            stale=stale,
            invalidated_by=invalidated_by,
            invalidation_reason=invalidation_reason,
            current_file_authoritative=authoritative,
            warning=(
                "This stale memory is historical and must not be treated as the current file."
                if stale
                else None
            ),
            start_line=start_line,
            end_line=actual_end,
            total_lines=len(lines),
            content="".join(lines[start_line - 1 : actual_end]),
            content_truncated=False,
            next_start_line=actual_end + 1 if actual_end < len(lines) else None,
        )

    def search(
        self, task_id: str, query: MemoryQuery
    ) -> tuple[MemorySearchHit, ...]:
        state = load_state(task_path(self._project_root, task_id))
        if (
            not isinstance(query, MemoryQuery)
            or not isinstance(query.query, str)
            or not query.query.strip()
            or not isinstance(query.include_stale, bool)
            or not isinstance(query.limit, int)
            or isinstance(query.limit, bool)
            or not 1 <= query.limit <= 20
            or (query.path is not None and not isinstance(query.path, str))
            or (query.phase is not None and not isinstance(query.phase, Phase))
        ):
            raise _memory_invalid_record(state.current_phase)
        if query.path is not None:
            try:
                from hancode.core.memory import _validate_relative_path

                _validate_relative_path(query.path)
            except ValueError as exc:
                raise _memory_invalid_record(state.current_phase) from exc
        snapshot = self.load(task_id).snapshot
        invalidated_by = dict(snapshot.invalidated_by)
        records = {record.memory_id: record for record in snapshot.records}
        needle = query.query.casefold()
        hits: list[MemorySearchHit] = []
        for record in snapshot.records:
            stale = record.memory_id in invalidated_by
            if stale and not query.include_stale:
                continue
            if query.path is not None and query.path not in record.paths:
                continue
            if query.phase is not None and record.phase is not query.phase:
                continue
            sources: list[str] = []
            if any(needle in path.casefold() for path in record.paths):
                sources.append("path")
            if needle in record.summary.casefold():
                sources.append("summary")
            if record.blob_ref is not None:
                try:
                    text = self.read_blob_bytes(task_id, record.memory_id).decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise _memory_corrupt(state.current_phase) from exc
                if needle in text.casefold():
                    sources.append("content")
            if not sources:
                continue
            invalidation_id = invalidated_by.get(record.memory_id)
            hits.append(
                MemorySearchHit(
                    memory_id=record.memory_id,
                    seq=record.seq,
                    phase=record.phase,
                    kind=record.kind,
                    tool_name=record.tool_name,
                    success=record.success,
                    summary=record.summary,
                    error_code=record.error_code,
                    paths=record.paths,
                    media_type=record.media_type,
                    blob_bytes=record.blob_bytes,
                    record_generation=record.workspace_generation,
                    current_generation=snapshot.workspace_generation,
                    stale=stale,
                    invalidated_by=invalidation_id,
                    invalidation_reason=_invalidation_reason(
                        records.get(invalidation_id) if invalidation_id else None,
                        record.paths,
                    ),
                    match_sources=tuple(sources),
                )
            )
        hits.sort(
            key=lambda hit: (
                hit.stale,
                "path" not in hit.match_sources,
                "summary" not in hit.match_sources,
                "content" not in hit.match_sources,
                hit.phase is not state.current_phase,
                -hit.seq,
                hit.memory_id,
            )
        )
        return tuple(hits)

    def record_tool_result(
        self,
        task_id: str,
        *,
        phase: Phase,
        action: Action,
        result: ToolResult,
        observation: object,
        state: TaskState,
    ) -> MemoryRecord:
        del observation
        if (
            not isinstance(action, Action)
            or not isinstance(result, ToolResult)
            or not isinstance(state, TaskState)
            or state.task_id != task_id
            or action.phase is not phase
            or action.tool_name != result.action_name
        ):
            raise _memory_invalid_record(phase)
        paths: tuple[str, ...] = ()
        blob: MemoryBlob | None = None
        kind = MemoryKind.TOOL_RESULT
        invalidates: tuple[str, ...] = ()
        if action.tool_name in {"memory_read", "memory_search"}:
            kind = MemoryKind.MEMORY_ACCESS
        elif action.tool_name == "read_file" and result.success:
            if not isinstance(result.output, Mapping):
                raise _memory_invalid_record(phase)
            path = result.output.get("path")
            content = result.output.get("content")
            if not isinstance(path, str) or not isinstance(content, str):
                raise _memory_invalid_record(phase)
            paths = (path,)
            blob = MemoryBlob.text(content)
        elif action.tool_name == "list_files" and result.success:
            if not isinstance(result.output, Mapping):
                raise _memory_invalid_record(phase)
            path = result.output.get("path")
            if not isinstance(path, str):
                raise _memory_invalid_record(phase)
            paths = () if path == "." else (path,)
            try:
                blob = MemoryBlob.json(result.output)
            except ValueError as exc:
                raise _memory_invalid_record(phase) from exc
        elif action.tool_name in {"search_text", "get_diff"} and result.success:
            if not isinstance(result.output, Mapping):
                raise _memory_invalid_record(phase)
            entries = result.output.get(
                "matches" if action.tool_name == "search_text" else "files"
            )
            if not isinstance(entries, list):
                raise _memory_invalid_record(phase)
            extracted_paths: list[str] = []
            for entry in entries:
                if not isinstance(entry, Mapping):
                    raise _memory_invalid_record(phase)
                path = entry.get("path")
                if not isinstance(path, str):
                    raise _memory_invalid_record(phase)
                extracted_paths.append(path)
            paths = tuple(sorted(set(extracted_paths)))
            try:
                blob = MemoryBlob.json(result.output)
            except ValueError as exc:
                raise _memory_invalid_record(phase) from exc
        elif action.tool_name in {"write_file", "edit_file"}:
            target = action.args.get("path")
            if not isinstance(target, str):
                raise _memory_invalid_record(phase)
            if result.success:
                if not isinstance(result.output, Mapping) or result.output.get("path") != target:
                    raise _memory_invalid_record(phase)
            paths = (target,)
            if result.success or result.mutation_applied is None:
                kind = MemoryKind.INVALIDATION
                latest_by_path = dict(self.load(task_id).snapshot.latest_by_path)
                target_id = latest_by_path.get(target)
                invalidates = () if target_id is None else (target_id,)
        draft = MemoryRecordDraft(
            phase=phase,
            kind=kind,
            tool_name=action.tool_name,
            success=result.success,
            summary=(
                _memory_access_summary(result)
                if kind is MemoryKind.MEMORY_ACCESS
                else _tool_result_summary(result, invalidation=kind is MemoryKind.INVALIDATION)
            ),
            error_code=result.error_code,
            paths=paths,
            checkpoint_id=state.latest_checkpoint,
            invalidates=invalidates,
            blob=blob,
        )
        return self.append(task_id, draft).record

    def record_rollback(
        self,
        task_id: str,
        *,
        phase: Phase,
        result: RollbackResult,
        observation: object,
        state: TaskState,
    ) -> MemoryRecord:
        del observation
        if (
            not isinstance(result, RollbackResult)
            or not isinstance(state, TaskState)
            or state.task_id != task_id
            or result.status is not OperationStatus.SUCCEEDED
            or not isinstance(result.checkpoint_id, str)
            or not result.checkpoint_id
            or not result.restored_files
            or result.failed_files
            or result.error is not None
        ):
            raise _memory_invalid_record(phase)
        paths = tuple(sorted(result.restored_files))
        latest_by_path = dict(self.load(task_id).snapshot.latest_by_path)
        invalidates = tuple(
            memory_id
            for path, memory_id in sorted(latest_by_path.items())
            if path in paths
        )
        return self.append(
            task_id,
            MemoryRecordDraft(
                phase=phase,
                kind=MemoryKind.ROLLBACK,
                tool_name="rollback_last_checkpoint",
                success=True,
                summary=json.dumps(
                    {
                        "outcome": "succeeded",
                        "reason": "rollback",
                        "restored_file_count": len(paths),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                paths=paths,
                checkpoint_id=result.checkpoint_id,
                invalidates=invalidates,
            ),
        ).record

    def append(
        self, task_id: str, draft: MemoryRecordDraft
    ) -> MemoryAppendResult:
        if not isinstance(draft, MemoryRecordDraft):
            raise _memory_invalid_record(Phase.SPEC)
        loaded = self.load(task_id)
        config = load_config(self._project_root, task_id)
        records = loaded.snapshot.records
        seq = len(records) + 1
        generation = loaded.snapshot.workspace_generation + (
            1 if draft.kind in {MemoryKind.INVALIDATION, MemoryKind.ROLLBACK} else 0
        )
        blob = draft.blob
        record = MemoryRecord(
            schema_version=1,
            memory_id=f"mem-{seq:06d}",
            seq=seq,
            task_id=task_id,
            phase=draft.phase,
            kind=draft.kind,
            tool_name=draft.tool_name,
            success=draft.success,
            summary=draft.summary,
            error_code=draft.error_code,
            paths=draft.paths,
            content_sha256=None if blob is None else blob.content_sha256,
            blob_ref=(
                None
                if blob is None
                else f"blobs/{blob.content_sha256}{blob.media_type.extension}"
            ),
            blob_bytes=None if blob is None else blob.byte_count,
            media_type=None if blob is None else blob.media_type,
            workspace_generation=generation,
            checkpoint_id=draft.checkpoint_id,
            invalidates=draft.invalidates,
            record_digest="0" * 64,
        )
        record = replace(record, record_digest=digest_memory_record(record))
        try:
            MemoryRecord.from_dict(record.to_dict())
            prospective_records = (*records, record)
            _validate_replay(prospective_records, task_id)
        except (TypeError, ValueError) as exc:
            raise _memory_invalid_record(draft.phase) from exc

        task_root = task_path(self._project_root, task_id)
        memory_root = task_root / "memory"
        blobs_root = memory_root / "blobs"
        events_path = memory_root / "events.jsonl"
        index_path = memory_root / "index.json"
        if blob is not None:
            blob_path = blobs_root / f"{blob.content_sha256}{blob.media_type.extension}"
            if not blob_path.exists() and blob.byte_count > config.max_memory_blob_bytes:
                raise _memory_blob_too_large(draft.phase)
        index = _project_index(
            prospective_records, task_id, config.max_memory_recent_events
        )
        if (
            _prospective_memory_bytes(
                memory_root,
                index_path,
                blobs_root,
                record,
                index,
                blob,
                draft.phase,
            )
            > config.max_memory_task_bytes
        ):
            raise _memory_quota_exceeded(draft.phase)
        created_blob_path: Path | None = None
        try:
            if blob is not None:
                created_blob_path = _persist_blob(blobs_root, blob, draft.phase)
            _append_event(events_path, record, draft.phase)
            _atomic_write_json(index_path, index.to_dict(), draft.phase)
        except HanCodeError:
            record_persisted = _record_is_persisted(
                events_path,
                task_id,
                blobs_root,
                record,
                draft.phase,
            )
            if record_persisted:
                recovered = self.load(task_id)
                return MemoryAppendResult(
                    record=record,
                    snapshot=recovered.snapshot,
                    audit_signals=loaded.audit_signals + recovered.audit_signals,
                )
            if created_blob_path is not None:
                try:
                    created_blob_path.unlink(missing_ok=True)
                except OSError as exc:
                    raise _memory_write_error(draft.phase) from exc
            raise
        restored = self.load(task_id)
        return MemoryAppendResult(
            record=record,
            snapshot=restored.snapshot,
            audit_signals=loaded.audit_signals + restored.audit_signals,
        )


def _project_index(
    records: tuple[MemoryRecord, ...], task_id: str, recent_limit: int
) -> MemoryIndex:
    latest_by_path, _invalidated_by, generation = _validate_replay(records, task_id)
    index = MemoryIndex(
        schema_version=1,
        task_id=task_id,
        next_seq=len(records) + 1,
        workspace_generation=generation,
        last_record_digest=None if not records else records[-1].record_digest,
        recent_limit=recent_limit,
        recent_memory_ids=tuple(
            record.memory_id for record in records[-recent_limit:]
        ),
        latest_by_path=latest_by_path,
        index_digest="0" * 64,
    )
    return replace(index, index_digest=digest_memory_index(index))


def _snapshot(
    records: tuple[MemoryRecord, ...], memory_root: Path, phase: Phase
) -> MemorySnapshot:
    latest_by_path, invalidated_by, generation = _validate_replay(
        records, memory_root.parent.name
    )
    return MemorySnapshot(
        records=records,
        workspace_generation=generation,
        latest_by_path=latest_by_path,
        invalidated_by=invalidated_by,
        total_bytes=_memory_bytes(memory_root, phase),
    )


def _validate_replay(
    records: tuple[MemoryRecord, ...], task_id: str
) -> tuple[tuple[tuple[str, str], ...], tuple[tuple[str, str], ...], int]:
    latest_by_path: dict[str, str] = {}
    invalidated_by: dict[str, str] = {}
    known_ids: set[str] = set()
    generation = 0
    for expected_seq, record in enumerate(records, start=1):
        if (
            record.seq != expected_seq
            or record.memory_id != f"mem-{expected_seq:06d}"
            or record.task_id != task_id
        ):
            raise ValueError("Memory record sequence or identity is invalid.")
        expected_generation = generation + (
            1
            if record.kind in {MemoryKind.INVALIDATION, MemoryKind.ROLLBACK}
            else 0
        )
        if record.workspace_generation != expected_generation:
            raise ValueError("Memory generation is invalid.")
        for target in record.invalidates:
            if target not in known_ids or target in invalidated_by:
                raise ValueError("Memory invalidation target is invalid.")
            invalidated_by[target] = record.memory_id
            for path, current_id in tuple(latest_by_path.items()):
                if current_id == target:
                    del latest_by_path[path]
        generation = expected_generation
        if (
            record.kind is MemoryKind.TOOL_RESULT
            and record.tool_name == "read_file"
            and record.success
            and record.blob_ref is not None
            and len(record.paths) == 1
        ):
            latest_by_path[record.paths[0]] = record.memory_id
        known_ids.add(record.memory_id)
    return (
        tuple(sorted(latest_by_path.items())),
        tuple(sorted(invalidated_by.items())),
        generation,
    )


def _read_records(
    path: Path, task_id: str, blobs_root: Path, phase: Phase
) -> tuple[MemoryRecord, ...]:
    try:
        content = path.read_bytes()
        if content and not content.endswith(b"\n"):
            raise ValueError("Memory event tail is incomplete.")
        records: list[MemoryRecord] = []
        for line in content.splitlines():
            if not line:
                raise ValueError("Memory event line is empty.")
            value = json.loads(line.decode("utf-8"))
            if not isinstance(value, dict):
                raise ValueError("Memory event must be an object.")
            record = MemoryRecord.from_dict(value)
            _validate_blob(record, blobs_root, phase)
            records.append(record)
        result = tuple(records)
        _validate_replay(result, task_id)
        return result
    except HanCodeError:
        raise
    except (OSError, UnicodeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise _memory_corrupt(phase) from exc


def _read_index(path: Path, phase: Phase) -> MemoryIndex:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("Memory index must be an object.")
        return MemoryIndex.from_dict(value)
    except (OSError, UnicodeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise _memory_corrupt(phase) from exc


def _validate_blob(record: MemoryRecord, blobs_root: Path, phase: Phase) -> None:
    if record.blob_ref is None:
        return
    path = blobs_root.parent / record.blob_ref
    _require_safe_regular_file(path, phase)
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise _memory_corrupt(phase) from exc
    if (
        len(content) != record.blob_bytes
        or hashlib.sha256(content).hexdigest() != record.content_sha256
    ):
        raise _memory_corrupt(phase)


def _persist_blob(
    blobs_root: Path, blob: MemoryBlob, phase: Phase
) -> Path | None:
    path = blobs_root / f"{blob.content_sha256}{blob.media_type.extension}"
    _require_safe_paths((blobs_root, path), phase)
    if path.exists():
        _require_safe_regular_file(path, phase)
        try:
            if path.read_bytes() != blob.content:
                raise _memory_corrupt(phase)
        except OSError as exc:
            raise _memory_corrupt(phase) from exc
        return None
    _atomic_write_bytes(path, blob.content, phase)
    return path


def _record_is_persisted(
    events_path: Path,
    task_id: str,
    blobs_root: Path,
    record: MemoryRecord,
    phase: Phase,
) -> bool:
    records = _read_records(events_path, task_id, blobs_root, phase)
    return any(
        existing.memory_id == record.memory_id
        and existing.record_digest == record.record_digest
        for existing in records
    )


def _append_event(path: Path, record: MemoryRecord, phase: Phase) -> None:
    encoded = _event_bytes(record)
    try:
        _require_safe_regular_file(path, phase)
        with path.open("ab") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except HanCodeError:
        raise
    except OSError as exc:
        raise _memory_write_error(phase) from exc


def _prospective_memory_bytes(
    memory_root: Path,
    index_path: Path,
    blobs_root: Path,
    record: MemoryRecord,
    index: MemoryIndex,
    blob: MemoryBlob | None,
    phase: Phase,
) -> int:
    try:
        total = (
            _memory_bytes(memory_root, phase)
            - index_path.stat().st_size
            + len(_json_document_bytes(index.to_dict()))
            + len(_event_bytes(record))
        )
        if blob is not None:
            blob_path = blobs_root / f"{blob.content_sha256}{blob.media_type.extension}"
            if not blob_path.exists():
                total += blob.byte_count
        return total
    except HanCodeError:
        raise
    except OSError as exc:
        raise _memory_corrupt(phase) from exc


def _event_bytes(record: MemoryRecord) -> bytes:
    return (
        json.dumps(
            record.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _tool_result_summary(result: ToolResult, *, invalidation: bool = False) -> str:
    summary: dict[str, object] = {
        "exit_code": result.exit_code,
        "outcome": "succeeded" if result.success else "failed",
        "timed_out": result.timed_out,
    }
    if invalidation:
        summary["reason"] = "source_write"
    return json.dumps(
        summary,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _memory_access_summary(result: ToolResult) -> str:
    if not result.success:
        return json.dumps(
            {"outcome": "failed", "error_code": result.error_code},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    if not isinstance(result.output, Mapping):
        raise _memory_invalid_record(Phase.SPEC)
    if result.action_name == "memory_read":
        memory_id = result.output.get("memory_id")
        start_line = result.output.get("start_line")
        end_line = result.output.get("end_line")
        stale = result.output.get("stale")
        if (
            not isinstance(memory_id, str)
            or not isinstance(start_line, int)
            or isinstance(start_line, bool)
            or not isinstance(end_line, int)
            or isinstance(end_line, bool)
            or not isinstance(stale, bool)
        ):
            raise _memory_invalid_record(Phase.SPEC)
        summary: dict[str, object] = {
            "outcome": "succeeded",
            "memory_id": memory_id,
            "start_line": start_line,
            "end_line": end_line,
            "stale": stale,
        }
    else:
        returned_count = result.output.get("returned_count")
        hits = result.output.get("hits")
        if (
            not isinstance(returned_count, int)
            or isinstance(returned_count, bool)
            or not isinstance(hits, list)
        ):
            raise _memory_invalid_record(Phase.SPEC)
        memory_ids: list[str] = []
        for hit in hits:
            if not isinstance(hit, Mapping) or not isinstance(hit.get("memory_id"), str):
                raise _memory_invalid_record(Phase.SPEC)
            memory_ids.append(hit["memory_id"])
        summary = {
            "outcome": "succeeded",
            "returned_count": returned_count,
            "memory_ids": memory_ids,
        }
    return json.dumps(
        summary, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def _invalidation_reason(
    invalidation: MemoryRecord | None, paths: tuple[str, ...]
) -> str | None:
    if invalidation is None:
        return None
    try:
        summary = json.loads(invalidation.summary)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(summary, dict):
        return None
    reasons = summary.get("reason_by_path")
    if isinstance(reasons, dict):
        for path in paths:
            reason = reasons.get(path)
            if isinstance(reason, str):
                return reason
    reason = summary.get("reason")
    return reason if isinstance(reason, str) else None


def _json_document_bytes(value: dict[str, object]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _atomic_write_bytes(path: Path, content: bytes, phase: Phase) -> None:
    descriptor, temporary_name = mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary_path = Path(temporary_name)
    try:
        _require_safe_paths((temporary_path, path), phase)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except HanCodeError:
        raise
    except OSError as exc:
        raise _memory_write_error(phase) from exc
    finally:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass


def _atomic_write_json(
    path: Path, value: dict[str, object], phase: Phase
) -> None:
    encoded = _json_document_bytes(value)
    descriptor, temporary_name = mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary_path = Path(temporary_name)
    try:
        _require_safe_paths((temporary_path,), phase)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        _require_safe_paths((path,), phase)
        os.replace(temporary_path, path)
    except HanCodeError:
        raise
    except OSError as exc:
        raise _memory_write_error(phase) from exc
    finally:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass


def _memory_bytes(memory_root: Path, phase: Phase) -> int:
    total = 0
    try:
        for path in memory_root.rglob("*"):
            if path.is_file():
                _require_safe_regular_file(path, phase)
                if not path.name.endswith(".tmp"):
                    total += path.stat().st_size
    except HanCodeError:
        raise
    except OSError as exc:
        raise _memory_corrupt(phase) from exc
    return total


def _require_safe_regular_file(path: Path, phase: Phase) -> None:
    if _is_link(path):
        raise _memory_path_link_error(phase)
    if not path.is_file():
        raise _memory_corrupt(phase)


def _require_safe_paths(paths: tuple[Path, ...], phase: Phase) -> None:
    if any(_is_link(path) for path in paths):
        raise _memory_path_link_error(phase)


def _is_link(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        if callable(is_junction) and is_junction():
            return True
        attributes = getattr(os.lstat(path), "st_file_attributes", 0)
        return bool(
            attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        )
    except FileNotFoundError:
        return False
    except (OSError, RuntimeError):
        return True


def _memory_corrupt(phase: Phase) -> HanCodeError:
    return _memory_error(
        "memory_corrupt",
        "Task runtime memory is invalid or corrupt.",
        phase,
        "valid_runtime_memory_required",
        "Repair or restore the task memory directory before continuing.",
    )


def _memory_write_error(phase: Phase) -> HanCodeError:
    return _memory_error(
        "memory_write_error",
        "Task runtime memory could not be persisted.",
        phase,
        "runtime_memory_persistence_required",
        "Restore task memory write access before continuing.",
    )


def _memory_invalid_record(phase: Phase) -> HanCodeError:
    return _memory_error(
        "memory_invalid_record",
        "Task runtime memory record is invalid.",
        phase,
        "valid_memory_record_required",
        "Provide canonical memory metadata bound to the current task.",
    )


def _memory_not_found(phase: Phase) -> HanCodeError:
    return _memory_error(
        "memory_not_found",
        "The requested memory ID does not exist for the current task.",
        phase,
        "task_bound_memory_id_required",
        "Use memory_search to find a memory ID in the current task.",
    )


def _memory_content_unavailable(phase: Phase) -> HanCodeError:
    return _memory_error(
        "memory_content_unavailable",
        "The requested memory record does not contain readable content.",
        phase,
        "memory_blob_required",
        "Choose a memory record that carries a persisted blob.",
    )


def _memory_blob_too_large(phase: Phase) -> HanCodeError:
    return _memory_error(
        "memory_blob_too_large",
        "Task runtime memory blob exceeds the configured byte limit.",
        phase,
        "max_memory_blob_bytes",
        "Reduce the safe tool payload or increase max_memory_blob_bytes.",
    )


def _memory_quota_exceeded(phase: Phase) -> HanCodeError:
    return _memory_error(
        "memory_quota_exceeded",
        "Task runtime memory exceeds the configured task byte limit.",
        phase,
        "max_memory_task_bytes",
        "Increase max_memory_task_bytes before recording more memory.",
    )


def _memory_path_link_error(phase: Phase) -> HanCodeError:
    return _memory_error(
        "memory_path_link_not_allowed",
        "Task runtime memory paths must not be links or reparse points.",
        phase,
        "canonical_memory_path_required",
        "Replace linked memory paths with regular files and directories inside the task.",
    )


def _memory_error(
    error_code: str,
    message: str,
    phase: Phase,
    denied_rule: str,
    suggested_fix: str,
) -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code=error_code,
            message=message,
            phase=phase.value,
            denied_rule=denied_rule,
            suggested_fix=suggested_fix,
        )
    )


__all__ = ["FilesystemMemoryStore"]
