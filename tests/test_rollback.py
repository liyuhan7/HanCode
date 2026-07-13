from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

from hancode.checkpoints import (
    commit_checkpoint,
    create_checkpoint,
    rollback_last_checkpoint,
)
from hancode.errors import HanCodeError, StructuredError
from hancode.models import OperationStatus, Phase, TaskStatus
from hancode.state import load_state, save_state
from hancode.workspace import init_project_workspace, init_task_workspace
import hancode.checkpoints as checkpoints


_CREATED_AT = datetime(2026, 7, 13, 8, 30, tzinfo=UTC)


def test_rollback_last_checkpoint_restores_file(tmp_path: Path) -> None:
    task_root = _task_root(tmp_path, phase=Phase.CODE)
    source = tmp_path / "src" / "main.py"
    source.parent.mkdir()
    source.write_text("before", encoding="utf-8")
    checkpoint = create_checkpoint(task_root, [source], "Before update.", created_at=_CREATED_AT)
    source.write_text("after", encoding="utf-8")
    commit_checkpoint(task_root, checkpoint.checkpoint_id)
    save_state(task_root, replace(load_state(task_root), current_phase=Phase.REVIEW))

    result = rollback_last_checkpoint(task_root)

    assert result.status is OperationStatus.SUCCEEDED
    assert result.restored_files == ("src/main.py",)
    assert source.read_text(encoding="utf-8") == "before"


