"""Tests for learn-and-reflect sections on intermediate delivery artifacts."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from hancode.delivery_support.learnings import (
    ProcessStats,
    build_plan_learning,
    build_review_learning,
    build_spec_learning,
    build_test_report_learning,
    compute_process_stats,
    upsert_learning_section,
)
from hancode.delivery_support.result import (
    RequirementCoverage,
    RequirementStatus,
)
from hancode.runtime.delivery_pipeline import DeliveryPipeline
from hancode.runtime.feedback import FailureCategory, FeedbackReport
from hancode.core.models import Phase
from hancode.core.state import load_state, save_state
from hancode.storage.trace import TraceEvent
from hancode.storage.workspace import init_project_workspace, init_task_workspace


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _event(
    event_type: str,
    *,
    phase: Phase = Phase.CODE,
    status: str = "succeeded",
    observation: dict[str, object] | None = None,
    action: dict[str, object] | None = None,
) -> TraceEvent:
    return TraceEvent(
        event_id="evt-000001",
        seq=1,
        event_type=event_type,
        task_id="task-001",
        phase=phase,
        timestamp=datetime.now(UTC),
        status=status,
        observation=observation,
        action=action,
    )


def _init(tmp_path: Path) -> tuple[Path, Path]:
    project_root = tmp_path / "proj"
    project_root.mkdir()
    init_project_workspace(project_root, "proj-001", "HanCode", "Test")
    task_root = init_task_workspace(project_root, "task-001")
    return project_root, task_root


def _failed_report() -> FeedbackReport:
    return FeedbackReport(
        passed=False,
        failure_category=FailureCategory.ASSERTION_FAILURE,
        summary="1 failed, 3 passed",
        next_action_hint="Compare the implementation with the PLAN expectation.",
        failed_count=1,
        passed_count=3,
    )


def _mark_artifact(task_root: Path, filename: str, content: str) -> None:
    (task_root / filename).write_text(content, encoding="utf-8")
    state = load_state(task_root)
    save_state(task_root, replace(state, artifacts={**state.artifacts, filename: True}))


# ---------------------------------------------------------------------------
# compute_process_stats
# ---------------------------------------------------------------------------


def test_compute_process_stats_counts_trace_events() -> None:
    events = (
        _event("policy_denied", status="denied"),
        _event("policy_denied", status="denied"),
        _event("checkpoint_created"),
        _event("checkpoint_created"),
        _event("test_result_recorded", observation={"test_status": "failed"}),
        _event("rollback_performed", status="succeeded"),
    )
    stats = compute_process_stats(events)
    assert stats == ProcessStats(
        test_failures=1,
        checkpoints_created=2,
        rollbacks_performed=1,
        policy_denials=2,
    )


def test_compute_process_stats_ignores_passing_tests_and_failed_rollbacks() -> None:
    events = (
        _event("test_result_recorded", observation={"test_status": "passed"}),
        _event("rollback_performed", status="failed"),
        _event("run_completed", status="succeeded"),
    )
    stats = compute_process_stats(events)
    assert stats == ProcessStats(0, 0, 0, 0)


def test_compute_process_stats_handles_empty_events() -> None:
    assert compute_process_stats(()) == ProcessStats(0, 0, 0, 0)


# ---------------------------------------------------------------------------
# learning section builders
# ---------------------------------------------------------------------------


def test_build_test_report_learning_failed_contains_failure_chain() -> None:
    section = build_test_report_learning(_failed_report())
    assert section.startswith("## 学习与反思")
    assert "assertion_failure" in section
    assert "复盘问题" in section


def test_build_test_report_learning_passed_contains_reflection() -> None:
    report = FeedbackReport(
        passed=True,
        failure_category=FailureCategory.NONE,
        summary="1 passed",
        next_action_hint="Continue.",
        passed_count=1,
    )
    section = build_test_report_learning(report)
    assert "通过" in section
    assert "复盘问题" in section


def test_build_review_learning_reports_core_coverage() -> None:
    requirements = [
        RequirementCoverage("REQ-1", RequirementStatus.COVERED, "test.py", None, True),
        RequirementCoverage("REQ-2", RequirementStatus.PARTIAL, "x", "risk", True),
    ]
    section = build_review_learning(requirements, [])
    assert "1/2" in section
    assert "REQ-2" in section
    assert "复盘问题" in section


def test_build_spec_learning_reflects_process_facts() -> None:
    stats = ProcessStats(
        test_failures=0,
        checkpoints_created=0,
        rollbacks_performed=1,
        policy_denials=2,
    )
    section = build_spec_learning("Implement integer addition.", stats)
    assert "2" in section and "回滚" in section
    assert "复盘问题" in section


def test_build_plan_learning_reflects_process_facts() -> None:
    stats = ProcessStats(
        test_failures=2,
        checkpoints_created=3,
        rollbacks_performed=1,
        policy_denials=0,
    )
    section = build_plan_learning(stats)
    assert "3" in section and "2" in section and "1" in section
    assert "复盘问题" in section


# ---------------------------------------------------------------------------
# upsert idempotency
# ---------------------------------------------------------------------------


def test_upsert_learning_section_appends_once() -> None:
    updated = upsert_learning_section(
        "# Plan\n\nSteps.\n", "## 学习与反思\n\n- fact\n"
    )
    assert updated.count("## 学习与反思") == 1
    assert updated.startswith("# Plan")
    assert "## 学习与反思" in updated


def test_upsert_learning_section_replaces_previous_section() -> None:
    content = "# Plan\n\nSteps.\n\n## 学习与反思\n\n- old\n"
    updated = upsert_learning_section(content, "## 学习与反思\n\n- new\n")
    assert updated.count("## 学习与反思") == 1
    assert "- old" not in updated
    assert "- new" in updated


def test_upsert_learning_section_is_idempotent() -> None:
    section = "## 学习与反思\n\n- fact\n"
    once = upsert_learning_section("# P\n\ns\n", section)
    twice = upsert_learning_section(once, section)
    assert once == twice


# ---------------------------------------------------------------------------
# DeliveryPipeline integration
# ---------------------------------------------------------------------------


def test_record_test_appends_learning_section(tmp_path: Path) -> None:
    _, task_root = _init(tmp_path)
    pipeline = DeliveryPipeline()
    pipeline.record_test(task_root, _failed_report(), "pytest -q")
    content = (task_root / "TEST_REPORT.md").read_text(encoding="utf-8")
    assert "## 学习与反思" in content
    assert "assertion_failure" in content


def test_record_review_appends_learning_section(tmp_path: Path) -> None:
    _, task_root = _init(tmp_path)
    pipeline = DeliveryPipeline()
    pipeline.record_review(
        task_root,
        "task-001",
        [RequirementCoverage("REQ-1", RequirementStatus.COVERED, "t.py", None, True)],
        [],
    )
    content = (task_root / "REVIEW.md").read_text(encoding="utf-8")
    assert "## 学习与反思" in content
    assert "REQ-1" in content


def test_finalize_enhances_spec_and_plan_and_is_idempotent(tmp_path: Path) -> None:
    project_root, task_root = _init(tmp_path)
    _mark_artifact(task_root, "SPEC.md", "# SPEC\n\nRequirements.\n")
    _mark_artifact(task_root, "PLAN.md", "# PLAN\n\nSteps.\n")

    pipeline = DeliveryPipeline()
    pipeline.record_test(task_root, _failed_report(), "pytest")
    pipeline.record_review(
        task_root,
        "task-001",
        [RequirementCoverage("REQ-1", RequirementStatus.COVERED, "t.py", None, True)],
        [],
    )
    pipeline.finalize(task_root, "task-001")

    spec_content = (task_root / "SPEC.md").read_text(encoding="utf-8")
    assert "## 学习与反思" in spec_content
    assert "复盘问题" in spec_content

    pipeline.finalize(task_root, "task-001")
    assert (task_root / "SPEC.md").read_text(encoding="utf-8") == spec_content
    assert (task_root / "PLAN.md").read_text(encoding="utf-8").count("## 学习与反思") == 1


def test_finalize_enhance_skips_missing_artifacts(tmp_path: Path) -> None:
    project_root, task_root = _init(tmp_path)
    pipeline = DeliveryPipeline()
    pipeline.record_test(task_root, _failed_report(), "pytest")
    pipeline.record_review(task_root, "task-001", [], [])
    evidence = pipeline.finalize(task_root, "task-001")
    assert evidence is not None
    assert not (task_root / "SPEC.md").exists()
    assert not (task_root / "PLAN.md").exists()


def test_enhance_learning_keeps_test_report_readable(tmp_path: Path) -> None:
    _, task_root = _init(tmp_path)
    pipeline = DeliveryPipeline()
    pipeline.record_test(task_root, _failed_report(), "pytest -q")
    from hancode.tooling.delivery_tools import read_test_report
    result = read_test_report(tmp_path / "proj", task_root)
    assert result.success is True
    assert result.output.get("failure_category") == "assertion_failure"
