from __future__ import annotations

import json
from pathlib import Path

import pytest

from hancode.core.errors import HanCodeError
from hancode.storage.learning_store import (
    LearningEventType,
    LearningStore,
)
from hancode.storage.workspace import init_project_workspace, init_task_workspace


def _task(tmp_path: Path) -> tuple[LearningStore, Path]:
    init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )
    task_root = init_task_workspace(tmp_path, "task-001")
    return LearningStore(), task_root


def _append(store: LearningStore, task_root: Path, n: int) -> None:
    for index in range(n):
        store.append(
            task_root,
            "task-001",
            LearningEventType.REQUIREMENT_UNDERSTOOD,
            {"index": index},
            occurred_at=f"2026-08-06T00:00:{index:02d}Z",
        )


def test_append_assigns_sequential_seq_and_event_id(tmp_path: Path) -> None:
    store, task_root = _task(tmp_path)
    _append(store, task_root, 3)

    events = store.read_events(task_root)

    assert [event.seq for event in events] == [1, 2, 3]
    assert [event.event_id for event in events] == [
        "LE-000001",
        "LE-000002",
        "LE-000003",
    ]
    assert events[0].previous_digest is None
    assert events[1].previous_digest == events[0].digest


def test_events_survive_and_read_in_order(tmp_path: Path) -> None:
    store, task_root = _task(tmp_path)
    _append(store, task_root, 2)

    reopened = LearningStore()
    events = reopened.read_events(task_root)

    assert [event.payload["index"] for event in events] == [0, 1]
    assert events[0].event_type is LearningEventType.REQUIREMENT_UNDERSTOOD


def test_append_rejects_cross_task_id(tmp_path: Path) -> None:
    store, task_root = _task(tmp_path)

    with pytest.raises(HanCodeError) as exc_info:
        store.append(
            task_root,
            "task-999",
            LearningEventType.DECISION_RECORDED,
            {},
            occurred_at="2026-08-06T00:00:00Z",
        )

    assert exc_info.value.to_dict()["error_code"] == "learning_task_identity_mismatch"


def test_projection_reflects_head_digest_and_source_seq(tmp_path: Path) -> None:
    store, task_root = _task(tmp_path)
    _append(store, task_root, 2)

    projection = json.loads(
        (task_root / "learning" / "evidence.json").read_text(encoding="utf-8")
    )
    events = store.read_events(task_root)

    assert projection["source_event_seq"] == 2
    assert projection["digest"] == events[-1].digest
    assert projection["task_id"] == "task-001"


def test_deleted_projection_is_rebuilt_from_events(tmp_path: Path) -> None:
    store, task_root = _task(tmp_path)
    _append(store, task_root, 2)
    projection_path = task_root / "learning" / "evidence.json"
    projection_path.unlink()

    rebuilt = store.load_projection(task_root)

    assert rebuilt["source_event_seq"] == 2
    assert projection_path.is_file()


def test_tampered_digest_chain_fails_closed(tmp_path: Path) -> None:
    store, task_root = _task(tmp_path)
    _append(store, task_root, 2)
    events_path = task_root / "learning" / "events.jsonl"
    lines = events_path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[0])
    record["payload"] = {"index": 999}
    lines[0] = json.dumps(record)
    events_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(HanCodeError) as exc_info:
        store.read_events(task_root)

    assert exc_info.value.to_dict()["error_code"] == "learning_events_corrupt"


def test_partial_tail_write_accepts_complete_prefix(tmp_path: Path) -> None:
    store, task_root = _task(tmp_path)
    _append(store, task_root, 2)
    events_path = task_root / "learning" / "events.jsonl"
    text = events_path.read_text(encoding="utf-8")
    # Append a partial, non-newline-terminated third record.
    events_path.write_text(text + '{"seq": 3, "event_ty', encoding="utf-8")

    events = store.read_events(task_root)

    assert [event.seq for event in events] == [1, 2]


def test_mid_file_corruption_fails_closed(tmp_path: Path) -> None:
    store, task_root = _task(tmp_path)
    _append(store, task_root, 3)
    events_path = task_root / "learning" / "events.jsonl"
    lines = events_path.read_text(encoding="utf-8").splitlines()
    lines[1] = "{ this is not json }"
    events_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(HanCodeError) as exc_info:
        store.read_events(task_root)

    assert exc_info.value.to_dict()["error_code"] == "learning_events_corrupt"


def test_append_rejects_unknown_event_type_value(tmp_path: Path) -> None:
    store, task_root = _task(tmp_path)

    with pytest.raises((ValueError, HanCodeError)):
        store.append(
            task_root,
            "task-001",
            "NotARealEvent",  # type: ignore[arg-type]
            {},
            occurred_at="2026-08-06T00:00:00Z",
        )
