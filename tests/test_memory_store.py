from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from hancode.core.actions import Action, ActionType
from hancode.core.errors import HanCodeError
from hancode.core.memory import MemoryBlob, MemoryKind, MemoryQuery, MemoryRecordDraft
from hancode.core.models import OperationStatus, Phase
from hancode.core.state import load_state
from hancode.storage.checkpoints import RollbackResult
from hancode.storage.memory import FilesystemMemoryStore, _read_verified_blob
from hancode.storage.workspace import init_project_workspace, init_task_workspace
from hancode.tooling.registry import ToolResult


def _initialize_task(project_root: Path, task_id: str = "task-001") -> Path:
    init_project_workspace(
        project_root,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Harness",
    )
    return init_task_workspace(project_root, task_id, goal="Implement memory.")


def _set_config(project_root: Path, **values: object) -> None:
    path = project_root / ".hancode" / "project.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(values)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_load_lazily_initializes_memory_for_an_existing_task(tmp_path: Path) -> None:
    task_root = _initialize_task(tmp_path)
    memory_root = task_root / "memory"
    assert not memory_root.exists()

    result = FilesystemMemoryStore(tmp_path).load("task-001")

    assert result.snapshot.records == ()
    assert result.snapshot.workspace_generation == 0
    assert result.snapshot.latest_by_path == ()
    assert result.snapshot.invalidated_by == ()
    assert result.audit_signals == ()
    assert (memory_root / "events.jsonl").read_text(encoding="utf-8") == ""
    assert (memory_root / "blobs").is_dir()
    assert json.loads((memory_root / "index.json").read_text(encoding="utf-8"))[
        "next_seq"
    ] == 1


def test_append_read_file_memory_is_restored_by_another_store(tmp_path: Path) -> None:
    task_root = _initialize_task(tmp_path)
    store = FilesystemMemoryStore(tmp_path)
    draft = MemoryRecordDraft(
        phase=Phase.CODE,
        kind=MemoryKind.TOOL_RESULT,
        tool_name="read_file",
        success=True,
        summary="Read src/main.py.",
        paths=("src/main.py",),
        blob=MemoryBlob.text("print('hello')\n"),
    )

    appended = store.append("task-001", draft)
    restored = FilesystemMemoryStore(tmp_path).load("task-001")

    assert appended.record.memory_id == "mem-000001"
    assert restored.snapshot.records == (appended.record,)
    assert restored.snapshot.latest_by_path == (("src/main.py", "mem-000001"),)
    blob_path = task_root / "memory" / appended.record.blob_ref  # type: ignore[operator]
    assert blob_path.read_bytes() == b"print('hello')\n"


def test_read_returns_task_bound_text_blob_lines_and_authority(tmp_path: Path) -> None:
    _initialize_task(tmp_path)
    store = FilesystemMemoryStore(tmp_path)
    record = store.append(
        "task-001",
        MemoryRecordDraft(
            phase=Phase.CODE,
            kind=MemoryKind.TOOL_RESULT,
            tool_name="read_file",
            success=True,
            summary="Read src/main.py.",
            paths=("src/main.py",),
            blob=MemoryBlob.text("first\nsecond\nthird\n"),
        ),
    ).record

    result = store.read(
        "task-001", record.memory_id, start_line=1, end_line=2
    )

    assert result.memory_id == record.memory_id
    assert result.start_line == 1
    assert result.end_line == 2
    assert result.total_lines == 3
    assert result.content == "first\nsecond\n"
    assert result.next_start_line == 3
    assert result.stale is False
    assert result.current_file_authoritative is True


def test_read_reports_stable_errors_for_missing_content_and_range(tmp_path: Path) -> None:
    _initialize_task(tmp_path)
    store = FilesystemMemoryStore(tmp_path)
    metadata = store.append(
        "task-001",
        MemoryRecordDraft(
            phase=Phase.CODE,
            kind=MemoryKind.TOOL_RESULT,
            tool_name="run_tests",
            success=True,
            summary="Tests passed.",
        ),
    ).record

    with pytest.raises(HanCodeError) as missing:
        store.read("task-001", "mem-999999", start_line=1, end_line=1)
    with pytest.raises(HanCodeError) as unavailable:
        store.read("task-001", metadata.memory_id, start_line=1, end_line=1)

    content = store.append(
        "task-001",
        MemoryRecordDraft(
            phase=Phase.CODE,
            kind=MemoryKind.TOOL_RESULT,
            tool_name="read_file",
            success=True,
            summary="Read src/main.py.",
            paths=("src/main.py",),
            blob=MemoryBlob.text("one line\n"),
        ),
    ).record
    with pytest.raises(HanCodeError) as invalid_range:
        store.read("task-001", content.memory_id, start_line=2, end_line=2)

    assert missing.value.structured_error.error_code == "memory_not_found"
    assert unavailable.value.structured_error.error_code == "memory_content_unavailable"
    assert invalid_range.value.structured_error.error_code == "memory_invalid_record"


