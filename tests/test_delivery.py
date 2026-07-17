from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

import hancode.delivery as delivery
from hancode.agent_loop import AgentRunResult
from hancode.delivery import (
    DeliveryResult,
    KnowledgeCategory,
    KnowledgeItem,
    RequirementCoverage,
    RequirementStatus,
    ResultBuilder,
    write_deliverables,
    write_knowledge,
    write_review,
    write_test_report,
)
from hancode.feedback import FailureCategory, FeedbackReport
from hancode.errors import HanCodeError
from hancode.models import Phase, Risk, TaskStatus
from hancode.state import load_state, reconcile_state, save_state
from hancode.trace import TraceEvent
from hancode.workspace import init_project_workspace, init_task_workspace


def test_write_test_report_contains_command_status_summary(tmp_path: Path) -> None:
    task_root = _init_task(tmp_path)
    report = FeedbackReport(
        passed=False,
        failure_category=FailureCategory.ASSERTION_FAILURE,
        summary="1 failed, 3 passed",
        next_action_hint="Inspect the failing assertion.",
        failed_count=1,
        passed_count=3,
    )

    path = write_test_report(task_root, report, "uv run pytest")

    assert path == task_root / "TEST_REPORT.md"
    assert path.read_text(encoding="utf-8") == (
        "# 测试报告\n\n"
        "| 字段 | 值 |\n"
        "| --- | --- |\n"
        "| 命令 | `uv run pytest` |\n"
        "| 状态 | failed |\n"
        "| 失败分类 | assertion_failure |\n"
        "| 通过数 | 3 |\n"
        "| 失败数 | 1 |\n\n"
        "## 摘要\n\n"
        "1 failed, 3 passed\n\n"
        "## 下一步\n\n"
        "Inspect the failing assertion.\n"
    )
    assert load_state(task_root).artifacts["TEST_REPORT.md"] is True


def test_code_change_requires_test_or_risk_note(tmp_path: Path) -> None:
    task_root = _init_task(tmp_path)
    state = load_state(task_root)
    save_state(task_root, replace(state, current_phase=Phase.CODE))
    save_state(
        task_root,
        replace(
            load_state(task_root),
            current_phase=Phase.TEST,
            files_changed=("src/example.py",),
        ),
    )

    result = ResultBuilder().build(task_root, _run_result(task_root))

    assert result.status is TaskStatus.BLOCKED
    assert any("测试" in risk.message for risk in result.risks)


def test_review_contains_requirement_coverage_table(tmp_path: Path) -> None:
    task_root = _init_task(tmp_path)
    coverage = [
        RequirementCoverage(
            requirement_id="FR-15",
            status=RequirementStatus.COVERED,
            evidence="tests/test_delivery.py::test_write_test_report_contains_command_status_summary",
            risk=None,
            is_core=True,
        )
    ]

    path = write_review(task_root, coverage, ["Rollback evidence should be checked."])

    content = path.read_text(encoding="utf-8")
    assert content.startswith("# 审查记录\n")
    assert "| 需求 | 状态 | 证据 | 风险 |" in content
    assert "| FR-15 | covered |" in content
    assert "Rollback evidence should be checked." in content
    assert load_state(task_root).artifacts["REVIEW.md"] is True


def test_review_escapes_markdown_control_text(tmp_path: Path) -> None:
    task_root = _init_task(tmp_path)
    coverage = [
        RequirementCoverage(
            requirement_id="FR-15",
            status=RequirementStatus.COVERED,
            evidence="[evidence](https://example.test) `literal`",
            risk="[risk](https://example.test)",
            is_core=True,
        )
    ]

    content = write_review(
        task_root,
        coverage,
        ["[follow-up](https://example.test) https://example.test <b>literal</b>"],
    ).read_text(encoding="utf-8")

    assert "\\[evidence\\](https&#58;//example.test) \\`literal\\`" in content
    assert "\\[risk\\](https&#58;//example.test)" in content
    assert "\\[follow-up\\](https&#58;//example.test)" in content
    assert "https&#58;//example.test" in content
    assert "&lt;b&gt;literal&lt;/b&gt;" in content


