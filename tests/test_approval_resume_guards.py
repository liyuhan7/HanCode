"""S3-R3: unit coverage for the resume-time security guards.

These test the two checks the design (§10 digest binding, §11 stale target)
makes non-negotiable, directly on the AgentLoop, without the phase/artifact
machinery of a full engine run.
"""

from __future__ import annotations

from pathlib import Path


from hancode.core.actions import Action, ActionType
from hancode.core.config import load_config
from hancode.core.models import Phase
from hancode.core.state import load_state
from hancode.policy.approval_policy import ApprovalPolicy
from hancode.runtime.approval_request import ApprovalRequestBuilder
from hancode.runtime.engine import create_agent_loop
from hancode.storage.workspace import init_project_workspace, init_task_workspace, task_path


def _prepare(tmp_path: Path):
    import json

    init_project_workspace(tmp_path, "project-001", "Course", "Assignment")
    init_task_workspace(tmp_path, "task-001", goal="g")
    pf = tmp_path / ".hancode" / "project.json"
    project = json.loads(pf.read_text(encoding="utf-8"))
    project["approval_mode"] = "all_source_writes"
    pf.write_text(json.dumps(project), encoding="utf-8")
    config = load_config(tmp_path, "task-001")
    loop = create_agent_loop(tmp_path, "task-001")
    state = load_state(task_path(tmp_path, "task-001"))
    builder = ApprovalRequestBuilder(config)
    return loop, state, builder


def _build_record(tmp_path: Path, builder, state, target: str, content: str):
    action = Action(
        type=ActionType.TOOL_CALL,
        phase=state.current_phase,
        tool_name="write_file",
        args={"path": target, "content": content},
        reason="write target",
    )
    requirement = ApprovalPolicy(load_config(tmp_path, "task-001")).evaluate(
        action=action,
        policy_decision=_Allowed(state.current_phase),
        state=state,
    )
    return builder.build(
        project_id="project-001",
        task_id="task-001",
        state=state,
        action=action,
        requirement=requirement,
        project_root=tmp_path,
    )


class _Allowed:
    def __init__(self, phase: Phase) -> None:
        self.allowed = True
        self.reason = "ok"
        self.phase = phase
        self.requires_checkpoint = True
        self.suggested_fix = "n/a"
        self.denied_rule = None


def test_preconditions_hold_when_workspace_unchanged(tmp_path: Path) -> None:
    loop, state, builder = _prepare(tmp_path)
    src = tmp_path / "src.txt"
    src.write_text("original", encoding="utf-8")
    record = _build_record(tmp_path, builder, state, "src.txt", "new content")

    assert loop._validate_approval_preconditions(state, record) is True


def test_preconditions_fail_when_target_changed(tmp_path: Path) -> None:
    loop, state, builder = _prepare(tmp_path)
    src = tmp_path / "src.txt"
    src.write_text("original", encoding="utf-8")
    record = _build_record(tmp_path, builder, state, "src.txt", "new content")

    # Tamper with the target after the approval was recorded.
    src.write_text("tampered by user", encoding="utf-8")

    assert loop._validate_approval_preconditions(state, record) is False


def test_preconditions_fail_when_target_deleted(tmp_path: Path) -> None:
    loop, state, builder = _prepare(tmp_path)
    src = tmp_path / "src.txt"
    src.write_text("original", encoding="utf-8")
    record = _build_record(tmp_path, builder, state, "src.txt", "new content")

    src.unlink()

    assert loop._validate_approval_preconditions(state, record) is False


def test_digest_intact_for_untampered_record(tmp_path: Path) -> None:
    loop, state, builder = _prepare(tmp_path)
    record = _build_record(tmp_path, builder, state, "src.txt", "content")

    assert loop._digest_intact(record) is True


def test_digest_mismatch_when_action_fields_altered(tmp_path: Path) -> None:
    loop, state, builder = _prepare(tmp_path)
    record = _build_record(tmp_path, builder, state, "src.txt", "content")

    # Simulate a manifest whose args were altered after the digest was signed.
    from dataclasses import replace

    tampered_snapshot = replace(
        record.action, args={"path": "src.txt", "content": "EVIL"}
    )
    tampered = replace(record, action=tampered_snapshot)

    assert loop._digest_intact(tampered) is False