def test_record_tool_result_persists_a_read_file_snapshot(tmp_path: Path) -> None:
    task_root = _initialize_task(tmp_path)
    action = Action(
        type=ActionType.TOOL_CALL,
        phase=Phase.CODE,
        tool_name="read_file",
        args={"path": "src/main.py"},
        reason=None,
    )
    result = ToolResult(
        success=True,
        action_name="read_file",
        output={"path": "src/main.py", "content": "print('hello')\n", "redacted": False},
    )

    record = FilesystemMemoryStore(tmp_path).record_tool_result(
        "task-001",
        phase=Phase.CODE,
        action=action,
        result=result,
        observation={"kind": "tool_feedback"},
        state=load_state(task_root),
    )

    assert record.kind is MemoryKind.TOOL_RESULT
    assert record.paths == ("src/main.py",)
    assert record.blob_ref is not None and record.blob_ref.endswith(".txt")
    assert "print('hello')" not in record.summary
    assert FilesystemMemoryStore(tmp_path).load("task-001").snapshot.latest_by_path == (
        ("src/main.py", record.memory_id),
    )


def test_record_successful_write_invalidates_the_current_read_snapshot(
    tmp_path: Path,
) -> None:
    task_root = _initialize_task(tmp_path)
    store = FilesystemMemoryStore(tmp_path)
    read_action = Action(
        type=ActionType.TOOL_CALL,
        phase=Phase.CODE,
        tool_name="read_file",
        args={"path": "src/main.py"},
        reason=None,
    )
    read = store.record_tool_result(
        "task-001",
        phase=Phase.CODE,
        action=read_action,
        result=ToolResult(
            success=True,
            action_name="read_file",
            output={"path": "src/main.py", "content": "before\n", "redacted": False},
        ),
        observation={"kind": "tool_feedback"},
        state=load_state(task_root),
    )
    write_action = Action(
        type=ActionType.TOOL_CALL,
        phase=Phase.CODE,
        tool_name="write_file",
        args={"path": "src/main.py", "content": "after\n"},
        reason="Replace the implementation.",
    )

    invalidation = store.record_tool_result(
        "task-001",
        phase=Phase.CODE,
        action=write_action,
        result=ToolResult(
            success=True,
            action_name="write_file",
            output={"path": "src/main.py", "bytes_written": 6},
            mutation_applied=True,
        ),
        observation={"kind": "tool_feedback"},
        state=load_state(task_root),
    )

    assert invalidation.kind is MemoryKind.INVALIDATION
    assert invalidation.invalidates == (read.memory_id,)
    assert invalidation.workspace_generation == 1
    assert store.load("task-001").snapshot.latest_by_path == ()

    stale = store.read(
        "task-001", read.memory_id, start_line=1, end_line=1
    )
    assert stale.invalidation_reason == "source_write"


def test_repeated_read_supersedes_old_snapshot_without_advancing_generation(
    tmp_path: Path,
) -> None:
    _initialize_task(tmp_path)
    store = FilesystemMemoryStore(tmp_path)
    first = store.append(
        "task-001",
        MemoryRecordDraft(
            phase=Phase.CODE,
            kind=MemoryKind.TOOL_RESULT,
            tool_name="read_file",
            success=True,
            summary="Read src/main.py first.",
            paths=("src/main.py",),
            blob=MemoryBlob.text("v1\n"),
        ),
    ).record
    second = store.append(
        "task-001",
        MemoryRecordDraft(
            phase=Phase.CODE,
            kind=MemoryKind.TOOL_RESULT,
            tool_name="read_file",
            success=True,
            summary="Read src/main.py again.",
            paths=("src/main.py",),
            blob=MemoryBlob.text("v1\n"),
        ),
    ).record

    snapshot = store.load("task-001").snapshot
    old = store.read("task-001", first.memory_id, start_line=1, end_line=1)
    current = store.read("task-001", second.memory_id, start_line=1, end_line=1)

    assert snapshot.workspace_generation == 0
    assert snapshot.latest_by_path == (("src/main.py", second.memory_id),)
    assert snapshot.superseded_by == ((first.memory_id, second.memory_id),)
    assert old.stale is True
    assert old.superseded_by == second.memory_id
    assert old.invalidation_reason == "superseded"
    assert old.current_file_authoritative is False
    assert current.stale is False
    assert current.current_file_authoritative is True


def test_write_leaves_all_snapshots_for_same_path_stale(tmp_path: Path) -> None:
    task_root = _initialize_task(tmp_path)
    store = FilesystemMemoryStore(tmp_path)
    read_action = Action(
        type=ActionType.TOOL_CALL,
        phase=Phase.CODE,
        tool_name="read_file",
        args={"path": "src/main.py"},
        reason=None,
    )
    reads = [
        store.record_tool_result(
            "task-001",
            phase=Phase.CODE,
            action=read_action,
            result=ToolResult(
                success=True,
                action_name="read_file",
                output={"path": "src/main.py", "content": "v1\n", "redacted": False},
            ),
            observation={"kind": "tool_feedback"},
            state=load_state(task_root),
        )
        for _ in range(2)
    ]
    write_action = Action(
        type=ActionType.TOOL_CALL,
        phase=Phase.CODE,
        tool_name="write_file",
        args={"path": "src/main.py", "content": "v2\n"},
        reason="Update implementation.",
    )

    store.record_tool_result(
        "task-001",
        phase=Phase.CODE,
        action=write_action,
        result=ToolResult(
            success=True,
            action_name="write_file",
            output={"path": "src/main.py", "bytes_written": 3},
            mutation_applied=True,
        ),
        observation={"kind": "tool_feedback"},
        state=load_state(task_root),
    )

    assert all(
        store.read("task-001", record.memory_id, start_line=1, end_line=1).stale
        for record in reads
    )


