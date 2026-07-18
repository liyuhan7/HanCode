from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
from typing import Any

import pytest

from hancode.errors import HanCodeError
from hancode.workspace import init_project_workspace, init_task_workspace, task_path


def test_workspace_initializes_project_files(tmp_path: Path) -> None:
    workspace = init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )

    assert workspace == tmp_path / ".hancode"
    assert (workspace / "tasks").is_dir()
    assert json.loads((workspace / "project.json").read_text(encoding="utf-8")) == {
        "workspace_version": 1,
        "project_id": "course-project",
        "course_name": "AI4SE",
        "assignment_name": "Coding Agent Harness",
        "project_root": ".",
    }
    assert (workspace / "project_memory.md").read_text(encoding="utf-8") == (
        "# Project Memory\n"
    )
    assert (workspace / "course_context.md").read_text(encoding="utf-8") == (
        "# Course Context\n"
    )
    assert (workspace / "experience.md").read_text(encoding="utf-8") == "# Experience\n"


def test_new_task_uses_project_configured_retry_budget(tmp_path: Path) -> None:
    workspace = init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )
    metadata = json.loads((workspace / "project.json").read_text(encoding="utf-8"))
    metadata["retry_budget"] = 7
    (workspace / "project.json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )

    task_workspace = init_task_workspace(tmp_path, "task-001")

    assert json.loads((task_workspace / "state.json").read_text(encoding="utf-8"))[
        "retry_budget_remaining"
    ] == 7


@pytest.mark.parametrize("link_target", ["workspace", "tasks"])
def test_workspace_rejects_windows_reparse_point_directory_on_python311(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, link_target: str
) -> None:
    workspace = init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )
    target = workspace if link_target == "workspace" else workspace / "tasks"
    original_lstat = os.lstat

    def fake_lstat(path: Any) -> Any:
        if Path(path) == target:
            return SimpleNamespace(st_file_attributes=0x400)
        return original_lstat(path)

    monkeypatch.setattr(os, "lstat", fake_lstat)

    with pytest.raises(HanCodeError) as error:
        init_project_workspace(
            tmp_path,
            project_id="course-project",
            course_name="AI4SE",
            assignment_name="Coding Agent Harness",
        )

    assert error.value.structured_error.error_code in {
        "workspace_link_not_allowed",
        "workspace_path_outside_project_root",
    }


def test_project_workspace_init_preserves_existing_files(tmp_path: Path) -> None:
    workspace = init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )
    existing_metadata = (workspace / "project.json").read_text(encoding="utf-8")
    (workspace / "project_memory.md").write_text("existing evidence\n", encoding="utf-8")

    result = init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )

    assert result == workspace
    assert (workspace / "project.json").read_text(encoding="utf-8") == existing_metadata
    assert (workspace / "project_memory.md").read_text(encoding="utf-8") == "existing evidence\n"


@pytest.mark.parametrize("task_id", ["../outside", "C:/outside"])
def test_workspace_rejects_path_outside_project_root(tmp_path: Path, task_id: str) -> None:
    with pytest.raises(HanCodeError) as exc_info:
        task_path(tmp_path, task_id)

    assert exc_info.value.to_dict() == {
        "error_code": "workspace_path_outside_project_root",
        "message": "Task workspace path must stay inside the project workspace.",
        "phase": "spec",
        "denied_rule": "workspace_root_boundary",
        "suggested_fix": "Use a relative task ID without parent-directory segments.",
    }


@pytest.mark.parametrize("task_id", ["", ".", "nested/task"])
def test_workspace_rejects_invalid_task_id(tmp_path: Path, task_id: str) -> None:
    with pytest.raises(HanCodeError) as exc_info:
        task_path(tmp_path, task_id)

    assert exc_info.value.to_dict() == {
        "error_code": "invalid_task_id",
        "message": "Task ID must be a single non-empty path component.",
        "phase": "spec",
        "denied_rule": "valid_task_id_required",
        "suggested_fix": "Use a task ID without path separators or dot segments.",
    }


def test_workspace_rejects_tasks_directory_escape_via_link(tmp_path: Path) -> None:
    workspace = init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )
    outside_root = tmp_path / "outside-root"
    outside_root.mkdir()

    tasks_dir = workspace / "tasks"
    tasks_dir.rmdir()
    _link_directory(tasks_dir, outside_root)

    with pytest.raises(HanCodeError) as exc_info:
        task_path(tmp_path, "task-001")

    assert exc_info.value.to_dict() == {
        "error_code": "workspace_path_outside_project_root",
        "message": "Task workspace path must stay inside the project workspace.",
        "phase": "spec",
        "denied_rule": "workspace_root_boundary",
        "suggested_fix": "Use a relative task ID without parent-directory segments.",
    }


