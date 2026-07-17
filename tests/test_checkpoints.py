from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

import pytest

from hancode.checkpoints import commit_checkpoint, create_checkpoint
from hancode.errors import HanCodeError, StructuredError
from hancode.models import Phase
from hancode.state import load_state, save_state
from hancode.workspace import init_project_workspace, init_task_workspace
import hancode.checkpoints as checkpoints


_CREATED_AT = datetime(2026, 7, 13, 8, 30, tzinfo=UTC)


def test_create_checkpoint_snapshots_existing_source_file(tmp_path: Path) -> None:
    task_root = _code_task(tmp_path)
    source = tmp_path / "src" / "main.py"
    source.parent.mkdir()
    source.write_bytes(b"print('before')\n")

    manifest = create_checkpoint(task_root, [source], "Before changing main.", created_at=_CREATED_AT)

    assert manifest.checkpoint_id == "ckpt-001"
    assert manifest.status == "pending"
    assert manifest.rollback_available is False
    assert manifest.files[0].path == "src/main.py"
    assert manifest.files[0].action == "modify"
    assert manifest.files[0].before_sha256 == hashlib.sha256(b"print('before')\n").hexdigest()
    snapshot = task_root / "checkpoints" / "ckpt-001" / manifest.files[0].before_snapshot
    assert snapshot.read_bytes() == b"print('before')\n"