def test_record_rollback_invalidates_the_current_read_snapshot(tmp_path: Path) -> None:
    task_root = _initialize_task(tmp_path)
    store = FilesystemMemoryStore(tmp_path)
    read_action = Action(
        type=ActionType.TOOL_CALL,
        phase=Phase.REVIEW,
        tool_name="read_file",
        args={"path": "src/main.py"},
        reason=None,
    )
    read = store.record_tool_result(
        "task-001",
        phase=Phase.REVIEW,
        action=read_action,
        result=ToolResult(
            success=True,
            action_name="read_file",
            output={"path": "src/main.py", "content": "after\n", "redacted": False},
        ),
        observation={"kind": "tool_feedback"},
        state=load_state(task_root),
    )

    rollback = store.record_rollback(
        "task-001",
        phase=Phase.REVIEW,
        result=RollbackResult(
            status=OperationStatus.SUCCEEDED,
            checkpoint_id="cp-000001",
            restored_files=("src/main.py",),
            failed_files=(),
            error=None,
        ),
        observation={"kind": "rollback_feedback"},
        state=load_state(task_root),
    )

    assert rollback.kind is MemoryKind.ROLLBACK
    assert rollback.invalidates == (read.memory_id,)
    assert rollback.workspace_generation == 1
    stale = store.read(
        "task-001", read.memory_id, start_line=1, end_line=1
    )
    assert stale.invalidation_reason == "rollback"


def test_record_list_files_keeps_a_json_payload_without_file_snapshot(
    tmp_path: Path,
) -> None:
    task_root = _initialize_task(tmp_path)
    action = Action(
        type=ActionType.TOOL_CALL,
        phase=Phase.CODE,
        tool_name="list_files",
        args={"path": "src"},
        reason=None,
    )

    record = FilesystemMemoryStore(tmp_path).record_tool_result(
        "task-001",
        phase=Phase.CODE,
        action=action,
        result=ToolResult(
            success=True,
            action_name="list_files",
            output={"path": "src", "files": ["src/main.py"]},
        ),
        observation={"kind": "tool_feedback"},
        state=load_state(task_root),
    )

    assert record.blob_ref is not None and record.blob_ref.endswith(".json")
    assert record.paths == ("src",)
    assert FilesystemMemoryStore(tmp_path).load("task-001").snapshot.latest_by_path == ()


@pytest.mark.parametrize(
    ("tool_name", "args", "result", "expected_summary"),
    [
        (
            "memory_read",
            {"memory_id": "mem-000001", "start_line": 1, "end_line": 200},
            ToolResult(
                success=True,
                action_name="memory_read",
                output={
                    "memory_id": "mem-000001",
                    "start_line": 1,
                    "end_line": 3,
                    "stale": True,
                    "content": "secret historical body",
                },
            ),
            {
                "outcome": "succeeded",
                "memory_id": "mem-000001",
                "start_line": 1,
                "end_line": 3,
                "stale": True,
            },
        ),
        (
            "memory_search",
            {"query": "secret query"},
            ToolResult(
                success=True,
                action_name="memory_search",
                output={
                    "returned_count": 2,
                    "hits": [
                        {"memory_id": "mem-000002"},
                        {"memory_id": "mem-000001"},
                    ],
                },
            ),
            {
                "outcome": "succeeded",
                "returned_count": 2,
                "memory_ids": ["mem-000002", "mem-000001"],
            },
        ),
        (
            "memory_read",
            {"memory_id": "mem-999999"},
            ToolResult(
                success=False,
                action_name="memory_read",
                error_summary="Missing memory.",
                error_code="memory_not_found",
                mutation_applied=False,
            ),
            {"outcome": "failed", "error_code": "memory_not_found"},
        ),
    ],
)
def test_record_memory_tool_access_keeps_metadata_without_query_or_blob(
    tmp_path: Path,
    tool_name: str,
    args: dict[str, object],
    result: ToolResult,
    expected_summary: dict[str, object],
) -> None:
    task_root = _initialize_task(tmp_path)
    action = Action(
        type=ActionType.TOOL_CALL,
        phase=Phase.CODE,
        tool_name=tool_name,
        args=args,
        reason=None,
    )

    record = FilesystemMemoryStore(tmp_path).record_tool_result(
        "task-001",
        phase=Phase.CODE,
        action=action,
        result=result,
        observation={"kind": "tool_feedback"},
        state=load_state(task_root),
    )

    assert record.kind is MemoryKind.MEMORY_ACCESS
    assert record.blob_ref is None
    assert json.loads(record.summary) == expected_summary
    assert "secret query" not in record.summary
    assert "secret historical body" not in record.summary


