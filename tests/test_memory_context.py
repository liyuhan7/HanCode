from __future__ import annotations

from pathlib import Path

from hancode.core.config import load_config
from hancode.core.memory import MemoryBlob, MemoryKind, MemoryRecordDraft
from hancode.core.models import Phase
from hancode.core.state import load_state
from hancode.runtime.memory import MemoryContextPacker
from hancode.storage.memory import FilesystemMemoryStore
from hancode.storage.workspace import init_project_workspace, init_task_workspace


def _workspace(project_root: Path) -> Path:
    init_project_workspace(
        project_root,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Harness",
    )
    return init_task_workspace(project_root, "task-001", goal="Remember source files.")


def test_packer_projects_current_read_file_as_file_index_and_hot_content(
    tmp_path: Path,
) -> None:
    task_root = _workspace(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("VALUE = 1\n", encoding="utf-8")
    store = FilesystemMemoryStore(tmp_path)
    record = store.append(
        "task-001",
        MemoryRecordDraft(
            phase=Phase.SPEC,
            kind=MemoryKind.TOOL_RESULT,
            tool_name="read_file",
            success=True,
            summary="Read src/main.py.",
            paths=("src/main.py",),
            blob=MemoryBlob.text("VALUE = 1\n"),
        ),
    ).record

    memory = MemoryContextPacker(
        project_root=tmp_path,
        config=load_config(tmp_path, "task-001"),
        store=store,
    ).build(
        task_id="task-001",
        phase=Phase.SPEC,
        state=load_state(task_root),
        observation=None,
        source_snippets={},
    )

    assert memory.to_dict() == {
        "workspace_generation": 0,
        "recent_events": [
            {
                "memory_id": record.memory_id,
                "seq": 1,
                "phase": "spec",
                "kind": "tool_result",
                "tool_name": "read_file",
                "success": True,
                "summary": "Read src/main.py.",
                "error_code": None,
                "paths": ["src/main.py"],
                "workspace_generation": 0,
                "stale": False,
            }
        ],
        "file_index": [
            {
                "path": "src/main.py",
                "memory_id": record.memory_id,
                "phase": "spec",
                "seq": 1,
                "content_sha256": record.content_sha256,
                "blob_bytes": len(b"VALUE = 1\n"),
                "record_generation": 0,
                "current_generation": 0,
                "hot_eligible": True,
            }
        ],
        "hot_contents": [
            {
                "path": "src/main.py",
                "memory_id": record.memory_id,
                "content_sha256": record.content_sha256,
                "workspace_generation": 0,
                "content": "VALUE = 1\n",
            }
        ],
        "directory_listings": [],
        "action_guidance": {
            "reusable_evidence": [
                {
                    "tool_name": "read_file",
                    "path": "src/main.py",
                    "memory_id": record.memory_id,
                }
            ]
        },
    }


def test_packer_keeps_readable_non_source_metadata_as_reusable_evidence(
    tmp_path: Path,
) -> None:
    task_root = _workspace(tmp_path)
    project_metadata = tmp_path / ".hancode" / "project.json"
    content = project_metadata.read_text(encoding="utf-8")
    store = FilesystemMemoryStore(tmp_path)
    record = store.append(
        "task-001",
        MemoryRecordDraft(
            phase=Phase.SPEC,
            kind=MemoryKind.TOOL_RESULT,
            tool_name="read_file",
            success=True,
            summary="Read .hancode/project.json.",
            paths=(".hancode/project.json",),
            blob=MemoryBlob.text(content),
        ),
    ).record

    memory = MemoryContextPacker(
        project_root=tmp_path,
        config=load_config(tmp_path, "task-001"),
        store=store,
    ).build(
        task_id="task-001",
        phase=Phase.SPEC,
        state=load_state(task_root),
        observation=None,
        source_snippets={},
    )

    assert memory.workspace_generation == 0
    assert memory.file_index[0].path == ".hancode/project.json"
    assert memory.action_constraints[0].memory_id == record.memory_id


def test_packer_persists_external_content_change_as_invalidation(tmp_path: Path) -> None:
    task_root = _workspace(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("VALUE = 2\n", encoding="utf-8")
    store = FilesystemMemoryStore(tmp_path)
    record = store.append(
        "task-001",
        MemoryRecordDraft(
            phase=Phase.SPEC,
            kind=MemoryKind.TOOL_RESULT,
            tool_name="read_file",
            success=True,
            summary="Read src/main.py.",
            paths=("src/main.py",),
            blob=MemoryBlob.text("VALUE = 1\n"),
        ),
    ).record

    memory = MemoryContextPacker(
        project_root=tmp_path,
        config=load_config(tmp_path, "task-001"),
        store=store,
    ).build(
        task_id="task-001",
        phase=Phase.SPEC,
        state=load_state(task_root),
        observation=None,
        source_snippets={},
    )

    snapshot = store.load("task-001").snapshot
    assert memory.file_index == ()
    assert memory.hot_contents == ()
    assert dict(snapshot.invalidated_by) == {record.memory_id: "mem-000002"}
    assert snapshot.records[-1].summary == (
        '{"outcome":"invalidated","reason_by_path":{"src/main.py":"content_changed"},'
        '"source":"context_fingerprint_probe"}'
    )


def test_recent_events_keep_substantive_records_over_memory_access(
    tmp_path: Path,
) -> None:
    task_root = _workspace(tmp_path)
    store = FilesystemMemoryStore(tmp_path)
    read_record = store.append(
        "task-001",
        MemoryRecordDraft(
            phase=Phase.CODE,
            kind=MemoryKind.TOOL_RESULT,
            tool_name="read_file",
            success=True,
            summary="Read src/main.py.",
            paths=("src/main.py",),
            blob=MemoryBlob.text("VALUE = 1\n"),
        ),
    ).record
    for index in range(8):
        store.append(
            "task-001",
            MemoryRecordDraft(
                phase=Phase.CODE,
                kind=MemoryKind.MEMORY_ACCESS,
                tool_name="memory_search",
                success=True,
                summary=f'{{"outcome":"succeeded","returned_count":{index}}}',
            ),
        )

    memory = MemoryContextPacker(
        project_root=tmp_path,
        config=load_config(tmp_path, "task-001"),
        store=store,
    ).build(
        task_id="task-001",
        phase=Phase.CODE,
        state=load_state(task_root),
        observation=None,
        source_snippets={},
    )

    kinds = [event.kind for event in memory.recent_events]
    access_events = [k for k in kinds if k is MemoryKind.MEMORY_ACCESS]
    assert read_record.memory_id in {event.memory_id for event in memory.recent_events}
    assert len(access_events) == 2
    # Substantive records precede the retained memory-access summaries.
    assert kinds.index(MemoryKind.TOOL_RESULT) < kinds.index(MemoryKind.MEMORY_ACCESS)
    # The full access history remains persisted even though context is trimmed.
    stored = store.load("task-001").snapshot.records
    assert sum(1 for r in stored if r.kind is MemoryKind.MEMORY_ACCESS) == 8


def test_unrelated_write_generation_keeps_current_file_hot(tmp_path: Path) -> None:
    task_root = _workspace(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("A = 1\n", encoding="utf-8")
    store = FilesystemMemoryStore(tmp_path)
    record = store.append(
        "task-001",
        MemoryRecordDraft(
            phase=Phase.SPEC,
            kind=MemoryKind.TOOL_RESULT,
            tool_name="read_file",
            success=True,
            summary="Read src/a.py.",
            paths=("src/a.py",),
            blob=MemoryBlob.text("A = 1\n"),
        ),
    ).record
    store.append(
        "task-001",
        MemoryRecordDraft(
            phase=Phase.SPEC,
            kind=MemoryKind.INVALIDATION,
            tool_name="write_file",
            success=True,
            summary='{"outcome":"succeeded","reason":"source_write"}',
            paths=("src/b.py",),
        ),
    )

    memory = MemoryContextPacker(
        project_root=tmp_path,
        config=load_config(tmp_path, "task-001"),
        store=store,
    ).build(
        task_id="task-001",
        phase=Phase.SPEC,
        state=load_state(task_root),
        observation=None,
        source_snippets={},
    )

    assert memory.workspace_generation == 1
    assert memory.file_index[0].memory_id == record.memory_id
    assert memory.file_index[0].record_generation == 0
    assert memory.file_index[0].current_generation == 1
    assert memory.file_index[0].hot_eligible is True
    assert memory.hot_contents[0].memory_id == record.memory_id
    assert memory.hot_contents[0].content == "A = 1\n"


def test_packer_projects_latest_list_files_as_directory_listing(
    tmp_path: Path,
) -> None:
    task_root = _workspace(tmp_path)
    store = FilesystemMemoryStore(tmp_path)
    store.append(
        "task-001",
        MemoryRecordDraft(
            phase=Phase.SPEC,
            kind=MemoryKind.TOOL_RESULT,
            tool_name="list_files",
            success=True,
            summary='{"outcome":"succeeded"}',
            paths=(".hancode/src",),
            blob=MemoryBlob.json({"path": ".hancode/src", "files": ["old.py"]}),
        ),
    )
    latest = store.append(
        "task-001",
        MemoryRecordDraft(
            phase=Phase.SPEC,
            kind=MemoryKind.TOOL_RESULT,
            tool_name="list_files",
            success=True,
            summary='{"outcome":"succeeded"}',
            paths=(".hancode/src",),
            blob=MemoryBlob.json(
                {"path": ".hancode/src", "files": ["a.py", "b.py"]}
            ),
        ),
    ).record

    memory = MemoryContextPacker(
        project_root=tmp_path,
        config=load_config(tmp_path, "task-001"),
        store=store,
    ).build(
        task_id="task-001",
        phase=Phase.SPEC,
        state=load_state(task_root),
        observation=None,
        source_snippets={},
    )

    assert len(memory.directory_listings) == 1
    listing = memory.directory_listings[0]
    assert listing.path == ".hancode/src"
    assert listing.memory_id == latest.memory_id
    assert listing.files == ("a.py", "b.py")
    assert memory.to_dict()["directory_listings"] == [
        {
            "path": ".hancode/src",
            "memory_id": latest.memory_id,
            "seq": latest.seq,
            "files": ["a.py", "b.py"],
        }
    ]
