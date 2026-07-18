from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from hancode.errors import HanCodeError
from hancode.state import load_state, save_state
from hancode.workspace import init_project_workspace, init_task_workspace


_ARTIFACTS = (
    "SPEC.md",
    "PLAN.md",
    "TEST_REPORT.md",
    "REVIEW.md",
    "KNOWLEDGE.md",
    "DELIVERABLES.md",
)


def _task_workspace(tmp_path: Path) -> tuple[Path, Path]:
    project_root = tmp_path / "project"
    project_root.mkdir()
    init_project_workspace(project_root, "project-001", "Course", "Assignment")
    task_root = init_task_workspace(project_root, "task-001")
    return project_root, task_root


def _mark_artifacts(task_root: Path, names: tuple[str, ...]) -> None:
    state = load_state(task_root)
    artifacts = dict(state.artifacts)
    for name in names:
        artifacts[name] = True
        (task_root / name).write_text(f"# {name}\n", encoding="utf-8")
    save_state(task_root, replace(state, artifacts=artifacts))


def test_export_copies_only_declared_delivery_artifacts(tmp_path: Path) -> None:
    from hancode.export import export_task_artifacts

    project_root, task_root = _task_workspace(tmp_path)
    _mark_artifacts(task_root, _ARTIFACTS)
    output_dir = tmp_path / "deliverables"

    result = export_task_artifacts(project_root, "task-001", output_dir)

    assert result.to_dict() == {
        "task_id": "task-001",
        "output_dir": str(output_dir.resolve()),
        "artifacts": list(_ARTIFACTS),
    }
    assert sorted(path.name for path in output_dir.iterdir()) == sorted(_ARTIFACTS)
    assert not (output_dir / "state.json").exists()
    assert not (output_dir / "trace.jsonl").exists()


def test_export_rejects_inconsistent_task_state(tmp_path: Path) -> None:
    from hancode.export import export_task_artifacts

    project_root, task_root = _task_workspace(tmp_path)
    state = load_state(task_root)
    artifacts = dict(state.artifacts)
    artifacts["SPEC.md"] = True
    save_state(task_root, replace(state, artifacts=artifacts))

    with pytest.raises(HanCodeError) as error:
        export_task_artifacts(project_root, "task-001", tmp_path / "deliverables")

    assert error.value.structured_error.error_code == "export_state_inconsistent"


def test_export_rejects_existing_output_without_overwriting(tmp_path: Path) -> None:
    from hancode.export import export_task_artifacts

    project_root, task_root = _task_workspace(tmp_path)
    _mark_artifacts(task_root, ("SPEC.md",))
    output_dir = tmp_path / "deliverables"
    output_dir.mkdir()
    sentinel = output_dir / "sentinel.txt"
    sentinel.write_text("keep", encoding="utf-8")

    with pytest.raises(HanCodeError) as error:
        export_task_artifacts(project_root, "task-001", output_dir)

    assert error.value.structured_error.error_code == "export_output_exists"
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_export_rejects_task_path_escape(tmp_path: Path) -> None:
    from hancode.export import export_task_artifacts

    project_root, _ = _task_workspace(tmp_path)

    with pytest.raises(HanCodeError) as error:
        export_task_artifacts(project_root, "../outside", tmp_path / "deliverables")

    assert error.value.structured_error.error_code in {
        "workspace_path_outside_project_root",
        "invalid_task_id",
    }


def test_export_rejects_linked_output_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hancode.export as export_module

    project_root, task_root = _task_workspace(tmp_path)
    _mark_artifacts(task_root, ("SPEC.md",))
    linked_parent = tmp_path / "linked-parent"
    output_dir = linked_parent / "deliverables"

    monkeypatch.setattr(export_module, "_is_link", lambda path: path == linked_parent)

    with pytest.raises(HanCodeError) as error:
        export_module.export_task_artifacts(project_root, "task-001", output_dir)

    assert error.value.structured_error.error_code == "export_output_link_not_allowed"