def test_task_workspace_requires_initialized_project_workspace(tmp_path: Path) -> None:
    with pytest.raises(HanCodeError) as exc_info:
        init_task_workspace(tmp_path, "task-001")

    assert exc_info.value.to_dict() == {
        "error_code": "project_workspace_not_initialized",
        "message": "Project workspace is not initialized.",
        "phase": "spec",
        "denied_rule": "project_workspace_required",
        "suggested_fix": "Initialize the project workspace before creating a task workspace.",
    }


def test_task_workspace_rejects_invalid_project_metadata(tmp_path: Path) -> None:
    workspace = init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )
    (workspace / "project.json").write_text("{invalid", encoding="utf-8")

    with pytest.raises(HanCodeError) as exc_info:
        init_task_workspace(tmp_path, "task-001")

    assert exc_info.value.to_dict() == {
        "error_code": "invalid_project_workspace",
        "message": "Project workspace metadata is invalid.",
        "phase": "spec",
        "denied_rule": "valid_project_metadata_required",
        "suggested_fix": "Repair project.json before creating a task workspace.",
    }


def test_task_workspace_initializes_required_artifacts(tmp_path: Path) -> None:
    init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )

    workspace = init_task_workspace(tmp_path, "task-001")

    assert workspace == tmp_path / ".hancode" / "tasks" / "task-001"
    assert (workspace / "checkpoints").is_dir()
    assert (workspace / "trace.jsonl").read_text(encoding="utf-8") == ""
    assert (workspace / "history.jsonl").read_text(encoding="utf-8") == ""
    assert json.loads((workspace / "state.json").read_text(encoding="utf-8")) == {
        "schema_version": 1,
        "task_id": "task-001",
        "goal": None,
        "status": "created",
        "current_phase": "spec",
        "files_changed": [],
        "latest_checkpoint": None,
        "checkpoint_seq": 0,
        "tests_run": [],
        "latest_test_status": "none",
        "test_status_consumed": False,
        "retry_budget_remaining": 2,
        "inconsistent": False,
        "source_edits_this_phase": 0,
        "rollback_required": False,
        "rollback_done": False,
        "pending_checkpoint_recovery_id": None,
        "phase_completed": {
            "spec": False,
            "plan": False,
            "code": False,
            "test": False,
            "review": False,
            "deliver": False,
        },
        "artifacts": {
            "SPEC.md": False,
            "PLAN.md": False,
            "TEST_REPORT.md": False,
            "REVIEW.md": False,
            "KNOWLEDGE.md": False,
            "DELIVERABLES.md": False,
        },
    }
    for artifact in (
        "SPEC.md",
        "PLAN.md",
        "TEST_REPORT.md",
        "REVIEW.md",
        "KNOWLEDGE.md",
        "DELIVERABLES.md",
    ):
        assert not (workspace / artifact).exists()


def test_workspace_has_separate_history(tmp_path: Path) -> None:
    init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )
    first = init_task_workspace(tmp_path, "task-001")
    second = init_task_workspace(tmp_path, "task-002")

    (first / "history.jsonl").write_text('{"task_id":"task-001"}\n', encoding="utf-8")

    assert first != second
    assert (second / "history.jsonl").read_text(encoding="utf-8") == ""
    assert json.loads((first / "state.json").read_text(encoding="utf-8"))["task_id"] == (
        "task-001"
    )
    assert json.loads((second / "state.json").read_text(encoding="utf-8"))["task_id"] == (
        "task-002"
    )
    assert (first / "checkpoints") != (second / "checkpoints")


def test_task_workspace_state_json_contains_all_required_fields(tmp_path: Path) -> None:
    init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )
    workspace = init_task_workspace(tmp_path, "task-001")
    state = json.loads((workspace / "state.json").read_text(encoding="utf-8"))

    required_keys = {
        "schema_version",
        "task_id",
        "goal",
        "status",
        "current_phase",
        "files_changed",
        "latest_checkpoint",
        "checkpoint_seq",
        "tests_run",
        "latest_test_status",
        "test_status_consumed",
        "retry_budget_remaining",
        "inconsistent",
        "source_edits_this_phase",
        "rollback_required",
        "rollback_done",
        "phase_completed",
        "artifacts",
    }
    assert required_keys.issubset(state.keys()), (
        f"Missing keys: {required_keys - set(state.keys())}"
    )

    assert state["schema_version"] == 1
    assert state["task_id"] == "task-001"
    assert state["goal"] is None
    assert state["status"] == "created"
    assert state["current_phase"] == "spec"
    assert state["files_changed"] == []
    assert state["latest_checkpoint"] is None
    assert state["checkpoint_seq"] == 0
    assert state["tests_run"] == []
    assert state["latest_test_status"] == "none"
    assert state["test_status_consumed"] is False
    assert state["retry_budget_remaining"] == 2
    assert state["inconsistent"] is False
    assert state["source_edits_this_phase"] == 0
    assert state["rollback_required"] is False
    assert state["rollback_done"] is False
    assert state["phase_completed"] == {
        "spec": False,
        "plan": False,
        "code": False,
        "test": False,
        "review": False,
        "deliver": False,
    }
    assert state["artifacts"] == {
        "SPEC.md": False,
        "PLAN.md": False,
        "TEST_REPORT.md": False,
        "REVIEW.md": False,
        "KNOWLEDGE.md": False,
        "DELIVERABLES.md": False,
    }