def test_rollback_marks_manifest_rolled_back(tmp_path: Path) -> None:
    task_root = _task_root(tmp_path, phase=Phase.CODE)
    source = tmp_path / "src" / "main.py"
    source.parent.mkdir()
    source.write_text("before", encoding="utf-8")
    checkpoint = create_checkpoint(task_root, [source], "Before update.", created_at=_CREATED_AT)
    source.write_text("after", encoding="utf-8")
    commit_checkpoint(task_root, checkpoint.checkpoint_id)
    save_state(task_root, replace(load_state(task_root), current_phase=Phase.REVIEW))

    rollback_last_checkpoint(task_root)

    manifest = json.loads(
        (task_root / "checkpoints" / checkpoint.checkpoint_id / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["status"] == "rolled_back"
    assert manifest["rollback_available"] is False


def test_rollback_resets_review_state(tmp_path: Path) -> None:
    task_root = _task_root(tmp_path, phase=Phase.CODE)
    source = tmp_path / "src" / "main.py"
    source.parent.mkdir()
    source.write_text("before", encoding="utf-8")
    checkpoint = create_checkpoint(task_root, [source], "Before update.", created_at=_CREATED_AT)
    source.write_text("after", encoding="utf-8")
    commit_checkpoint(task_root, checkpoint.checkpoint_id)
    phase_completed = dict(load_state(task_root).phase_completed)
    phase_completed.update({"code": True, "test": True, "review": True})
    save_state(
        task_root,
        replace(
            load_state(task_root),
            current_phase=Phase.REVIEW,
            latest_test_status="failed",
            test_status_consumed=True,
            retry_budget_remaining=1,
            source_edits_this_phase=2,
            rollback_required=True,
            phase_completed=phase_completed,
        ),
    )

    result = rollback_last_checkpoint(task_root)

    state = load_state(task_root)
    assert result.status is OperationStatus.SUCCEEDED
    assert state.current_phase is Phase.REVIEW
    assert state.latest_checkpoint == checkpoint.checkpoint_id
    assert state.latest_test_status == "none"
    assert state.test_status_consumed is False
    assert state.source_edits_this_phase == 0
    assert state.rollback_required is False
    assert state.rollback_done is True
    assert state.retry_budget_remaining == 1
    assert state.phase_completed["code"] is False
    assert state.phase_completed["test"] is False
    assert state.phase_completed["review"] is False


def test_rollback_writes_trace_event(tmp_path: Path) -> None:
    task_root = _task_root(tmp_path, phase=Phase.CODE)
    source = tmp_path / "src" / "main.py"
    source.parent.mkdir()
    source.write_text("before", encoding="utf-8")
    checkpoint = create_checkpoint(task_root, [source], "Before update.", created_at=_CREATED_AT)
    source.write_text("after", encoding="utf-8")
    commit_checkpoint(task_root, checkpoint.checkpoint_id)
    save_state(task_root, replace(load_state(task_root), current_phase=Phase.REVIEW))

    rollback_last_checkpoint(task_root)

    events = [
        json.loads(line)
        for line in (task_root / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [(event["event_type"], event["status"]) for event in events[-2:]] == [
        ("rollback_started", "running"),
        ("rollback_performed", "succeeded"),
    ]


def test_rollback_compensates_files_when_multi_file_restore_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_root = _task_root(tmp_path, phase=Phase.CODE)
    first = tmp_path / "src" / "a.py"
    second = tmp_path / "src" / "b.py"
    first.parent.mkdir()
    first.write_text("before-a", encoding="utf-8")
    second.write_text("before-b", encoding="utf-8")
    checkpoint = create_checkpoint(task_root, [first, second], "Before updates.", created_at=_CREATED_AT)
    first.write_text("after-a", encoding="utf-8")
    second.write_text("after-b", encoding="utf-8")
    commit_checkpoint(task_root, checkpoint.checkpoint_id)
    save_state(task_root, replace(load_state(task_root), current_phase=Phase.REVIEW))
    original_replace = Path.replace

    def fail_second_restore(source: Path, target: Path) -> Path:
        if source.name.startswith(".b.py.rollback"):
            raise OSError("simulated second restore failure")
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", fail_second_restore)

    result = rollback_last_checkpoint(task_root)

    assert result.status is OperationStatus.FAILED
    assert result.error is not None
    assert result.error.error_code == "rollback_restore_failed"
    assert result.restored_files == ()
    assert first.read_text(encoding="utf-8") == "after-a"
    assert second.read_text(encoding="utf-8") == "after-b"
    assert not list((tmp_path / "src").glob(".b.py.rollback*"))
    manifest = json.loads(
        (task_root / "checkpoints" / checkpoint.checkpoint_id / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["status"] == "committed"
    assert load_state(task_root).rollback_done is False


def test_rollback_writes_failed_trace_after_restore_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_root = _task_root(tmp_path, phase=Phase.CODE)
    first = tmp_path / "src" / "a.py"
    second = tmp_path / "src" / "b.py"
    first.parent.mkdir()
    first.write_text("before-a", encoding="utf-8")
    second.write_text("before-b", encoding="utf-8")
    checkpoint = create_checkpoint(task_root, [first, second], "Before updates.", created_at=_CREATED_AT)
    first.write_text("after-a", encoding="utf-8")
    second.write_text("after-b", encoding="utf-8")
    commit_checkpoint(task_root, checkpoint.checkpoint_id)
    save_state(task_root, replace(load_state(task_root), current_phase=Phase.REVIEW))
    original_replace = Path.replace

    def fail_second_restore(source: Path, target: Path) -> Path:
        if source.name.startswith(".b.py.rollback"):
            raise OSError("simulated second restore failure")
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", fail_second_restore)

    rollback_last_checkpoint(task_root)

    events = [
        json.loads(line)
        for line in (task_root / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert events[-1]["event_type"] == "rollback_performed"
    assert events[-1]["status"] == "failed"


def test_rollback_marks_state_inconsistent_when_file_compensation_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_root = _task_root(tmp_path, phase=Phase.CODE)
    first = tmp_path / "src" / "a.py"
    second = tmp_path / "src" / "b.py"
    first.parent.mkdir()
    first.write_text("before-a", encoding="utf-8")
    second.write_text("before-b", encoding="utf-8")
    checkpoint = create_checkpoint(task_root, [first, second], "Before updates.", created_at=_CREATED_AT)
    first.write_text("after-a", encoding="utf-8")
    second.write_text("after-b", encoding="utf-8")
    commit_checkpoint(task_root, checkpoint.checkpoint_id)
    save_state(task_root, replace(load_state(task_root), current_phase=Phase.REVIEW))
    original_replace = Path.replace

    def fail_restore_and_compensation(source: Path, target: Path) -> Path:
        if source.name.startswith(".b.py.rollback") or source.name.startswith(
            ".a.py.rollback-compensate"
        ):
            raise OSError("simulated restore compensation failure")
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", fail_restore_and_compensation)

    result = rollback_last_checkpoint(task_root)

    assert result.status is OperationStatus.FAILED
    assert result.error is not None
    assert result.error.error_code == "rollback_compensation_failed"
    state = load_state(task_root)
    assert state.status is TaskStatus.INCONSISTENT
    assert state.inconsistent is True


def test_rollback_removes_file_created_after_checkpoint(tmp_path: Path) -> None:
    task_root = _task_root(tmp_path, phase=Phase.CODE)
    created = create_checkpoint(
        task_root,
        [Path("src/new_module.py")],
        "Before creating module.",
        created_at=_CREATED_AT,
    )
    source = tmp_path / "src" / "new_module.py"
    source.parent.mkdir()
    source.write_text("new module", encoding="utf-8")
    commit_checkpoint(task_root, created.checkpoint_id)
    save_state(task_root, replace(load_state(task_root), current_phase=Phase.REVIEW))

    result = rollback_last_checkpoint(task_root)

    assert result.status is OperationStatus.SUCCEEDED
    assert result.restored_files == ("src/new_module.py",)
    assert not source.exists()


def test_rollback_serializes_result_for_feedback(tmp_path: Path) -> None:
    task_root, source, checkpoint_id = _committed_modified_checkpoint(tmp_path)
    save_state(task_root, replace(load_state(task_root), current_phase=Phase.REVIEW))

    result = rollback_last_checkpoint(task_root)

    assert result.to_dict() == {
        "status": "succeeded",
        "checkpoint_id": checkpoint_id,
        "restored_files": ["src/main.py"],
        "failed_files": [],
        "error": None,
        "error_summary": None,
    }
    assert source.read_text(encoding="utf-8") == "before"


def test_rollback_requires_review_phase(tmp_path: Path) -> None:
    task_root, source, checkpoint_id = _committed_modified_checkpoint(tmp_path)

    result = rollback_last_checkpoint(task_root)

    assert result.status is OperationStatus.BLOCKED
    assert result.checkpoint_id == checkpoint_id
    assert result.error is not None
    assert result.error.error_code == "rollback_requires_review_phase"
    assert source.read_text(encoding="utf-8") == "after"


def test_rollback_requires_latest_checkpoint(tmp_path: Path) -> None:
    task_root, source, _ = _committed_modified_checkpoint(tmp_path)
    save_state(
        task_root,
        replace(load_state(task_root), current_phase=Phase.REVIEW, latest_checkpoint=None),
    )

    result = rollback_last_checkpoint(task_root)

    assert result.status is OperationStatus.BLOCKED
    assert result.error is not None
    assert result.error.error_code == "rollback_checkpoint_required"
    assert source.read_text(encoding="utf-8") == "after"


def test_damaged_manifest_blocks_rollback(tmp_path: Path) -> None:
    task_root, source, checkpoint_id = _committed_modified_checkpoint(tmp_path)
    manifest_path = task_root / "checkpoints" / checkpoint_id / "manifest.json"
    manifest_path.write_text("{not-json", encoding="utf-8")
    save_state(task_root, replace(load_state(task_root), current_phase=Phase.REVIEW))

    result = rollback_last_checkpoint(task_root)

    assert result.status is OperationStatus.BLOCKED
    assert result.error is not None
    assert result.error.error_code == "checkpoint_manifest_invalid"
    assert source.read_text(encoding="utf-8") == "after"


def test_rollback_does_not_restore_protected_files(tmp_path: Path) -> None:
    task_root, source, checkpoint_id = _committed_modified_checkpoint(tmp_path)
    manifest_path = task_root / "checkpoints" / checkpoint_id / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][0]["path"] = ".env"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    protected = tmp_path / ".env"
    protected.write_text("do-not-change", encoding="utf-8")
    save_state(task_root, replace(load_state(task_root), current_phase=Phase.REVIEW))

    result = rollback_last_checkpoint(task_root)

    assert result.status is OperationStatus.BLOCKED
    assert result.error is not None
    assert result.error.error_code == "checkpoint_path_not_source"
    assert source.read_text(encoding="utf-8") == "after"
    assert protected.read_text(encoding="utf-8") == "do-not-change"


def test_rollback_blocks_external_content_conflict_without_writes(tmp_path: Path) -> None:
    task_root, source, checkpoint_id = _committed_modified_checkpoint(tmp_path)
    source.write_text("external change", encoding="utf-8")
    save_state(task_root, replace(load_state(task_root), current_phase=Phase.REVIEW))

    result = rollback_last_checkpoint(task_root)

    assert result.status is OperationStatus.BLOCKED
    assert result.error is not None
    assert result.error.error_code == "rollback_conflict"
    assert source.read_text(encoding="utf-8") == "external change"
    manifest = json.loads(
        (task_root / "checkpoints" / checkpoint_id / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["status"] == "committed"
    events = [
        json.loads(line)
        for line in (task_root / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert events[-1]["event_type"] == "rollback_performed"
    assert events[-1]["status"] == "blocked"


def test_rollback_blocks_when_current_file_cannot_be_verified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_root, source, _ = _committed_modified_checkpoint(tmp_path)
    save_state(task_root, replace(load_state(task_root), current_phase=Phase.REVIEW))
    original_read_bytes = Path.read_bytes

    def fail_current_source_read(path: Path) -> bytes:
        if path == source:
            raise OSError("simulated current source read failure")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", fail_current_source_read)

    result = rollback_last_checkpoint(task_root)

    assert result.status is OperationStatus.BLOCKED
    assert result.error is not None
    assert result.error.error_code == "rollback_conflict"
    assert source.read_text(encoding="utf-8") == "after"


def test_rollback_blocks_inconsistent_task_state(tmp_path: Path) -> None:
    task_root, source, _ = _committed_modified_checkpoint(tmp_path)
    save_state(
        task_root,
        replace(
            load_state(task_root),
            current_phase=Phase.REVIEW,
            status=TaskStatus.INCONSISTENT,
            inconsistent=True,
        ),
    )

    result = rollback_last_checkpoint(task_root)

    assert result.status is OperationStatus.BLOCKED
    assert result.error is not None
    assert result.error.error_code == "rollback_inconsistent_state"
    assert source.read_text(encoding="utf-8") == "after"


def test_rollback_blocks_repeated_restore(tmp_path: Path) -> None:
    task_root, _, checkpoint_id = _committed_modified_checkpoint(tmp_path)
    save_state(task_root, replace(load_state(task_root), current_phase=Phase.REVIEW))
    first_result = rollback_last_checkpoint(task_root)

    second_result = rollback_last_checkpoint(task_root)

    assert first_result.status is OperationStatus.SUCCEEDED
    assert second_result.status is OperationStatus.BLOCKED
    assert second_result.checkpoint_id == checkpoint_id
    assert second_result.error is not None
    assert second_result.error.error_code == "rollback_not_available"


def test_rollback_blocks_snapshot_escape_before_writing_source(tmp_path: Path) -> None:
    task_root, source, checkpoint_id = _committed_modified_checkpoint(tmp_path)
    manifest_path = task_root / "checkpoints" / checkpoint_id / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][0]["before_snapshot"] = "../trace.jsonl"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    save_state(task_root, replace(load_state(task_root), current_phase=Phase.REVIEW))

    result = rollback_last_checkpoint(task_root)

    assert result.status is OperationStatus.BLOCKED
    assert result.error is not None
    assert result.error.error_code == "checkpoint_manifest_invalid"
    assert source.read_text(encoding="utf-8") == "after"


def test_rollback_blocks_external_source_symlink_before_writing(
    tmp_path: Path,
) -> None:
    task_root, source, _ = _committed_modified_checkpoint(tmp_path)
    external = tmp_path / "external.py"
    external.write_text("external", encoding="utf-8")
    original_source = source.with_name("main-original.py")
    source.rename(original_source)
    try:
        source.symlink_to(external)
    except OSError as exc:
        pytest.skip(f"Windows does not permit symlink creation: {exc}")
    save_state(task_root, replace(load_state(task_root), current_phase=Phase.REVIEW))

    result = rollback_last_checkpoint(task_root)

    assert result.status is OperationStatus.BLOCKED
    assert result.error is not None
    assert result.error.error_code == "checkpoint_path_not_source"
    assert external.read_text(encoding="utf-8") == "external"


def test_rollback_does_not_reuse_preexisting_restore_temporary_path(tmp_path: Path) -> None:
    task_root, source, _ = _committed_modified_checkpoint(tmp_path)
    temporary_path = source.with_name(".main.py.rollback.tmp")
    temporary_path.write_text("do-not-overwrite", encoding="utf-8")
    save_state(task_root, replace(load_state(task_root), current_phase=Phase.REVIEW))

    result = rollback_last_checkpoint(task_root)

    assert result.status is OperationStatus.SUCCEEDED
    assert source.read_text(encoding="utf-8") == "before"
    assert temporary_path.read_text(encoding="utf-8") == "do-not-overwrite"


def test_rollback_compensates_files_when_manifest_update_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_root = _task_root(tmp_path, phase=Phase.CODE)
    source = tmp_path / "src" / "main.py"
    source.parent.mkdir()
    source.write_text("before", encoding="utf-8")
    checkpoint = create_checkpoint(task_root, [source], "Before update.", created_at=_CREATED_AT)
    source.write_text("after", encoding="utf-8")
    commit_checkpoint(task_root, checkpoint.checkpoint_id)
    save_state(task_root, replace(load_state(task_root), current_phase=Phase.REVIEW))
    original_write_manifest = checkpoints._write_manifest

    def fail_rolled_back_manifest(path: Path, manifest: object, *, atomic: bool) -> None:
        if getattr(manifest, "status", None) == "rolled_back":
            raise OSError("simulated manifest write failure")
        original_write_manifest(path, manifest, atomic=atomic)

    monkeypatch.setattr(checkpoints, "_write_manifest", fail_rolled_back_manifest)

    result = rollback_last_checkpoint(task_root)

    assert result.status is OperationStatus.FAILED
    assert result.error is not None
    assert result.error.error_code == "rollback_manifest_update_failed"
    assert source.read_text(encoding="utf-8") == "after"
    manifest = json.loads(
        (task_root / "checkpoints" / checkpoint.checkpoint_id / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["status"] == "committed"
    assert load_state(task_root).rollback_done is False
    events = [
        json.loads(line)
        for line in (task_root / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert events[-1]["event_type"] == "rollback_performed"
    assert events[-1]["status"] == "failed"


def test_rollback_compensates_manifest_and_files_when_state_update_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_root = _task_root(tmp_path, phase=Phase.CODE)
    source = tmp_path / "src" / "main.py"
    source.parent.mkdir()
    source.write_text("before", encoding="utf-8")
    checkpoint = create_checkpoint(task_root, [source], "Before update.", created_at=_CREATED_AT)
    source.write_text("after", encoding="utf-8")
    commit_checkpoint(task_root, checkpoint.checkpoint_id)
    save_state(task_root, replace(load_state(task_root), current_phase=Phase.REVIEW))
    original_save_state = checkpoints.save_state

    def fail_rolled_back_state(task_root: Path, state: object) -> None:
        if getattr(state, "rollback_done", False):
            raise HanCodeError(
                StructuredError(
                    error_code="state_write_error",
                    message="simulated state failure",
                    phase="review",
                    denied_rule="simulated",
                    suggested_fix="retry",
                )
            )
        original_save_state(task_root, state)

    monkeypatch.setattr(checkpoints, "save_state", fail_rolled_back_state)

    result = rollback_last_checkpoint(task_root)

    assert result.status is OperationStatus.FAILED
    assert result.error is not None
    assert result.error.error_code == "rollback_state_update_failed"
    assert source.read_text(encoding="utf-8") == "after"
    manifest = json.loads(
        (task_root / "checkpoints" / checkpoint.checkpoint_id / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["status"] == "committed"
    assert manifest["rollback_available"] is True
    assert load_state(task_root).rollback_done is False
    events = [
        json.loads(line)
        for line in (task_root / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert events[-1]["event_type"] == "rollback_performed"
    assert events[-1]["status"] == "failed"


def test_rollback_compensates_state_manifest_and_files_when_trace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_root = _task_root(tmp_path, phase=Phase.CODE)
    source = tmp_path / "src" / "main.py"
    source.parent.mkdir()
    source.write_text("before", encoding="utf-8")
    checkpoint = create_checkpoint(task_root, [source], "Before update.", created_at=_CREATED_AT)
    source.write_text("after", encoding="utf-8")
    commit_checkpoint(task_root, checkpoint.checkpoint_id)
    save_state(task_root, replace(load_state(task_root), current_phase=Phase.REVIEW))
    original_append_trace = checkpoints.append_trace

    def fail_final_trace(*args: object, **kwargs: object) -> object:
        if kwargs.get("event_type") == "rollback_performed":
            raise HanCodeError(
                StructuredError(
                    error_code="trace_write_error",
                    message="simulated trace failure",
                    phase="review",
                    denied_rule="simulated",
                    suggested_fix="retry",
                )
            )
        return original_append_trace(*args, **kwargs)

    monkeypatch.setattr(checkpoints, "append_trace", fail_final_trace)

    result = rollback_last_checkpoint(task_root)

    assert result.status is OperationStatus.FAILED
    assert result.error is not None
    assert result.error.error_code == "rollback_trace_failed"
    assert source.read_text(encoding="utf-8") == "after"
    manifest = json.loads(
        (task_root / "checkpoints" / checkpoint.checkpoint_id / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["status"] == "committed"
    assert load_state(task_root).rollback_done is False


def _task_root(tmp_path: Path, *, phase: Phase) -> Path:
    init_project_workspace(tmp_path, "project-001", "SE", "Harness")
    task_root = init_task_workspace(tmp_path, "task-001")
    save_state(task_root, replace(load_state(task_root), current_phase=phase))
    return task_root


def _committed_modified_checkpoint(tmp_path: Path) -> tuple[Path, Path, str]:
    task_root = _task_root(tmp_path, phase=Phase.CODE)
    source = tmp_path / "src" / "main.py"
    source.parent.mkdir()
    source.write_text("before", encoding="utf-8")
    checkpoint = create_checkpoint(task_root, [source], "Before update.", created_at=_CREATED_AT)
    source.write_text("after", encoding="utf-8")
    commit_checkpoint(task_root, checkpoint.checkpoint_id)
    return task_root, source, checkpoint.checkpoint_id
