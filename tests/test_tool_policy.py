from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from hancode.core.actions import Action, ActionType
from hancode.core.config import HanCodeConfig
from hancode.core.interactions import InteractionRecord, InteractionStatus
from hancode.core.models import Phase, TaskStatus
from hancode.core.state import TaskState
from hancode.policy.path_policy import PathZone
from hancode.policy.tool_policy import PolicyDecision, ToolPolicy, allowed_tools_for_phase
from hancode.core.test_remediation import RemediationDecision, RemediationKind, digest_remediation
from hancode.storage.test_remediations import TestRemediationStore
from hancode.storage.delivery_evidence import DeliveryEvidenceStore
from hancode.core.delivery_evidence import DeliveryEvidence


@pytest.mark.parametrize(
    ("phase", "expected"),
    [
        (
            Phase.SPEC,
            (
                "list_files",
                "memory_read",
                "memory_search",
                "read_file",
                "search_text",
                "write_file",
            ),
        ),
        (
            Phase.CODE,
            (
                "edit_file",
                "get_diff",
                "list_checkpoints",
                "list_files",
                "memory_read",
                "memory_search",
                "read_file",
                "record_remediation",
                "record_test_strategy",
                "search_text",
                "write_file",
            ),
        ),
        (
            Phase.TEST,
            (
                "get_diff",
                "list_checkpoints",
                "list_files",
                "memory_read",
                "memory_search",
                "read_file",
                "read_test_report",
                "run_build",
                "run_tests",
                "search_text",
                "write_file",
            ),
        ),
        (
            Phase.REVIEW,
            (
                "get_diff",
                "list_checkpoints",
                "list_files",
                "memory_read",
                "memory_search",
                "read_file",
                "read_test_report",
                "record_remediation",
                "record_review",
                "rollback_last_checkpoint",
                "run_build",
                "search_text",
                "write_file",
            ),
        ),
    ],
)
def test_allowed_tools_for_phase_returns_sorted_policy_matrix(
    phase: Phase, expected: tuple[str, ...]
) -> None:
    assert allowed_tools_for_phase(phase) == expected


@pytest.mark.parametrize("phase", tuple(Phase))
@pytest.mark.parametrize(
    ("tool_name", "args"),
    [
        ("memory_read", {"memory_id": "mem-000001"}),
        ("memory_search", {"query": "needle"}),
    ],
)
def test_memory_tools_are_read_only_policy_actions_in_every_phase(
    tmp_path: Path, phase: Phase, tool_name: str, args: dict[str, object]
) -> None:
    decision = _policy(tmp_path).evaluate(
        action=_action(tool_name, phase, args, None),
        phase=phase,
        state=_state(phase),
    )

    assert decision.allowed is True
    assert decision.requires_checkpoint is False
    assert decision.target_zone is None


def test_allows_code_source_write_and_requires_checkpoint(tmp_path: Path) -> None:
    decision = _policy(tmp_path).evaluate(
        action=_write_action(Phase.CODE, "src/main.py"),
        phase=Phase.CODE,
        state=_state(Phase.CODE),
    )

    assert decision == PolicyDecision(
        allowed=True,
        reason="Action is allowed.",
        phase=Phase.CODE,
        requires_checkpoint=True,
        target_zone=PathZone.SOURCE,
        denied_rule=None,
        suggested_fix="",
    )
    assert decision.to_dict() == {
        "allowed": True,
        "requires_checkpoint": True,
        "error_code": None,
        "message": "Action is allowed.",
        "phase": "code",
        "target_zone": "source",
        "denied_rule": None,
        "suggested_fix": "",
    }


