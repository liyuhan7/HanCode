"""Textual application entry point for the HanCode TUI (S4-T1, S4-T5, S4-T6).

The app is the only Textual-aware layer. It:
- forwards composer input to :class:`TuiSessionController` and the CommandParser,
- runs AgentLoop in a background Worker (never on the UI thread),
- receives trace/run messages posted by the Worker and updates widgets.

The Worker posts :mod:`messages` — it never touches widgets directly. A single
Task Worker runs at a time (the controller's ``busy`` flag guards this).
"""

from __future__ import annotations

from pathlib import Path

from textual.app import App
from textual.widgets import Input
from textual.worker import Worker, get_current_worker

from hancode.app.inspection_service import InspectionService
from hancode.app.interaction_service import InteractionService
from hancode.app.recovery_service import RecoveryService, RollbackPreview
from hancode.app.task_service import TaskService
from hancode.core.errors import HanCodeError
from hancode.interfaces.tui.commands import (
    PlainTextIntent,
    TuiCommand,
    TuiCommandError,
    classify_plain_text,
    parse_command,
)
from hancode.interfaces.tui.controller import TuiSessionController
from hancode.interfaces.tui.messages import RunFailed, RunFinished, TraceArrived
from hancode.interfaces.tui.screens.main import MainScreen
from hancode.storage.trace import TraceEvent


class _WorkerTraceObserver:
    """Posts each persisted trace event to the app as a Textual message."""

    def __init__(self, app: "HanCodeTuiApp") -> None:
        self._app = app

    def on_trace(self, event: TraceEvent) -> None:
        self._app.call_from_thread(self._app.post_message, TraceArrived(event))