@pytest.mark.parametrize(
    ("tool_name", "args", "output", "expected_paths"),
    [
        (
            "search_text",
            {"query": "TODO"},
            {"query": "TODO", "matches": [{"path": "src/a.py"}, {"path": "src/b.py"}]},
            ("src/a.py", "src/b.py"),
        ),
        (
            "get_diff",
            {},
            {"files": [{"path": "src/a.py", "diff": "@@"}]},
            ("src/a.py",),
        ),
    ],
)
def test_record_search_and_diff_keep_json_payloads(
    tmp_path: Path,
    tool_name: str,
    args: dict[str, object],
    output: dict[str, object],
    expected_paths: tuple[str, ...],
) -> None:
    task_root = _initialize_task(tmp_path)
    action = Action(
        type=ActionType.TOOL_CALL,
        phase=Phase.CODE,
        tool_name=tool_name,
        args=args,
        reason=None,
    )

    record = FilesystemMemoryStore(tmp_path).record_tool_result(
        "task-001",
        phase=Phase.CODE,
        action=action,
        result=ToolResult(success=True, action_name=tool_name, output=output),
        observation={"kind": "tool_feedback"},
        state=load_state(task_root),
    )

    assert record.paths == expected_paths
    assert record.blob_ref is not None and record.blob_ref.endswith(".json")
    assert record.summary == '{"exit_code":null,"outcome":"succeeded","timed_out":false}'


def test_record_successful_write_rejects_a_mismatched_output_path(tmp_path: Path) -> None:
    task_root = _initialize_task(tmp_path)
    action = Action(
        type=ActionType.TOOL_CALL,
        phase=Phase.CODE,
        tool_name="write_file",
        args={"path": "src/main.py", "content": "after\n"},
        reason="Replace the implementation.",
    )

    with pytest.raises(HanCodeError) as exc_info:
        FilesystemMemoryStore(tmp_path).record_tool_result(
            "task-001",
            phase=Phase.CODE,
            action=action,
            result=ToolResult(
                success=True,
                action_name="write_file",
                output={"path": "src/other.py", "bytes_written": 6},
                mutation_applied=True,
            ),
            observation={"kind": "tool_feedback"},
            state=load_state(task_root),
        )

    assert exc_info.value.structured_error.error_code == "memory_invalid_record"


def test_same_content_creates_two_records_and_one_blob(tmp_path: Path) -> None:
    task_root = _initialize_task(tmp_path)
    store = FilesystemMemoryStore(tmp_path)
    blob = MemoryBlob.text("shared content\n")

    first = store.append(
        "task-001",
        MemoryRecordDraft(
            phase=Phase.CODE,
            kind=MemoryKind.TOOL_RESULT,
            tool_name="read_file",
            success=True,
            summary="Read src/a.py.",
            paths=("src/a.py",),
            blob=blob,
        ),
    )
    second = store.append(
        "task-001",
        MemoryRecordDraft(
            phase=Phase.CODE,
            kind=MemoryKind.TOOL_RESULT,
            tool_name="read_file",
            success=True,
            summary="Read src/b.py.",
            paths=("src/b.py",),
            blob=blob,
        ),
    )

    assert (first.record.memory_id, second.record.memory_id) == (
        "mem-000001",
        "mem-000002",
    )
    assert len(FilesystemMemoryStore(tmp_path).load("task-001").snapshot.records) == 2
    assert [path.name for path in (task_root / "memory" / "blobs").iterdir()] == [
        f"{blob.content_sha256}.txt"
    ]


def test_load_recovers_a_valid_event_tail_ahead_of_index(tmp_path: Path) -> None:
    task_root = _initialize_task(tmp_path)
    store = FilesystemMemoryStore(tmp_path)
    store.load("task-001")
    index_path = task_root / "memory" / "index.json"
    initial_index = index_path.read_bytes()
    appended = store.append(
        "task-001",
        MemoryRecordDraft(
            phase=Phase.CODE,
            kind=MemoryKind.TOOL_RESULT,
            tool_name="list_files",
            success=True,
            summary="Listed source files.",
        ),
    )
    index_path.write_bytes(initial_index)

    recovered = FilesystemMemoryStore(tmp_path).load("task-001")

    assert recovered.snapshot.records == (appended.record,)
    assert recovered.audit_signals == ("memory_index_recovered",)
    assert json.loads(index_path.read_text(encoding="utf-8"))["next_seq"] == 2


def test_load_fails_closed_when_a_referenced_blob_is_missing(tmp_path: Path) -> None:
    task_root = _initialize_task(tmp_path)
    appended = FilesystemMemoryStore(tmp_path).append(
        "task-001",
        MemoryRecordDraft(
            phase=Phase.CODE,
            kind=MemoryKind.TOOL_RESULT,
            tool_name="read_file",
            success=True,
            summary="Read src/main.py.",
            paths=("src/main.py",),
            blob=MemoryBlob.text("content\n"),
        ),
    )
    blob_path = task_root / "memory" / appended.record.blob_ref  # type: ignore[operator]
    blob_path.unlink()

    with pytest.raises(HanCodeError) as exc_info:
        FilesystemMemoryStore(tmp_path).load("task-001")

    assert exc_info.value.structured_error.error_code == "memory_corrupt"