@pytest.mark.parametrize(
    ("tool_name", "phase", "args", "reason"),
    [
        ("edit_file", Phase.SPEC, {"path": "src/main.py", "old_string": "a", "new_string": "b"}, "Update code."),
        ("run_tests", Phase.PLAN, {"command": "pytest -q"}, None),
        ("rollback_last_checkpoint", Phase.CODE, {}, None),
    ],
)
def test_denies_tool_not_allowed_in_phase(
    tmp_path: Path,
    tool_name: str,
    phase: Phase,
    args: dict[str, object],
    reason: str | None,
) -> None:
    decision = _policy(tmp_path).evaluate(
        action=_action(tool_name, phase, args, reason),
        phase=phase,
        state=_state(phase),
    )

    assert decision.allowed is False
    assert decision.denied_rule == "tool_not_allowed_in_phase"
    assert decision.to_dict()["error_code"] == "policy_denied"


def test_run_tests_is_only_available_in_test_phase() -> None:
    assert "run_tests" not in allowed_tools_for_phase(Phase.CODE)
    assert "run_tests" in allowed_tools_for_phase(Phase.TEST)
    assert "run_tests" not in allowed_tools_for_phase(Phase.REVIEW)


def test_test_phase_can_discover_project_files() -> None:
    tools = set(allowed_tools_for_phase(Phase.TEST))

    assert {"list_files", "read_file", "search_text", "run_tests"} <= tools


def test_defensively_denies_write_without_reason(tmp_path: Path) -> None:
    action = _write_action(Phase.CODE, "src/main.py")
    object.__setattr__(action, "reason", " ")

    decision = _policy(tmp_path).evaluate(
        action=action,
        phase=Phase.CODE,
        state=_state(Phase.CODE),
    )

    assert decision.allowed is False
    assert decision.denied_rule == "reason_required_for_write"


def test_denial_serializes_structured_policy_error(tmp_path: Path) -> None:
    decision = _policy(tmp_path).evaluate(
        action=_write_action(Phase.CODE, "assignment.md"),
        phase=Phase.CODE,
        state=_state(Phase.CODE),
    )

    assert decision.to_dict() == {
        "allowed": False,
        "requires_checkpoint": False,
        "error_code": "policy_denied",
        "message": "Target path is a protected course or credential file.",
        "phase": "code",
        "target_zone": None,
        "denied_rule": "protected_path",
        "suggested_fix": "Modify allowed source code instead; do not change course evaluation or credential files.",
    }


@pytest.mark.parametrize(
    ("path", "denied_rule"),
    [
        ("assignment.md", "protected_path"),
        ("../outside.py", "path_out_of_scope"),
        ("src/../src/main.py", "path_out_of_scope"),
    ],
)
def test_denies_protected_or_out_of_scope_write(
    tmp_path: Path, path: str, denied_rule: str
) -> None:
    decision = _policy(tmp_path).evaluate(
        action=_write_action(Phase.CODE, path),
        phase=Phase.CODE,
        state=_state(Phase.CODE),
    )

    assert decision.allowed is False
    assert decision.denied_rule == denied_rule
    assert decision.suggested_fix


def test_allows_only_phase_artifact_for_artifact_write(tmp_path: Path) -> None:
    policy = _policy(tmp_path)
    path = ".hancode/tasks/task-001/SPEC.md"

    allowed = policy.evaluate(
        action=_write_action(Phase.SPEC, path),
        phase=Phase.SPEC,
        state=_state(Phase.SPEC),
    )
    denied = policy.evaluate(
        action=_write_action(Phase.PLAN, path),
        phase=Phase.PLAN,
        state=_state(Phase.PLAN),
    )

    assert allowed.allowed is True
    assert allowed.requires_checkpoint is False
    assert denied.allowed is False
    assert denied.denied_rule == "artifact_not_allowed_in_phase"