class HanCodeTuiApp(App[None]):
    """Interactive terminal session for the HanCode harness."""

    TITLE = "HanCode"

    def __init__(
        self,
        *,
        project_root: Path,
        task_service: TaskService | None = None,
        interaction_service: InteractionService | None = None,
        inspection_service: InspectionService | None = None,
        recovery_service: RecoveryService | None = None,
    ) -> None:
        super().__init__()
        self._project_root = project_root
        self._task_service = task_service or TaskService()
        self._interaction_service = interaction_service or InteractionService()
        self._inspection_service = inspection_service or InspectionService()
        self._recovery_service = recovery_service or RecoveryService()
        self._pending_rollback: RollbackPreview | None = None
        self.controller = TuiSessionController(
            project_root, task_service=self._task_service
        )

    def on_mount(self) -> None:
        self.push_screen(MainScreen(project_root=self._project_root))

    def on_input_submitted(self, event: "Input.Submitted") -> None:
        if event.input.id == "tui-composer":
            value = event.value
            event.input.value = ""
            self.submit_input(value)

    # -- composer submission --------------------------------------------

    def submit_input(self, raw: str) -> None:
        """Handle one composer submission (command or plain text)."""
        text = raw.strip()
        if not text:
            return
        if text.startswith("/"):
            self._handle_command(parse_command(text))
            return
        self._handle_plain_text(text)

    def _handle_command(self, command: TuiCommand | TuiCommandError) -> None:
        if isinstance(command, TuiCommandError):
            self._notify(command.message)
            return
        if command.name == "run":
            self.start_run(resume=False)
        elif command.name == "resume":
            self.start_run(resume=True)
        elif command.name == "task":
            self._create_and_run(command.args[0])
        elif command.name == "use":
            self._select(command.args[0])
        elif command.name == "rollback":
            self.request_rollback()
        elif command.name == "artifacts":
            self._show_artifacts()
        elif command.name == "open":
            self._open_artifact(command.args[0])
        # Other commands (help/tasks/status/trace/clear/quit) are UI-local.

    def _handle_plain_text(self, text: str) -> None:
        state = self.controller.state
        intent = classify_plain_text(
            text,
            has_active_task=state.active_task_id is not None,
            waiting_input=bool(state.pending_interaction_id),
        )
        if intent is PlainTextIntent.CREATE_TASK:
            self._create_and_run(text)
        elif intent is PlainTextIntent.ANSWER:
            self.submit_answer(text)
        else:
            self._notify(
                "当前 Task 不在等待输入状态。使用 /task <goal> 或 /run、/resume。"
            )

    def _create_and_run(self, goal: str) -> None:
        if not self.controller.can_mutate():
            self._notify("任务正在运行，请稍后。")
            return
        try:
            summary = self._task_service.create(self._project_root, goal)
        except HanCodeError as exc:
            self._notify(exc.structured_error.message)
            return
        self.controller.set_active_summary(summary)
        self.start_run(resume=False)

    def _select(self, task_id: str) -> None:
        if not self.controller.can_mutate():
            self._notify("任务正在运行，无法切换。")
            return
        try:
            self.controller.select_task(task_id)
        except HanCodeError as exc:
            self._notify(exc.structured_error.message)

    # -- run lifecycle ---------------------------------------------------

    def start_run(self, *, resume: bool) -> None:
        state = self.controller.state
        task_id = state.active_task_id
        if task_id is None:
            self._notify("请先选择或创建一个任务。")
            return
        if not self.controller.can_mutate():
            self._notify("已有任务在运行。")
            return
        self.controller.mark_running(task_id)
        self._run_worker(task_id, resume=resume)

    def submit_answer(self, answer: str) -> None:
        """Answer a pending interaction, then auto-resume (S4-T6)."""
        state = self.controller.state
        task_id = state.active_task_id
        interaction_id = state.pending_interaction_id
        if task_id is None or interaction_id is None:
            self._notify("当前没有待回答的问题。")
            return
        if not self.controller.can_mutate():
            self._notify("任务正在运行，请稍后。")
            return
        try:
            self._interaction_service.answer(
                self._project_root,
                task_id,
                answer,
                interaction_id=interaction_id,
            )
        except HanCodeError as exc:
            self._notify(exc.structured_error.message)
            return
        self._notify(f"Answer submitted · {len(answer.strip())} chars")
        self.start_run(resume=True)

    # -- rollback (explicit confirmation) --------------------------------

    def request_rollback(self) -> None:
        """Preview the latest checkpoint's affected files and await confirmation."""
        task_id = self.controller.state.active_task_id
        if task_id is None:
            self._notify("请先选择一个任务。")
            return
        if not self.controller.can_mutate():
            self._notify("任务正在运行，无法回退。")
            return
        try:
            preview = self._recovery_service.preview_last(self._project_root, task_id)
        except HanCodeError as exc:
            self._notify(exc.structured_error.message)
            return
        if not preview.available or preview.checkpoint_id is None:
            self._notify("没有可回退的 checkpoint。")
            return
        self._pending_rollback = preview
        files = "\n".join(f"- {name}" for name in preview.files)
        self._notify(
            f"Rollback {task_id} to {preview.checkpoint_id}?\n"
            f"Files affected:\n{files}\n[确认: /rollback confirm]"
        )

    def confirm_rollback(self) -> None:
        preview = self._pending_rollback
        task_id = self.controller.state.active_task_id
        self._pending_rollback = None
        if preview is None or task_id is None:
            return
        if not self.controller.can_mutate():
            self._notify("任务正在运行，无法回退。")
            return
        try:
            summary = self._recovery_service.rollback_last(self._project_root, task_id)
        except HanCodeError as exc:
            self._notify(exc.structured_error.message)
            return
        self._notify(
            f"Rolled back to {summary.checkpoint_id} · "
            f"{len(summary.restored_files)} files restored"
        )
        self._refresh_active_summary(task_id)

    def cancel_rollback(self) -> None:
        self._pending_rollback = None

    def _show_artifacts(self) -> None:
        summary = self.controller.state.active_task
        if summary is None:
            self._notify("请先选择一个任务。")
            return
        declared = [name for name, present in summary.artifacts.items() if present]
        if not declared:
            self._notify("当前任务没有可用产物。")
            return
        self._notify("产物: " + ", ".join(sorted(declared)))

    def _open_artifact(self, name: str) -> None:
        task_id = self.controller.state.active_task_id
        if task_id is None:
            self._notify("请先选择一个任务。")
            return
        try:
            preview = self._inspection_service.read_artifact(
                self._project_root, task_id, name
            )
        except HanCodeError as exc:
            self._notify(exc.structured_error.message)
            return
        self._render_detail(f"# {preview.name}\n\n{preview.content}")

    def _refresh_active_summary(self, task_id: str) -> None:
        try:
            summary = self._task_service.get(self._project_root, task_id)
        except HanCodeError:
            return
        self.controller.set_active_summary(summary)
        self._refresh_phase_bar()

    def _render_detail(self, text: str) -> None:
        try:
            from textual.widgets import Static

            panel = self.query_one("#tui-detail-panel", Static)
        except Exception:
            return
        panel.update(text)

    def _run_worker(self, task_id: str, *, resume: bool) -> None:
        observer = _WorkerTraceObserver(self)

        def _body() -> None:
            worker = get_current_worker()
            try:
                result = self._task_service.run(
                    self._project_root,
                    task_id,
                    resume=resume,
                    trace_observer=observer,
                )
            except HanCodeError as exc:
                if not worker.is_cancelled:
                    self.call_from_thread(self.post_message, RunFailed(exc.structured_error))
                return
            if not worker.is_cancelled:
                self.call_from_thread(self.post_message, RunFinished(result))

        self.run_worker(_body, thread=True, exclusive=True, group="task-run")

    # -- message handlers ------------------------------------------------

    def on_trace_arrived(self, message: TraceArrived) -> None:
        self.controller.on_trace(message.event)
        self._refresh_activity()

    def on_run_finished(self, message: RunFinished) -> None:
        self.controller.on_run_finished()
        self._refresh_phase_bar()

    def on_run_failed(self, message: RunFailed) -> None:
        self.controller.on_run_finished()
        self._notify(message.error.message)
        self._refresh_phase_bar()

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        # Worker completion is surfaced via explicit RunFinished/RunFailed
        # messages; this hook is intentionally a no-op placeholder.
        pass

    # -- widget refresh helpers -----------------------------------------

    def _refresh_activity(self) -> None:
        try:
            from hancode.interfaces.tui.widgets.activity_log import ActivityLog

            log = self.query_one("#tui-activity-log", ActivityLog)
        except Exception:
            return
        events = self.controller.state.trace_events
        if events:
            log.append_event(events[-1])

    def _refresh_phase_bar(self) -> None:
        try:
            from hancode.interfaces.tui.widgets.phase_bar import PhaseBar

            bar = self.query_one("#tui-phase-bar", PhaseBar)
        except Exception:
            return
        bar.update_summary(self.controller.state.active_task)

    def _notify(self, text: str) -> None:
        try:
            self.notify(text)
        except Exception:
            pass


__all__ = ["HanCodeTuiApp"]
