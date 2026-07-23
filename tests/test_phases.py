from __future__ import annotations

from hancode.core.models import Phase, TaskStatus
from hancode.core.phases import build_phase_gate
from hancode.core.state import TaskState


def _state(
    phase: Phase,
    *,
    artifacts: dict[str, bool] | None = None,
    source_edits_this_phase: int = 0,
    latest_test_status: str = "none",
    rollback_required: bool = False,
    rollback_done: bool = False,
) -> TaskState:
    values = {
        "SPEC.md": True,
        "PLAN.md": True,
        "TEST_REPORT.md": False,
        "REVIEW.md": False,
        "KNOWLEDGE.md": False,
        "DELIVERABLES.md": False,
    }
    if artifacts is not None:
        values.update(artifacts)
    return TaskState(
        schema_version=1,
        task_id="task-001",
        goal="Implement gate.",
        status=TaskStatus.CREATED,
        current_phase=phase,
        files_changed=(),
        latest_checkpoint=None,
        checkpoint_seq=0,
        tests_run=(),
        latest_test_status=latest_test_status,
        test_status_consumed=False,
        retry_budget_remaining=2,
        inconsistent=False,
        source_edits_this_phase=source_edits_this_phase,
        rollback_required=rollback_required,
        rollback_done=rollback_done,
        phase_completed={item.value: False for item in Phase},
        artifacts=values,
    )


def test_spec_gate_requires_spec_artifact() -> None:
    gate = build_phase_gate(Phase.SPEC, _state(Phase.SPEC, artifacts={"SPEC.md": False}))

    assert gate.can_finish is False
    assert gate.to_dict() == {
        "phase": "spec",
        "can_finish": False,
        "requirements": [
            {
                "id": "spec_artifact_required",
                "description": "SPEC.md must exist.",
                "satisfied": False,
            }
        ],
    }


def test_plan_gate_requires_plan_artifact() -> None:
    gate = build_phase_gate(Phase.PLAN, _state(Phase.PLAN, artifacts={"PLAN.md": False}))

    assert gate.can_finish is False
    assert gate.to_dict() == {
        "phase": "plan",
        "can_finish": False,
        "requirements": [
            {
                "id": "plan_artifact_required",
                "description": "PLAN.md must exist.",
                "satisfied": False,
            }
        ],
    }


def test_code_gate_requires_source_edit() -> None:
    gate = build_phase_gate(Phase.CODE, _state(Phase.CODE))

    assert gate.can_finish is False
    assert gate.to_dict() == {
        "phase": "code",
        "can_finish": False,
        "requirements": [
            {
                "id": "source_change_required",
                "description": (
                    "At least one allowed source change is required."
                ),
                "satisfied": False,
            }
        ],
    }


def test_test_gate_requires_test_execution() -> None:
    gate = build_phase_gate(Phase.TEST, _state(Phase.TEST))

    assert gate.can_finish is False
    assert gate.to_dict() == {
        "phase": "test",
        "can_finish": False,
        "requirements": [
            {
                "id": "test_execution_required",
                "description": "The configured tests must be executed.",
                "satisfied": False,
            }
        ],
    }


def test_review_gate_requires_review_and_completed_rollback() -> None:
    gate = build_phase_gate(
        Phase.REVIEW,
        _state(Phase.REVIEW, rollback_required=True, rollback_done=False),
    )

    assert gate.can_finish is False
    descriptions = [r.description for r in gate.requirements]
    assert "REVIEW.md must exist." in descriptions
    assert "Required rollback must be completed." in descriptions


def test_deliver_gate_requires_knowledge_and_delivery_evidence() -> None:
    gate = build_phase_gate(Phase.DELIVER, _state(Phase.DELIVER))

    assert gate.can_finish is False
    assert gate.to_dict() == {
        "phase": "deliver",
        "can_finish": False,
        "requirements": [
            {
                "id": "knowledge_artifact_required",
                "description": "KNOWLEDGE.md must exist.",
                "satisfied": False,
            },
            {
                "id": "delivery_evidence_required",
                "description": (
                    "DELIVERABLES.md must exist or the latest tests must pass."
                ),
                "satisfied": False,
            },
        ],
    }


def test_phase_gate_serialization_is_deterministic() -> None:
    state = _state(Phase.CODE, source_edits_this_phase=1)

    gate_a = build_phase_gate(Phase.CODE, state)
    gate_b = build_phase_gate(Phase.CODE, state)

    assert gate_a.can_finish is True
    assert gate_a.to_dict() == gate_b.to_dict()
    assert gate_a.to_dict() == {
        "phase": "code",
        "can_finish": True,
        "requirements": [
            {
                "id": "source_change_required",
                "description": (
                    "At least one allowed source change is required."
                ),
                "satisfied": True,
            }
        ],
    }
