from __future__ import annotations

from dataclasses import replace

from hancode.app.task_models import TaskSummary
from hancode.core.models import Phase, TaskStatus
from hancode.core.router import select_next_phase
from hancode.core.state import TaskState


def test_paused_task_is_routable_and_resumable() -> None:
    paused = replace(_state(), status=TaskStatus.PAUSED)

    routing = select_next_phase(paused)
    summary = TaskSummary.from_state(paused)

    assert routing.blocked is True
    assert routing.reason == "task_paused"
    assert summary.resumable is True
    assert summary.to_dict()["status"] == "paused"


def _state() -> TaskState:
    return TaskState(
        schema_version=1,
        task_id="task-001",
        goal="Implement pause.",
        status=TaskStatus.RUNNING,
        current_phase=Phase.CODE,
        files_changed=(),
        latest_checkpoint=None,
        checkpoint_seq=0,
        tests_run=(),
        latest_test_status="none",
        test_status_consumed=False,
        retry_budget_remaining=2,
        inconsistent=False,
        source_edits_this_phase=0,
        rollback_required=False,
        rollback_done=False,
        phase_completed={phase.value: phase is not Phase.CODE for phase in Phase},
        artifacts={
            "SPEC.md": True,
            "PLAN.md": True,
            "TEST_REPORT.md": False,
            "REVIEW.md": False,
            "KNOWLEDGE.md": False,
            "DELIVERABLES.md": False,
        },
    )
