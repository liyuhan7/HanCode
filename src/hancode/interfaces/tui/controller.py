"""Textual-independent session controller (S4-T5).

The controller owns the immutable :class:`TuiViewState`, drives application
services, and enforces the single-run (busy) constraint. It performs no Textual
rendering, so its orchestration logic is fully unit-testable. The Textual app
layer forwards user intents to it and reads ``controller.state`` to render.
"""

from __future__ import annotations

from pathlib import Path

from dataclasses import replace

from hancode.app.inspection_service import InspectionService
from hancode.app.task_models import TaskSummary
from hancode.app.task_service import TaskService
from hancode.core.errors import HanCodeError
from hancode.interfaces.tui.view_state import (
    TuiViewState,
    reduce_run_finished,
    reduce_task_selected,
    reduce_trace_arrived,
)
from hancode.storage.trace import TraceEvent


class TuiSessionController:
    """Maps user intents to application services and holds the view state."""

    def __init__(
        self,
        project_root: Path,
        *,
        task_service: TaskService | None = None,
        inspection_service: InspectionService | None = None,
    ) -> None:
        self._project_root = project_root
        self._task_service = task_service or TaskService()
        self._inspection_service = inspection_service or InspectionService()
        self._state = TuiViewState.initial(project_root)

    @property
    def state(self) -> TuiViewState:
        return self._state

    # -- queries ---------------------------------------------------------

    def can_mutate(self) -> bool:
        """Whether mutating commands (/run, /rollback, new goal) are allowed."""
        return not self._state.busy

    # -- task selection and listing --------------------------------------

    def refresh_tasks(self) -> None:
        tasks = self._task_service.list_tasks(self._project_root)
        self._state = self._replace(tasks=tuple(tasks))

    def select_task(self, task_id: str) -> None:
        summary = self._task_service.get(self._project_root, task_id)
        # Clear the previous task's feed before restoring the selected one, so
        # events from different tasks never mix in the activity log.
        self._state = replace(
            self._state, trace_events=(), selected_event_id=None
        )
        self._state = reduce_task_selected(self._state, summary)
        self._restore_trace(task_id)

    def _restore_trace(self, task_id: str) -> None:
        try:
            page = self._inspection_service.read_trace(self._project_root, task_id)
        except HanCodeError:
            # A corrupt/unreadable trace must not break selection; start empty.
            return
        self._state = replace(self._state, trace_events=tuple(page.events))

    # -- run lifecycle ---------------------------------------------------

    def mark_running(self, task_id: str) -> None:
        self._state = self._state.with_busy(True, running_task_id=task_id)

    def on_trace(self, event: TraceEvent) -> None:
        self._state = reduce_trace_arrived(self._state, event)

    def clear_activity(self) -> None:
        """Drop the in-memory activity feed; the trace file is not affected."""
        self._state = replace(self._state, trace_events=(), selected_event_id=None)

    def on_run_finished(self) -> None:
        running_task_id = self._state.running_task_id
        self._state = reduce_run_finished(self._state)
        if running_task_id is not None:
            try:
                summary = self._task_service.get(self._project_root, running_task_id)
            except HanCodeError:
                return
            self._state = reduce_task_selected(self._state, summary)

    def set_active_summary(self, summary: TaskSummary) -> None:
        self._state = reduce_task_selected(self._state, summary)

    # -- helpers ---------------------------------------------------------

    def _replace(self, **changes: object) -> TuiViewState:
        return replace(self._state, **changes)  # type: ignore[arg-type]


__all__ = ["TuiSessionController"]
