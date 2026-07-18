from __future__ import annotations

from hancode.core.models import Phase, TaskStatus
from hancode.core.state import TaskState


_ARTIFACTS_BY_PHASE: dict[Phase, frozenset[str]] = {
    Phase.SPEC: frozenset({"SPEC.md"}),
    Phase.PLAN: frozenset({"PLAN.md"}),
    Phase.CODE: frozenset(),
    Phase.TEST: frozenset({"TEST_REPORT.md"}),
    Phase.REVIEW: frozenset({"REVIEW.md"}),
    Phase.DELIVER: frozenset({"KNOWLEDGE.md", "DELIVERABLES.md"}),
}


def can_write_artifact(phase: Phase, artifact_name: str) -> bool:
    if not isinstance(phase, Phase) or not isinstance(artifact_name, str):
        return False
    return artifact_name in _ARTIFACTS_BY_PHASE[phase]


def can_write_source(phase: Phase, state: TaskState) -> bool:
    if not isinstance(phase, Phase) or not isinstance(state, TaskState):
        return False
    return (
        phase is Phase.CODE
        and state.current_phase is Phase.CODE
        and state.artifacts["SPEC.md"]
        and state.artifacts["PLAN.md"]
        and not state.inconsistent
        and state.status is not TaskStatus.INCONSISTENT
    )
