from __future__ import annotations

import json
from pathlib import Path

import pytest

from hancode.app.learning_service import LearningService
from hancode.core.errors import HanCodeError
from hancode.storage.export import ExportProfile, export_task_profile
from hancode.storage.workspace import init_project_workspace, init_task_workspace


def _covered_task(tmp_path: Path) -> Path:
    project_root = tmp_path / "project"
    project_root.mkdir()
    init_project_workspace(project_root, "project-001", "Course", "Assignment")
    init_task_workspace(project_root, "task-001")
    service = LearningService()
    service.record_requirements(
        project_root,
        "task-001",
        goal="parser",
        requirements=[
            {
                "source_text": "reject empty",
                "student_understanding": "empty raises",
                "acceptance_evidence": "T-000001",
                "priority": "core",
                "is_core": True,
            }
        ],
    )
    service.record_change(
        project_root,
        "task-001",
        pre_change_checkpoint_id="ckpt-001",
        action_id="evt-000001",
        changed_paths=["src/parser.py"],
        diff_digest="a" * 64,
        reason="add empty-input guard",
        requirement_refs=["R-0001"],
        plan_step_refs=[],
    )
    service.record_test_attempt(
        project_root,
        "task-001",
        command="pytest",
        started_at="2026-08-06T00:01:00Z",
        finished_at="2026-08-06T00:01:01Z",
        exit_code=0,
        status="passed",
        passed_count=7,
        failed_count=0,
        failure_category=None,
        summary="ok",
        output_digest="b" * 64,
        tested_change_ids=["C-0001"],
        requirement_refs=["R-0001"],
    )
    return project_root


def test_learning_export_contains_phase_artifacts_and_manifest(tmp_path: Path) -> None:
    project_root = _covered_task(tmp_path)
    output_dir = tmp_path / "learning-out"

    result = export_task_profile(
        project_root, "task-001", output_dir, ExportProfile.LEARNING
    )

    names = {path.name for path in output_dir.iterdir()}
    assert "SPEC.md" in names
    assert "IMPLEMENTATION.md" in names
    assert "TEST_REPORT.md" in names
    assert "learning-manifest.json" in names
    assert "LEARNING_INDEX.md" in names
    manifest = json.loads((output_dir / "learning-manifest.json").read_text("utf-8"))
    assert manifest["profile"] == "learning"
    assert "learning_contract_status" in manifest
    assert result.profile == "learning"


def test_submission_export_excludes_internal_runtime_files(tmp_path: Path) -> None:
    project_root = _covered_task(tmp_path)
    # DELIVERABLES.md is needed for a submission; generate it via a minimal write.
    task_root = project_root / ".hancode" / "tasks" / "task-001"
    from dataclasses import replace

    from hancode.core.state import load_state, save_state

    (task_root / "DELIVERABLES.md").write_text("# 交付清单\n", encoding="utf-8")
    state = load_state(task_root)
    artifacts = dict(state.artifacts)
    artifacts["DELIVERABLES.md"] = True
    save_state(task_root, replace(state, artifacts=artifacts))

    output_dir = tmp_path / "submission-out"
    export_task_profile(
        project_root, "task-001", output_dir, ExportProfile.SUBMISSION
    )

    names = {path.name for path in output_dir.iterdir()}
    assert "DELIVERABLES.md" in names
    assert "delivery-manifest.json" in names
    assert "state.json" not in names
    assert "trace.jsonl" not in names
    assert "events.jsonl" not in names
    assert "SPEC.md" not in names  # learning-only artifact


def test_audit_export_includes_evidence_excludes_raw_runtime(tmp_path: Path) -> None:
    project_root = _covered_task(tmp_path)
    output_dir = tmp_path / "audit-out"

    export_task_profile(project_root, "task-001", output_dir, ExportProfile.AUDIT)

    names = {path.name for path in output_dir.iterdir()}
    assert "audit-manifest.json" in names
    assert "evidence.json" in names
    assert "memory" not in names
    assert ".env" not in names


def test_export_profile_rejects_existing_output(tmp_path: Path) -> None:
    project_root = _covered_task(tmp_path)
    output_dir = tmp_path / "learning-out"
    output_dir.mkdir()

    with pytest.raises(HanCodeError):
        export_task_profile(
            project_root, "task-001", output_dir, ExportProfile.LEARNING
        )
