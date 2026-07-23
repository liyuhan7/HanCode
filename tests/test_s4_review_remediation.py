"""Regression tests for the S4-R review blockers."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from hancode.app.approval_service import ApprovalService
from hancode.core.actions import Action, ActionType, parse_action
from hancode.core.approvals import ApprovalCategory
from hancode.core.config import load_config
from hancode.core.models import Phase
from hancode.core.state import load_state, save_state
from hancode.core.tool_specs import TOOL_SPEC_BY_NAME
from hancode.policy.tool_policy import ToolPolicy
from hancode.policy.approval_policy import ApprovalPolicy
from hancode.providers.mock import MockLLM
from hancode.runtime.engine import create_agent_loop
from hancode.storage.workspace import init_project_workspace, init_task_workspace
from hancode.storage.delivery_evidence import DeliveryEvidenceStore
from hancode.storage.checkpoint_queries import CheckpointQueryRepository
from hancode.interfaces import cli
from hancode.tooling.factory import build_default_tool_registry
from hancode.tooling.delivery_tools import read_test_report
from hancode.tooling.registry import ToolResult
from hancode.tooling.registry import ToolRegistry


def test_s4_structured_tool_actions_match_tool_specs() -> None:
    cases = (
        ("get_diff", Phase.REVIEW, {"scope": "task"}),
        (
            "record_review",
            Phase.REVIEW,
            {"requirements": [], "risks": []},
        ),
        ("record_knowledge", Phase.DELIVER, {"items": []}),
    )

    for tool_name, phase, args in cases:
        parsed = parse_action(
            {
                "type": "tool_call",
                "phase": phase.value,
                "tool_name": tool_name,
                "args": args,
                "reason": None,
            },
            phase,
        )

        assert isinstance(parsed, Action), (tool_name, parsed)
        assert parsed.tool_name in TOOL_SPEC_BY_NAME


def test_s4_tool_policy_uses_tool_specs_for_new_tools(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    init_project_workspace(project_root, "project-001", "Course", "Assignment")
    task_root = init_task_workspace(project_root, "task-001")
    config = load_config(project_root, "task-001")
    state = load_state(task_root)

    cases = (
        ("get_diff", Phase.CODE, {"scope": "task"}),
        ("run_build", Phase.TEST, {}),
        ("read_test_report", Phase.TEST, {}),
        ("list_checkpoints", Phase.CODE, {}),
        ("record_review", Phase.REVIEW, {"requirements": [], "risks": []}),
        ("record_knowledge", Phase.DELIVER, {"items": []}),
    )
    policy = ToolPolicy(config)

    for tool_name, phase, args in cases:
        action = Action(
            type=ActionType.TOOL_CALL,
            phase=phase,
            tool_name=tool_name,
            args=args,
            reason=None,
        )
        decision = policy.evaluate(
            action=action,
            phase=phase,
            state=replace(state, current_phase=phase),
        )

        assert decision.allowed is True, (tool_name, decision)


def test_default_registry_registers_structured_delivery_tools(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    init_project_workspace(project_root, "project-001", "Course", "Assignment")
    init_task_workspace(project_root, "task-001")
    config = load_config(project_root, "task-001")
    registry = build_default_tool_registry(config)

    actions = (
        Action(
            ActionType.TOOL_CALL,
            Phase.REVIEW,
            "record_review",
            {"requirements": [], "risks": []},
            None,
        ),
        Action(
            ActionType.TOOL_CALL,
            Phase.DELIVER,
            "record_knowledge",
            {"items": []},
            None,
        ),
    )

    for action in actions:
        result = registry.dispatch(action)
        assert isinstance(result, ToolResult)
        assert result.error_summary != "Tool is not registered."


def test_tool_policy_rejects_model_writes_to_deterministic_delivery_artifacts(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    init_project_workspace(project_root, "project-001", "Course", "Assignment")
    task_root = init_task_workspace(project_root, "task-001")
    config = load_config(project_root, "task-001")
    state = load_state(task_root)
    policy = ToolPolicy(config)

    for artifact in ("TEST_REPORT.md", "REVIEW.md", "KNOWLEDGE.md", "DELIVERABLES.md"):
        action = Action(
            type=ActionType.TOOL_CALL,
            phase=Phase.DELIVER,
            tool_name="write_file",
            args={"path": f".hancode/tasks/task-001/{artifact}", "content": "fake"},
            reason="Write the artifact.",
        )
        decision = policy.evaluate(
            action=action,
            phase=Phase.DELIVER,
            state=replace(state, current_phase=Phase.DELIVER),
        )

        assert decision.allowed is False
        assert decision.denied_rule == "deterministic_delivery_artifact"


def test_formal_agent_run_tests_generates_test_report(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    init_project_workspace(project_root, "project-001", "Course", "Assignment")
    task_root = init_task_workspace(project_root, "task-001")
    project_file = project_root / ".hancode" / "project.json"
    project_data = json.loads(project_file.read_text(encoding="utf-8"))
    project_data["test_command"] = "pytest -q"
    project_file.write_text(json.dumps(project_data), encoding="utf-8")
    (task_root / "SPEC.md").write_text("# Spec\n", encoding="utf-8")
    (task_root / "PLAN.md").write_text("# Plan\n", encoding="utf-8")
    state = load_state(task_root)
    save_state(
        task_root,
        replace(
            state,
            current_phase=Phase.TEST,
            phase_completed={
                **state.phase_completed,
                Phase.SPEC.value: True,
                Phase.PLAN.value: True,
                Phase.CODE.value: True,
            },
            artifacts={
                **state.artifacts,
                "SPEC.md": True,
                "PLAN.md": True,
            },
        ),
    )
    registry = ToolRegistry()
    registry.register(
        "run_tests",
        lambda command: ToolResult(
            success=True,
            action_name="run_tests",
            exit_code=0,
            stdout="1 passed",
            command=command or "pytest -q",
        ),
    )
    loop = create_agent_loop(
        project_root,
        "task-001",
        provider=MockLLM(
            [
                {
                    "type": "tool_call",
                    "phase": "test",
                    "tool_name": "run_tests",
                    "args": {},
                    "reason": None,
                }
            ]
        ),
        tool_registry=registry,
        max_steps=1,
    )

    result = loop.run("task-001")

    assert (task_root / "TEST_REPORT.md").is_file(), (
        result.status,
        result.error,
        result.final_state,
    )
    assert load_state(task_root).artifacts["TEST_REPORT.md"] is True


def _prepare_explicit_test_task(
    tmp_path: Path,
) -> tuple[Path, Path, list[str | None], ToolRegistry]:
    project_root = tmp_path / "project"
    project_root.mkdir()
    init_project_workspace(project_root, "project-001", "Course", "Assignment")
    project_file = project_root / ".hancode" / "project.json"
    project_data = json.loads(project_file.read_text(encoding="utf-8"))
    project_data["test_command"] = "pytest -q"
    project_file.write_text(json.dumps(project_data), encoding="utf-8")
    task_root = init_task_workspace(project_root, "task-001")
    (task_root / "SPEC.md").write_text("# Spec\n", encoding="utf-8")
    (task_root / "PLAN.md").write_text("# Plan\n", encoding="utf-8")
    state = load_state(task_root)
    save_state(
        task_root,
        replace(
            state,
            current_phase=Phase.TEST,
            phase_completed={
                **state.phase_completed,
                Phase.SPEC.value: True,
                Phase.PLAN.value: True,
                Phase.CODE.value: True,
            },
            artifacts={
                **state.artifacts,
                "SPEC.md": True,
                "PLAN.md": True,
            },
        ),
    )

    calls: list[str | None] = []
    registry = ToolRegistry()

    def run_tests_tool(command: str | None) -> ToolResult:
        calls.append(command)
        return ToolResult(
            success=True,
            action_name="run_tests",
            exit_code=0,
            stdout="1 passed",
            command=command,
        )

    registry.register("run_tests", run_tests_tool)
    return project_root, task_root, calls, registry


def test_explicit_run_tests_rejection_does_not_start_runner(tmp_path: Path) -> None:
    project_root, task_root, calls, registry = _prepare_explicit_test_task(tmp_path)
    provider = MockLLM(
        [
            {
                "type": "tool_call",
                "phase": "test",
                "tool_name": "run_tests",
                "args": {"command": "python -m pytest tests/test_app.py"},
                "reason": "Run the selected test file.",
            }
        ]
    )
    loop = create_agent_loop(
        project_root,
        "task-001",
        provider=provider,
        tool_registry=registry,
        max_steps=1,
    )

    waiting = loop.run("task-001")
    assert waiting.status.value == "waiting_approval", (
        waiting.error,
        waiting.final_state,
    )
    assert calls == []

    ApprovalService(project_root).reject("task-001", reason="Do not run this command.")
    loop.run("task-001", resume=True)

    assert calls == []
    assert load_state(task_root).status.value != "completed"


def test_approved_explicit_run_tests_executes_the_approved_command(
    tmp_path: Path,
) -> None:
    project_root, task_root, calls, registry = _prepare_explicit_test_task(tmp_path)
    command = "python -m pytest tests/test_app.py"
    loop = create_agent_loop(
        project_root,
        "task-001",
        provider=MockLLM(
            [
                {
                    "type": "tool_call",
                    "phase": "test",
                    "tool_name": "run_tests",
                    "args": {"command": command},
                    "reason": "Run the selected test file.",
                }
            ]
        ),
        tool_registry=registry,
        max_steps=1,
    )

    waiting = loop.run("task-001")
    assert waiting.status.value == "waiting_approval", (
        waiting.error,
        waiting.final_state,
    )
    ApprovalService(project_root).approve("task-001")

    loop.run("task-001", resume=True)

    assert calls == [command]
    report = (task_root / "TEST_REPORT.md").read_text(encoding="utf-8")
    trace = (task_root / "trace.jsonl").read_text(encoding="utf-8")
    assert command in report
    assert command in trace


def test_formal_agent_run_build_persists_build_state_and_evidence(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    init_project_workspace(project_root, "project-001", "Course", "Assignment")
    task_root = init_task_workspace(project_root, "task-001")
    project_file = project_root / ".hancode" / "project.json"
    project_data = json.loads(project_file.read_text(encoding="utf-8"))
    project_data.update(
        {
            "test_command": "pytest -q",
            "build_command": "python -c \"print('build')\"",
            "confirm_agent_build": False,
        }
    )
    project_file.write_text(json.dumps(project_data), encoding="utf-8")
    (task_root / "SPEC.md").write_text("# Spec\n", encoding="utf-8")
    (task_root / "PLAN.md").write_text("# Plan\n", encoding="utf-8")
    state = load_state(task_root)
    save_state(
        task_root,
        replace(
            state,
            current_phase=Phase.TEST,
            phase_completed={
                **state.phase_completed,
                Phase.SPEC.value: True,
                Phase.PLAN.value: True,
                Phase.CODE.value: True,
            },
            artifacts={**state.artifacts, "SPEC.md": True, "PLAN.md": True},
        ),
    )
    registry = ToolRegistry()
    registry.register(
        "run_build",
        lambda: ToolResult(
            success=True,
            action_name="run_build",
            exit_code=0,
            stdout="build",
            command="python -c print",
        ),
    )
    loop = create_agent_loop(
        project_root,
        "task-001",
        provider=MockLLM(
            [
                {
                    "type": "tool_call",
                    "phase": "test",
                    "tool_name": "run_build",
                    "args": {},
                    "reason": None,
                }
            ]
        ),
        tool_registry=registry,
        max_steps=1,
    )

    loop.run("task-001")

    assert load_state(task_root).latest_build_status == "passed"
    evidence = json.loads(
        (task_root / "delivery" / "evidence.json").read_text(encoding="utf-8")
    )
    assert evidence["latest_build_status"] == "passed"


def test_approved_agent_build_updates_state_and_evidence(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    init_project_workspace(project_root, "project-001", "Course", "Assignment")
    task_root = init_task_workspace(project_root, "task-001")
    project_file = project_root / ".hancode" / "project.json"
    project_data = json.loads(project_file.read_text(encoding="utf-8"))
    project_data.update(
        {
            "test_command": "pytest -q",
            "build_command": "python -c \"print('build')\"",
            "confirm_agent_build": True,
        }
    )
    project_file.write_text(json.dumps(project_data), encoding="utf-8")
    (task_root / "SPEC.md").write_text("# Spec\n", encoding="utf-8")
    (task_root / "PLAN.md").write_text("# Plan\n", encoding="utf-8")
    state = load_state(task_root)
    save_state(
        task_root,
        replace(
            state,
            current_phase=Phase.TEST,
            phase_completed={
                **state.phase_completed,
                Phase.SPEC.value: True,
                Phase.PLAN.value: True,
                Phase.CODE.value: True,
            },
            artifacts={**state.artifacts, "SPEC.md": True, "PLAN.md": True},
        ),
    )
    registry = ToolRegistry()
    registry.register(
        "run_build",
        lambda: ToolResult(
            success=True,
            action_name="run_build",
            exit_code=0,
            stdout="build",
            command="python -c print",
        ),
    )
    loop = create_agent_loop(
        project_root,
        "task-001",
        provider=MockLLM(
            [
                {
                    "type": "tool_call",
                    "phase": "test",
                    "tool_name": "run_build",
                    "args": {},
                    "reason": None,
                }
            ]
        ),
        tool_registry=registry,
        max_steps=1,
    )

    waiting = loop.run("task-001")
    assert waiting.status.value == "waiting_approval"
    ApprovalService(project_root).approve("task-001")

    loop.run("task-001", resume=True)

    assert load_state(task_root).latest_build_status == "passed"
    evidence = DeliveryEvidenceStore().load(task_root)
    assert evidence is not None
    assert evidence.latest_build_status == "passed"


def test_approved_source_write_updates_edit_tracking(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    init_project_workspace(project_root, "project-001", "Course", "Assignment")
    task_root = init_task_workspace(project_root, "task-001", goal="Write source.")
    project_file = project_root / ".hancode" / "project.json"
    project_data = json.loads(project_file.read_text(encoding="utf-8"))
    project_data["approval_mode"] = "all_source_writes"
    project_file.write_text(json.dumps(project_data), encoding="utf-8")
    (task_root / "SPEC.md").write_text("# Spec\n", encoding="utf-8")
    (task_root / "PLAN.md").write_text("# Plan\n", encoding="utf-8")
    state = load_state(task_root)
    save_state(
        task_root,
        replace(
            state,
            current_phase=Phase.CODE,
            phase_completed={
                **state.phase_completed,
                Phase.SPEC.value: True,
                Phase.PLAN.value: True,
            },
            artifacts={**state.artifacts, "SPEC.md": True, "PLAN.md": True},
        ),
    )
    config = load_config(project_root, "task-001")
    loop = create_agent_loop(
        project_root,
        "task-001",
        provider=MockLLM(
            [
                {
                    "type": "tool_call",
                    "phase": "code",
                    "tool_name": "write_file",
                    "args": {
                        "path": "src/main.py",
                        "content": "print('ok')\n",
                    },
                    "reason": "Implement the source change.",
                }
            ]
        ),
        tool_registry=build_default_tool_registry(config),
        max_steps=1,
    )

    waiting = loop.run("task-001")
    assert waiting.status.value == "waiting_approval"
    ApprovalService(project_root).approve("task-001")

    loop.run("task-001", resume=True)

    final_state = load_state(task_root)
    assert final_state.source_edits_this_phase == 1
    assert "src/main.py" in final_state.files_changed


def test_cli_build_records_delivery_evidence(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    init_project_workspace(project_root, "project-001", "Course", "Assignment")
    task_root = init_task_workspace(project_root, "task-001")
    project_file = project_root / ".hancode" / "project.json"
    project_data = json.loads(project_file.read_text(encoding="utf-8"))
    project_data["build_command"] = "python -c \"print('build')\""
    project_file.write_text(json.dumps(project_data), encoding="utf-8")

    result = CliRunner().invoke(
        cli.app,
        ["task", "build", "task-001", "--project-root", str(project_root)],
    )

    assert result.exit_code == 0, result.stdout
    evidence = DeliveryEvidenceStore().load(task_root)
    assert evidence is not None
    assert evidence.latest_build_status == "passed"


def test_structured_delivery_evidence_is_redacted_and_bounded(tmp_path: Path) -> None:
    from hancode.core.delivery_evidence import (
        KnowledgeCategory,
        KnowledgeItem,
        RequirementCoverage,
        RequirementStatus,
    )
    from hancode.runtime.delivery_pipeline import DeliveryPipeline

    project_root = tmp_path / "project"
    project_root.mkdir()
    init_project_workspace(project_root, "project-001", "Course", "Assignment")
    task_root = init_task_workspace(project_root, "task-001")
    secret = "token=structured-evidence-secret"
    long_text = "x" * 10_000
    pipeline = DeliveryPipeline()

    pipeline.record_review(
        task_root,
        "task-001",
        [RequirementCoverage("REQ-1", RequirementStatus.COVERED, secret + long_text, secret, True)],
        [secret + long_text],
    )
    pipeline.record_knowledge(
        task_root,
        "task-001",
        [KnowledgeItem(KnowledgeCategory.DESIGN_DECISION, secret, secret + long_text, secret)],
    )

    evidence = DeliveryEvidenceStore().load(task_root)
    assert evidence is not None
    assert secret not in json.dumps(evidence, default=str)
    assert len(evidence.requirements[0].evidence) <= 4096
    assert len(evidence.knowledge_items[0].detail) <= 4096
    assert evidence.knowledge_items[0].source_trace_id == "token=[REDACTED]"


def test_structured_delivery_evidence_rejects_excess_items(tmp_path: Path) -> None:
    from hancode.core.delivery_evidence import RequirementCoverage, RequirementStatus
    from hancode.core.errors import HanCodeError
    from hancode.runtime.delivery_pipeline import DeliveryPipeline

    project_root = tmp_path / "project"
    project_root.mkdir()
    init_project_workspace(project_root, "project-001", "Course", "Assignment")
    task_root = init_task_workspace(project_root, "task-001")

    with pytest.raises(HanCodeError) as error:
        DeliveryPipeline().record_review(
            task_root,
            "task-001",
            [RequirementCoverage(str(index), RequirementStatus.COVERED, "ok", None, True) for index in range(101)],
            [],
        )

    assert error.value.structured_error.error_code == "delivery_evidence_limit_exceeded"


def test_formal_agent_get_diff_persists_diff_evidence(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    init_project_workspace(project_root, "project-001", "Course", "Assignment")
    task_root = init_task_workspace(project_root, "task-001")
    (task_root / "SPEC.md").write_text("# Spec\n", encoding="utf-8")
    (task_root / "PLAN.md").write_text("# Plan\n", encoding="utf-8")
    (task_root / "TEST_REPORT.md").write_text("# Tests\n", encoding="utf-8")
    state = load_state(task_root)
    save_state(
        task_root,
        replace(
            state,
            goal="Inspect task changes.",
            current_phase=Phase.REVIEW,
            phase_completed={
                **state.phase_completed,
                Phase.SPEC.value: True,
                Phase.PLAN.value: True,
                Phase.CODE.value: True,
                Phase.TEST.value: True,
            },
            latest_test_status="passed",
            artifacts={
                **state.artifacts,
                "SPEC.md": True,
                "PLAN.md": True,
                "TEST_REPORT.md": True,
            },
        ),
    )
    registry = ToolRegistry()
    registry.register(
        "get_diff",
        lambda scope: ToolResult(
            success=True,
            action_name="get_diff",
            output={"files": [], "risks": []},
        ),
    )
    loop = create_agent_loop(
        project_root,
        "task-001",
        provider=MockLLM(
            [
                {
                    "type": "tool_call",
                    "phase": "review",
                    "tool_name": "get_diff",
                    "args": {"scope": "task"},
                    "reason": None,
                }
            ]
        ),
        tool_registry=registry,
        max_steps=1,
    )

    loop.run("task-001")

    evidence = DeliveryEvidenceStore().load(task_root)
    assert evidence is not None
    assert evidence.latest_diff_sha256 is not None


def test_build_requires_approval_when_configured(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    init_project_workspace(project_root, "project-001", "Course", "Assignment")
    task_root = init_task_workspace(project_root, "task-001")
    config = load_config(project_root, "task-001")
    state = load_state(task_root)
    action = Action(ActionType.TOOL_CALL, Phase.TEST, "run_build", {}, None)
    policy_decision = ToolPolicy(config).evaluate(
        action=action,
        phase=Phase.TEST,
        state=replace(state, current_phase=Phase.TEST),
    )

    requirement = ApprovalPolicy(config).evaluate(
        action=action,
        policy_decision=policy_decision,
        state=replace(state, current_phase=Phase.TEST),
    )

    assert requirement.required is True
    assert requirement.category is ApprovalCategory.RUN_BUILD


def test_build_service_persists_state_and_trace(tmp_path: Path) -> None:
    from hancode.app.build_service import BuildService

    project_root = tmp_path / "project"
    project_root.mkdir()
    init_project_workspace(project_root, "project-001", "Course", "Assignment")
    init_task_workspace(project_root, "task-001")
    project_file = project_root / ".hancode" / "project.json"
    project_data = json.loads(project_file.read_text(encoding="utf-8"))
    project_data["build_command"] = "python -c \"print('ok')\""
    project_file.write_text(json.dumps(project_data), encoding="utf-8")

    summary = BuildService().run(project_root, "task-001")

    task_root = project_root / ".hancode" / "tasks" / "task-001"
    assert summary.status == "passed"
    assert load_state(task_root).latest_build_status == "passed"
    assert "tool_completed" in (task_root / "trace.jsonl").read_text(encoding="utf-8")


def test_delivery_evidence_is_persisted_per_task_without_pipeline_memory(
    tmp_path: Path,
) -> None:
    from hancode.core.delivery_evidence import RequirementCoverage, RequirementStatus
    from hancode.runtime.delivery_pipeline import DeliveryPipeline

    project_root = tmp_path / "project"
    project_root.mkdir()
    init_project_workspace(project_root, "project-001", "Course", "Assignment")
    task_a = init_task_workspace(project_root, "task-a")
    task_b = init_task_workspace(project_root, "task-b")
    coverage = [
        RequirementCoverage("FR-A", RequirementStatus.COVERED, "test_a", None, True)
    ]

    DeliveryPipeline().record_review(task_a, "task-a", coverage, ["risk-a"])
    persisted_a = DeliveryEvidenceStore().load(task_a)
    assert persisted_a is not None
    assert tuple(item.requirement_id for item in persisted_a.requirements) == ("FR-A",)

    DeliveryPipeline().record_review(task_b, "task-b", [], ["risk-b"])
    persisted_b = DeliveryEvidenceStore().load(task_b)
    assert persisted_b is not None
    assert persisted_b.requirements == ()
    assert persisted_b.review_risks == ("risk-b",)


def test_checkpoint_query_rejects_snapshot_escape(tmp_path: Path) -> None:
    import hashlib

    project_root = tmp_path / "project"
    project_root.mkdir()
    init_project_workspace(project_root, "project-001", "Course", "Assignment")
    task_root = init_task_workspace(project_root, "task-001")
    checkpoint_dir = task_root / "checkpoints" / "ckpt-001"
    checkpoint_dir.mkdir(parents=True)
    outside = task_root / "outside.txt"
    outside.write_bytes(b"outside")
    manifest = {
        "schema_version": 1,
        "project_id": "project-001",
        "checkpoint_id": "ckpt-001",
        "task_id": "task-001",
        "phase": "code",
        "reason": "test",
        "created_at": "2026-07-21T00:00:00+00:00",
        "status": "committed",
        "files": [
            {
                "path": "src/main.py",
                "action": "modify",
                "before_snapshot": "../../outside.txt",
                "before_sha256": hashlib.sha256(b"outside").hexdigest(),
                "after_sha256": "b" * 64,
            }
        ],
        "rollback_available": True,
    }
    (checkpoint_dir / "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    try:
        CheckpointQueryRepository().read_before(task_root, "ckpt-001", "src/main.py")
    except Exception:
        return
    raise AssertionError("snapshot outside checkpoints/<id>/files was accepted")


def test_read_test_report_redacts_bounds_and_parses_pipeline_format(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    init_project_workspace(project_root, "project-001", "Course", "Assignment")
    task_root = init_task_workspace(project_root, "task-001")
    report = (
        "# 测试报告\n\n"
        "| 命令 | `pytest -q` |\n"
        "| 状态 | passed |\n"
        "| 通过数 | 12 |\n"
        "| 失败数 | 0 |\n\n"
        "token=live-report-secret\n"
        + ("x" * 20_000)
    )
    report_path = task_root / "TEST_REPORT.md"
    report_path.write_text(report, encoding="utf-8")
    state = load_state(task_root)
    save_state(task_root, replace(state, artifacts={**state.artifacts, "TEST_REPORT.md": True}))

    result = read_test_report(project_root, task_root)

    assert result.success is True
    assert isinstance(result.output, dict)
    assert result.output["command"] == "pytest -q"
    assert result.output["passed_count"] == 12
    assert result.output["failed_count"] == 0
    assert result.output["truncated"] is True
    assert "live-report-secret" not in str(result.output)
    assert len(str(result.output["content"])) < len(report)


def test_delivery_evidence_store_rejects_invalid_schema(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    init_project_workspace(project_root, "project-001", "Course", "Assignment")
    task_root = init_task_workspace(project_root, "task-001")
    evidence_path = task_root / "delivery" / "evidence.json"
    evidence_path.parent.mkdir()
    evidence_path.write_text(
        json.dumps(
            {
                "schema_version": 999,
                "task_id": "task-001",
                "requirements": [],
                "review_risks": [],
                "knowledge_items": [],
                "latest_test_report_sha256": None,
                "latest_diff_sha256": None,
                "latest_build_status": "none",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(Exception):
        DeliveryEvidenceStore().load(task_root)


def test_finalize_returns_blocked_result_when_test_gate_fails(tmp_path: Path) -> None:
    from hancode.core.delivery_evidence import RequirementCoverage, RequirementStatus
    from hancode.runtime.delivery_pipeline import DeliveryPipeline
    from hancode.runtime.feedback import FailureCategory, FeedbackReport

    project_root = tmp_path / "project"
    project_root.mkdir()
    init_project_workspace(project_root, "project-001", "Course", "Assignment")
    task_root = init_task_workspace(project_root, "task-001")
    pipeline = DeliveryPipeline()
    pipeline.record_test(
        task_root,
        FeedbackReport(
            passed=False,
            failure_category=FailureCategory.ASSERTION_FAILURE,
            summary="failed",
            next_action_hint="fix",
        ),
        "pytest -q",
    )
    state = load_state(task_root)
    save_state(task_root, replace(state, latest_test_status="failed"))
    pipeline.record_review(
        task_root,
        "task-001",
        [RequirementCoverage("FR-1", RequirementStatus.COVERED, "test", None, True)],
        [],
    )

    result = pipeline.finalize(task_root, "task-001")

    assert result.status.value == "blocked"
    assert any("测试" in blocker for blocker in result.blockers)
    assert "- blocked" in (task_root / "DELIVERABLES.md").read_text(encoding="utf-8")


def test_provider_to_agent_to_delivery_path_completes_offline(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    init_project_workspace(project_root, "project-001", "Course", "Assignment")
    task_root = init_task_workspace(project_root, "task-001")
    project_file = project_root / ".hancode" / "project.json"
    project_data = json.loads(project_file.read_text(encoding="utf-8"))
    project_data["test_command"] = "pytest -q"
    project_file.write_text(json.dumps(project_data), encoding="utf-8")
    (task_root / "SPEC.md").write_text("# Spec\n", encoding="utf-8")
    (task_root / "PLAN.md").write_text("# Plan\n", encoding="utf-8")
    state = load_state(task_root)
    save_state(
        task_root,
        replace(
            state,
            current_phase=Phase.TEST,
            phase_completed={
                **state.phase_completed,
                Phase.SPEC.value: True,
                Phase.PLAN.value: True,
                Phase.CODE.value: True,
            },
            artifacts={**state.artifacts, "SPEC.md": True, "PLAN.md": True},
        ),
    )
    config = load_config(project_root, "task-001")
    registry = build_default_tool_registry(
        config,
        run_tests_tool=lambda command: ToolResult(
            success=True,
            action_name="run_tests",
            exit_code=0,
            stdout="1 passed",
            command=command or "pytest -q",
        ),
    )
    provider = MockLLM(
        [
            {
                "type": "tool_call",
                "phase": "test",
                "tool_name": "run_tests",
                "args": {},
                "reason": None,
            },
            {"type": "finish_phase", "phase": "test", "tool_name": None, "args": {}, "reason": None},
            {
                "type": "tool_call",
                "phase": "review",
                "tool_name": "record_review",
                "args": {
                    "requirements": [
                        {
                            "requirement_id": "FR-1",
                            "status": "covered",
                            "evidence": "tests/test_app.py",
                            "risk": None,
                            "is_core": True,
                        }
                    ],
                    "risks": [],
                },
                "reason": None,
            },
            {"type": "finish_phase", "phase": "review", "tool_name": None, "args": {}, "reason": None},
            {
                "type": "tool_call",
                "phase": "deliver",
                "tool_name": "record_knowledge",
                "args": {
                    "items": [
                        {
                            "category": "design_decision",
                            "summary": "Use the delivery service.",
                            "detail": "All artifacts use the formal path.",
                            "source_trace_id": "evt-000001",
                        }
                    ]
                },
                "reason": None,
            },
            {"type": "finish_phase", "phase": "deliver", "tool_name": None, "args": {}, "reason": None},
        ]
    )

    result = create_agent_loop(
        project_root,
        "task-001",
        provider=provider,
        tool_registry=registry,
        max_steps=6,
    ).run("task-001")

    assert result.status.value == "completed", (result.error, result.final_state)
    assert load_state(task_root).status.value == "completed"
    assert (task_root / "TEST_REPORT.md").is_file()
    assert (task_root / "DELIVERABLES.md").is_file()
