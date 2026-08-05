"""Deterministic, freshness-checked runtime memory projection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from hancode.core.config import HanCodeConfig
from hancode.core.errors import HanCodeError, StructuredError
from hancode.core.memory import MemoryKind, MemoryMediaType, MemoryRecord
from hancode.core.models import Phase
from hancode.core.state import TaskState
from hancode.storage.memory import FilesystemMemoryStore
from hancode.tooling.memory_tools import MemoryFreshnessChecker

_MAX_RECENT_MEMORY_ACCESSES = 2


@dataclass(frozen=True, slots=True)
class MemoryEventContext:
    memory_id: str
    seq: int
    phase: Phase
    kind: MemoryKind
    tool_name: str | None
    success: bool
    summary: str
    error_code: str | None
    paths: tuple[str, ...]
    workspace_generation: int
    stale: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "memory_id": self.memory_id, "seq": self.seq, "phase": self.phase.value,
            "kind": self.kind.value, "tool_name": self.tool_name, "success": self.success,
            "summary": self.summary, "error_code": self.error_code, "paths": list(self.paths),
            "workspace_generation": self.workspace_generation, "stale": self.stale,
        }


@dataclass(frozen=True, slots=True)
class MemoryFileContext:
    path: str
    memory_id: str
    phase: Phase
    seq: int
    content_sha256: str
    blob_bytes: int
    record_generation: int
    current_generation: int
    hot_eligible: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path, "memory_id": self.memory_id, "phase": self.phase.value,
            "seq": self.seq, "content_sha256": self.content_sha256,
            "blob_bytes": self.blob_bytes, "record_generation": self.record_generation,
            "current_generation": self.current_generation, "hot_eligible": self.hot_eligible,
        }


@dataclass(frozen=True, slots=True)
class MemoryHotContent:
    path: str
    memory_id: str
    content_sha256: str
    workspace_generation: int
    content: str

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path, "memory_id": self.memory_id,
            "content_sha256": self.content_sha256,
            "workspace_generation": self.workspace_generation, "content": self.content,
        }


@dataclass(frozen=True, slots=True)
class MemoryContext:
    workspace_generation: int
    recent_events: tuple[MemoryEventContext, ...]
    file_index: tuple[MemoryFileContext, ...]
    hot_contents: tuple[MemoryHotContent, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "workspace_generation": self.workspace_generation,
            "recent_events": [event.to_dict() for event in self.recent_events],
            "file_index": [entry.to_dict() for entry in self.file_index],
            "hot_contents": [entry.to_dict() for entry in self.hot_contents],
        }


@dataclass(frozen=True, slots=True)
class MemoryContextPacker:
    project_root: Path
    config: HanCodeConfig
    store: FilesystemMemoryStore

    def build(
        self, *, task_id: str, phase: Phase, state: TaskState,
        observation: object | None, source_snippets: Mapping[str, str],
    ) -> MemoryContext:
        if state.task_id != task_id:
            raise _memory_context_error("memory_task_identity_mismatch", phase)
        snapshot = MemoryFreshnessChecker(
            self.project_root, self.config, self.store
        ).refresh_all(task_id)
        records = _records_by_id(snapshot.records)
        selected = _select_current_files(
            snapshot.latest_by_path, records, state, phase, self.config.max_memory_file_entries
        )
        invalidated_by = dict(snapshot.invalidated_by)
        file_index = tuple(
            _file_context(path, record, snapshot.workspace_generation)
            for path, record in selected
        )
        hot_contents = self._hot_contents(
            selected, snapshot.workspace_generation, state, observation, source_snippets
        )
        substantive = [
            record
            for record in snapshot.records
            if record.kind is not MemoryKind.MEMORY_ACCESS
        ][-self.config.max_memory_recent_events:]
        accesses = [
            record
            for record in snapshot.records
            if record.kind is MemoryKind.MEMORY_ACCESS
        ][-_MAX_RECENT_MEMORY_ACCESSES:]
        recent = tuple(
            MemoryEventContext(
                memory_id=record.memory_id, seq=record.seq, phase=record.phase, kind=record.kind,
                tool_name=record.tool_name, success=record.success, summary=record.summary,
                error_code=record.error_code, paths=record.paths,
                workspace_generation=record.workspace_generation,
                stale=record.memory_id in invalidated_by,
            )
            for record in (*substantive, *accesses)
        )
        return MemoryContext(snapshot.workspace_generation, recent, file_index, hot_contents)

    def _hot_contents(
        self, selected: tuple[tuple[str, MemoryRecord], ...], generation: int,
        state: TaskState, observation: object | None, source_snippets: Mapping[str, str],
    ) -> tuple[MemoryHotContent, ...]:
        observed_memory_id = _observed_content_memory_id(observation)
        result: list[MemoryHotContent] = []
        for path, record in selected:
            if len(result) >= self.config.max_memory_hot_contents:
                break
            if (
                record.media_type is not MemoryMediaType.TEXT
                or path in source_snippets
                or record.memory_id == observed_memory_id
            ):
                continue
            try:
                content = self.store.read_blob_bytes(state.task_id, record.memory_id).decode("utf-8")
            except UnicodeDecodeError as exc:
                raise _memory_context_error("memory_corrupt", record.phase) from exc
            result.append(MemoryHotContent(
                path=path, memory_id=record.memory_id,
                content_sha256=record.content_sha256 or "",
                workspace_generation=generation, content=content,
            ))
        return tuple(result)


def _records_by_id(records: tuple[MemoryRecord, ...]) -> dict[str, MemoryRecord]:
    return {record.memory_id: record for record in records}


def _select_current_files(
    latest_by_path: tuple[tuple[str, str], ...], records: Mapping[str, MemoryRecord],
    state: TaskState, phase: Phase, limit: int,
) -> tuple[tuple[str, MemoryRecord], ...]:
    selected: list[tuple[str, MemoryRecord]] = []
    for path, memory_id in latest_by_path:
        record = records.get(memory_id)
        if record is None or record.tool_name != "read_file" or not record.success:
            raise _memory_context_error("memory_corrupt", phase)
        selected.append((path, record))
    selected.sort(key=lambda item: (
        item[0] not in state.files_changed, item[1].phase is not phase,
        -item[1].seq, item[0].casefold(), item[0],
    ))
    return tuple(selected[:limit])


def _file_context(path: str, record: MemoryRecord, generation: int) -> MemoryFileContext:
    if record.content_sha256 is None or record.blob_bytes is None:
        raise _memory_context_error("memory_corrupt", record.phase)
    return MemoryFileContext(
        path=path, memory_id=record.memory_id, phase=record.phase, seq=record.seq,
        content_sha256=record.content_sha256, blob_bytes=record.blob_bytes,
        record_generation=record.workspace_generation, current_generation=generation,
        hot_eligible=record.media_type is MemoryMediaType.TEXT,
    )


def _observed_content_memory_id(observation: object | None) -> str | None:
    if not isinstance(observation, Mapping):
        return None
    memory_ref = observation.get("memory_ref")
    if not isinstance(memory_ref, Mapping) or memory_ref.get("has_content") is not True:
        return None
    memory_id = memory_ref.get("memory_id")
    return memory_id if isinstance(memory_id, str) else None


def _memory_context_error(error_code: str, phase: Phase) -> HanCodeError:
    return HanCodeError(StructuredError(
        error_code=error_code,
        message="Task runtime memory cannot be projected into context.",
        phase=phase.value,
        denied_rule="valid_runtime_memory_required",
        suggested_fix="Repair task runtime memory before continuing.",
    ))