def test_state_sync_failure_leaves_reconcilable_artifact_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_root = _init_task(tmp_path)
    original_save_state = delivery.save_state

    def fail_save_state(task_root: Path, state: object) -> None:
        raise HanCodeError(
            delivery.StructuredError(
                error_code="state_write_error",
                message="Task state could not be persisted.",
                phase=Phase.DELIVER.value,
                denied_rule="state_write_required",
                suggested_fix="Restore task state storage.",
            )
        )

    monkeypatch.setattr(delivery, "save_state", fail_save_state)

    with pytest.raises(HanCodeError) as error:
        write_test_report(
            task_root,
            FeedbackReport(
                passed=True,
                failure_category=FailureCategory.NONE,
                summary="1 passed",
                next_action_hint="Continue.",
            ),
            "uv run pytest",
        )

    assert error.value.to_dict()["error_code"] == "delivery_state_sync_failed"
    assert (task_root / "TEST_REPORT.md").is_file()
    assert load_state(task_root).artifacts["TEST_REPORT.md"] is False
    assert reconcile_state(task_root, load_state(task_root)).status is TaskStatus.INCONSISTENT
    monkeypatch.setattr(delivery, "save_state", original_save_state)


def test_write_test_report_rejects_artifact_link(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_root = _init_task(tmp_path)
    monkeypatch.setattr(delivery, "_is_link", lambda path: path.name == "TEST_REPORT.md")

    with pytest.raises(HanCodeError) as error:
        write_test_report(
            task_root,
            FeedbackReport(
                passed=True,
                failure_category=FailureCategory.NONE,
                summary="1 passed",
                next_action_hint="Continue.",
            ),
            "uv run pytest",
        )

    assert error.value.to_dict()["error_code"] == "delivery_artifact_link_not_allowed"


def test_knowledge_contains_decisions_failures_and_reusable_lessons(tmp_path: Path) -> None:
    task_root = _init_task(tmp_path)
    items = [
        KnowledgeItem(
            category=KnowledgeCategory.REQUIREMENT_UNDERSTANDING,
            summary="交付阶段只生成固定产物。",
            detail="不修改业务代码。",
            source_phase=Phase.DELIVER,
            source_trace_id="evt-000001",
        ),
        KnowledgeItem(
            category=KnowledgeCategory.DESIGN_DECISION,
            summary="报告使用稳定 Markdown 表格。",
            detail="便于课程检查。",
            source_phase=Phase.REVIEW,
            source_trace_id="evt-000002",
        ),
        KnowledgeItem(
            category=KnowledgeCategory.TESTING_EXPERIENCE,
            summary="先观察失败测试。",
            detail="测试输出应有命令和分类。",
            source_phase=Phase.TEST,
            source_trace_id="evt-000003",
        ),
        KnowledgeItem(
            category=KnowledgeCategory.ERROR_FIX,
            summary="断言失败需要明确修正路径。",
            detail="不要盲目重试。",
            source_phase=Phase.REVIEW,
            source_trace_id="evt-000004",
        ),
        KnowledgeItem(
            category=KnowledgeCategory.REUSABLE_PATTERN,
            summary="所有产物都使用原子写入。",
            detail="避免部分文件。",
            source_phase=Phase.DELIVER,
            source_trace_id="evt-000005",
        ),
    ]

    path = write_knowledge(task_root, items)

    content = path.read_text(encoding="utf-8")
    for heading in ("需求理解", "设计决策", "测试经验", "错误修复", "可复用模式"):
        assert f"## {heading}" in content
    assert "evt-000003" in content
    assert load_state(task_root).artifacts["KNOWLEDGE.md"] is True


def test_write_knowledge_requires_at_least_one_trace_reference(tmp_path: Path) -> None:
    task_root = _init_task(tmp_path)
    items = [replace(item, source_trace_id="") for item in _knowledge_items()]

    with pytest.raises(HanCodeError) as error:
        write_knowledge(task_root, items)

    assert error.value.to_dict()["error_code"] == "delivery_knowledge_provenance_required"


def test_deliver_requires_knowledge_file(tmp_path: Path) -> None:
    task_root = _init_task(tmp_path)

    result = ResultBuilder().build(task_root, _run_result(task_root))

    assert result.status is TaskStatus.BLOCKED
    assert any("KNOWLEDGE.md" in risk.message for risk in result.risks)


def test_deliver_requires_deliverables_file(tmp_path: Path) -> None:
    task_root = _init_task(tmp_path)
    _write_required_artifacts(task_root)

    result = ResultBuilder().build(task_root, _run_result(task_root))

    assert result.status is TaskStatus.BLOCKED
    assert any("DELIVERABLES.md" in risk.message for risk in result.risks)


def test_deliverables_records_missing_test_and_review_as_risks(tmp_path: Path) -> None:
    task_root = _init_task(tmp_path)

    path = write_deliverables(task_root, _run_result(task_root))

    content = path.read_text(encoding="utf-8")
    assert "缺少通过的测试结果。" in content
    assert "缺少必需交付物：TEST_REPORT.md。" in content
    assert "缺少必需交付物：REVIEW.md。" in content


def test_deliver_with_failed_tests_returns_blocked(tmp_path: Path) -> None:
    task_root = _init_task(tmp_path)
    _write_required_artifacts(task_root)
    state = load_state(task_root)
    save_state(
        task_root,
        replace(
            state,
            latest_test_status="failed",
            tests_run=("uv run pytest",),
        ),
    )
    write_deliverables(task_root, _run_result(task_root))

    result = ResultBuilder().build(task_root, _run_result(task_root))

    assert result.status is TaskStatus.BLOCKED
    assert any("测试失败" in risk.message for risk in result.risks)


def test_result_builder_returns_coverage_and_knowledge_items(tmp_path: Path) -> None:
    task_root = _init_task(tmp_path)
    coverage = [
        RequirementCoverage(
            requirement_id="FR-15",
            status=RequirementStatus.COVERED,
            evidence="tests/test_delivery.py",
            risk=None,
            is_core=True,
        )
    ]
    knowledge_items = _knowledge_items()
    _write_required_artifacts(task_root)
    write_deliverables(task_root, _run_result(task_root), coverage)

    result = ResultBuilder().build(
        task_root,
        _run_result(task_root),
        coverage,
        knowledge_items,
    )

    assert result.status is TaskStatus.COMPLETED
    assert result.requirements_coverage == tuple(coverage)
    assert result.knowledge_items == tuple(knowledge_items)


def test_deliverables_status_uses_covered_core_requirements(tmp_path: Path) -> None:
    task_root = _init_task(tmp_path)
    coverage = [
        RequirementCoverage(
            requirement_id="FR-15",
            status=RequirementStatus.COVERED,
            evidence="tests/test_delivery.py",
            risk=None,
            is_core=True,
        )
    ]
    _write_required_artifacts(task_root)

    path = write_deliverables(task_root, _run_result(task_root), coverage)

    assert "## 最终状态\n\n- completed\n" in path.read_text(encoding="utf-8")


def test_result_builder_redacts_and_serializes_required_fields(tmp_path: Path) -> None:
    task_root = _init_task(tmp_path)
    coverage = [
        RequirementCoverage(
            requirement_id="FR-15",
            status=RequirementStatus.COVERED,
            evidence="token=delivery-secret",
            risk="secret=delivery-secret",
            is_core=True,
        )
    ]
    knowledge_items = [
        KnowledgeItem(
            category=category,
            summary="token=delivery-secret",
            detail="token=delivery-secret",
            source_phase=Phase.DELIVER,
            source_trace_id="evt-000001",
        )
        for category in KnowledgeCategory
    ]
    _write_required_artifacts(task_root)
    run_result = replace(
        _run_result(task_root),
        risks=(Risk(level="high", message="token=delivery-secret"),),
    )
    write_deliverables(task_root, run_result, coverage)

    serialized = ResultBuilder().build(
        task_root,
        run_result,
        coverage,
        knowledge_items,
    ).to_dict()

    assert {
        "status",
        "task_id",
        "course_project_summary",
        "requirements_covered",
        "files_changed",
        "tests_run",
        "test_status",
        "checkpoints",
        "rollback_performed",
        "deliverables",
        "knowledge_items",
        "risks",
        "next_steps",
        "trace_event_ids",
    } <= set(serialized)
    assert serialized["trace_event_ids"] == ["evt-000001"]
    assert "delivery-secret" not in json.dumps(serialized)


def test_delivery_result_to_dict_redacts_directly_constructed_values() -> None:
    result = DeliveryResult(
        status=TaskStatus.COMPLETED,
        task_id="Authorization: Basic ZGVsaXZlcnktc2VjcmV0",
        course_project_summary="token=delivery-secret",
        requirements_coverage=(
            RequirementCoverage(
                requirement_id="token=delivery-secret",
                status=RequirementStatus.COVERED,
                evidence="token=delivery-secret",
                risk="token=delivery-secret",
                is_core=True,
            ),
        ),
        files_changed=("token=delivery-secret",),
        tests_run=("token=delivery-secret",),
        latest_test_status="passed",
        latest_checkpoint="token=delivery-secret",
        rollback_done=False,
        deliverables=("token=delivery-secret",),
        knowledge_items=(
            KnowledgeItem(
                category=KnowledgeCategory.DESIGN_DECISION,
                summary="token=delivery-secret",
                detail="token=delivery-secret",
                source_phase=Phase.DELIVER,
                source_trace_id="token=delivery-secret",
            ),
        ),
        trace_event_ids=("token=delivery-secret",),
        risks=(Risk(level="token=delivery-secret", message="token=delivery-secret"),),
        next_steps=("token=delivery-secret",),
    )

    serialized = json.dumps(result.to_dict())

    assert "delivery-secret" not in serialized
    assert "ZGVsaXZlcnktc2VjcmV0" not in serialized


def test_result_builder_blocks_when_delivery_coverage_differs_from_receipt(
    tmp_path: Path,
) -> None:
    task_root = _init_task(tmp_path)
    coverage = [
        RequirementCoverage(
            requirement_id="FR-15",
            status=RequirementStatus.COVERED,
            evidence="tests/test_delivery.py",
            risk=None,
            is_core=True,
        )
    ]
    _write_required_artifacts(task_root)
    write_deliverables(task_root, _run_result(task_root))

    result = ResultBuilder().build(task_root, _run_result(task_root), coverage)

    assert result.status is TaskStatus.BLOCKED
    assert any("覆盖" in risk.message for risk in result.risks)


def test_delivery_status_is_persisted_and_not_overridden_by_stale_run_result(
    tmp_path: Path,
) -> None:
    task_root = _init_task(tmp_path)
    coverage = [
        RequirementCoverage(
            requirement_id="FR-15",
            status=RequirementStatus.COVERED,
            evidence="tests/test_delivery.py",
            risk=None,
            is_core=True,
        )
    ]
    _write_required_artifacts(task_root)

    path = write_deliverables(task_root, _run_result(task_root), coverage)
    stale_result = replace(_run_result(task_root), status=TaskStatus.BLOCKED)
    result = ResultBuilder().build(task_root, stale_result, coverage)

    assert "## 最终状态\n\n- completed\n" in path.read_text(encoding="utf-8")
    assert load_state(task_root).status is TaskStatus.COMPLETED
    assert result.status is TaskStatus.COMPLETED


@pytest.mark.parametrize("status", [TaskStatus.BLOCKED, TaskStatus.INCONSISTENT])
def test_result_builder_preserves_non_completed_task_state(
    tmp_path: Path, status: TaskStatus
) -> None:
    task_root = _init_task(tmp_path)
    coverage = [
        RequirementCoverage(
            requirement_id="FR-15",
            status=RequirementStatus.COVERED,
            evidence="tests/test_delivery.py",
            risk=None,
            is_core=True,
        )
    ]
    _write_required_artifacts(task_root)
    write_deliverables(task_root, _run_result(task_root), coverage)
    state = load_state(task_root)
    save_state(
        task_root,
        replace(
            state,
            status=status,
            inconsistent=status is TaskStatus.INCONSISTENT,
        ),
    )

    result = ResultBuilder().build(task_root, _run_result(task_root), coverage)

    assert result.status is status


def test_write_deliverables_rejects_artifact_drift(tmp_path: Path) -> None:
    task_root = _init_task(tmp_path)
    _write_required_artifacts(task_root)
    (task_root / "TEST_REPORT.md").unlink()

    with pytest.raises(HanCodeError) as error:
        write_deliverables(task_root, _run_result(task_root))

    assert error.value.to_dict()["error_code"] == "delivery_state_inconsistent"


def test_write_deliverables_rejects_non_run_result(tmp_path: Path) -> None:
    task_root = _init_task(tmp_path)
    original_state = load_state(task_root)

    with pytest.raises(HanCodeError) as error:
        write_deliverables(task_root, object())  # type: ignore[arg-type]

    assert error.value.to_dict()["error_code"] == "delivery_result_invalid"
    assert load_state(task_root) == original_state


def test_result_builder_rejects_link_task_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_root = _init_task(tmp_path)
    monkeypatch.setattr(delivery, "_is_link", lambda path: path == task_root)

    with pytest.raises(HanCodeError) as error:
        ResultBuilder().build(task_root, _run_result(task_root))

    assert error.value.to_dict()["error_code"] == "delivery_path_invalid"


def test_delivery_link_check_fails_closed_when_junction_probe_is_indeterminate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_root = _init_task(tmp_path)
    run_result = _run_result(task_root)
    monkeypatch.setattr(
        Path,
        "is_junction",
        lambda _path: (_ for _ in ()).throw(AttributeError("st_reparse_tag")),
    )

    with pytest.raises(HanCodeError) as error:
        ResultBuilder().build(task_root, run_result)

    assert error.value.to_dict()["error_code"] == "delivery_path_invalid"


@pytest.mark.parametrize(
    "status",
    [RequirementStatus.PARTIAL, RequirementStatus.MISSING, RequirementStatus.UNTESTED],
)
def test_core_requirement_without_covered_evidence_blocks_delivery(
    tmp_path: Path, status: RequirementStatus
) -> None:
    task_root = _init_task(tmp_path)
    coverage = [
        RequirementCoverage(
            requirement_id="FR-16",
            status=status,
            evidence="tests/test_delivery.py",
            risk="Needs evidence.",
            is_core=True,
        )
    ]
    _write_required_artifacts(task_root)
    write_deliverables(task_root, _run_result(task_root), coverage)

    result = ResultBuilder().build(task_root, _run_result(task_root), coverage)

    assert result.status is TaskStatus.BLOCKED
    assert any("FR-16" in risk.message for risk in result.risks)


def _write_required_artifacts(task_root: Path) -> None:
    write_test_report(
        task_root,
        FeedbackReport(
            passed=True,
            failure_category=FailureCategory.NONE,
            summary="1 passed",
            next_action_hint="Continue.",
            passed_count=1,
        ),
        "uv run pytest",
    )
    write_review(
        task_root,
        [
            RequirementCoverage(
                requirement_id="FR-15",
                status=RequirementStatus.COVERED,
                evidence="tests/test_delivery.py",
                risk=None,
                is_core=True,
            )
        ],
        [],
    )
    write_knowledge(
        task_root,
        _knowledge_items(),
    )
    state = load_state(task_root)
    save_state(
        task_root,
        replace(
            state,
            latest_test_status="passed",
            tests_run=("uv run pytest",),
        ),
    )


def _knowledge_items() -> list[KnowledgeItem]:
    return [
        KnowledgeItem(
            category=category,
            summary=category.value,
            detail="Evidence is recorded.",
            source_phase=Phase.DELIVER,
            source_trace_id="evt-000001",
        )
        for category in KnowledgeCategory
    ]


def _init_task(tmp_path: Path) -> Path:
    project_root = tmp_path / "project"
    project_root.mkdir()
    init_project_workspace(
        project_root,
        project_id="project-001",
        course_name="Software Engineering",
        assignment_name="Delivery artifacts",
    )
    return init_task_workspace(project_root, "task-001")


def _run_result(task_root: Path) -> AgentRunResult:
    state = load_state(task_root)
    return AgentRunResult(
        status=state.status,
        steps=1,
        tool_calls=(),
        risks=(Risk(level="info", message="No additional risks."),),
        final_observation=None,
        error=None,
        final_state=state,
        retry_budget_remaining=state.retry_budget_remaining,
        trace_events=(
            TraceEvent(
                event_id="evt-000001",
                seq=1,
                event_type="run_completed",
                task_id=state.task_id,
                phase=Phase.DELIVER,
                timestamp=datetime.now(UTC),
                status="succeeded",
            ),
        ),
    )