def test_append_rejects_blob_over_utf8_byte_limit(tmp_path: Path) -> None:
    _initialize_task(tmp_path)
    _set_config(tmp_path, max_memory_blob_bytes=5)

    with pytest.raises(HanCodeError) as exc_info:
        FilesystemMemoryStore(tmp_path).append(
            "task-001",
            MemoryRecordDraft(
                phase=Phase.CODE,
                kind=MemoryKind.TOOL_RESULT,
                tool_name="read_file",
                success=True,
                summary="Read src/main.py.",
                paths=("src/main.py",),
                blob=MemoryBlob.text("你好"),
            ),
        )

    assert exc_info.value.structured_error.error_code == "memory_blob_too_large"


def test_ensure_capacity_uses_actual_task_memory_bytes(tmp_path: Path) -> None:
    _initialize_task(tmp_path)
    store = FilesystemMemoryStore(tmp_path)
    current_bytes = store.load("task-001").snapshot.total_bytes
    _set_config(tmp_path, max_memory_task_bytes=current_bytes)

    store.ensure_capacity("task-001", reserved_bytes=0)
    with pytest.raises(HanCodeError) as exc_info:
        store.ensure_capacity("task-001", reserved_bytes=1)

    assert exc_info.value.structured_error.error_code == "memory_quota_exceeded"


def test_append_checks_prospective_total_before_writing(tmp_path: Path) -> None:
    task_root = _initialize_task(tmp_path)
    store = FilesystemMemoryStore(tmp_path)
    current_bytes = store.load("task-001").snapshot.total_bytes
    _set_config(tmp_path, max_memory_task_bytes=current_bytes + 1)

    with pytest.raises(HanCodeError) as exc_info:
        store.append(
            "task-001",
            MemoryRecordDraft(
                phase=Phase.CODE,
                kind=MemoryKind.TOOL_RESULT,
                tool_name="read_file",
                success=True,
                summary="Read src/main.py.",
                paths=("src/main.py",),
                blob=MemoryBlob.text("content\n"),
            ),
        )

    assert exc_info.value.structured_error.error_code == "memory_quota_exceeded"
    assert (task_root / "memory" / "events.jsonl").read_bytes() == b""
    assert list((task_root / "memory" / "blobs").iterdir()) == []


def test_invalidation_advances_generation_and_removes_current_file(tmp_path: Path) -> None:
    _initialize_task(tmp_path)
    store = FilesystemMemoryStore(tmp_path)
    read = store.append(
        "task-001",
        MemoryRecordDraft(
            phase=Phase.CODE,
            kind=MemoryKind.TOOL_RESULT,
            tool_name="read_file",
            success=True,
            summary="Read src/main.py.",
            paths=("src/main.py",),
            blob=MemoryBlob.text("v1\n"),
        ),
    )

    invalidation = store.append(
        "task-001",
        MemoryRecordDraft(
            phase=Phase.CODE,
            kind=MemoryKind.INVALIDATION,
            tool_name=None,
            success=True,
            summary="src/main.py changed.",
            paths=("src/main.py",),
            invalidates=(read.record.memory_id,),
        ),
    )

    assert invalidation.record.workspace_generation == 1
    assert invalidation.snapshot.latest_by_path == ()
    assert invalidation.snapshot.invalidated_by == (
        (read.record.memory_id, invalidation.record.memory_id),
    )


def test_path_only_invalidation_advances_generation_without_snapshot(tmp_path: Path) -> None:
    _initialize_task(tmp_path)

    appended = FilesystemMemoryStore(tmp_path).append(
        "task-001",
        MemoryRecordDraft(
            phase=Phase.CODE,
            kind=MemoryKind.INVALIDATION,
            tool_name="write_file",
            success=True,
            summary="{\"outcome\":\"succeeded\"}",
            paths=("src/new_file.py",),
        ),
    )

    assert appended.record.workspace_generation == 1
    assert appended.record.invalidates == ()
    assert appended.snapshot.workspace_generation == 1


def test_append_evicts_stale_blob_bodies_to_free_capacity(tmp_path: Path) -> None:
    task_root = _initialize_task(tmp_path)
    store = FilesystemMemoryStore(tmp_path)
    read = store.record_tool_result(
        "task-001",
        phase=Phase.CODE,
        action=Action(
            type=ActionType.TOOL_CALL,
            phase=Phase.CODE,
            tool_name="read_file",
            args={"path": "src/main.py"},
            reason=None,
        ),
        result=ToolResult(
            success=True,
            action_name="read_file",
            output={
                "path": "src/main.py",
                "content": "X" * 4000 + "\n",
                "redacted": False,
            },
        ),
        observation={"kind": "tool_feedback"},
        state=load_state(task_root),
    )
    # Supersede the large snapshot so its blob becomes evictable.
    store.record_tool_result(
        "task-001",
        phase=Phase.CODE,
        action=Action(
            type=ActionType.TOOL_CALL,
            phase=Phase.CODE,
            tool_name="write_file",
            args={"path": "src/main.py", "content": "small\n"},
            reason="Shrink implementation.",
        ),
        result=ToolResult(
            success=True,
            action_name="write_file",
            output={"path": "src/main.py", "bytes_written": 6},
            mutation_applied=True,
        ),
        observation={"kind": "tool_feedback"},
        state=load_state(task_root),
    )
    current_bytes = store.load("task-001").snapshot.total_bytes
    _set_config(tmp_path, max_memory_task_bytes=current_bytes + 100)

    appended = store.append(
        "task-001",
        MemoryRecordDraft(
            phase=Phase.CODE,
            kind=MemoryKind.TOOL_RESULT,
            tool_name="list_files",
            success=True,
            summary="Listed files after eviction.",
        ),
    )

    manifest = json.loads(
        (task_root / "memory" / "evicted.json").read_text(encoding="utf-8")
    )
    assert read.content_sha256 in manifest["evicted"]
    assert not (task_root / "memory" / read.blob_ref).exists()  # type: ignore[operator]
    assert len(appended.snapshot.records) == 3
    reloaded = FilesystemMemoryStore(tmp_path).load("task-001")
    assert "memory_blob_evicted" in reloaded.audit_signals


