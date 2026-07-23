from __future__ import annotations

from dataclasses import dataclass

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


@dataclass(frozen=True, slots=True)
class PhaseRequirement:
    requirement_id: str
    description: str
    satisfied: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.requirement_id,
            "description": self.description,
            "satisfied": self.satisfied,
        }


@dataclass(frozen=True, slots=True)
class PhaseGate:
    phase: Phase
    requirements: tuple[PhaseRequirement, ...]

    @property
    def can_finish(self) -> bool:
        return all(item.satisfied for item in self.requirements)

    def to_dict(self) -> dict[str, object]:
        return {
            "phase": self.phase.value,
            "can_finish": self.can_finish,
            "requirements": [
                requirement.to_dict() for requirement in self.requirements
            ],
        }


def build_phase_gate(phase: Phase, state: TaskState) -> PhaseGate:
    if phase is Phase.SPEC:
        requirements: tuple[PhaseRequirement, ...] = (
            PhaseRequirement(
                requirement_id="spec_artifact_required",
                description="SPEC.md must exist.",
                satisfied=state.artifacts["SPEC.md"],
            ),
        )
    elif phase is Phase.PLAN:
        requirements = (
            PhaseRequirement(
                requirement_id="plan_artifact_required",
                description="PLAN.md must exist.",
                satisfied=state.artifacts["PLAN.md"],
            ),
        )
    elif phase is Phase.CODE:
        requirements = (
            PhaseRequirement(
                requirement_id="source_change_required",
                description="At least one allowed source change is required.",
                satisfied=state.source_edits_this_phase > 0,
            ),
        )
    elif phase is Phase.TEST:
        requirements = (
            PhaseRequirement(
                requirement_id="test_execution_required",
                description="The configured tests must be executed.",
                satisfied=state.latest_test_status != "none",
            ),
        )
    elif phase is Phase.REVIEW:
        requirements = (
            PhaseRequirement(
                requirement_id="review_artifact_required",
                description="REVIEW.md must exist.",
                satisfied=state.artifacts["REVIEW.md"],
            ),
            PhaseRequirement(
                requirement_id="rollback_completed_if_required",
                description="Required rollback must be completed.",
                satisfied=(not state.rollback_required or state.rollback_done),
            ),
        )
    else:
        requirements = (
            PhaseRequirement(
                requirement_id="knowledge_artifact_required",
                description="KNOWLEDGE.md must exist.",
                satisfied=state.artifacts["KNOWLEDGE.md"],
            ),
            PhaseRequirement(
                requirement_id="delivery_evidence_required",
                description=(
                    "DELIVERABLES.md must exist or the latest tests must pass."
                ),
                satisfied=(
                    state.artifacts["DELIVERABLES.md"]
                    or state.latest_test_status == "passed"
                ),
            ),
        )

    return PhaseGate(phase=phase, requirements=requirements)
