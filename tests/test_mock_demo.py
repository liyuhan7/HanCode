from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
import shutil

import pytest

from hancode.demo_support import runner as demo
from hancode.core.errors import HanCodeError, StructuredError
from hancode.core.models import Phase, TaskStatus


_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_FIXTURE_ROOT = _REPOSITORY_ROOT / "examples" / "broken_project"


def _copy_fixture(tmp_path: Path) -> Path:
    assert _FIXTURE_ROOT.is_dir(), "T23 broken-project fixture must exist."
    project_root = tmp_path / "broken_project"
    shutil.copytree(_FIXTURE_ROOT, project_root, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return project_root


def test_mock_demo_runs_without_real_credentials_and_generates_delivery_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "HANCODE_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    project_root = _copy_fixture(tmp_path)
    result = demo.run_mock_demo(project_root)

    task_root = project_root / ".hancode" / "tasks" / "task-001"
    assert result.status is TaskStatus.COMPLETED
    assert result.final_state.status is TaskStatus.COMPLETED
    assert result.final_state.latest_test_status == "passed"
    assert result.final_state.rollback_done is True
    assert all(
        (task_root / artifact).is_file()
        for artifact in (
            "SPEC.md",
            "PLAN.md",
            "TEST_REPORT.md",
            "REVIEW.md",
            "KNOWLEDGE.md",
            "DELIVERABLES.md",
        )
    )
    test_report = (task_root / "TEST_REPORT.md").read_text(encoding="utf-8")
    assert "Ran 1 test" in test_report


def test_mock_demo_reuses_default_registry_with_injected_test_tool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[object] = []
    original = demo.build_default_tool_registry

    def build_registry(config: object, *, run_tests_tool: object = None) -> object:
        captured.append(run_tests_tool)
        return original(config, run_tests_tool=run_tests_tool)  # type: ignore[arg-type]

    monkeypatch.setattr(demo, "build_default_tool_registry", build_registry)

    result = demo.run_mock_demo(_copy_fixture(tmp_path))

    assert result.status is TaskStatus.COMPLETED
    assert len(captured) == 1
    assert callable(captured[0])


def test_mock_demo_trace_proves_the_required_control_flow(tmp_path: Path) -> None:
    project_root = _copy_fixture(tmp_path)
    result = demo.run_mock_demo(project_root)
    task_root = project_root / ".hancode" / "tasks" / "task-001"
    events = [
        json.loads(line)
        for line in (task_root / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    event_types = [event["event_type"] for event in events]

    assert result.status is TaskStatus.COMPLETED
    assert {
        "task_started",
        "policy_denied",
        "checkpoint_created",
        "test_completed",
        "feedback_generated",
        "retry_budget_consumed",
        "rollback_performed",
        "deliverable_created",
        "run_completed",
    }.issubset(event_types)
    assert any(
        event["event_type"] == "policy_denied"
        and event["action"]["args"]["path"] == "assignment.md"
        for event in events
    )
    assert any(
        event["event_type"] == "feedback_generated"
        and event["observation"]["failure_category"] == "assertion_failure"
        for event in events
    )
    assert events[-1]["event_type"] == "run_completed"


def test_mock_demo_rolls_back_retry_and_preserves_the_protected_assignment(
    tmp_path: Path,
) -> None:
    project_root = _copy_fixture(tmp_path)
    assignment_before = (project_root / "assignment.md").read_text(encoding="utf-8")

    result = demo.run_mock_demo(project_root)

    task_root = project_root / ".hancode" / "tasks" / "task-001"
    events = [
        json.loads(line)
        for line in (task_root / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    retry = next(event for event in events if event["event_type"] == "retry_budget_consumed")
    rollback = next(event for event in events if event["event_type"] == "rollback_performed")

    assert result.final_state.retry_budget_remaining == 0
    assert retry["observation"] == {"before": 1, "after": 0}
    assert rollback["status"] == "succeeded"
    assert rollback["observation"]["restored_files"] == ["src/calculator.py"]
    assert (project_root / "assignment.md").read_text(encoding="utf-8") == assignment_before


def test_mock_demo_is_repeatable_in_fresh_workspaces(tmp_path: Path) -> None:
    first_root = _copy_fixture(tmp_path / "first")
    second_root = _copy_fixture(tmp_path / "second")

    first = demo.run_mock_demo(first_root)
    second = demo.run_mock_demo(second_root)

    def signature(project_root: Path) -> list[tuple[str, str, str]]:
        trace_path = project_root / ".hancode" / "tasks" / "task-001" / "trace.jsonl"
        return [
            (event["event_type"], event["phase"], event["status"])
            for event in (json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines())
        ]

    assert first.status is TaskStatus.COMPLETED
    assert second.status is TaskStatus.COMPLETED
    assert signature(first_root) == signature(second_root)


def test_mock_demo_rejects_a_non_clean_project_root(tmp_path: Path) -> None:
    project_root = tmp_path / "not-a-demo-fixture"
    project_root.mkdir()
    (project_root / "existing.txt").write_text("keep me", encoding="utf-8")

    with pytest.raises(HanCodeError) as error:
        demo.run_mock_demo(project_root)

    assert error.value.structured_error.error_code == "mock_demo_fixture_required"
    assert (project_root / "existing.txt").read_text(encoding="utf-8") == "keep me"


def test_mock_demo_rejects_a_tampered_fixture_before_initializing_workspace(
    tmp_path: Path,
) -> None:
    project_root = _copy_fixture(tmp_path)
    assignment = project_root / "assignment.md"
    assignment.write_text("tampered", encoding="utf-8")

    with pytest.raises(HanCodeError) as error:
        demo.run_mock_demo(project_root)

    assert error.value.structured_error.error_code == "mock_demo_fixture_required"
    assert not (project_root / ".hancode").exists()


def test_delivery_gate_only_accepts_the_expected_missing_artifact_boundary(
    tmp_path: Path,
) -> None:
    completed = demo.run_mock_demo(_copy_fixture(tmp_path))
    artifacts = dict(completed.final_state.artifacts)
    artifacts["KNOWLEDGE.md"] = False
    artifacts["DELIVERABLES.md"] = False
    gate_state = replace(
        completed.final_state,
        status=TaskStatus.BLOCKED,
        current_phase=Phase.REVIEW,
        artifacts=artifacts,
    )
    expected_gate_result = replace(
        completed,
        status=TaskStatus.BLOCKED,
        final_state=gate_state,
        error=StructuredError(
            error_code="max_steps_exceeded",
            message="expected demo boundary",
            phase=Phase.REVIEW.value,
            denied_rule="max_steps_limit",
            suggested_fix="continue the demo delivery orchestration",
        ),
    )
    unexpected_gate_result = replace(
        expected_gate_result,
        error=replace(expected_gate_result.error, error_code="trace_write_failed"),
    )
    wrong_phase_gate_result = replace(
        expected_gate_result,
        error=replace(expected_gate_result.error, phase=Phase.DELIVER.value),
    )
    wrong_rule_gate_result = replace(
        expected_gate_result,
        error=replace(expected_gate_result.error, denied_rule="other_rule"),
    )

    assert demo._is_expected_delivery_gate(gate_state, expected_gate_result) is True
    assert demo._is_expected_delivery_gate(gate_state, unexpected_gate_result) is False
    assert demo._is_expected_delivery_gate(gate_state, wrong_phase_gate_result) is False
    assert demo._is_expected_delivery_gate(gate_state, wrong_rule_gate_result) is False


def test_mock_demo_failure_result_uses_the_persisted_trace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_root = _copy_fixture(tmp_path)

    def fail_knowledge(*_args: object, **_kwargs: object) -> Path:
        raise HanCodeError(
            StructuredError(
                error_code="forced_knowledge_failure",
                message="force the demo failure boundary",
                phase=Phase.DELIVER.value,
                denied_rule="test_stub",
                suggested_fix="remove the deterministic test stub",
            )
        )

    monkeypatch.setattr(demo, "write_knowledge", fail_knowledge)

    result = demo.run_mock_demo(project_root)

    persisted = [
        json.loads(line)
        for line in (
            project_root / ".hancode" / "tasks" / "task-001" / "trace.jsonl"
        ).read_text(encoding="utf-8").splitlines()
    ]
    assert result.status is TaskStatus.BLOCKED
    assert [(event.event_id, event.seq) for event in result.trace_events] == [
        (event["event_id"], event["seq"]) for event in persisted
    ]


def test_packaged_mock_demo_runs_without_repository_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    result = demo.run_packaged_mock_demo()

    assert result.status is TaskStatus.COMPLETED
    assert set(result.deliverables) == {
        "SPEC.md",
        "PLAN.md",
        "TEST_REPORT.md",
        "REVIEW.md",
        "KNOWLEDGE.md",
        "DELIVERABLES.md",
    }
