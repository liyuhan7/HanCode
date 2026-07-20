from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from hancode.core.errors import HanCodeError
from hancode.core.interactions import InteractionRecord, InteractionStatus
from hancode.core.models import Phase, TaskStatus
from hancode.core.state import TaskState, load_state, reconcile_state, save_state
from hancode.storage.workspace import init_project_workspace, init_task_workspace


def test_state_json_is_single_machine_source(tmp_path: Path) -> None:
    task_root = _init_task(tmp_path)
    (task_root / "SPEC.md").write_text("# Manually created spec\n", encoding="utf-8")

    state = load_state(task_root)

    assert isinstance(state, TaskState)
    assert state.status is TaskStatus.CREATED
    assert state.current_phase is Phase.SPEC
    assert state.artifacts["SPEC.md"] is False
    assert state.files_changed == ()


def test_state_parse_error_blocks_task(tmp_path: Path) -> None:
    task_root = _init_task(tmp_path)
    (task_root / "state.json").write_text('{"secret": "do-not-leak"', encoding="utf-8")

    with pytest.raises(HanCodeError) as exc_info:
        load_state(task_root)

    assert exc_info.value.to_dict() == {
        "error_code": "state_parse_error",
        "message": "Task state file is invalid.",
        "phase": "spec",
        "denied_rule": "valid_task_state_required",
        "suggested_fix": "Repair state.json before continuing the task.",
    }
    assert "do-not-leak" not in str(exc_info.value)


def test_reconcile_detects_artifact_drift_without_auto_fix(tmp_path: Path) -> None:
    task_root = _init_task(tmp_path)
    state_file = task_root / "state.json"
    original_state_json = state_file.read_text(encoding="utf-8")
    (task_root / "SPEC.md").write_text("# Manually created spec\n", encoding="utf-8")

    reconciled = reconcile_state(task_root, load_state(task_root))

    assert reconciled.status is TaskStatus.INCONSISTENT
    assert reconciled.inconsistent is True
    assert reconciled.artifacts["SPEC.md"] is False
    assert state_file.read_text(encoding="utf-8") == original_state_json


def test_reconcile_detects_missing_expected_artifact(tmp_path: Path) -> None:
    task_root = _init_task(tmp_path)
    state = load_state(task_root)
    artifacts = dict(state.artifacts)
    artifacts["SPEC.md"] = True

    reconciled = reconcile_state(task_root, replace(state, artifacts=artifacts))

    assert reconciled.status is TaskStatus.INCONSISTENT
    assert reconciled.inconsistent is True
    assert reconciled.artifacts["SPEC.md"] is True


def test_reconcile_does_not_clear_existing_inconsistent_state(tmp_path: Path) -> None:
    task_root = _init_task(tmp_path)
    consistent = load_state(task_root)
    assert reconcile_state(task_root, consistent) is consistent

    inconsistent = replace(
        consistent,
        status=TaskStatus.INCONSISTENT,
        inconsistent=True,
    )
    assert reconcile_state(task_root, inconsistent) is inconsistent


@pytest.mark.parametrize("status", list(TaskStatus))
def test_state_save_preserves_allowed_status_values(
    tmp_path: Path, status: TaskStatus
) -> None:
    task_root = _init_task(tmp_path)

    state = load_state(task_root)
    if status is TaskStatus.WAITING_INPUT:
        interaction = InteractionRecord(
            interaction_id="ask-000001",
            phase=Phase.SPEC,
            question="Question?",
            answer=None,
            status=InteractionStatus.WAITING,
        )
        state = replace(
            state,
            status=TaskStatus.WAITING_INPUT,
            interaction_seq=1,
            interactions=(interaction,),
            pending_interaction_id=interaction.interaction_id,
        )
    save_state(task_root, replace(state, status=status))

    persisted = json.loads((task_root / "state.json").read_text(encoding="utf-8"))
    assert persisted["status"] == status.value
    assert load_state(task_root).status is status


def test_files_changed_updated_only_by_code_write(tmp_path: Path) -> None:
    task_root = _init_task(tmp_path)

    with pytest.raises(HanCodeError) as spec_error:
        save_state(
            task_root,
            replace(load_state(task_root), files_changed=("src/main.py",)),
        )

    assert spec_error.value.to_dict() == {
        "error_code": "files_changed_update_outside_code",
        "message": "files_changed can only be updated from the code phase.",
        "phase": "spec",
        "denied_rule": "files_changed_code_write_only",
        "suggested_fix": (
            "Update files_changed only after a successful code-phase "
            "edit_file or write_file."
        ),
    }

    save_state(task_root, replace(load_state(task_root), current_phase=Phase.CODE))
    save_state(
        task_root,
        replace(
            load_state(task_root),
            current_phase=Phase.TEST,
            files_changed=("src/main.py",),
        ),
    )
    test_state = load_state(task_root)
    assert test_state.files_changed == ("src/main.py",)

    with pytest.raises(HanCodeError) as test_error:
        save_state(
            task_root,
            replace(
                test_state,
                files_changed=("src/main.py", "tests/test_main.py"),
            ),
        )

    assert test_error.value.to_dict()["phase"] == "test"
    assert load_state(task_root).files_changed == ("src/main.py",)