@pytest.mark.parametrize(
    ("state_kwargs", "phase", "denied_rule"),
    [
        ({"artifacts": {"SPEC.md": False}}, Phase.CODE, "spec_required_before_source_write"),
        ({"artifacts": {"PLAN.md": False}}, Phase.CODE, "plan_required_before_source_write"),
        ({"inconsistent": True}, Phase.CODE, "state_must_be_consistent"),
        ({}, Phase.PLAN, "source_write_requires_code_phase"),
    ],
)
def test_denies_source_write_when_prerequisite_is_missing(
    tmp_path: Path,
    state_kwargs: dict[str, object],
    phase: Phase,
    denied_rule: str,
) -> None:
    state = _state(phase, **state_kwargs)  # type: ignore[arg-type]
    decision = _policy(tmp_path).evaluate(
        action=_write_action(phase, "src/main.py"),
        phase=phase,
        state=state,
    )

    assert decision.allowed is False
    assert decision.denied_rule == denied_rule


def test_denies_source_write_when_state_phase_is_not_code(tmp_path: Path) -> None:
    decision = _policy(tmp_path).evaluate(
        action=_write_action(Phase.CODE, "src/main.py"),
        phase=Phase.CODE,
        state=_state(Phase.PLAN),
    )

    assert decision.allowed is False
    assert decision.denied_rule == "source_write_requires_code_phase"


@pytest.mark.parametrize(
    ("phase", "state_kwargs", "allowed", "denied_rule"),
    [
        (Phase.SPEC, {"artifacts": {"SPEC.md": True}}, True, None),
        (Phase.SPEC, {"artifacts": {"SPEC.md": False}}, False, "spec_finish_requirements"),
        (Phase.PLAN, {"artifacts": {"PLAN.md": True}}, True, None),
        (Phase.PLAN, {"artifacts": {"PLAN.md": False}}, False, "plan_finish_requirements"),
        (
            Phase.CODE,
            {
                "source_edits_this_phase": 1,
                "test_strategy_digest": "a" * 64,
            },
            True,
            None,
        ),
        (Phase.CODE, {}, False, "code_finish_requirements"),
        (Phase.TEST, {"latest_test_status": "passed"}, True, None),
        (Phase.TEST, {}, False, "test_finish_requirements"),
        (Phase.REVIEW, {"artifacts": {"REVIEW.md": True}, "rollback_required": True, "rollback_done": True}, True, None),
        (Phase.REVIEW, {"artifacts": {"REVIEW.md": True}, "rollback_required": True}, False, "review_finish_requirements"),
        (Phase.DELIVER, {"artifacts": {"KNOWLEDGE.md": True, "DELIVERABLES.md": True}}, True, None),
        (Phase.DELIVER, {"artifacts": {"KNOWLEDGE.md": True}}, False, "deliver_finish_requirements"),
    ],
)
def test_finish_phase_uses_deterministic_state_gate(
    tmp_path: Path,
    phase: Phase,
    state_kwargs: dict[str, object],
    allowed: bool,
    denied_rule: str | None,
) -> None:
    state = _state(phase, **state_kwargs)  # type: ignore[arg-type]
    decision = _policy(tmp_path).evaluate(
        action=_finish_action(phase),
        phase=phase,
        state=state,
    )

    assert decision.allowed is allowed
    assert decision.denied_rule == denied_rule


def test_allows_control_actions_without_tool_dispatch(tmp_path: Path) -> None:
    policy = _policy(tmp_path, interaction_mode="ask_user")
    state = _state(Phase.CODE)

    ask_user = policy.evaluate(
        action=_ask_user_action(Phase.CODE), phase=Phase.CODE, state=state
    )

    assert ask_user.allowed is True
    assert ask_user.requires_checkpoint is False


def test_final_is_not_model_selectable(tmp_path: Path) -> None:
    decision = _policy(tmp_path).evaluate(
        action=_final_action(Phase.CODE),
        phase=Phase.CODE,
        state=_state(Phase.CODE),
    )

    assert not decision.allowed
    assert decision.denied_rule == "final_not_model_selectable"


