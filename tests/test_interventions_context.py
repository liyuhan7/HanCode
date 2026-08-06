"""Context injection tests for Runtime Steering (S17-R1)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from hancode.core.config import load_config
from hancode.core.errors import HanCodeError
from hancode.core.interventions import (
    InterventionKind,
    InterventionRecord,
    InterventionStatus,
)
from hancode.core.models import Phase
from hancode.core.state import TaskState, load_state
from hancode.runtime.context import ContextBuilder, build_context
from hancode.storage.workspace import init_project_workspace, init_task_workspace


def _workspace(tmp_path: Path) -> tuple[Path, Path]:
    project_root = tmp_path / "project"
    project_root.mkdir()
    init_project_workspace(project_root, "project-001", "SE", "Harness")
    return project_root, init_task_workspace(project_root, "task-001")


def _state(task_root: Path, *, goal: str) -> TaskState:
    return replace(load_state(task_root), goal=goal)


def _record(
    sequence: int,
    *,
    run_id: str = "run-a",
    status: InterventionStatus = InterventionStatus.PENDING,
    content: str = "requirement",
) -> InterventionRecord:
    return InterventionRecord(
        intervention_id=f"iv-{sequence:06d}",
        task_id="task-001",
        run_id=run_id,
        sequence=sequence,
        kind=InterventionKind.STEER,
        status=status,
        content=content,
        submitted_at="2026-01-01T00:00:00+00:00",
        delivered_at=None if status is InterventionStatus.PENDING else "t",
        consumed_at="t" if status is InterventionStatus.CONSUMED else None,
    )


def test_pending_delivered_consumed_all_effective(tmp_path: Path) -> None:
    project_root, task_root = _workspace(tmp_path)
    config = load_config(project_root, "task-001")
    state = _state(task_root, goal="Steer me.")
    records = (
        _record(1, status=InterventionStatus.PENDING, content="pending req"),
        _record(2, status=InterventionStatus.DELIVERED, content="delivered req"),
        _record(3, status=InterventionStatus.CONSUMED, content="consumed req"),
    )

    context = build_context(
        project_root,
        "task-001",
        Phase.SPEC,
        config,
        state=state,
        user_interventions=records,
        intervention_revision=3,
    )

    block = context["user_interventions"]
    assert block["revision"] == 3
    assert [item["sequence"] for item in block["effective"]] == [1, 2, 3]
    # awaiting_acknowledgement excludes the consumed record.
    assert [item["sequence"] for item in block["awaiting_acknowledgement"]] == [1, 2]


def test_context_builder_matches_functional_builder(tmp_path: Path) -> None:
    project_root, task_root = _workspace(tmp_path)
    config = load_config(project_root, "task-001")
    state = _state(task_root, goal="Steer me.")
    records = (_record(1),)

    functional = build_context(
        project_root,
        "task-001",
        Phase.SPEC,
        config,
        state=state,
        user_interventions=records,
        intervention_revision=1,
    )
    adapter = ContextBuilder(project_root, config).build(
        task_id="task-001",
        phase=Phase.SPEC,
        state=state,
        user_interventions=records,
        intervention_revision=1,
    )
    assert functional == adapter


def test_no_interventions_omits_block(tmp_path: Path) -> None:
    project_root, task_root = _workspace(tmp_path)
    config = load_config(project_root, "task-001")
    state = _state(task_root, goal="Steer me.")

    context = build_context(
        project_root, "task-001", Phase.SPEC, config, state=state
    )

    assert "user_interventions" not in context


def test_steering_not_dropped_when_budget_too_small(tmp_path: Path) -> None:
    project_root, task_root = _workspace(tmp_path)
    config = load_config(project_root, "task-001")
    tight_config = replace(config, max_context_chars=200)
    state = _state(task_root, goal="Steer me.")
    records = (_record(1, content="an important long steering requirement"),)

    with pytest.raises(HanCodeError) as exc:
        build_context(
            project_root,
            "task-001",
            Phase.SPEC,
            tight_config,
            state=state,
            user_interventions=records,
            intervention_revision=1,
        )

    assert (
        exc.value.structured_error.error_code == "intervention_context_budget_exceeded"
    )


def test_steering_content_is_redacted(tmp_path: Path) -> None:
    project_root, task_root = _workspace(tmp_path)
    config = load_config(project_root, "task-001")
    state = _state(task_root, goal="Steer me.")
    records = (_record(1, content="use token=sk-shhh-do-not-leak now"),)

    context = build_context(
        project_root,
        "task-001",
        Phase.SPEC,
        config,
        state=state,
        user_interventions=records,
        intervention_revision=1,
    )

    effective = context["user_interventions"]["effective"]
    assert "sk-shhh-do-not-leak" not in effective[0]["content"]
    assert "[REDACTED]" in effective[0]["content"]
