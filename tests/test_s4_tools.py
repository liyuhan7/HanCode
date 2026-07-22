"""Tests for read_test_report and list_checkpoints tools — S4-R3 + S4-R4."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hancode.storage.workspace import init_project_workspace, init_task_workspace
from hancode.tooling.delivery_tools import read_test_report
from hancode.tooling.checkpoint_tools import list_checkpoints
from hancode.app.checkpoint_inspection_service import CheckpointInspectionService


# ---------------------------------------------------------------------------
# read_test_report tests
# ---------------------------------------------------------------------------

class TestReadTestReport:
    def test_read_test_report_requires_declared_artifact(self, tmp_path: Path) -> None:
        project_root = tmp_path / "proj"
        project_root.mkdir()
        init_project_workspace(project_root, "proj-001", "HanCode", "Test")
        task_root = init_task_workspace(project_root, "task-001")

        result = read_test_report(project_root, task_root)
        assert result.success is False
        assert "not present" in (result.error_summary or "").lower() or "not found" in (result.error_summary or "").lower()

    def test_read_test_report_returns_content(self, tmp_path: Path) -> None:
        project_root = tmp_path / "proj"
        project_root.mkdir()
        init_project_workspace(project_root, "proj-001", "HanCode", "Test")
        task_root = init_task_workspace(project_root, "task-001")

        # Write a test report
        report = "# Test Report\n\n- passed: 5\n- failed: 1\n"
        (task_root / "TEST_REPORT.md").write_text(report, encoding="utf-8")
        # Update state artifacts
        from hancode.core.state import load_state, save_state
        from dataclasses import replace
        state = load_state(task_root)
        state = replace(state, artifacts={**state.artifacts, "TEST_REPORT.md": True})
        save_state(task_root, state)

        result = read_test_report(project_root, task_root)
        assert result.success is True
        assert isinstance(result.output, dict)
        assert result.output["status"] == "failed"

    def test_read_test_report_rejects_link(self, tmp_path: Path) -> None:
        project_root = tmp_path / "proj"
        project_root.mkdir()
        init_project_workspace(project_root, "proj-001", "HanCode", "Test")
        task_root = init_task_workspace(project_root, "task-001")

        report_path = task_root / "TEST_REPORT.md"
        real_path = task_root / "real_report.md"
        real_path.write_text("# test", encoding="utf-8")
        try:
            report_path.symlink_to(real_path)
        except OSError:
            pytest.skip("Symlink not supported")

        result = read_test_report(project_root, task_root)
        assert result.success is False


# ---------------------------------------------------------------------------
# list_checkpoints tests
# ---------------------------------------------------------------------------

class TestListCheckpoints:
    def test_list_checkpoints_returns_empty(self, tmp_path: Path) -> None:
        project_root = tmp_path / "proj"
        project_root.mkdir()
        init_project_workspace(project_root, "proj-001", "HanCode", "Test")
        task_root = init_task_workspace(project_root, "task-001")

        result = list_checkpoints(project_root, task_root)
        assert result.success is True
        assert isinstance(result.output, dict)
        assert result.output["checkpoints"] == []

    def test_list_checkpoints_returns_summaries(self, tmp_path: Path) -> None:
        project_root = tmp_path / "proj"
        project_root.mkdir()
        init_project_workspace(project_root, "proj-001", "HanCode", "Test")
        task_root = init_task_workspace(project_root, "task-001")

        # Create a checkpoint
        from tests.test_checkpoint_query import _write_minimal_manifest, _make_checkpoint_dir
        ckpt_dir = _make_checkpoint_dir(task_root, "ckpt-001")
        _write_minimal_manifest(ckpt_dir, checkpoint_id="ckpt-001", task_id="task-001")

        result = list_checkpoints(project_root, task_root)
        assert result.success is True
        assert len(result.output["checkpoints"]) == 1
        c = result.output["checkpoints"][0]
        assert c["checkpoint_id"] == "ckpt-001"
        assert "files" in c
        # Must not expose snapshot paths
        for f in c["files"]:
            assert "checkpoints" not in f.lower()

    def test_list_checkpoints_hides_snapshot_paths(self, tmp_path: Path) -> None:
        project_root = tmp_path / "proj"
        project_root.mkdir()
        init_project_workspace(project_root, "proj-001", "HanCode", "Test")
        task_root = init_task_workspace(project_root, "task-001")

        from tests.test_checkpoint_query import _write_minimal_manifest, _make_checkpoint_dir
        ckpt_dir = _make_checkpoint_dir(task_root, "ckpt-001")
        _write_minimal_manifest(ckpt_dir, checkpoint_id="ckpt-001", task_id="task-001")

        result = list_checkpoints(project_root, task_root)
        output_str = json.dumps(result.output)
        assert "before_snapshot" not in output_str
        assert "files/001-" not in output_str


class TestCheckpointInspectionService:
    def test_list_returns_summaries(self, tmp_path: Path) -> None:
        project_root = tmp_path / "proj"
        project_root.mkdir()
        init_project_workspace(project_root, "proj-001", "HanCode", "Test")
        task_root = init_task_workspace(project_root, "task-001")

        svc = CheckpointInspectionService()
        result = svc.list_checkpoints(project_root, "task-001")
        assert isinstance(result, tuple)