def test_denies_ask_user_when_interaction_is_disabled(tmp_path: Path) -> None:
    decision = _policy(tmp_path).evaluate(
        action=_ask_user_action(Phase.CODE),
        phase=Phase.CODE,
        state=_state(Phase.CODE),
    )

    assert decision.allowed is False
    assert decision.denied_rule == "interaction_disabled"


def test_denies_ask_user_without_question(tmp_path: Path) -> None:
    action = _ask_user_action(Phase.CODE)
    object.__setattr__(action, "args", {})

    decision = _policy(tmp_path, interaction_mode="ask_user").evaluate(
        action=action,
        phase=Phase.CODE,
        state=_state(Phase.CODE),
    )

    assert decision.allowed is False
    assert decision.denied_rule == "interaction_question_required"


def test_denies_ask_user_question_over_configured_limit(tmp_path: Path) -> None:
    decision = _policy(
        tmp_path,
        interaction_mode="ask_user",
        max_interaction_question_chars=5,
    ).evaluate(
        action=_ask_user_action(Phase.CODE, question="Too long"),
        phase=Phase.CODE,
        state=_state(Phase.CODE),
    )

    assert decision.allowed is False
    assert decision.denied_rule == "interaction_question_too_long"


def test_denies_ask_user_when_an_interaction_is_pending(tmp_path: Path) -> None:
    interaction = InteractionRecord(
        interaction_id="ask-000001",
        phase=Phase.CODE,
        question="Choose a target.",
        answer=None,
        status=InteractionStatus.WAITING,
    )
    state = replace(
        _state(Phase.CODE),
        status=TaskStatus.WAITING_INPUT,
        interaction_seq=1,
        interactions=(interaction,),
        pending_interaction_id=interaction.interaction_id,
    )

    decision = _policy(tmp_path, interaction_mode="ask_user").evaluate(
        action=_ask_user_action(Phase.CODE),
        phase=Phase.CODE,
        state=state,
    )

    assert decision.allowed is False
    assert decision.denied_rule == "interaction_already_pending"


def test_denies_ask_user_after_phase_interaction_limit(tmp_path: Path) -> None:
    interaction = InteractionRecord(
        interaction_id="ask-000001",
        phase=Phase.CODE,
        question="Which target?",
        answer="src/main.py",
        status=InteractionStatus.ANSWERED,
    )
    state = replace(_state(Phase.CODE), interaction_seq=1, interactions=(interaction,))

    decision = _policy(
        tmp_path,
        interaction_mode="ask_user",
        max_interactions_per_phase=1,
    ).evaluate(
        action=_ask_user_action(Phase.CODE),
        phase=Phase.CODE,
        state=state,
    )

    assert decision.allowed is False
    assert decision.denied_rule == "interaction_limit_exceeded"


@pytest.mark.parametrize("question", ["Provide the API key", "Enter your password"])
def test_denies_ask_user_secret_request(tmp_path: Path, question: str) -> None:
    decision = _policy(tmp_path, interaction_mode="ask_user").evaluate(
        action=_ask_user_action(Phase.CODE, question=question),
        phase=Phase.CODE,
        state=_state(Phase.CODE),
    )

    assert decision.allowed is False
    assert decision.denied_rule == "interaction_secret_request_denied"


def test_edit_file_source_write_requires_checkpoint(tmp_path: Path) -> None:
    decision = _policy(tmp_path).evaluate(
        action=_action(
            "edit_file",
            Phase.CODE,
            {"path": "src/main.py", "old_string": "old", "new_string": "new"},
            "Update code.",
        ),
        phase=Phase.CODE,
        state=_state(Phase.CODE),
    )

    assert decision.allowed is True
    assert decision.requires_checkpoint is True


def test_denies_action_phase_mismatch(tmp_path: Path) -> None:
    decision = _policy(tmp_path).evaluate(
        action=_write_action(Phase.CODE, "src/main.py"),
        phase=Phase.PLAN,
        state=_state(Phase.PLAN),
    )

    assert decision.allowed is False
    assert decision.denied_rule == "action_phase_mismatch"


