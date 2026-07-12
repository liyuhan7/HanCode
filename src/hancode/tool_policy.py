"""Deterministic policy checks before tool dispatch."""

from __future__ import annotations

from dataclasses import dataclass

from hancode.actions import Action, ActionType
from hancode.config import HanCodeConfig
from hancode.models import Phase, TaskStatus
from hancode.path_policy import PathClassifier, PathZone
from hancode.phases import can_write_artifact
from hancode.state import TaskState


_ALLOWED_TOOL_PHASES = {
    "read_file": frozenset(Phase),
    "list_files": frozenset({Phase.SPEC, Phase.PLAN, Phase.CODE, Phase.REVIEW}),
    "search_text": frozenset({Phase.SPEC, Phase.PLAN, Phase.CODE, Phase.REVIEW}),
    "write_file": frozenset(Phase),
    "edit_file": frozenset({Phase.CODE}),
    "run_tests": frozenset({Phase.CODE, Phase.TEST, Phase.REVIEW}),
    "rollback_last_checkpoint": frozenset({Phase.REVIEW}),
}
_WRITE_TOOLS = frozenset({"write_file", "edit_file"})


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """The deterministic outcome of evaluating an action."""

    allowed: bool
    reason: str
    phase: Phase
    requires_checkpoint: bool = False
    denied_rule: str | None = None
    suggested_fix: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "requires_checkpoint": self.requires_checkpoint,
            "error_code": None if self.allowed else "policy_denied",
            "message": self.reason,
            "phase": self.phase.value,
            "denied_rule": self.denied_rule,
            "suggested_fix": self.suggested_fix,
        }


class ToolPolicy:
    """Evaluate actions against phase, path, and task-state constraints."""

    def __init__(self, config: HanCodeConfig) -> None:
        self._path_classifier = PathClassifier(config)

    def evaluate(
        self, *, action: Action, phase: Phase, state: TaskState
    ) -> PolicyDecision:
        if action.phase is not phase:
            return _denied(
                phase,
                "Action phase does not match the current phase.",
                "action_phase_mismatch",
                "Use the current phase in the action.",
            )
        if action.type is ActionType.FINISH_PHASE:
            return self._evaluate_finish_phase(phase, state)
        if action.type in {ActionType.ASK_USER, ActionType.FINAL}:
            return _allowed(phase)
        if action.type is not ActionType.TOOL_CALL or action.tool_name is None:
            return _denied(
                phase,
                "Action is not an executable tool call.",
                "unsupported_action",
                "Use a supported tool call or control action.",
            )

        allowed_phases = _ALLOWED_TOOL_PHASES.get(action.tool_name)
        if allowed_phases is None or phase not in allowed_phases:
            return _denied(
                phase,
                "Tool is not allowed in the current phase.",
                "tool_not_allowed_in_phase",
                "Choose a tool allowed in the current phase.",
            )
        if action.tool_name not in _WRITE_TOOLS:
            return _allowed(phase)
        if action.reason is None or not action.reason.strip():
            return _denied(
                phase,
                "Write actions require a reason.",
                "reason_required_for_write",
                "Provide a non-empty reason for the write action.",
            )

        target = action.args.get("path")
        if not isinstance(target, str) or not target.strip():
            return _denied(
                phase,
                "Write actions require a valid target path.",
                "write_path_required",
                "Provide a non-empty relative path.",
            )
        zone = self._path_classifier.classify(target)
        if zone is PathZone.PROTECTED:
            return _denied(
                phase,
                "Target path is protected.",
                "protected_path",
                "Choose an allowed artifact or source path.",
            )
        if zone is PathZone.OUT_OF_SCOPE:
            return _denied(
                phase,
                "Target path is outside the writable workspace zones.",
                "path_out_of_scope",
                "Use a configured artifact or source path inside the workspace.",
            )
        if zone is PathZone.ARTIFACT:
            if can_write_artifact(phase, _artifact_name(target)):
                return _allowed(phase)
            return _denied(
                phase,
                "Artifact is not writable in the current phase.",
                "artifact_not_allowed_in_phase",
                "Write the artifact in its designated phase.",
            )
        if zone is PathZone.SOURCE:
            return self._evaluate_source_write(phase, state)
        return _denied(
            phase,
            "Target path is not in a writable zone.",
            "path_out_of_scope",
            "Use a configured artifact or source path inside the workspace.",
        )

    @staticmethod
    def _evaluate_source_write(phase: Phase, state: TaskState) -> PolicyDecision:
        if state.inconsistent or state.status is TaskStatus.INCONSISTENT:
            return _denied(
                phase,
                "Source writes require a consistent task state.",
                "state_must_be_consistent",
                "Resolve task-state inconsistencies before modifying source files.",
            )
        if phase is not Phase.CODE or state.current_phase is not Phase.CODE:
            return _denied(
                phase,
                "Source writes are only allowed in the code phase.",
                "source_write_requires_code_phase",
                "Return to the code phase before modifying source files.",
            )
        if not state.artifacts["SPEC.md"]:
            return _denied(
                phase,
                "Source writes require SPEC.md.",
                "spec_required_before_source_write",
                "Generate SPEC.md before modifying source files.",
            )
        if not state.artifacts["PLAN.md"]:
            return _denied(
                phase,
                "Source writes require PLAN.md.",
                "plan_required_before_source_write",
                "Generate PLAN.md before modifying source files.",
            )
        return _allowed(phase, requires_checkpoint=True)

    @staticmethod
    def _evaluate_finish_phase(phase: Phase, state: TaskState) -> PolicyDecision:
        if phase is Phase.SPEC:
            ready = state.artifacts["SPEC.md"]
            rule = "spec_finish_requirements"
            fix = "Generate SPEC.md before finishing the spec phase."
        elif phase is Phase.PLAN:
            ready = state.artifacts["PLAN.md"]
            rule = "plan_finish_requirements"
            fix = "Generate PLAN.md before finishing the plan phase."
        elif phase is Phase.CODE:
            ready = state.source_edits_this_phase > 0
            rule = "code_finish_requirements"
            fix = "Make an allowed source change before finishing the code phase."
        elif phase is Phase.TEST:
            ready = state.latest_test_status != "none"
            rule = "test_finish_requirements"
            fix = "Run the configured tests before finishing the test phase."
        elif phase is Phase.REVIEW:
            ready = state.artifacts["REVIEW.md"] and (
                not state.rollback_required or state.rollback_done
            )
            rule = "review_finish_requirements"
            fix = "Generate REVIEW.md and complete any required rollback."
        else:
            ready = state.artifacts["KNOWLEDGE.md"] and state.artifacts[
                "DELIVERABLES.md"
            ]
            rule = "deliver_finish_requirements"
            fix = "Generate KNOWLEDGE.md and DELIVERABLES.md before finishing."
        if ready:
            return _allowed(phase)
        return _denied(
            phase,
            "Current phase completion requirements are not met.",
            rule,
            fix,
        )


def _artifact_name(target: str) -> str:
    return target.replace("\\", "/").rsplit("/", 1)[-1]


def _allowed(phase: Phase, *, requires_checkpoint: bool = False) -> PolicyDecision:
    return PolicyDecision(
        allowed=True,
        reason="Action is allowed.",
        phase=phase,
        requires_checkpoint=requires_checkpoint,
    )


def _denied(
    phase: Phase, reason: str, denied_rule: str, suggested_fix: str
) -> PolicyDecision:
    return PolicyDecision(
        allowed=False,
        reason=reason,
        phase=phase,
        denied_rule=denied_rule,
        suggested_fix=suggested_fix,
    )
