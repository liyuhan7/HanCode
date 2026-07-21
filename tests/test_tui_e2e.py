"""S4-T8: TUI end-to-end MockLLM demo.

Drives the full arc inside one TUI session:
launch → goal → create task → spec asks → answer → auto-resume → write SPEC →
finish spec, then verifies trace restoration via InspectionService (as a fresh
session would) and artifact preview through the allow-list.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from hancode.app.inspection_service import InspectionService
from hancode.core.models import Phase, TaskStatus
from hancode.interfaces.tui.app import HanCodeTuiApp
from hancode.providers.mock import MockLLM
from hancode.storage.workspace import init_project_workspace


def _enable_interaction(tmp_path: Path) -> None:
    init_project_workspace(tmp_path, "project-001", "Course", "Assignment")
    project_file = tmp_path / ".hancode" / "project.json"
    project = json.loads(project_file.read_text(encoding="utf-8"))
    project["interaction_mode"] = "ask_user"
    project_file.write_text(json.dumps(project), encoding="utf-8")


def _ask_actions() -> list[dict[str, object]]:
    return [
        {
            "type": "ask_user",
            "phase": Phase.SPEC.value,
            "tool_name": None,
            "args": {"question": "Which framework should be used?"},
            "reason": "The framework is ambiguous.",
        }
    ]


def _resume_actions() -> list[dict[str, object]]:
    return [
        {
            "type": "tool_call",
            "phase": Phase.SPEC.value,
            "tool_name": "write_file",
            "args": {
                "path": ".hancode/tasks/task-001/SPEC.md",
                "content": "# SPEC\n\nUse FastAPI for the CSV grade report.\n",
            },
            "reason": "Persist the specification artifact.",
        },
        {
            "type": "finish_phase",
            "phase": Phase.SPEC.value,
            "tool_name": None,
            "args": {},
            "reason": None,
        },
    ]


class _SequencedFactory:
    def __init__(self) -> None:
        self._sequences = [_ask_actions(), _resume_actions()]

    def __call__(self, config: object, *, credential: object = None) -> MockLLM:
        return MockLLM(list(self._sequences.pop(0)))


def test_tui_full_ask_answer_resume_and_inspection(tmp_path: Path) -> None:
    from hancode.app.task_service import TaskService

    _enable_interaction(tmp_path)
    service = TaskService(provider_factory=_SequencedFactory())

    async def _run() -> None:
        app = HanCodeTuiApp(project_root=tmp_path, task_service=service)
        async with app.run_test() as pilot:
            # 1. Natural-language goal creates and runs the task.
            app.submit_input("Implement a CSV grade report CLI")
            await app.workers.wait_for_complete()
            await pilot.pause()

            # 2. The spec phase paused for input.
            state = app.controller.state
            assert state.active_task is not None
            assert state.active_task.status is TaskStatus.WAITING_INPUT
            assert state.pending_interaction_id is not None
            # Trace events streamed live during the run.
            assert state.trace_events

            # 3. Answering auto-resumes and completes the spec write.
            app.submit_answer("Use FastAPI.")
            await app.workers.wait_for_complete()
            await pilot.pause()

    asyncio.run(_run())

    # 4. SPEC was written to disk.
    spec = tmp_path / ".hancode" / "tasks" / "task-001" / "SPEC.md"
    assert spec.is_file()
    assert "FastAPI" in spec.read_text(encoding="utf-8")

    # 5. A fresh session can restore the full trace via InspectionService.
    inspection = InspectionService()
    page = inspection.read_trace(tmp_path, "task-001")
    assert page.events
    seqs = [event.seq for event in page.events]
    assert seqs == sorted(seqs)
    event_types = {event.event_type for event in page.events}
    assert "interaction_requested" in event_types
    assert "interaction_answered" in event_types

    # 6. Answer text never leaks into the persisted trace.
    for event in page.events:
        blob = json.dumps(event.to_dict(), ensure_ascii=False)
        assert "Use FastAPI." not in blob


def test_tui_artifact_preview_after_completion(tmp_path: Path) -> None:
    from hancode.app.task_service import TaskService

    _enable_interaction(tmp_path)
    service = TaskService(provider_factory=_SequencedFactory())

    async def _run() -> None:
        app = HanCodeTuiApp(project_root=tmp_path, task_service=service)
        async with app.run_test() as pilot:
            app.submit_input("Implement a CSV grade report CLI")
            await app.workers.wait_for_complete()
            await pilot.pause()
            app.submit_answer("Use FastAPI.")
            await app.workers.wait_for_complete()
            await pilot.pause()

    asyncio.run(_run())

    # SPEC.md is declared present, so the allow-listed preview succeeds.
    preview = InspectionService().read_artifact(tmp_path, "task-001", "SPEC.md")
    assert "FastAPI" in preview.content