def test_memory_read_reports_evicted_content(tmp_path: Path) -> None:
    task_root = _initialize_task(tmp_path)
    store = FilesystemMemoryStore(tmp_path)
    record = store.append(
        "task-001",
        MemoryRecordDraft(
            phase=Phase.CODE,
            kind=MemoryKind.TOOL_RESULT,
            tool_name="get_diff",
            success=True,
            summary="Captured diff.",
            paths=("src/a.py",),
            blob=MemoryBlob.text("historical body\n"),
        ),
    ).record
    memory_root = task_root / "memory"
    (memory_root / "evicted.json").write_text(
        json.dumps({"schema_version": 1, "evicted": [record.content_sha256]}),
        encoding="utf-8",
    )
    (memory_root / record.blob_ref).unlink()  # type: ignore[operator]

    with pytest.raises(HanCodeError) as exc_info:
        store.read("task-001", record.memory_id, start_line=1, end_line=1)

    assert exc_info.value.structured_error.error_code == "memory_content_evicted"


def test_load_recovers_incomplete_event_tail_using_trusted_index(
    tmp_path: Path,
) -> None:
    task_root = _initialize_task(tmp_path)
    store = FilesystemMemoryStore(tmp_path)
    committed = store.append(
        "task-001",
        MemoryRecordDraft(
            phase=Phase.CODE,
            kind=MemoryKind.TOOL_RESULT,
            tool_name="list_files",
            success=True,
            summary="Listed source files.",
        ),
    ).record
    events_path = task_root / "memory" / "events.jsonl"
    with events_path.open("ab") as handle:
        handle.write(b'{"partial": "event without newline"')

    recovered = FilesystemMemoryStore(tmp_path).load("task-001")

    assert recovered.snapshot.records == (committed,)
    assert "memory_event_tail_recovered" in recovered.audit_signals
    assert events_path.read_bytes().endswith(b"\n")
    assert len(events_path.read_text(encoding="utf-8").splitlines()) == 1


def test_load_rejects_incomplete_event_tail_when_index_is_missing(
    tmp_path: Path,
) -> None:
    task_root = _initialize_task(tmp_path)
    store = FilesystemMemoryStore(tmp_path)
    store.append(
        "task-001",
        MemoryRecordDraft(
            phase=Phase.CODE,
            kind=MemoryKind.TOOL_RESULT,
            tool_name="list_files",
            success=True,
            summary="Listed source files.",
        ),
    )
    events_path = task_root / "memory" / "events.jsonl"
    with events_path.open("ab") as handle:
        handle.write(b'{"partial": "no newline"')
    (task_root / "memory" / "index.json").unlink()

    with pytest.raises(HanCodeError) as exc_info:
        FilesystemMemoryStore(tmp_path).load("task-001")

    assert exc_info.value.structured_error.error_code == "memory_corrupt"


def test_load_removes_orphan_blob_but_keeps_referenced_blobs(
    tmp_path: Path,
) -> None:
    task_root = _initialize_task(tmp_path)
    store = FilesystemMemoryStore(tmp_path)
    referenced = store.append(
        "task-001",
        MemoryRecordDraft(
            phase=Phase.CODE,
            kind=MemoryKind.TOOL_RESULT,
            tool_name="read_file",
            success=True,
            summary="Read src/main.py.",
            paths=("src/main.py",),
            blob=MemoryBlob.text("kept\n"),
        ),
    ).record
    blobs_root = task_root / "memory" / "blobs"
    orphan_blob = MemoryBlob.text("orphaned\n")
    orphan_path = blobs_root / f"{orphan_blob.content_sha256}.txt"
    orphan_path.write_bytes(orphan_blob.content)
    stray_path = blobs_root / "not-a-content-address.txt"
    stray_path.write_bytes(b"leave me\n")

    loaded = FilesystemMemoryStore(tmp_path).load("task-001")

    referenced_name = referenced.blob_ref.rsplit("/", 1)[-1]  # type: ignore[union-attr]
    assert "memory_orphan_blob_removed" in loaded.audit_signals
    assert not orphan_path.exists()
    assert (blobs_root / referenced_name).exists()
    assert stray_path.exists()


