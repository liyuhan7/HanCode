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
    }


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
