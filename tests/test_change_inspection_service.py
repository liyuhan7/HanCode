"""Tests for app/change_inspection_service.py — S4-R1."""

from __future__ import annotations

from pathlib import Path

import pytest

from hancode.app.change_inspection_service import ChangeInspectionService
from hancode.core.change_models import DiffScope, TaskDiff
from hancode.storage.workspace import init_project_workspace, init_task_workspace


class TestChangeInspectionService:
    def test_get_diff_returns_task_diff(self, tmp_path: Path) -> None:
        project_root = tmp_path / "proj"
        project_root.mkdir()
        init_project_workspace(project_root, "proj-001", "HanCode", "Test")
        init_task_workspace(project_root, "task-001")

        svc = ChangeInspectionService()
        result = svc.get_diff(project_root, "task-001")

        assert isinstance(result, TaskDiff)
        assert result.task_id == "task-001"
        assert result.scope is DiffScope.TASK

    def test_get_diff_with_scope(self, tmp_path: Path) -> None:
        project_root = tmp_path / "proj"
        project_root.mkdir()
        init_project_workspace(project_root, "proj-001", "HanCode", "Test")
        init_task_workspace(project_root, "task-001")

        svc = ChangeInspectionService()
        result = svc.get_diff(project_root, "task-001", scope=DiffScope.LATEST)

        assert result.scope is DiffScope.LATEST

    def test_get_diff_raises_for_nonexistent_task(self, tmp_path: Path) -> None:
        project_root = tmp_path / "proj"
        project_root.mkdir()
        init_project_workspace(project_root, "proj-001", "HanCode", "Test")

        svc = ChangeInspectionService()
        with pytest.raises(Exception):
            svc.get_diff(project_root, "task-999")
