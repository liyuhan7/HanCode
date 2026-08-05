from __future__ import annotations

import json
from pathlib import Path

from hancode.core.config import load_config
from hancode.core.memory import MemoryBlob, MemoryKind, MemoryRecordDraft
from hancode.core.models import Phase
from hancode.storage.memory import FilesystemMemoryStore
from hancode.storage.workspace import init_project_workspace, init_task_workspace
from hancode.tooling.memory_tools import (
    MemoryFreshnessChecker,
    memory_read,
    memory_search,
)


def _workspace(project_root: Path) -> None:
    init_project_workspace(project_root, "project-001", "AI4SE", "Harness")
    init_task_workspace(project_root, "task-001", goal="Recover memory.")


def _set_budget(project_root: Path, value: int) -> None:
    path = project_root / ".hancode" / "project.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["max_observation_bytes"] = value
    path.write_text(json.dumps(data), encoding="utf-8")


def test_memory_read_refreshes_current_file_then_returns_stale_history(
    tmp_path: Path,
) -> None:
    _workspace(tmp_path)
    (tmp_path / "src").mkdir()
    target = tmp_path / "src" / "main.py"
    target.write_text("before\n", encoding="utf-8")
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
            blob=MemoryBlob.text("before\n"),
        ),
    ).record
    target.write_text("after\n", encoding="utf-8")
    checker = MemoryFreshnessChecker(tmp_path, load_config(tmp_path, "task-001"), store)

    result = memory_read(
        "task-001", record.memory_id, checker=checker, store=store,
        max_observation_bytes=8192,
    )
    repeated = memory_read(
        "task-001", record.memory_id, checker=checker, store=store,
        max_observation_bytes=8192,
    )

    assert result.success is True
    assert result.output["content"] == "before\n"  # type: ignore[index]
    assert result.output["stale"] is True  # type: ignore[index]
    assert result.output["invalidation_reason"] == "content_changed"  # type: ignore[index]
    assert result.output["current_file_authoritative"] is False  # type: ignore[index]
    assert "must not be treated as the current file" in result.output["warning"]  # type: ignore[index,operator]
    assert repeated.success is True
    assert len(store.load("task-001").snapshot.records) == 2


def test_memory_read_pretty_prints_json_and_paginates(tmp_path: Path) -> None:
    _workspace(tmp_path)
    store = FilesystemMemoryStore(tmp_path)
    record = store.append(
        "task-001",
        MemoryRecordDraft(
            phase=Phase.TEST,
            kind=MemoryKind.TOOL_RESULT,
            tool_name="get_diff",
            success=True,
            summary="Diff captured.",
            blob=MemoryBlob.json({"z": 1, "message": "你好"}),
        ),
    ).record

    result = memory_read(
        "task-001", record.memory_id,
        checker=MemoryFreshnessChecker(tmp_path, load_config(tmp_path, "task-001"), store),
        store=store, max_observation_bytes=8192, start_line=2, end_line=3,
    )

    assert result.success is True
    assert result.output["content"] == '  "message": "你好",\n  "z": 1\n'  # type: ignore[index]
    assert result.output["start_line"] == 2  # type: ignore[index]
    assert result.output["end_line"] == 3  # type: ignore[index]
    assert result.output["total_lines"] == 4  # type: ignore[index]
    assert result.output["next_start_line"] == 4  # type: ignore[index]
    assert result.output["current_file_authoritative"] is False  # type: ignore[index]


