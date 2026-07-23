"""S5-R6 product-path Textual tests using deterministic fake services."""

from __future__ import annotations

import asyncio
from pathlib import Path

from hancode.app.delivery_inspection_service import (
    DeliverySummary,
    TestReportSummary as ReportSummary,
)
from hancode.app.task_models import TaskSummary
from hancode.core.change_models import (
    ChangeType,
    CheckpointSummary,
    DiffScope,
    FileDiff,
    TaskDiff,
)
from hancode.core.models import Phase, TaskStatus
from hancode.core.state import TaskState
from hancode.interfaces.tui.app import HanCodeTuiApp
from hancode.interfaces.tui.operations import TuiServices
from hancode.interfaces.tui.presenters import DetailKind
from hancode.runtime.agent_loop import AgentRunResult
from hancode.storage.export import ExportResult


def _summary(status: TaskStatus = TaskStatus.CREATED) -> TaskSummary:
    return TaskSummary(
        task_id="task-001",
        goal="Build a report",
        status=status,
        current_phase=Phase.DELIVER if status is TaskStatus.COMPLETED else Phase.SPEC,
        retry_budget_remaining=2,
        latest_test_status="passed" if status is TaskStatus.COMPLETED else "none",
        files_changed=("src/main.py",),
        tests_run=("pytest -q",),
        latest_checkpoint="ckpt-001",
        rollback_required=False,
        inconsistent=False,
        artifacts={
            "SPEC.md": False,
            "PLAN.md": False,
            "TEST_REPORT.md": True,
            "REVIEW.md": False,
            "KNOWLEDGE.md": False,
            "DELIVERABLES.md": False,
        },
        resumable=False,
    )


def _completed_result() -> AgentRunResult:
    state = TaskState(
        schema_version=1,
        task_id="task-001",
        goal="Build a report",
        status=TaskStatus.COMPLETED,
        current_phase=Phase.DELIVER,
        files_changed=("src/main.py",),
        latest_checkpoint="ckpt-001",
        checkpoint_seq=1,
        tests_run=("pytest -q",),
        latest_test_status="passed",
        test_status_consumed=True,
        retry_budget_remaining=2,
        inconsistent=False,
        source_edits_this_phase=0,
        rollback_required=False,
        rollback_done=False,
        phase_completed={phase.value: True for phase in Phase},
        artifacts={
            "SPEC.md": False,
            "PLAN.md": False,
            "TEST_REPORT.md": True,
            "REVIEW.md": False,
            "KNOWLEDGE.md": False,
            "DELIVERABLES.md": False,
        },
    )
    return AgentRunResult(
        status=TaskStatus.COMPLETED,
        steps=1,
        tool_calls=(),
        risks=(),
        final_observation=None,
        error=None,
        final_state=state,
        retry_budget_remaining=2,
        trace_events=(),
    )


class _TaskService:
    def __init__(self) -> None:
        self.summary = _summary()
        self.run_calls: list[tuple[str, bool]] = []

    def create(self, project_root: Path, goal: str) -> TaskSummary:
        return self.summary

    def list_tasks(self, project_root: Path) -> tuple[TaskSummary, ...]:
        return (self.summary,)

    def get(self, project_root: Path, task_id: str) -> TaskSummary:
        return self.summary

    def run(
        self,
        project_root: Path,
        task_id: str,
        *,
        resume: bool = False,
        trace_observer: object = None,
    ) -> AgentRunResult:
        self.run_calls.append((task_id, resume))
        self.summary = _summary(TaskStatus.COMPLETED)
        return _completed_result()


def _unused_services() -> dict[str, object]:
    return {
        "interaction": object(),
        "approval": object(),
        "inspection": object(),
        "changes": object(),
        "test_reports": object(),
        "checkpoints": object(),
        "recovery": object(),
    }


