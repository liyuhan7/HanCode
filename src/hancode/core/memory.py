"""Immutable domain models for task-scoped runtime memory."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath
from typing import Mapping

from hancode.core.models import Phase


_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_MEMORY_ID_RE = re.compile(r"mem-[0-9]{6,}")


class MemoryKind(str, Enum):
    TOOL_RESULT = "tool_result"
    INVALIDATION = "invalidation"
    ROLLBACK = "rollback"
    MEMORY_ACCESS = "memory_access"


class MemoryMediaType(str, Enum):
    TEXT = "text/plain"
    JSON = "application/json"

    @property
    def extension(self) -> str:
        return ".txt" if self is MemoryMediaType.TEXT else ".json"


@dataclass(frozen=True, slots=True)
class MemoryQuery:
    query: str
    path: str | None = None
    phase: Phase | None = None
    include_stale: bool = False
    limit: int = 5


@dataclass(frozen=True, slots=True)
class MemorySlice:
    memory_id: str
    phase: Phase
    kind: MemoryKind
    tool_name: str | None
    media_type: MemoryMediaType
    paths: tuple[str, ...]
    record_generation: int
    current_generation: int
    stale: bool
    invalidated_by: str | None
    invalidation_reason: str | None
    current_file_authoritative: bool
    warning: str | None
    start_line: int
    end_line: int
    total_lines: int
    content: str
    content_truncated: bool
    next_start_line: int | None


@dataclass(frozen=True, slots=True)
class MemorySearchHit:
    memory_id: str
    seq: int
    phase: Phase
    kind: MemoryKind
    tool_name: str | None
    success: bool
    summary: str
    error_code: str | None
    paths: tuple[str, ...]
    media_type: MemoryMediaType | None
    blob_bytes: int | None
    record_generation: int
    current_generation: int
    stale: bool
    invalidated_by: str | None
    invalidation_reason: str | None
    match_sources: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MemoryBlob:
    content: bytes
    media_type: MemoryMediaType
    content_sha256: str
    byte_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.content, bytes):
            raise ValueError("Memory blob content must be bytes.")
        if not isinstance(self.media_type, MemoryMediaType):
            raise ValueError("Memory blob media type is invalid.")
        if (
            not isinstance(self.byte_count, int)
            or isinstance(self.byte_count, bool)
            or self.byte_count != len(self.content)
            or _SHA256_RE.fullmatch(self.content_sha256) is None
            or hashlib.sha256(self.content).hexdigest() != self.content_sha256
        ):
            raise ValueError("Memory blob digest or size is invalid.")

    @classmethod
    def text(cls, value: str) -> MemoryBlob:
        if not isinstance(value, str):
            raise ValueError("Memory text blob must be a string.")
        return cls._from_bytes(value.encode("utf-8"), MemoryMediaType.TEXT)

    @classmethod
    def json(cls, value: object) -> MemoryBlob:
        try:
            content = _canonical_json(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("Memory JSON blob must be JSON-compatible.") from exc
        return cls._from_bytes(content, MemoryMediaType.JSON)

    @classmethod
    def _from_bytes(
        cls, content: bytes, media_type: MemoryMediaType
    ) -> MemoryBlob:
        return cls(
            content=content,
            media_type=media_type,
            content_sha256=hashlib.sha256(content).hexdigest(),
            byte_count=len(content),
        )


@dataclass(frozen=True, slots=True)
class MemoryRecordDraft:
    phase: Phase
    kind: MemoryKind
    tool_name: str | None
    success: bool
    summary: str
    error_code: str | None = None
    paths: tuple[str, ...] = ()
    checkpoint_id: str | None = None
    invalidates: tuple[str, ...] = ()
    blob: MemoryBlob | None = None


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    schema_version: int
    memory_id: str
    seq: int
    task_id: str
    phase: Phase
    kind: MemoryKind
    tool_name: str | None
    success: bool
    summary: str
    error_code: str | None
    paths: tuple[str, ...]
    content_sha256: str | None
    blob_ref: str | None
    blob_bytes: int | None
    media_type: MemoryMediaType | None
    workspace_generation: int
    checkpoint_id: str | None
    invalidates: tuple[str, ...]
    record_digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "memory_id": self.memory_id,
            "seq": self.seq,
            "task_id": self.task_id,
            "phase": self.phase.value,
            "kind": self.kind.value,
            "tool_name": self.tool_name,
            "success": self.success,
            "summary": self.summary,
            "error_code": self.error_code,
            "paths": list(self.paths),
            "content_sha256": self.content_sha256,
            "blob_ref": self.blob_ref,
            "blob_bytes": self.blob_bytes,
            "media_type": None if self.media_type is None else self.media_type.value,
            "workspace_generation": self.workspace_generation,
            "checkpoint_id": self.checkpoint_id,
            "invalidates": list(self.invalidates),
            "record_digest": self.record_digest,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> MemoryRecord:
        if frozenset(data) != frozenset(cls.__dataclass_fields__):
            raise ValueError("Memory record fields do not match schema.")
        paths = _required_string_list(data, "paths")
        invalidates = _required_string_list(data, "invalidates")
        media_value = data.get("media_type")
        record = cls(
            schema_version=_required_int(data, "schema_version"),
            memory_id=_required_text(data, "memory_id"),
            seq=_required_int(data, "seq"),
            task_id=_required_text(data, "task_id"),
            phase=Phase(_required_text(data, "phase")),
            kind=MemoryKind(_required_text(data, "kind")),
            tool_name=_optional_text(data, "tool_name"),
            success=_required_bool(data, "success"),
            summary=_required_text(data, "summary"),
            error_code=_optional_text(data, "error_code"),
            paths=paths,
            content_sha256=_optional_sha256(data, "content_sha256"),
            blob_ref=_optional_text(data, "blob_ref"),
            blob_bytes=_optional_int(data, "blob_bytes"),
            media_type=(
                None
                if media_value is None
                else MemoryMediaType(_required_text(data, "media_type"))
            ),
            workspace_generation=_required_int(data, "workspace_generation"),
            checkpoint_id=_optional_text(data, "checkpoint_id"),
            invalidates=invalidates,
            record_digest=_required_sha256(data, "record_digest"),
        )
        _validate_record(record)
        return record


@dataclass(frozen=True, slots=True)
class MemoryIndex:
    schema_version: int
    task_id: str
    next_seq: int
    workspace_generation: int
    last_record_digest: str | None
    recent_limit: int
    recent_memory_ids: tuple[str, ...]
    latest_by_path: tuple[tuple[str, str], ...]
    index_digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "next_seq": self.next_seq,
            "workspace_generation": self.workspace_generation,
            "last_record_digest": self.last_record_digest,
            "recent_limit": self.recent_limit,
            "recent_memory_ids": list(self.recent_memory_ids),
            "latest_by_path": dict(self.latest_by_path),
            "index_digest": self.index_digest,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> MemoryIndex:
        if frozenset(data) != frozenset(cls.__dataclass_fields__):
            raise ValueError("Memory index fields do not match schema.")
        recent_ids = _required_string_list(data, "recent_memory_ids")
        latest_value = data.get("latest_by_path")
        if not isinstance(latest_value, dict) or not all(
            isinstance(path, str)
            and isinstance(memory_id, str)
            and path
            and memory_id
            for path, memory_id in latest_value.items()
        ):
            raise ValueError("Invalid memory index file mapping.")
        index = cls(
            schema_version=_required_int(data, "schema_version"),
            task_id=_required_text(data, "task_id"),
            next_seq=_required_int(data, "next_seq"),
            workspace_generation=_required_int(data, "workspace_generation"),
            last_record_digest=_optional_sha256(data, "last_record_digest"),
            recent_limit=_required_int(data, "recent_limit"),
            recent_memory_ids=recent_ids,
            latest_by_path=tuple(sorted(latest_value.items())),
            index_digest=_required_sha256(data, "index_digest"),
        )
        if index.schema_version != 1 or index.next_seq < 1:
            raise ValueError("Memory index version or sequence is invalid.")
        if index.workspace_generation < 0 or index.recent_limit < 1:
            raise ValueError("Memory index limits are invalid.")
        for path, memory_id in index.latest_by_path:
            _validate_relative_path(path)
            if _MEMORY_ID_RE.fullmatch(memory_id) is None:
                raise ValueError("Memory index identifier is invalid.")
        if any(_MEMORY_ID_RE.fullmatch(value) is None for value in recent_ids):
            raise ValueError("Memory recent identifier is invalid.")
        if digest_memory_index(index) != index.index_digest:
            raise ValueError("Memory index digest does not match.")
        return index


@dataclass(frozen=True, slots=True)
class MemorySnapshot:
    records: tuple[MemoryRecord, ...]
    workspace_generation: int
    latest_by_path: tuple[tuple[str, str], ...]
    invalidated_by: tuple[tuple[str, str], ...]
    total_bytes: int


@dataclass(frozen=True, slots=True)
class MemoryLoadResult:
    snapshot: MemorySnapshot
    audit_signals: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MemoryAppendResult:
    record: MemoryRecord
    snapshot: MemorySnapshot
    audit_signals: tuple[str, ...] = ()


def digest_memory_record(record: MemoryRecord) -> str:
    data = record.to_dict()
    data.pop("record_digest", None)
    return hashlib.sha256(_canonical_json(data)).hexdigest()


def digest_memory_index(index: MemoryIndex) -> str:
    data = index.to_dict()
    data.pop("index_digest", None)
    return hashlib.sha256(_canonical_json(data)).hexdigest()


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _validate_record(record: MemoryRecord) -> None:
    if record.schema_version != 1:
        raise ValueError("Unsupported memory record schema version.")
    if record.seq < 1 or record.memory_id != f"mem-{record.seq:06d}":
        raise ValueError("Memory record sequence is invalid.")
    if _MEMORY_ID_RE.fullmatch(record.memory_id) is None:
        raise ValueError("Memory record identifier is invalid.")
    if record.workspace_generation < 0:
        raise ValueError("Memory workspace generation is invalid.")
    if len(set(record.paths)) != len(record.paths):
        raise ValueError("Memory record paths must be unique.")
    for path in record.paths:
        _validate_relative_path(path)
    if len(set(record.invalidates)) != len(record.invalidates):
        raise ValueError("Memory invalidation identifiers must be unique.")
    if any(_MEMORY_ID_RE.fullmatch(value) is None for value in record.invalidates):
        raise ValueError("Memory invalidation identifier is invalid.")
    blob_fields = (
        record.content_sha256,
        record.blob_ref,
        record.blob_bytes,
        record.media_type,
    )
    if any(value is None for value in blob_fields) != all(
        value is None for value in blob_fields
    ):
        raise ValueError("Memory blob metadata must be all present or all absent.")
    if record.content_sha256 is not None:
        assert record.media_type is not None
        assert record.blob_ref is not None
        assert record.blob_bytes is not None
        expected_ref = (
            f"blobs/{record.content_sha256}{record.media_type.extension}"
        )
        if record.blob_ref != expected_ref or record.blob_bytes < 0:
            raise ValueError("Memory blob metadata is invalid.")
        if (
            record.kind is not MemoryKind.TOOL_RESULT
            or not record.success
            or record.invalidates
        ):
            raise ValueError("Memory blob is not allowed for this record.")
    if (
        record.kind in {MemoryKind.TOOL_RESULT, MemoryKind.MEMORY_ACCESS}
        and record.tool_name is None
    ):
        raise ValueError("Memory tool record requires a tool name.")
    invalidating_kinds = {MemoryKind.INVALIDATION, MemoryKind.ROLLBACK}
    if record.kind in invalidating_kinds:
        if not record.paths:
            raise ValueError("Memory invalidation record requires paths.")
    elif record.invalidates:
        raise ValueError("Only invalidation records can invalidate memory.")
    if record.record_digest != digest_memory_record(record):
        raise ValueError("Memory record digest does not match.")


def _validate_relative_path(value: str) -> None:
    path = PurePosixPath(value)
    if (
        not value
        or "\\" in value
        or path.is_absolute()
        or value in {".", ".."}
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.as_posix() != value
    ):
        raise ValueError("Memory path is not a canonical relative POSIX path.")


def _required_text(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Invalid memory field: {key}.")
    return value


def _optional_text(data: Mapping[str, object], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    return _required_text(data, key)


def _required_int(data: Mapping[str, object], key: str) -> int:
    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"Invalid memory field: {key}.")
    return value


def _optional_int(data: Mapping[str, object], key: str) -> int | None:
    value = data.get(key)
    if value is None:
        return None
    return _required_int(data, key)


def _required_bool(data: Mapping[str, object], key: str) -> bool:
    value = data.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"Invalid memory field: {key}.")
    return value


def _required_sha256(data: Mapping[str, object], key: str) -> str:
    value = _required_text(data, key)
    if _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"Invalid memory field: {key}.")
    return value


def _optional_sha256(data: Mapping[str, object], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    return _required_sha256(data, key)


def _required_string_list(data: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = data.get(key)
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise ValueError(f"Invalid memory field: {key}.")
    return tuple(value)


__all__ = [
    "MemoryAppendResult",
    "MemoryBlob",
    "MemoryIndex",
    "MemoryKind",
    "MemoryLoadResult",
    "MemoryMediaType",
    "MemoryQuery",
    "MemoryRecord",
    "MemoryRecordDraft",
    "MemorySearchHit",
    "MemorySlice",
    "MemorySnapshot",
    "digest_memory_index",
    "digest_memory_record",
]
