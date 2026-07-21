"""Approval policy: determines whether a tool action requires human approval.

ApprovalPolicy runs AFTER ToolPolicy, and only receives allowed actions.
It decides whether the allowed action still needs explicit user confirmation
before execution.
"""

from __future__ import annotations

from dataclasses import dataclass

from hancode.core.actions import Action, ActionType
from hancode.core.approvals import ApprovalCategory
from hancode.core.config import HanCodeConfig
from hancode.core.state import TaskState
from hancode.policy.tool_policy import PolicyDecision


@dataclass(frozen=True, slots=True)
class ApprovalRequirement:
    """The outcome of evaluating whether an action needs human approval."""

    required: bool
    category: ApprovalCategory | None
    reason: str
    risk_level: str
    targets: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "required": self.required,
            "category": None if self.category is None else self.category.value,
            "reason": self.reason,
            "risk_level": self.risk_level,
            "targets": list(self.targets),
        }


def _no_approval(reason: str) -> ApprovalRequirement:
    return ApprovalRequirement(
        required=False,
        category=None,
        reason=reason,
        risk_level="none",
        targets=(),
    )


def _require(
    category: ApprovalCategory,
    reason: str,
    *,
    targets: tuple[str, ...],
    risk_level: str = "medium",
) -> ApprovalRequirement:
    return ApprovalRequirement(
        required=True,
        category=category,
        reason=reason,
        risk_level=risk_level,
        targets=targets,
    )


_SOURCE_WRITE_TOOLS = frozenset({"write_file", "edit_file"})
_OVERWRITE_TOOLS = frozenset({"write_file"})


class ApprovalPolicy:
    """Determines whether a Policy-allowed action still needs human approval."""

    def __init__(self, config: HanCodeConfig) -> None:
        self._config = config
        self._mode = config.approval_mode

    def evaluate(
        self,
        *,
        action: Action,
        policy_decision: PolicyDecision,
        state: TaskState,
    ) -> ApprovalRequirement:
        """Evaluate whether the action requires approval.

        Precondition: policy_decision.allowed must be True.
        """
        if not policy_decision.allowed:
            # This is a defensive guard: denied actions should never reach here.
            return _no_approval("Policy already denied; approval not applicable.")

        if action.type is not ActionType.TOOL_CALL or action.tool_name is None:
            return _no_approval("Only tool calls may require approval.")

        tool_name = action.tool_name

        # ---- Rollback approval (checked independently of approval_mode) ----
        if tool_name == "rollback_last_checkpoint":
            return self._evaluate_rollback(action, state)

        if self._mode == "disabled":
            return _no_approval("Approval mode is disabled.")

        # ---- Source write approval ----
        if tool_name in _SOURCE_WRITE_TOOLS:
            return self._evaluate_source_write(action, state)

        return _no_approval(f"Tool {tool_name} does not require approval.")

    def _evaluate_source_write(
        self, action: Action, state: TaskState
    ) -> ApprovalRequirement:
        tool_name = action.tool_name
        assert tool_name is not None

        target_paths = self._extract_paths(action)
        targets = tuple(target_paths) if target_paths else ()

        # Determine the relevant target path for source zone checking
        path_value = action.args.get("path")
        path_str = str(path_value) if isinstance(path_value, str) else "unknown"

        is_overwrite = tool_name in _OVERWRITE_TOOLS
        # Heuristic: if the file already exists in the project, it's an overwrite
        # The actual file existence is checked by the ApprovalRequestBuilder later.

        if self._mode == "all_source_writes":
            category = (
                ApprovalCategory.SOURCE_OVERWRITE
                if is_overwrite
                else ApprovalCategory.SOURCE_WRITE
            )
            return _require(
                category,
                f"Source write to {path_str} requires approval (mode: all_source_writes).",
                targets=targets,
                risk_level="high" if is_overwrite else "medium",
            )

        if self._mode == "first_source_write":
            if state.source_edits_this_phase == 0:
                return _require(
                    ApprovalCategory.SOURCE_WRITE,
                    f"First source write in phase ({path_str}) requires approval.",
                    targets=targets,
                    risk_level="medium",
                )
            # For overwrites in first_source_write mode, always require approval
            if is_overwrite:
                return _require(
                    ApprovalCategory.SOURCE_OVERWRITE,
                    f"Overwrite of {path_str} requires approval.",
                    targets=targets,
                    risk_level="high",
                )
            return _no_approval(
                f"Source writes already approved in phase (edits: {state.source_edits_this_phase})."
            )

        return _no_approval("Approval mode is disabled.")

    def _evaluate_rollback(
        self, action: Action, state: TaskState
    ) -> ApprovalRequirement:
        if not self._config.confirm_agent_rollback:
            return _no_approval("Agent rollback confirmation is disabled.")

        # Forced rollback (retry budget exhausted) does NOT go through ApprovalPolicy.
        # This is enforced by the AgentLoop, which bypasses ApprovalPolicy for
        # router-triggered rollbacks.

        return _require(
            ApprovalCategory.ROLLBACK,
            "Agent-requested rollback requires confirmation.",
            targets=(),
            risk_level="high",
        )

    @staticmethod
    def _extract_paths(action: Action) -> list[str]:
        """Extract normalized target paths from an action's args."""
        paths: list[str] = []
        path_value = action.args.get("path")
        if isinstance(path_value, str) and path_value.strip():
            p = path_value.strip().replace("\\", "/")
            # Remove leading ./ if any
            while p.startswith("./"):
                p = p[2:]
            while p.startswith("/"):
                p = p[1:]
            if p:
                paths.append(p)
        return paths