def test_read_verified_blob_returns_the_bytes_it_hashed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_root = _initialize_task(tmp_path)
    store = FilesystemMemoryStore(tmp_path)
    record = store.append(
        "task-001",
        MemoryRecordDraft(
            phase=Phase.CODE,
            kind=MemoryKind.TOOL_RESULT,
            tool_name="read_file",
            success=True,
            summary="Read src/main.py.",
            paths=("src/main.py",),
            blob=MemoryBlob.text("verified\n"),
        ),
    ).record
    blob_path = task_root / "memory" / record.blob_ref  # type: ignore[operator]
    reads = 0
    original_read_bytes = Path.read_bytes

    def counting_read_bytes(path: Path) -> bytes:
        nonlocal reads
        if path == blob_path:
            reads += 1
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", counting_read_bytes)

    content = _read_verified_blob(
        record, task_root / "memory" / "blobs", Phase.CODE
    )

    assert content == b"verified\n"
    assert reads == 1


def test_search_loads_memory_only_once_and_reads_shared_blob_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _initialize_task(tmp_path)
    store = FilesystemMemoryStore(tmp_path)
    shared = MemoryBlob.text("needle shared\n")
    for name in ("a", "b", "c"):
        store.append(
            "task-001",
            MemoryRecordDraft(
                phase=Phase.CODE,
                kind=MemoryKind.TOOL_RESULT,
                tool_name="read_file",
                success=True,
                summary=f"Read src/{name}.py.",
                paths=(f"src/{name}.py",),
                blob=shared,
            ),
        )
    blob_path = (
        tmp_path
        / ".hancode"
        / "tasks"
        / "task-001"
        / "memory"
        / "blobs"
        / f"{shared.content_sha256}.txt"
    )
    load_calls = 0
    original_load = FilesystemMemoryStore.load

    def counting_load(self: FilesystemMemoryStore, task_id: str):  # type: ignore[no-untyped-def]
        nonlocal load_calls
        load_calls += 1
        return original_load(self, task_id)

    monkeypatch.setattr(FilesystemMemoryStore, "load", counting_load)

    blob_reads = 0
    original_read_bytes = Path.read_bytes

    def counting_read_bytes(path: Path) -> bytes:
        nonlocal blob_reads
        if path == blob_path:
            blob_reads += 1
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", counting_read_bytes)

    hits = store.search("task-001", MemoryQuery(query="needle", include_stale=True))

    # One load for the whole request (no nested per-blob reload), and the shared
    # blob is verified once during load plus once in the cached search loop.
    assert len(hits) == 3
    assert load_calls == 1
    assert blob_reads == 4


def test_load_rejects_linked_memory_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_root = _initialize_task(tmp_path)
    memory_root = task_root / "memory"
    original_is_symlink = Path.is_symlink

    def fake_is_symlink(path: Path) -> bool:
        return path == memory_root or original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    with pytest.raises(HanCodeError) as exc_info:
        FilesystemMemoryStore(tmp_path).load("task-001")

    assert exc_info.value.structured_error.error_code == "memory_path_link_not_allowed"


def test_load_rejects_junction_memory_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_root = _initialize_task(tmp_path)
    memory_root = task_root / "memory"
    original_is_junction = Path.is_junction

    def fake_is_junction(path: Path) -> bool:
        return path == memory_root or original_is_junction(path)

    monkeypatch.setattr(Path, "is_junction", fake_is_junction)

    with pytest.raises(HanCodeError) as exc_info:
        FilesystemMemoryStore(tmp_path).load("task-001")

    assert exc_info.value.structured_error.error_code == "memory_path_link_not_allowed"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("task_id", "task-002"),
        ("seq", 2),
        ("record_digest", "0" * 64),
    ],
)
def test_load_rejects_event_identity_sequence_or_digest_drift(
    tmp_path: Path, field: str, value: object
) -> None:
    task_root = _initialize_task(tmp_path)
    FilesystemMemoryStore(tmp_path).append(
        "task-001",
        MemoryRecordDraft(
            phase=Phase.CODE,
            kind=MemoryKind.TOOL_RESULT,
            tool_name="list_files",
            success=True,
            summary="Listed source files.",
        ),
    )
    events_path = task_root / "memory" / "events.jsonl"
    event = json.loads(events_path.read_text(encoding="utf-8"))
    event[field] = value
    events_path.write_text(json.dumps(event) + "\n", encoding="utf-8")

    with pytest.raises(HanCodeError) as exc_info:
        FilesystemMemoryStore(tmp_path).load("task-001")

    assert exc_info.value.structured_error.error_code == "memory_corrupt"


def test_event_write_failure_compensates_new_unreferenced_blob(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_root = _initialize_task(tmp_path)
    store = FilesystemMemoryStore(tmp_path)
    store.load("task-001")
    events_path = task_root / "memory" / "events.jsonl"
    original_open = Path.open

    def fail_event_open(path: Path, *args: object, **kwargs: object) -> object:
        if path == events_path and args and args[0] == "ab":
            raise PermissionError("event append blocked")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_event_open)

    with pytest.raises(HanCodeError) as exc_info:
        store.append(
            "task-001",
            MemoryRecordDraft(
                phase=Phase.CODE,
                kind=MemoryKind.TOOL_RESULT,
                tool_name="read_file",
                success=True,
                summary="Read src/main.py.",
                paths=("src/main.py",),
                blob=MemoryBlob.text("content\n"),
            ),
        )

    assert exc_info.value.structured_error.error_code == "memory_write_error"
    assert events_path.read_bytes() == b""
    assert list((task_root / "memory" / "blobs").iterdir()) == []


