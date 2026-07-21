"""S4-T3: InspectionService — historical trace paging and safe artifact preview.

The TUI must never read ``trace.jsonl`` or task files directly. InspectionService
provides the only read path:
- ``read_trace`` returns persisted events in seq order, validates sequence
  integrity, task-id binding, and refuses symlinked trace files.
- ``read_artifact`` only previews allow-listed delivery artifacts that the task
  state declares present, and refuses source files / credentials / links.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hancode.app.inspection_service import InspectionService
from hancode.core.errors import HanCodeError
from hancode.core.models import Phase
from hancode.storage.trace import append_trace
from hancode.storage.workspace import (
    init_project_workspace,
    init_task_workspace,
    task_path,
)


def _project(tmp_path: Path) -> Path:
    init_project_workspace(tmp_path, "project-001", "Course", "Assignment")
    init_task_workspace(tmp_path, "task-001", goal="Write the spec.")
    return tmp_path


def _append_events(tmp_path: Path, count: int) -> None:
    root = task_path(tmp_path, "task-001")
    for index in range(count):
        append_trace(
            root,
            event_type="phase_started" if index % 2 == 0 else "phase_completed",
            task_id="task-001",
            phase=Phase.SPEC,
            status="running" if index % 2 == 0 else "succeeded",
        )


# ---------------------------------------------------------------------------
# read_trace
# ---------------------------------------------------------------------------


def test_read_trace_returns_events_in_seq_order(tmp_path: Path) -> None:
    _project(tmp_path)
    _append_events(tmp_path, 3)

    page = InspectionService().read_trace(tmp_path, "task-001")

    seqs = [event.seq for event in page.events]
    assert seqs == [1, 2, 3]
    assert page.has_more is False
    assert page.next_seq is None


def test_read_trace_honours_after_seq_and_limit(tmp_path: Path) -> None:
    _project(tmp_path)
    _append_events(tmp_path, 5)

    page = InspectionService().read_trace(tmp_path, "task-001", after_seq=1, limit=2)

    assert [event.seq for event in page.events] == [2, 3]
    assert page.has_more is True
    assert page.next_seq == 3


def test_read_trace_rejects_gapped_sequence(tmp_path: Path) -> None:
    _project(tmp_path)
    root = task_path(tmp_path, "task-001")
    trace_file = root / "trace.jsonl"
    # Hand-craft a broken trace: seq jumps from 1 to 3.
    bad = "\n".join(
        json.dumps(
            {
                "event_id": f"evt-{seq:06d}",
                "seq": seq,
                "event_type": "phase_started",
                "task_id": "task-001",
                "phase": "spec",
                "timestamp": "2026-07-21T00:00:00+00:00",
                "status": "running",
                "action": None,
                "observation": None,
                "error_summary": None,
                "state_transition": None,
            }
        )
        for seq in (1, 3)
    )
    trace_file.write_text(bad + "\n", encoding="utf-8")

    with pytest.raises(HanCodeError):
        InspectionService().read_trace(tmp_path, "task-001")


def test_read_trace_rejects_wrong_task_id(tmp_path: Path) -> None:
    _project(tmp_path)
    root = task_path(tmp_path, "task-001")
    trace_file = root / "trace.jsonl"
    trace_file.write_text(
        json.dumps(
            {
                "event_id": "evt-000001",
                "seq": 1,
                "event_type": "phase_started",
                "task_id": "task-999",
                "phase": "spec",
                "timestamp": "2026-07-21T00:00:00+00:00",
                "status": "running",
                "action": None,
                "observation": None,
                "error_summary": None,
                "state_transition": None,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(HanCodeError):
        InspectionService().read_trace(tmp_path, "task-001")


def test_read_trace_rejects_symlink(tmp_path: Path) -> None:
    _project(tmp_path)
    root = task_path(tmp_path, "task-001")
    trace_file = root / "trace.jsonl"
    if trace_file.exists():
        trace_file.unlink()
    external = tmp_path / "external.jsonl"
    external.write_text("", encoding="utf-8")
    try:
        trace_file.symlink_to(external)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted in this environment")

    with pytest.raises(HanCodeError):
        InspectionService().read_trace(tmp_path, "task-001")


# ---------------------------------------------------------------------------
# read_artifact
# ---------------------------------------------------------------------------


def _declare_artifact(tmp_path: Path, name: str, content: str) -> None:
    from dataclasses import replace

    from hancode.core.state import load_state, save_state

    root = task_path(tmp_path, "task-001")
    (root / name).write_text(content, encoding="utf-8")
    state = load_state(root)
    artifacts = dict(state.artifacts)
    artifacts[name] = True
    save_state(root, replace(state, artifacts=artifacts))


def test_read_artifact_allows_declared_artifact(tmp_path: Path) -> None:
    _project(tmp_path)
    _declare_artifact(tmp_path, "SPEC.md", "# SPEC\n\nDocument the target.\n")

    preview = InspectionService().read_artifact(tmp_path, "task-001", "SPEC.md")

    assert preview.name == "SPEC.md"
    assert "Document the target." in preview.content
    assert preview.truncated is False


def test_read_artifact_rejects_undeclared_artifact(tmp_path: Path) -> None:
    _project(tmp_path)
    # SPEC.md exists on disk but state does not declare it present.
    root = task_path(tmp_path, "task-001")
    (root / "SPEC.md").write_text("# SPEC\n", encoding="utf-8")

    with pytest.raises(HanCodeError):
        InspectionService().read_artifact(tmp_path, "task-001", "SPEC.md")


def test_read_artifact_rejects_source_file(tmp_path: Path) -> None:
    _project(tmp_path)

    with pytest.raises(HanCodeError):
        InspectionService().read_artifact(tmp_path, "task-001", "src/main.py")


def test_read_artifact_rejects_credentials(tmp_path: Path) -> None:
    _project(tmp_path)

    with pytest.raises(HanCodeError):
        InspectionService().read_artifact(tmp_path, "task-001", ".env")


def test_read_artifact_truncates_large_preview(tmp_path: Path) -> None:
    _project(tmp_path)
    _declare_artifact(tmp_path, "SPEC.md", "x" * 5000)

    preview = InspectionService().read_artifact(
        tmp_path, "task-001", "SPEC.md", max_chars=100
    )

    assert len(preview.content) <= 100
    assert preview.truncated is True