def test_create_checkpoint_redacts_secret_like_reason_from_manifest(tmp_path: Path) -> None:
    task_root = _code_task(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("before", encoding="utf-8")

    manifest = create_checkpoint(
        task_root,
        [Path("src/main.py")],
        "Use api_key=super-secret and Bearer access-token.",
    )

    persisted = (task_root / "checkpoints" / manifest.checkpoint_id / "manifest.json").read_text(encoding="utf-8")
    assert "super-secret" not in persisted
    assert "access-token" not in persisted
    assert "[REDACTED]" in persisted


def test_create_checkpoint_supports_missing_source_target(tmp_path: Path) -> None:
    task_root = _code_task(tmp_path)

    manifest = create_checkpoint(task_root, [Path("src/new_module.py")], "Before creating module.", created_at=_CREATED_AT)

    assert manifest.files == (
        replace(
            manifest.files[0],
            path="src/new_module.py",
            action="create",
            before_snapshot=None,
            before_sha256=None,
            after_sha256=None,
        ),
    )


def test_checkpoint_normalizes_deduplicates_and_sorts_paths(tmp_path: Path) -> None:
    task_root = _code_task(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("a", encoding="utf-8")
    (tmp_path / "src" / "b.py").write_text("b", encoding="utf-8")

    manifest = create_checkpoint(
        task_root,
        [tmp_path / "src" / "b.py", Path("src/a.py"), Path("src/b.py")],
        "Before ordered update.",
        created_at=_CREATED_AT,
    )

    assert [file.path for file in manifest.files] == ["src/a.py", "src/b.py"]


def test_create_checkpoint_updates_state_and_trace(tmp_path: Path) -> None:
    task_root = _code_task(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("before", encoding="utf-8")

    create_checkpoint(task_root, [Path("src/main.py")], "Before update.", created_at=_CREATED_AT)

    state = load_state(task_root)
    trace = json.loads((task_root / "trace.jsonl").read_text(encoding="utf-8"))
    assert (state.checkpoint_seq, state.latest_checkpoint) == (1, "ckpt-001")
    assert trace["event_type"] == "checkpoint_created"
    assert trace["status"] == "succeeded"
    assert trace["state_transition"] == {"latest_checkpoint": [None, "ckpt-001"]}


def test_create_checkpoint_rejects_when_project_checkpoint_limit_is_reached(
    tmp_path: Path,
) -> None:
    task_root = _code_task(tmp_path)
    project_file = tmp_path / ".hancode" / "project.json"
    project_data = json.loads(project_file.read_text(encoding="utf-8"))
    project_data["max_checkpoints_per_task"] = 1
    project_file.write_text(json.dumps(project_data), encoding="utf-8")
    (tmp_path / "src").mkdir()
    source = tmp_path / "src" / "main.py"
    source.write_text("before", encoding="utf-8")

    create_checkpoint(task_root, [source], "first")
    source.write_text("after", encoding="utf-8")

    with pytest.raises(HanCodeError) as error:
        create_checkpoint(task_root, [source], "second")

    assert error.value.structured_error.error_code == "checkpoint_limit_exceeded"
    assert not (task_root / "checkpoints" / "ckpt-002").exists()
    assert load_state(task_root).checkpoint_seq == 1


@pytest.mark.parametrize(
    ("files", "reason", "error_code"),
    [
        ([], "Before update.", "checkpoint_files_required"),
        ([Path("src/main.py")], "  ", "checkpoint_reason_required"),
        ([Path("assignment.md")], "Before update.", "checkpoint_path_not_source"),
        ([Path(".hancode/tasks/task-001/SPEC.md")], "Before update.", "checkpoint_path_not_source"),
        ([Path("../outside.py")], "Before update.", "checkpoint_path_not_source"),
    ],
)
def test_create_checkpoint_rejects_invalid_request(
    tmp_path: Path, files: list[Path], reason: str, error_code: str
) -> None:
    task_root = _code_task(tmp_path)

    with pytest.raises(HanCodeError) as error:
        create_checkpoint(task_root, files, reason)

    assert error.value.structured_error.error_code == error_code


def test_create_checkpoint_rejects_non_code_phase(tmp_path: Path) -> None:
    task_root = _code_task(tmp_path, phase=Phase.PLAN)

    with pytest.raises(HanCodeError) as error:
        create_checkpoint(task_root, [Path("src/main.py")], "Before update.")

    assert error.value.structured_error.error_code == "checkpoint_requires_code_phase"


def test_create_checkpoint_rejects_directory_target(tmp_path: Path) -> None:
    task_root = _code_task(tmp_path)
    (tmp_path / "src").mkdir()

    with pytest.raises(HanCodeError) as error:
        create_checkpoint(task_root, [Path("src")], "Before update.")

    assert error.value.structured_error.error_code == "checkpoint_target_is_directory"


def test_create_checkpoint_removes_snapshot_when_state_update_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_root = _code_task(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("before", encoding="utf-8")

    def fail_save_state(task_root: Path, state: object) -> None:
        raise HanCodeError(_error("state_write_error"))

    monkeypatch.setattr(checkpoints, "save_state", fail_save_state)

    with pytest.raises(HanCodeError) as error:
        create_checkpoint(task_root, [Path("src/main.py")], "Before update.")

    assert error.value.structured_error.error_code == "checkpoint_state_update_failed"
    assert not (task_root / "checkpoints" / "ckpt-001").exists()
    assert (load_state(task_root).checkpoint_seq, load_state(task_root).latest_checkpoint) == (0, None)
    assert (task_root / "trace.jsonl").read_text(encoding="utf-8") == ""


def test_create_checkpoint_compensates_state_when_trace_write_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_root = _code_task(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("before", encoding="utf-8")

    def fail_trace(*_: object, **__: object) -> object:
        raise HanCodeError(_error("trace_write_error"))

    monkeypatch.setattr(checkpoints, "append_trace", fail_trace)

    with pytest.raises(HanCodeError) as error:
        create_checkpoint(task_root, [Path("src/main.py")], "Before update.")

    assert error.value.structured_error.error_code == "checkpoint_trace_failed"
    assert not (task_root / "checkpoints" / "ckpt-001").exists()
    assert (load_state(task_root).checkpoint_seq, load_state(task_root).latest_checkpoint) == (0, None)
    assert (task_root / "trace.jsonl").read_text(encoding="utf-8") == ""


def test_create_checkpoint_hides_partial_snapshot_when_manifest_write_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_root = _code_task(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("before", encoding="utf-8")

    def fail_manifest(*_: object, **__: object) -> None:
        raise OSError("write failed")

    monkeypatch.setattr(checkpoints, "_write_manifest", fail_manifest)

    with pytest.raises(HanCodeError) as error:
        create_checkpoint(task_root, [Path("src/main.py")], "Before update.")

    assert error.value.structured_error.error_code == "checkpoint_snapshot_failed"
    assert not (task_root / "checkpoints" / "ckpt-001").exists()
    assert load_state(task_root).checkpoint_seq == 0


def test_create_checkpoint_reports_compensation_failure_when_cleanup_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_root = _code_task(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("before", encoding="utf-8")

    def fail_save_state(task_root: Path, state: object) -> None:
        raise HanCodeError(_error("state_write_error"))

    monkeypatch.setattr(checkpoints, "save_state", fail_save_state)
    monkeypatch.setattr(checkpoints, "_remove_checkpoint", lambda _: False)

    with pytest.raises(HanCodeError) as error:
        create_checkpoint(task_root, [Path("src/main.py")], "Before update.")

    assert error.value.structured_error.error_code == "checkpoint_compensation_failed"


@pytest.mark.parametrize(
    "protected_path",
    [
        Path(".env"),
        Path("credentials/api.key"),
        Path("tests/teacher_hidden.py"),
        Path("grading/score.py"),
        Path("samples/input.json"),
    ],
)
def test_create_checkpoint_excludes_protected_course_and_credential_files(
    tmp_path: Path, protected_path: Path
) -> None:
    task_root = _code_task(tmp_path)

    with pytest.raises(HanCodeError) as error:
        create_checkpoint(task_root, [protected_path], "Before update.")

    assert error.value.structured_error.error_code == "checkpoint_path_not_source"


def test_commit_checkpoint_records_after_hash_and_marks_committed(tmp_path: Path) -> None:
    task_root = _code_task(tmp_path)
    (tmp_path / "src").mkdir()
    source = tmp_path / "src" / "main.py"
    source.write_text("before", encoding="utf-8")
    created = create_checkpoint(task_root, [source], "Before update.", created_at=_CREATED_AT)
    source.write_text("after", encoding="utf-8")

    committed = commit_checkpoint(task_root, created.checkpoint_id)

    assert committed.status == "committed"
    assert committed.rollback_available is True
    assert committed.files[0].after_sha256 == hashlib.sha256(b"after").hexdigest()
    payload = json.loads((task_root / "checkpoints" / "ckpt-001" / "manifest.json").read_text(encoding="utf-8"))
    assert payload["status"] == "committed"
    assert payload["rollback_available"] is True


def test_commit_checkpoint_supports_created_file(tmp_path: Path) -> None:
    task_root = _code_task(tmp_path)
    created = create_checkpoint(task_root, [Path("src/new_module.py")], "Before create.", created_at=_CREATED_AT)
    target = tmp_path / "src" / "new_module.py"
    target.parent.mkdir()
    target.write_text("new", encoding="utf-8")

    committed = commit_checkpoint(task_root, created.checkpoint_id)

    assert committed.files[0].action == "create"
    assert committed.files[0].after_sha256 == hashlib.sha256(b"new").hexdigest()


def test_commit_checkpoint_records_auditable_transition(tmp_path: Path) -> None:
    task_root = _code_task(tmp_path)
    (tmp_path / "src").mkdir()
    source = tmp_path / "src" / "main.py"
    source.write_text("before", encoding="utf-8")
    created = create_checkpoint(task_root, [source], "Before update.", created_at=_CREATED_AT)
    source.write_text("after", encoding="utf-8")

    commit_checkpoint(task_root, created.checkpoint_id)

    events = [json.loads(line) for line in (task_root / "trace.jsonl").read_text(encoding="utf-8").splitlines()]
    assert events[-1]["event_type"] == "checkpoint_committed"
    assert events[-1]["status"] == "succeeded"
    assert events[-1]["state_transition"] == {"checkpoint_status": ["pending", "committed"]}


def test_commit_checkpoint_restores_pending_manifest_when_trace_write_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_root = _code_task(tmp_path)
    (tmp_path / "src").mkdir()
    source = tmp_path / "src" / "main.py"
    source.write_text("before", encoding="utf-8")
    created = create_checkpoint(task_root, [source], "Before update.")
    source.write_text("after", encoding="utf-8")

    def fail_trace(*_: object, **__: object) -> object:
        raise HanCodeError(_error("trace_write_error"))

    monkeypatch.setattr(checkpoints, "append_trace", fail_trace)

    with pytest.raises(HanCodeError) as error:
        commit_checkpoint(task_root, created.checkpoint_id)

    assert error.value.structured_error.error_code == "checkpoint_trace_failed"
    payload = json.loads((task_root / "checkpoints" / "ckpt-001" / "manifest.json").read_text(encoding="utf-8"))
    assert payload["status"] == "pending"
    assert payload["rollback_available"] is False


@pytest.mark.parametrize(
    "damage",
    ["missing_snapshot", "escaped_snapshot", "tampered_snapshot", "wrong_before_hash"],
)
def test_commit_checkpoint_rejects_unrecoverable_before_snapshot(
    tmp_path: Path, damage: str
) -> None:
    task_root = _code_task(tmp_path)
    (tmp_path / "src").mkdir()
    source = tmp_path / "src" / "main.py"
    source.write_text("before", encoding="utf-8")
    created = create_checkpoint(task_root, [source], "Before update.")
    manifest_path = task_root / "checkpoints" / created.checkpoint_id / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    snapshot_path = task_root / "checkpoints" / created.checkpoint_id / payload["files"][0]["before_snapshot"]
    if damage == "missing_snapshot":
        snapshot_path.unlink()
    elif damage == "escaped_snapshot":
        payload["files"][0]["before_snapshot"] = "../trace.jsonl"
    elif damage == "tampered_snapshot":
        snapshot_path.write_text("tampered", encoding="utf-8")
    else:
        payload["files"][0]["before_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    source.write_text("after", encoding="utf-8")

    with pytest.raises(HanCodeError) as error:
        commit_checkpoint(task_root, created.checkpoint_id)

    assert error.value.structured_error.error_code == "checkpoint_manifest_invalid"
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["status"] == "pending"


def test_commit_checkpoint_rejects_checkpoint_directory_symlink_outside_task(
    tmp_path: Path
) -> None:
    task_root = _code_task(tmp_path)
    (tmp_path / "src").mkdir()
    source = tmp_path / "src" / "main.py"
    source.write_text("before", encoding="utf-8")
    created = create_checkpoint(task_root, [source], "Before update.")
    source.write_text("after", encoding="utf-8")
    checkpoint_dir = task_root / "checkpoints" / created.checkpoint_id
    external_checkpoint = tmp_path / "external-checkpoint"
    checkpoint_dir.rename(external_checkpoint)
    try:
        checkpoint_dir.symlink_to(external_checkpoint, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Windows does not permit symlink creation: {exc}")

    with pytest.raises(HanCodeError) as error:
        commit_checkpoint(task_root, created.checkpoint_id)

    assert error.value.structured_error.error_code == "invalid_checkpoint_task_root"
    assert json.loads((external_checkpoint / "manifest.json").read_text(encoding="utf-8"))["status"] == "pending"


@pytest.mark.parametrize("link_name", ["files", "manifest.json"])
def test_commit_checkpoint_rejects_external_checkpoint_contents_symlink(
    tmp_path: Path, link_name: str
) -> None:
    task_root = _code_task(tmp_path)
    (tmp_path / "src").mkdir()
    source = tmp_path / "src" / "main.py"
    source.write_text("before", encoding="utf-8")
    created = create_checkpoint(task_root, [source], "Before update.")
    source.write_text("after", encoding="utf-8")
    checkpoint_dir = task_root / "checkpoints" / created.checkpoint_id
    linked_path = checkpoint_dir / link_name
    external_path = tmp_path / f"external-{link_name.replace('.', '-') }"
    linked_path.rename(external_path)
    try:
        linked_path.symlink_to(external_path, target_is_directory=link_name == "files")
    except OSError as exc:
        pytest.skip(f"Windows does not permit symlink creation: {exc}")

    with pytest.raises(HanCodeError) as error:
        commit_checkpoint(task_root, created.checkpoint_id)

    assert error.value.structured_error.error_code == "checkpoint_manifest_invalid"


def test_commit_checkpoint_rejects_committed_manifest_with_invalid_after_hash(tmp_path: Path) -> None:
    task_root = _code_task(tmp_path)
    (tmp_path / "src").mkdir()
    source = tmp_path / "src" / "main.py"
    source.write_text("before", encoding="utf-8")
    created = create_checkpoint(task_root, [source], "Before update.")
    source.write_text("after", encoding="utf-8")
    commit_checkpoint(task_root, created.checkpoint_id)
    manifest_path = task_root / "checkpoints" / created.checkpoint_id / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["files"][0]["after_sha256"] = "not-a-sha256"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(HanCodeError) as error:
        commit_checkpoint(task_root, created.checkpoint_id)

    assert error.value.structured_error.error_code == "checkpoint_manifest_invalid"


def test_create_checkpoint_rejects_external_temporary_checkpoint_symlink(tmp_path: Path) -> None:
    task_root = _code_task(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("before", encoding="utf-8")
    temporary_checkpoint = task_root / "checkpoints" / ".ckpt-001.tmp"
    external_directory = tmp_path / "external-temporary-checkpoint"
    external_directory.mkdir()
    sentinel = external_directory / "sentinel.txt"
    sentinel.write_text("do not remove", encoding="utf-8")
    try:
        temporary_checkpoint.symlink_to(external_directory, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Windows does not permit symlink creation: {exc}")

    with pytest.raises(HanCodeError) as error:
        create_checkpoint(task_root, [Path("src/main.py")], "Before update.")

    assert error.value.structured_error.error_code == "invalid_checkpoint_task_root"
    assert sentinel.read_text(encoding="utf-8") == "do not remove"


@pytest.mark.parametrize(
    ("checkpoint_id", "error_code"),
    [("ckpt-999", "checkpoint_not_found"), ("ckpt-invalid", "checkpoint_not_found")],
)
def test_commit_checkpoint_rejects_missing_checkpoint(
    tmp_path: Path, checkpoint_id: str, error_code: str
) -> None:
    task_root = _code_task(tmp_path)

    with pytest.raises(HanCodeError) as error:
        commit_checkpoint(task_root, checkpoint_id)

    assert error.value.structured_error.error_code == error_code


def test_commit_checkpoint_rejects_already_committed_manifest(tmp_path: Path) -> None:
    task_root = _code_task(tmp_path)
    (tmp_path / "src").mkdir()
    source = tmp_path / "src" / "main.py"
    source.write_text("before", encoding="utf-8")
    created = create_checkpoint(task_root, [source], "Before update.", created_at=_CREATED_AT)
    source.write_text("after", encoding="utf-8")
    commit_checkpoint(task_root, created.checkpoint_id)

    with pytest.raises(HanCodeError) as error:
        commit_checkpoint(task_root, created.checkpoint_id)

    assert error.value.structured_error.error_code == "checkpoint_not_pending"


@pytest.mark.parametrize(
    ("checkpoint_id", "manifest_change", "error_code"),
    [
        ("../outside", None, "checkpoint_not_found"),
        ("ckpt-001", ("checkpoint_id", "ckpt-999"), "checkpoint_manifest_invalid"),
        ("ckpt-001", ("project_id", "other-project"), "checkpoint_manifest_invalid"),
        ("ckpt-001", ("schema_version", 2), "checkpoint_manifest_invalid"),
        ("ckpt-001", ("files.0.path", ".env"), "checkpoint_path_not_source"),
        ("ckpt-001", ("files.0.before_snapshot", None), "checkpoint_manifest_invalid"),
    ],
)
def test_commit_checkpoint_rejects_untrusted_manifest_data(
    tmp_path: Path,
    checkpoint_id: str,
    manifest_change: tuple[str, object] | None,
    error_code: str,
) -> None:
    task_root = _code_task(tmp_path)
    (tmp_path / "src").mkdir()
    source = tmp_path / "src" / "main.py"
    source.write_text("before", encoding="utf-8")
    created = create_checkpoint(task_root, [source], "Before update.")
    source.write_text("after", encoding="utf-8")
    if manifest_change is not None:
        manifest_path = task_root / "checkpoints" / created.checkpoint_id / "manifest.json"
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        key, value = manifest_change
        if key.startswith("files.0."):
            payload["files"][0][key.removeprefix("files.0.")] = value
        else:
            payload[key] = value
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(HanCodeError) as error:
        commit_checkpoint(task_root, checkpoint_id)

    assert error.value.structured_error.error_code == error_code


def test_commit_checkpoint_preserves_pending_manifest_when_target_is_missing(tmp_path: Path) -> None:
    task_root = _code_task(tmp_path)
    (tmp_path / "src").mkdir()
    source = tmp_path / "src" / "main.py"
    source.write_text("before", encoding="utf-8")
    created = create_checkpoint(task_root, [source], "Before update.", created_at=_CREATED_AT)
    source.unlink()

    with pytest.raises(HanCodeError) as error:
        commit_checkpoint(task_root, created.checkpoint_id)

    assert error.value.structured_error.error_code == "checkpoint_target_missing"
    payload = json.loads((task_root / "checkpoints" / "ckpt-001" / "manifest.json").read_text(encoding="utf-8"))
    assert payload["status"] == "pending"


def _code_task(tmp_path: Path, *, phase: Phase = Phase.CODE) -> Path:
    init_project_workspace(tmp_path, "project-001", "SE", "Harness")
    task_root = init_task_workspace(tmp_path, "task-001")
    save_state(task_root, replace(load_state(task_root), current_phase=phase))
    return task_root


def _error(error_code: str) -> StructuredError:
    return StructuredError(
        error_code=error_code,
        message="simulated failure",
        phase="code",
        denied_rule="simulated",
        suggested_fix="retry",
    )