def test_denies_rollback_without_checkpoint(tmp_path: Path) -> None:
    decision = _policy(tmp_path).evaluate(
        action=_action("rollback_last_checkpoint", Phase.REVIEW, {}, None),
        phase=Phase.REVIEW,
        state=_state(Phase.REVIEW),
    )

    assert decision.allowed is False
    assert decision.denied_rule == "rollback_checkpoint_required"


def test_remediation_paths_remain_enforced_after_first_applied_write(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / ".hancode" / "tasks" / "task-001").mkdir(parents=True)
    decision = RemediationDecision(
        schema_version=1,
        task_id="task-001",
        failure_digest="a" * 64,
        kind=RemediationKind.MODIFY_SOURCE,
        diagnosis="Fix the declared implementation file.",
        planned_paths=("src/a.py",),
        question=None,
        created_at="2026-07-31T00:00:00+00:00",
        digest="pending",
    )
    decision = replace(decision, digest=digest_remediation(decision))
    TestRemediationStore(tmp_path).save_remediation(decision)
    state = replace(
        _state(Phase.CODE, latest_test_status="none"),
        latest_remediation_digest=decision.digest,
        remediation_applied=True,
    )

    result = _policy(tmp_path).evaluate(
        action=_write_action(Phase.CODE, "src/b.py"),
        phase=Phase.CODE,
        state=state,
    )

    assert result.allowed is False
    assert result.denied_rule == "remediation_planned_path_required"


def test_record_remediation_allowed_in_code_phase_when_test_failed(
    tmp_path: Path,
) -> None:
    """A failed-test remediation may be re-declared in CODE to expand scope."""
    state = replace(
        _state(Phase.CODE, latest_test_status="failed"),
        latest_test_failure_digest="a" * 64,
    )

    decision = _policy(tmp_path).evaluate(
        action=_action(
            "record_remediation",
            Phase.CODE,
            {
                "failure_digest": "a" * 64,
                "kind": "modify_source",
                "diagnosis": "Expand remediation to include index.html.",
                "planned_paths": [".hancode/src/index.html"],
                "question": None,
            },
            "Update remediation planned paths for cross-file fix.",
        ),
        phase=Phase.CODE,
        state=state,
    )

    assert decision.allowed is True
    assert decision.denied_rule is None


def _policy(
    project_root: Path,
    *,
    interaction_mode: str = "disabled",
    max_interactions_per_phase: int = 8,
    max_interaction_question_chars: int = 2048,
) -> ToolPolicy:
    return ToolPolicy(
        _config(
            project_root,
            interaction_mode=interaction_mode,
            max_interactions_per_phase=max_interactions_per_phase,
            max_interaction_question_chars=max_interaction_question_chars,
        )
    )


def _config(
    project_root: Path,
    *,
    interaction_mode: str = "disabled",
    max_interactions_per_phase: int = 8,
    max_interaction_question_chars: int = 2048,
) -> HanCodeConfig:
    return HanCodeConfig(
        project_root=project_root,
        hancode_root=project_root / ".hancode",
        allowed_workspace_root=project_root,
        task_root=project_root / ".hancode" / "tasks" / "task-001",
        llm_provider="mock",
        model_name=None,
        credential_source=None,
        test_command=None,
        build_command=None,
        max_steps=30,
        retry_budget=2,
        max_checkpoints_per_task=5,
        max_observation_bytes=8192,
        max_context_chars=24000,
        max_trace_events=1000,
        protected_patterns=("assignment.md",),
        writable_roots=(project_root / "src",),
        interaction_mode=interaction_mode,  # type: ignore[arg-type]
        max_interactions_per_phase=max_interactions_per_phase,
        max_interaction_question_chars=max_interaction_question_chars,
    )