def test_task_workspace_init_preserves_existing_state_and_trace(tmp_path: Path) -> None:
    init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )
    workspace = init_task_workspace(tmp_path, "task-001")

    (workspace / "state.json").write_text(
        '{"schema_version":1,"task_id":"task-001","status":"running"}\n',
        encoding="utf-8",
    )
    (workspace / "trace.jsonl").write_text('{"event":"existing"}\n', encoding="utf-8")
    (workspace / "history.jsonl").write_text('{"action":"existing"}\n', encoding="utf-8")

    result = init_task_workspace(tmp_path, "task-001")

    assert result == workspace
    assert json.loads((workspace / "state.json").read_text(encoding="utf-8"))["status"] == (
        "running"
    )
    assert (workspace / "trace.jsonl").read_text(encoding="utf-8") == '{"event":"existing"}\n'
    assert (workspace / "history.jsonl").read_text(encoding="utf-8") == (
        '{"action":"existing"}\n'
    )


def test_task_workspace_init_preserves_existing_checkpoints_and_artifacts(
    tmp_path: Path,
) -> None:
    init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )
    workspace = init_task_workspace(tmp_path, "task-001")

    (workspace / "SPEC.md").write_text("# Existing spec\n", encoding="utf-8")
    checkpoint_dir = workspace / "checkpoints" / "cp-001"
    checkpoint_dir.mkdir()
    (checkpoint_dir / "manifest.json").write_text('{"checkpoint":"cp-001"}\n', encoding="utf-8")

    result = init_task_workspace(tmp_path, "task-001")

    assert result == workspace
    assert (workspace / "SPEC.md").read_text(encoding="utf-8") == "# Existing spec\n"
    assert (checkpoint_dir / "manifest.json").read_text(encoding="utf-8") == (
        '{"checkpoint":"cp-001"}\n'
    )


@pytest.mark.parametrize(
    "metadata_json",
    [
        '{"workspace_version":1,"project_root":"."}',
        '{"workspace_version":1,"project_root":".","project_id":"","course_name":"AI4SE","assignment_name":"X"}',
        '{"workspace_version":1,"project_root":".","project_id":"p","course_name":"","assignment_name":"X"}',
        '{"workspace_version":2,"project_root":".","project_id":"p","course_name":"c","assignment_name":"a"}',
    ],
    ids=["missing_text_fields", "empty_project_id", "empty_course_name", "wrong_version"],
)
def test_task_workspace_rejects_incomplete_project_metadata(
    tmp_path: Path, metadata_json: str
) -> None:
    workspace = init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )
    (workspace / "project.json").write_text(metadata_json, encoding="utf-8")

    with pytest.raises(HanCodeError) as exc_info:
        init_task_workspace(tmp_path, "task-001")

    assert exc_info.value.to_dict() == {
        "error_code": "invalid_project_workspace",
        "message": "Project workspace metadata is invalid.",
        "phase": "spec",
        "denied_rule": "valid_project_metadata_required",
        "suggested_fix": "Repair project.json before creating a task workspace.",
    }


def test_task_workspace_rejects_missing_memory_files(tmp_path: Path) -> None:
    workspace = init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )
    (workspace / "project_memory.md").unlink()

    with pytest.raises(HanCodeError) as exc_info:
        init_task_workspace(tmp_path, "task-001")

    assert exc_info.value.to_dict() == {
        "error_code": "project_workspace_not_initialized",
        "message": "Project workspace is not initialized.",
        "phase": "spec",
        "denied_rule": "project_workspace_required",
        "suggested_fix": "Initialize the project workspace before creating a task workspace.",
    }


def _link_directory(link_path: Path, target_path: Path) -> None:
    try:
        link_path.symlink_to(target_path, target_is_directory=True)
        return
    except OSError as exc:
        if os.name != "nt":
            pytest.skip(f"Directory symlink unsupported in this environment: {exc}")

    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link_path), str(target_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip(
            "Directory link creation unavailable in this environment: "
            f"{result.stdout}{result.stderr}"
        )


def test_project_workspace_rejects_hancode_directory_link(tmp_path: Path) -> None:
    external_workspace = tmp_path / "external-hancode"
    external_workspace.mkdir()
    _link_directory(tmp_path / ".hancode", external_workspace)

    with pytest.raises(HanCodeError) as error:
        init_project_workspace(tmp_path, "course-project", "AI4SE", "Harness")

    assert error.value.structured_error.error_code == "workspace_link_not_allowed"