def test_tui_basic_create_run_completed(tmp_path: Path) -> None:
    task = _TaskService()
    values = _unused_services()
    app = HanCodeTuiApp(
        project_root=tmp_path,
        services=TuiServices(task=task, delivery=object(), **values),  # type: ignore[arg-type]
    )

    async def _run() -> None:
        async with app.run_test() as pilot:
            app.submit_input("Build a report")
            await app.workers.wait_for_complete()
            for _ in range(3):
                await pilot.pause()

    asyncio.run(_run())
    assert task.run_calls == [("task-001", False)]
    assert app.controller.state.active_task is not None
    assert app.controller.state.active_task.status is TaskStatus.COMPLETED


class _InspectionServices:
    def __init__(self) -> None:
        self.finalize_calls = 0
        self.export_calls: list[Path] = []

    def get_diff(self, project_root: Path, task_id: str, *, scope, path):  # type: ignore[no-untyped-def]
        return TaskDiff(
            task_id=task_id,
            scope=DiffScope(scope),
            checkpoint_ids=("ckpt-001",),
            files=(
                FileDiff(
                    path="src/main.py",
                    change_type=ChangeType.MODIFIED,
                    before_sha256=None,
                    current_sha256=None,
                    binary=False,
                    drifted=False,
                    unified_diff="@@ -1 +1 @@",
                    truncated=False,
                ),
            ),
            truncated=False,
            risks=(),
        )

    def read_test_report(self, project_root: Path, task_id: str) -> ReportSummary:
        return ReportSummary("passed", "pytest -q", 4, 0, "4 passed", False)

    def list_checkpoints(
        self, project_root: Path, task_id: str
    ) -> tuple[CheckpointSummary, ...]:
        return (
            CheckpointSummary(
                checkpoint_id="ckpt-001",
                phase=Phase.DELIVER,
                reason="latest",
                created_at="2026-07-23T00:00:00+00:00",
                status="committed",
                files=("src/main.py",),
                rollback_available=True,
            ),
        )

    def read_delivery_summary(self, project_root: Path, task_id: str) -> DeliverySummary:
        return DeliverySummary(
            task_id=task_id,
            status="ready",
            blockers=(),
            latest_test_status="passed",
            latest_build_status="passed",
            requirements=(),
            knowledge_count=0,
            artifacts={"TEST_REPORT.md": True},
            export_ready=True,
        )

    def get_result(self, project_root: Path, task_id: str) -> None:
        self.finalize_calls += 1
        raise AssertionError("delivery inspection must not finalize")

    def export(self, project_root: Path, task_id: str, output_dir: Path) -> ExportResult:
        self.export_calls.append(output_dir)
        return ExportResult(task_id, output_dir, ("TEST_REPORT.md",))


def test_tui_delivery_inspection_and_export_path(tmp_path: Path) -> None:
    task = _TaskService()
    services = _InspectionServices()
    values = _unused_services()
    values.update(
        {
            "changes": services,
            "test_reports": services,
            "checkpoints": services,
        }
    )
    app = HanCodeTuiApp(
        project_root=tmp_path,
        services=TuiServices(task=task, delivery=services, **values),  # type: ignore[arg-type]
    )
    app.controller.set_active_summary(_summary(TaskStatus.COMPLETED))

    async def _run() -> None:
        async with app.run_test():
            for command, detail_kind in (
                ("/diff latest", DetailKind.DIFF),
                ("/test", DetailKind.TEST_REPORT),
                ("/checkpoints", DetailKind.CHECKPOINTS),
                ("/delivery", DetailKind.DELIVERY),
            ):
                app.submit_input(command)
                await app.workers.wait_for_complete()
                await asyncio.sleep(0)
                assert app.controller.state.detail_kind is detail_kind
            app.submit_input(f"/export {tmp_path / 'delivery'}")
            await app.workers.wait_for_complete()
            await asyncio.sleep(0)

    asyncio.run(_run())
    assert services.finalize_calls == 0
    assert services.export_calls == [tmp_path / "delivery"]