def _state(
    phase: Phase,
    *,
    artifacts: dict[str, bool] | None = None,
    inconsistent: bool = False,
    source_edits_this_phase: int = 0,
    latest_test_status: str = "none",
    latest_checkpoint: str | None = None,
    rollback_required: bool = False,
    rollback_done: bool = False,
    test_strategy_digest: str | None = None,
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
        goal="Implement policy.",
        status=TaskStatus.INCONSISTENT if inconsistent else TaskStatus.CREATED,
        current_phase=phase,
        files_changed=(),
        latest_checkpoint=latest_checkpoint,
        checkpoint_seq=0,
        tests_run=(),
        latest_test_status=latest_test_status,
        test_status_consumed=False,
        retry_budget_remaining=2,
        inconsistent=inconsistent,
        source_edits_this_phase=source_edits_this_phase,
        rollback_required=rollback_required,
        rollback_done=rollback_done,
        phase_completed={item.value: False for item in Phase},
        artifacts=values,
        test_strategy_digest=test_strategy_digest,
    )


def _action(
    tool_name: str, phase: Phase, args: dict[str, object], reason: str | None
) -> Action:
    action = Action.from_values(
        type=ActionType.TOOL_CALL,
        phase=phase,
        tool_name=tool_name,
        args=args,
        reason=reason,
    )
    assert isinstance(action, Action)
    return action


def _write_action(phase: Phase, path: str) -> Action:
    return _action(
        "write_file", phase, {"path": path, "content": "content\n"}, "Create file."
    )


def _finish_action(phase: Phase) -> Action:
    action = Action.from_values(
        type=ActionType.FINISH_PHASE,
        phase=phase,
        tool_name=None,
        args={},
        reason=None,
    )
    assert isinstance(action, Action)
    return action


def test_deliver_finish_denied_without_diff_evidence_when_checkpoint_exists(
    tmp_path: Path,
) -> None:
    state = _state(
        Phase.DELIVER,
        artifacts={"KNOWLEDGE.md": True, "DELIVERABLES.md": True},
        latest_test_status="passed",
        latest_checkpoint="ckpt-001",
    )

    decision = _policy(tmp_path).evaluate(
        action=_finish_action(Phase.DELIVER),
        phase=Phase.DELIVER,
        state=state,
    )

    assert decision.allowed is False
    assert decision.denied_rule == "deliver_finish_requirements"


def test_deliver_finish_allowed_when_diff_evidence_present(tmp_path: Path) -> None:
    state = _state(
        Phase.DELIVER,
        artifacts={"KNOWLEDGE.md": True, "DELIVERABLES.md": True},
        latest_test_status="passed",
        latest_checkpoint="ckpt-001",
    )
    task_root = tmp_path / ".hancode" / "tasks" / "task-001"
    task_root.mkdir(parents=True)
    DeliveryEvidenceStore().save(
        task_root,
        DeliveryEvidence(
            task_id="task-001",
            requirements=(),
            knowledge_items=(),
            review_risks=(),
            latest_test_report_sha256=None,
            latest_diff_sha256="d" * 64,
            latest_build_status="none",
        ),
    )

    decision = _policy(tmp_path).evaluate(
        action=_finish_action(Phase.DELIVER),
        phase=Phase.DELIVER,
        state=state,
    )

    assert decision.allowed is True
    assert decision.denied_rule is None


def _ask_user_action(phase: Phase, *, question: str = "Continue?") -> Action:
    action = Action.from_values(
        type=ActionType.ASK_USER,
        phase=phase,
        tool_name=None,
        args={"question": question},
        reason=None,
    )
    assert isinstance(action, Action)
    return action


def _final_action(phase: Phase) -> Action:
    action = Action.from_values(
        type=ActionType.FINAL,
        phase=phase,
        tool_name=None,
        args={},
        reason=None,
    )
    assert isinstance(action, Action)
    return action