def test_index_replace_failure_recovers_from_committed_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_root = _initialize_task(tmp_path)
    store = FilesystemMemoryStore(tmp_path)
    store.load("task-001")
    index_path = task_root / "memory" / "index.json"
    original_replace = os.replace
    failed_once = False

    def fail_index_once(source: object, target: object) -> None:
        nonlocal failed_once
        if Path(target) == index_path and not failed_once:
            failed_once = True
            raise PermissionError("index replace blocked once")
        original_replace(source, target)

    monkeypatch.setattr("hancode.storage.memory.os.replace", fail_index_once)

    appended = store.append(
        "task-001",
        MemoryRecordDraft(
            phase=Phase.CODE,
            kind=MemoryKind.TOOL_RESULT,
            tool_name="read_file",
            success=True,
            summary="Read src/main.py.",
            paths=("src/main.py",),
            blob=MemoryBlob.text("content\n"),
        ),
    )

    assert appended.audit_signals == ("memory_index_recovered",)
    assert len(appended.snapshot.records) == 1
    assert len(list((task_root / "memory" / "blobs").iterdir())) == 1


def test_load_rejects_missing_authoritative_event_log(tmp_path: Path) -> None:
    task_root = _initialize_task(tmp_path)
    store = FilesystemMemoryStore(tmp_path)
    store.load("task-001")
    (task_root / "memory" / "events.jsonl").unlink()

    with pytest.raises(HanCodeError) as exc_info:
        store.load("task-001")

    assert exc_info.value.structured_error.error_code == "memory_corrupt"


def test_load_rejects_malformed_index_instead_of_rebuilding_it(tmp_path: Path) -> None:
    task_root = _initialize_task(tmp_path)
    store = FilesystemMemoryStore(tmp_path)
    store.load("task-001")
    (task_root / "memory" / "index.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(HanCodeError) as exc_info:
        store.load("task-001")

    assert exc_info.value.structured_error.error_code == "memory_corrupt"


def test_load_rejects_blob_digest_mismatch(tmp_path: Path) -> None:
    task_root = _initialize_task(tmp_path)
    appended = FilesystemMemoryStore(tmp_path).append(
        "task-001",
        MemoryRecordDraft(
            phase=Phase.CODE,
            kind=MemoryKind.TOOL_RESULT,
            tool_name="read_file",
            success=True,
            summary="Read src/main.py.",
            paths=("src/main.py",),
            blob=MemoryBlob.text("original\n"),
        ),
    )
    blob_path = task_root / "memory" / appended.record.blob_ref  # type: ignore[operator]
    blob_path.write_text("tampered\n", encoding="utf-8")

    with pytest.raises(HanCodeError) as exc_info:
        FilesystemMemoryStore(tmp_path).load("task-001")

    assert exc_info.value.structured_error.error_code == "memory_corrupt"


def test_recent_limit_change_rewrites_valid_index_without_recovery_signal(
    tmp_path: Path,
) -> None:
    task_root = _initialize_task(tmp_path)
    store = FilesystemMemoryStore(tmp_path)
    for number in range(2):
        store.append(
            "task-001",
            MemoryRecordDraft(
                phase=Phase.CODE,
                kind=MemoryKind.TOOL_RESULT,
                tool_name="list_files",
                success=True,
                summary=f"Listed source files {number}.",
            ),
        )
    _set_config(tmp_path, max_memory_recent_events=1)

    loaded = FilesystemMemoryStore(tmp_path).load("task-001")
    index = json.loads(
        (task_root / "memory" / "index.json").read_text(encoding="utf-8")
    )

    assert loaded.audit_signals == ()
    assert index["recent_limit"] == 1
    assert index["recent_memory_ids"] == ["mem-000002"]


def test_load_rejects_task_identity_drift(tmp_path: Path) -> None:
    task_root = _initialize_task(tmp_path)
    state_path = task_root / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["task_id"] = "task-002"
    state_path.write_text(json.dumps(state), encoding="utf-8")

    with pytest.raises(HanCodeError) as exc_info:
        FilesystemMemoryStore(tmp_path).load("task-001")

    assert exc_info.value.structured_error.error_code == "memory_task_identity_mismatch"


def test_json_blob_uses_canonical_content_and_json_extension(tmp_path: Path) -> None:
    task_root = _initialize_task(tmp_path)
    appended = FilesystemMemoryStore(tmp_path).append(
        "task-001",
        MemoryRecordDraft(
            phase=Phase.CODE,
            kind=MemoryKind.TOOL_RESULT,
            tool_name="list_files",
            success=True,
            summary="Listed source files.",
            blob=MemoryBlob.json({"z": 1, "paths": ["src/main.py"]}),
        ),
    )

    assert appended.record.blob_ref is not None
    assert appended.record.blob_ref.endswith(".json")
    assert (task_root / "memory" / appended.record.blob_ref).read_bytes() == (
        b'{"paths":["src/main.py"],"z":1}'
    )