@pytest.mark.parametrize("target_phase", [Phase.REVIEW, Phase.DELIVER])
def test_files_changed_cannot_change_when_leaving_code_for_later_phase(
    tmp_path: Path, target_phase: Phase
) -> None:
    task_root = _init_task(tmp_path)
    save_state(task_root, replace(load_state(task_root), current_phase=Phase.CODE))
    code_state = load_state(task_root)

    with pytest.raises(HanCodeError) as exc_info:
        save_state(
            task_root,
            replace(
                code_state,
                current_phase=target_phase,
                files_changed=("src/main.py",),
            ),
        )

    assert exc_info.value.to_dict()["error_code"] == "files_changed_update_outside_code"
    assert load_state(task_root).current_phase is Phase.CODE
    assert load_state(task_root).files_changed == ()


def test_state_save_rejects_task_identity_mismatch_without_overwrite(
    tmp_path: Path,
) -> None:
    task_root = _init_task(tmp_path)
    original_state_json = (task_root / "state.json").read_text(encoding="utf-8")
    state = load_state(task_root)

    with pytest.raises(HanCodeError) as exc_info:
        save_state(task_root, replace(state, task_id="task-002"))

    assert exc_info.value.to_dict() == {
        "error_code": "state_identity_mismatch",
        "message": "Task state identity does not match the persisted task.",
        "phase": "spec",
        "denied_rule": "state_task_identity_match_required",
        "suggested_fix": "Reload the persisted task state before saving changes.",
    }
    assert (task_root / "state.json").read_text(encoding="utf-8") == original_state_json


def test_task_state_nested_mappings_are_immutable(tmp_path: Path) -> None:
    task_root = _init_task(tmp_path)
    state = load_state(task_root)

    with pytest.raises(TypeError):
        state.phase_completed["spec"] = True  # type: ignore[index]
    with pytest.raises(TypeError):
        state.artifacts["SPEC.md"] = True  # type: ignore[index]

    save_state(task_root, state)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", 2),
        ("latest_test_status", "skipped"),
        ("artifacts", {"SPEC.md": False}),
        ("phase_completed", {"spec": False}),
        ("unexpected_field", True),
    ],
    ids=[
        "unsupported_version",
        "invalid_test_status",
        "incomplete_artifacts",
        "incomplete_phases",
        "unknown_field",
    ],
)
def test_state_schema_rejects_invalid_or_unknown_values(
    tmp_path: Path, field: str, value: object
) -> None:
    task_root = _init_task(tmp_path)
    state_file = task_root / "state.json"
    state_data = json.loads(state_file.read_text(encoding="utf-8"))
    state_data[field] = value
    state_file.write_text(json.dumps(state_data), encoding="utf-8")

    with pytest.raises(HanCodeError) as exc_info:
        load_state(task_root)

    assert exc_info.value.to_dict()["error_code"] == "state_parse_error"


def test_task_state_rejects_invalid_direct_values(tmp_path: Path) -> None:
    state = load_state(_init_task(tmp_path))

    with pytest.raises(ValueError, match="schema_version"):
        replace(state, schema_version=True)

    with pytest.raises(ValueError, match="latest_test_status"):
        replace(state, latest_test_status="skipped")


def test_state_save_is_atomic_when_replace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_root = _init_task(tmp_path)
    state_file = task_root / "state.json"
    original_state_json = state_file.read_text(encoding="utf-8")

    def fail_replace(source: Path, target: Path) -> Path:
        raise OSError("write denied: do-not-leak")

    monkeypatch.setattr(Path, "replace", fail_replace)

    with pytest.raises(HanCodeError) as exc_info:
        save_state(
            task_root,
            replace(
                load_state(task_root),
                status=TaskStatus.RUNNING,
                current_phase=Phase.CODE,
            ),
        )

    assert exc_info.value.to_dict() == {
        "error_code": "state_write_error",
        "message": "Task state file could not be saved.",
        "phase": "spec",
        "denied_rule": "state_persistence_required",
        "suggested_fix": "Restore task workspace write access before continuing.",
    }
    assert "do-not-leak" not in str(exc_info.value)
    assert state_file.read_text(encoding="utf-8") == original_state_json
    assert not (task_root / "state.json.tmp").exists()


def test_load_state_fails_closed_when_junction_probe_is_indeterminate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_root = _init_task(tmp_path)
    monkeypatch.setattr(
        Path,
        "is_junction",
        lambda _path: (_ for _ in ()).throw(AttributeError("st_reparse_tag")),
        raising=False,
    )

    with pytest.raises(HanCodeError) as error:
        load_state(task_root)

    assert error.value.to_dict()["error_code"] == "state_parse_error"


def _init_task(project_root: Path) -> Path:
    init_project_workspace(
        project_root,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )
    return init_task_workspace(project_root, "task-001")
