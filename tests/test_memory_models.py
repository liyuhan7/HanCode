from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import pytest

from hancode.core.memory import (
    MemoryBlob,
    MemoryKind,
    MemoryMediaType,
    MemoryQuery,
    MemoryRecord,
    MemorySearchHit,
    MemorySlice,
    digest_memory_record,
)
from hancode.core.models import Phase


def _valid_record() -> MemoryRecord:
    record = MemoryRecord(
        schema_version=1,
        memory_id="mem-000001",
        seq=1,
        task_id="task-001",
        phase=Phase.CODE,
        kind=MemoryKind.TOOL_RESULT,
        tool_name="read_file",
        success=True,
        summary="Read src/main.py.",
        error_code=None,
        paths=("src/main.py",),
        content_sha256="a" * 64,
        blob_ref=f"blobs/{'a' * 64}.txt",
        blob_bytes=12,
        media_type=MemoryMediaType.TEXT,
        workspace_generation=0,
        checkpoint_id=None,
        invalidates=(),
        record_digest="0" * 64,
    )
    return replace(record, record_digest=digest_memory_record(record))


def test_memory_record_strictly_round_trips_with_stable_digest() -> None:
    record = _valid_record()

    restored = MemoryRecord.from_dict(record.to_dict())

    assert restored == record
    assert digest_memory_record(restored) == record.record_digest


def test_memory_blob_canonicalizes_text_and_json_content() -> None:
    text_blob = MemoryBlob.text("你好\r\n")
    json_blob = MemoryBlob.json({"z": 1, "message": "你好"})

    assert text_blob.content == "你好\r\n".encode()
    assert text_blob.media_type is MemoryMediaType.TEXT
    assert text_blob.byte_count == len(text_blob.content)
    assert json_blob.content == '{"message":"你好","z":1}'.encode()
    assert json_blob.media_type is MemoryMediaType.JSON


@pytest.mark.parametrize(
    "mutate",
    [
        lambda data: data.update({"extra": True}),
        lambda data: data.update({"schema_version": True}),
        lambda data: data.update({"paths": ["../outside.py"]}),
        lambda data: data.update({"kind": "invalidation"}),
    ],
)
def test_memory_record_rejects_noncanonical_schema(
    mutate: Callable[[dict[str, object]], None],
) -> None:
    data = _valid_record().to_dict()
    mutate(data)

    with pytest.raises(ValueError):
        MemoryRecord.from_dict(data)


def test_memory_blob_rejects_forged_digest_or_size() -> None:
    with pytest.raises(ValueError):
        MemoryBlob(
            content=b"content",
            media_type=MemoryMediaType.TEXT,
            content_sha256="0" * 64,
            byte_count=1,
        )


def test_memory_query_slice_and_search_hit_are_immutable_slot_models() -> None:
    query = MemoryQuery(query="needle")
    slice_ = MemorySlice(
        memory_id="mem-000001",
        phase=Phase.CODE,
        kind=MemoryKind.TOOL_RESULT,
        tool_name="read_file",
        media_type=MemoryMediaType.TEXT,
        paths=("src/main.py",),
        record_generation=0,
        current_generation=0,
        stale=False,
        invalidated_by=None,
        invalidation_reason=None,
        current_file_authoritative=True,
        warning=None,
        start_line=1,
        end_line=1,
        total_lines=1,
        content="needle\n",
        content_truncated=False,
        next_start_line=None,
    )
    hit = MemorySearchHit(
        memory_id="mem-000001",
        seq=1,
        phase=Phase.CODE,
        kind=MemoryKind.TOOL_RESULT,
        tool_name="read_file",
        success=True,
        summary="Read src/main.py.",
        error_code=None,
        paths=("src/main.py",),
        media_type=MemoryMediaType.TEXT,
        blob_bytes=7,
        record_generation=0,
        current_generation=0,
        stale=False,
        invalidated_by=None,
        invalidation_reason=None,
        match_sources=("content",),
    )

    assert query.limit == 5
    assert slice_.current_file_authoritative is True
    assert hit.match_sources == ("content",)
    with pytest.raises((AttributeError, TypeError)):
        query.limit = 10  # type: ignore[misc]
