"""Tests for the Runtime Steering application service (S17 TUI enablement)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from hancode.app.intervention_service import InterventionService
from hancode.core.errors import HanCodeError
from hancode.core.state import load_state, save_state
from hancode.storage.interventions import InterventionStore
from hancode.storage.workspace import (
    init_project_workspace,
    init_task_workspace,
    task_path,
)


def _make_task(tmp_path: Path, *, active_run_id: str | None = "run-a") -> Path:
    init_project_workspace(tmp_path, "project-001", "AI4SE", "Harness")
    init_task_workspace(tmp_path, "task-001", goal="Steer me.")
    root = task_path(tmp_path, "task-001")
    save_state(root, replace(load_state(root), active_run_id=active_run_id))
    return tmp_path


def test_submit_persists_steering_for_active_run(tmp_path: Path) -> None:
    _make_task(tmp_path)
    service = InterventionService()

    result = service.submit(tmp_path, "task-001", "Only touch API validation.")

    assert result.intervention_id == "iv-000001"
    assert result.sequence == 1
    snapshot = InterventionStore(tmp_path).prepare_context("task-001", "run-a")
    assert snapshot.effective_records[0].content == "Only touch API validation."


def test_submit_rejected_without_active_run(tmp_path: Path) -> None:
    _make_task(tmp_path, active_run_id=None)
    service = InterventionService()

    with pytest.raises(HanCodeError) as exc:
        service.submit(tmp_path, "task-001", "Change the plan.")
    assert exc.value.structured_error.error_code == "steering_no_active_run"


def test_submit_rejects_empty_content(tmp_path: Path) -> None:
    _make_task(tmp_path)
    service = InterventionService()

    with pytest.raises(HanCodeError) as exc:
        service.submit(tmp_path, "task-001", "   ")
    assert exc.value.structured_error.error_code == "steering_content_required"


def test_submit_rejects_missing_task(tmp_path: Path) -> None:
    init_project_workspace(tmp_path, "project-001", "AI4SE", "Harness")
    service = InterventionService()

    with pytest.raises(HanCodeError) as exc:
        service.submit(tmp_path, "task-404", "Steer.")
    assert exc.value.structured_error.error_code == "task_not_found"


def test_submit_redacts_secret_content(tmp_path: Path) -> None:
    _make_task(tmp_path)
    service = InterventionService()

    result = service.submit(
        tmp_path, "task-001", "Use API_KEY=sk-supersecretvalue for the call."
    )

    snapshot = InterventionStore(tmp_path).prepare_context("task-001", "run-a")
    content = snapshot.effective_records[0].content
    assert "sk-supersecretvalue" not in content
    assert "[REDACTED]" in content
    assert result.sequence == 1