def test_memory_read_enforces_line_and_exact_utf8_output_budgets(tmp_path: Path) -> None:
    _workspace(tmp_path)
    store = FilesystemMemoryStore(tmp_path)
    record = store.append(
        "task-001",
        MemoryRecordDraft(
            phase=Phase.CODE,
            kind=MemoryKind.TOOL_RESULT,
            tool_name="read_file",
            success=True,
            summary="Large line.",
            paths=("src/main.py",),
            blob=MemoryBlob.text("界" * 1000 + "\n"),
        ),
    ).record
    checker = MemoryFreshnessChecker(tmp_path, load_config(tmp_path, "task-001"), store)

    invalid = memory_read(
        "task-001", record.memory_id, checker=checker, store=store,
        max_observation_bytes=600, start_line=1, end_line=201,
    )
    result = memory_read(
        "task-001", record.memory_id, checker=checker, store=store,
        max_observation_bytes=600,
    )
    too_small = memory_read(
        "task-001", record.memory_id, checker=checker, store=store,
        max_observation_bytes=10,
    )

    assert invalid.error_code == "memory_invalid_record"
    assert result.success is True
    assert len(json.dumps(result.output, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()) <= 600
    assert result.output["content"].endswith("[TRUNCATED]")  # type: ignore[index,union-attr]
    assert result.output["content_truncated"] is True  # type: ignore[index]
    assert result.output["next_start_line"] == 1  # type: ignore[index]
    assert result.output["next_byte_offset"] > 0  # type: ignore[index,operator]
    assert too_small.error_code == "memory_output_budget_too_small"


def test_memory_read_resumes_long_single_line_via_byte_offset(tmp_path: Path) -> None:
    _workspace(tmp_path)
    store = FilesystemMemoryStore(tmp_path)
    record = store.append(
        "task-001",
        MemoryRecordDraft(
            phase=Phase.CODE,
            kind=MemoryKind.TOOL_RESULT,
            tool_name="read_file",
            success=True,
            summary="Long single line.",
            paths=("src/main.py",),
            blob=MemoryBlob.text("A" * 4000 + "\n"),
        ),
    ).record
    checker = MemoryFreshnessChecker(tmp_path, load_config(tmp_path, "task-001"), store)

    recovered = ""
    offset = 0
    for _ in range(200):
        chunk = memory_read(
            "task-001", record.memory_id, checker=checker, store=store,
            max_observation_bytes=800, start_line=1, start_byte_offset=offset,
        )
        assert chunk.success is True
        content = chunk.output["content"]  # type: ignore[index]
        if chunk.output["content_truncated"]:  # type: ignore[index]
            recovered += content[: -len("[TRUNCATED]")]
            offset = chunk.output["next_byte_offset"]  # type: ignore[index]
        else:
            recovered += content
            break

    assert recovered == "A" * 4000 + "\n"


def test_memory_search_matches_sources_and_uses_fixed_ranking(tmp_path: Path) -> None:
    _workspace(tmp_path)
    store = FilesystemMemoryStore(tmp_path)
    content = store.append(
        "task-001",
        MemoryRecordDraft(
            phase=Phase.TEST,
            kind=MemoryKind.TOOL_RESULT,
            tool_name="get_diff",
            success=True,
            summary="Captured unrelated diff.",
            paths=("src/content.py",),
            blob=MemoryBlob.text("needle in body\n"),
        ),
    ).record
    summary = store.append(
        "task-001",
        MemoryRecordDraft(
            phase=Phase.CODE,
            kind=MemoryKind.TOOL_RESULT,
            tool_name="run_tests",
            success=True,
            summary="Needle in summary.",
        ),
    ).record
    path = store.append(
        "task-001",
        MemoryRecordDraft(
            phase=Phase.SPEC,
            kind=MemoryKind.TOOL_RESULT,
            tool_name="get_diff",
            success=True,
            summary="Captured path.",
            paths=("src/needle.py",),
            blob=MemoryBlob.json({"value": "other"}),
        ),
    ).record
    checker = MemoryFreshnessChecker(tmp_path, load_config(tmp_path, "task-001"), store)

    result = memory_search(
        "task-001", "NeEdLe", current_phase=Phase.SPEC, checker=checker,
        store=store, max_observation_bytes=8192,
    )

    assert result.success is True
    assert result.output["total_matches"] == 3  # type: ignore[index]
    assert [hit["memory_id"] for hit in result.output["hits"]] == [  # type: ignore[index,union-attr]
        path.memory_id, summary.memory_id, content.memory_id,
    ]
    assert [hit["match_sources"] for hit in result.output["hits"]] == [  # type: ignore[index,union-attr]
        ["path"], ["summary"], ["content"],
    ]


def test_memory_search_filters_stale_phase_path_and_task(tmp_path: Path) -> None:
    _workspace(tmp_path)
    init_task_workspace(tmp_path, "task-002", goal="Other task.")
    store = FilesystemMemoryStore(tmp_path)
    current = store.append(
        "task-001",
        MemoryRecordDraft(
            phase=Phase.CODE,
            kind=MemoryKind.TOOL_RESULT,
            tool_name="read_file",
            success=True,
            summary="Alpha current.",
            paths=("src/main.py",),
            blob=MemoryBlob.text("alpha\n"),
        ),
    ).record
    store.append(
        "task-001",
        MemoryRecordDraft(
            phase=Phase.CODE,
            kind=MemoryKind.INVALIDATION,
            tool_name="write_file",
            success=True,
            summary='{"outcome":"invalidated","reason":"source_write"}',
            paths=("src/main.py",),
            invalidates=(current.memory_id,),
        ),
    )
    store.append(
        "task-002",
        MemoryRecordDraft(
            phase=Phase.CODE,
            kind=MemoryKind.TOOL_RESULT,
            tool_name="run_tests",
            success=True,
            summary="Alpha other task.",
        ),
    )
    checker = MemoryFreshnessChecker(tmp_path, load_config(tmp_path, "task-001"), store)

    excluded = memory_search(
        "task-001", "alpha", current_phase=Phase.SPEC, checker=checker,
        store=store, max_observation_bytes=8192,
    )
    included = memory_search(
        "task-001", "alpha", current_phase=Phase.SPEC, checker=checker,
        store=store, max_observation_bytes=8192, include_stale=True,
        path="src/main.py", phase="code",
    )
    empty = memory_search(
        "task-001", "absent", current_phase=Phase.SPEC, checker=checker,
        store=store, max_observation_bytes=8192,
    )

    assert excluded.output["hits"] == []  # type: ignore[index]
    assert included.output["returned_count"] == 1  # type: ignore[index]
    assert included.output["hits"][0]["stale"] is True  # type: ignore[index]
    assert included.output["hits"][0]["invalidation_reason"] == "source_write"  # type: ignore[index]
    assert empty.output == {
        "total_matches": 0, "returned_count": 0, "truncated": False, "hits": []
    }


def test_memory_search_excludes_superseded_snapshot_by_default(tmp_path: Path) -> None:
    _workspace(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("alpha current\n", encoding="utf-8")
    store = FilesystemMemoryStore(tmp_path)
    old = store.append(
        "task-001",
        MemoryRecordDraft(
            phase=Phase.CODE,
            kind=MemoryKind.TOOL_RESULT,
            tool_name="read_file",
            success=True,
            summary="Alpha old.",
            paths=("src/main.py",),
            blob=MemoryBlob.text("alpha old\n"),
        ),
    ).record
    current = store.append(
        "task-001",
        MemoryRecordDraft(
            phase=Phase.CODE,
            kind=MemoryKind.TOOL_RESULT,
            tool_name="read_file",
            success=True,
            summary="Alpha current.",
            paths=("src/main.py",),
            blob=MemoryBlob.text("alpha current\n"),
        ),
    ).record
    checker = MemoryFreshnessChecker(tmp_path, load_config(tmp_path, "task-001"), store)

    excluded = memory_search(
        "task-001", "alpha old", current_phase=Phase.SPEC, checker=checker,
        store=store, max_observation_bytes=8192,
    )
    included = memory_search(
        "task-001", "alpha old", current_phase=Phase.SPEC, checker=checker,
        store=store, max_observation_bytes=8192, include_stale=True,
    )
    restored = memory_read(
        "task-001", old.memory_id, checker=checker, store=store,
        max_observation_bytes=8192,
    )

    assert excluded.output["hits"] == []  # type: ignore[index]
    assert included.output["hits"][0]["memory_id"] == old.memory_id  # type: ignore[index]
    assert included.output["hits"][0]["superseded_by"] == current.memory_id  # type: ignore[index]
    assert included.output["hits"][0]["stale"] is True  # type: ignore[index]
    assert restored.output["content"] == "alpha old\n"  # type: ignore[index]
    assert restored.output["superseded_by"] == current.memory_id  # type: ignore[index]
    assert restored.output["stale"] is True  # type: ignore[index]


def test_memory_search_reports_all_matches_before_limit_and_budget_truncation(
    tmp_path: Path,
) -> None:
    _workspace(tmp_path)
    store = FilesystemMemoryStore(tmp_path)
    for index in range(3):
        store.append(
            "task-001",
            MemoryRecordDraft(
                phase=Phase.SPEC,
                kind=MemoryKind.TOOL_RESULT,
                tool_name="run_tests",
                success=True,
                summary=f"needle {'detail ' * 100}{index}",
            ),
        )
    checker = MemoryFreshnessChecker(tmp_path, load_config(tmp_path, "task-001"), store)

    limited = memory_search(
        "task-001", "needle", current_phase=Phase.SPEC, checker=checker,
        store=store, max_observation_bytes=8192, limit=2,
    )
    budgeted = memory_search(
        "task-001", "needle", current_phase=Phase.SPEC, checker=checker,
        store=store, max_observation_bytes=500, limit=3,
    )

    assert limited.output["total_matches"] == 3  # type: ignore[index]
    assert limited.output["returned_count"] == 2  # type: ignore[index]
    assert limited.output["truncated"] is True  # type: ignore[index]
    assert budgeted.output["total_matches"] == 3  # type: ignore[index]
    assert budgeted.output["truncated"] is True  # type: ignore[index]
    if budgeted.output["hits"]:  # type: ignore[index]
        assert budgeted.output["hits"][0]["summary"].startswith("needle")  # type: ignore[index]
        assert budgeted.output["hits"][0]["summary"].endswith("[TRUNCATED]")  # type: ignore[index]
