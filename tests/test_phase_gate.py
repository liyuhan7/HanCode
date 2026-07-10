from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from hancode.models import Phase, TaskStatus
from hancode.phases import can_write_artifact, can_write_source
from hancode.state import TaskState, load_state
from hancode.workspace import init_project_workspace, init_task_workspace


@pytest.mark.parametrize(
    ("phase", "allowed_artifacts"),
    [
        (Phase.SPEC, {"SPEC.md"}),
        (Phase.PLAN, {"PLAN.md"}),
        (Phase.CODE, set()),
        (Phase.TEST, {"TEST_REPORT.md"}),
        (Phase.REVIEW, {"REVIEW.md"}),
        (Phase.DELIVER, {"KNOWLEDGE.md", "DELIVERABLES.md"}),
    ],
)
def test_phase_artifact_allowlist_is_exact(
    phase: Phase, allowed_artifacts: set[str]
) -> None:
    artifact_names = {
        "SPEC.md",
        "PLAN.md",
        "TEST_REPORT.md",
        "REVIEW.md",
        "KNOWLEDGE.md",
        "DELIVERABLES.md",
    }

    for artifact_name in artifact_names:
        assert can_write_artifact(phase, artifact_name) is (artifact_name in allowed_artifacts)


def test_spec_phase_rejects_source_write(tmp_path: Path) -> None:
    assert can_write_source(Phase.SPEC, _state_for_phase(tmp_path, Phase.SPEC)) is False


def test_plan_phase_rejects_source_write(tmp_path: Path) -> None:
    assert can_write_source(Phase.PLAN, _state_for_phase(tmp_path, Phase.PLAN)) is False


def test_code_phase_allows_source_write_when_prerequisites_ready(tmp_path: Path) -> None:
    assert can_write_source(Phase.CODE, _state_for_phase(tmp_path, Phase.CODE)) is True


def test_test_phase_only_writes_test_report(tmp_path: Path) -> None:
    state = _state_for_phase(tmp_path, Phase.TEST)

    assert can_write_artifact(Phase.TEST, "TEST_REPORT.md") is True
    assert can_write_source(Phase.TEST, state) is False


def test_review_phase_only_writes_review(tmp_path: Path) -> None:
    state = _state_for_phase(tmp_path, Phase.REVIEW)

    assert can_write_artifact(Phase.REVIEW, "REVIEW.md") is True
    assert can_write_source(Phase.REVIEW, state) is False


def test_deliver_phase_rejects_source_write(tmp_path: Path) -> None:
    assert can_write_source(Phase.DELIVER, _state_for_phase(tmp_path, Phase.DELIVER)) is False


def test_code_phase_rejects_source_write_without_spec(tmp_path: Path) -> None:
    state = _state_for_phase(tmp_path, Phase.CODE)
    artifacts = dict(state.artifacts)
    artifacts["SPEC.md"] = False

    assert can_write_source(Phase.CODE, replace(state, artifacts=artifacts)) is False


def test_code_phase_rejects_source_write_without_plan(tmp_path: Path) -> None:
    state = _state_for_phase(tmp_path, Phase.CODE)
    artifacts = dict(state.artifacts)
    artifacts["PLAN.md"] = False

    assert can_write_source(Phase.CODE, replace(state, artifacts=artifacts)) is False


def test_inconsistent_state_rejects_source_write(tmp_path: Path) -> None:
    state = _state_for_phase(tmp_path, Phase.CODE)

    assert can_write_source(Phase.CODE, replace(state, inconsistent=True)) is False


def test_inconsistent_status_rejects_source_write(tmp_path: Path) -> None:
    state = _state_for_phase(tmp_path, Phase.CODE)

    assert (
        can_write_source(
            Phase.CODE,
            replace(state, status=TaskStatus.INCONSISTENT),
        )
        is False
    )


def test_phase_argument_must_match_state_current_phase(tmp_path: Path) -> None:
    state = _state_for_phase(tmp_path, Phase.CODE)

    assert can_write_source(Phase.PLAN, state) is False


def test_unknown_phase_and_artifact_are_rejected(tmp_path: Path) -> None:
    state = _state_for_phase(tmp_path, Phase.CODE)

    assert can_write_artifact("code", "SPEC.md") is False  # type: ignore[arg-type]
    assert can_write_artifact(Phase.SPEC, "spec/SPEC.md") is False
    assert can_write_source("code", state) is False  # type: ignore[arg-type]


def _state_for_phase(project_root: Path, phase: Phase) -> TaskState:
    init_project_workspace(
        project_root,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )
    task_root = init_task_workspace(project_root, "task-001")
    state = load_state(task_root)
    artifacts = dict(state.artifacts)
    artifacts.update({"SPEC.md": True, "PLAN.md": True})
    return replace(state, current_phase=phase, artifacts=artifacts)
