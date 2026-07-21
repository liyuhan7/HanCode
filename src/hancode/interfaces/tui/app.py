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
from textual.widgets import Input, ListView
from textual.worker import Worker, get_current_worker

from hancode.app.inspection_service import InspectionService
from hancode.app.interaction_service import InteractionService
from hancode.app.recovery_service import RecoveryService, RollbackPreview
from hancode.app.task_service import TaskService
from hancode.core.errors import HanCodeError, StructuredError
from hancode.core.models import TaskStatus
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
            project_root,
            task_service=self._task_service,
            inspection_service=self._inspection_service,
        )

    def on_mount(self) -> None:
        self.push_screen(MainScreen(project_root=self._project_root), self._on_ready)

    def _on_ready(self, _screen: object = None) -> None:
        """Load the task list once the main screen is mounted."""
        try:
            self.controller.refresh_tasks()
        except HanCodeError as exc:
            self._notify(exc.structured_error.message)
            return
        self._refresh_task_list()

    def on_input_submitted(self, event: "Input.Submitted") -> None:
        if event.input.id == "tui-composer":
            value = event.value
            event.input.value = ""
            self.submit_input(value)

    def on_list_view_selected(self, event: "ListView.Selected") -> None:
        item_id = event.item.id
        if item_id is None or not item_id.startswith("task-"):
            return
        if not self.controller.can_mutate():
            self._notify("任务正在运行，无法切换。")
            return
        self._select(item_id[len("task-") :])

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
            self._handle_rollback(command.args)
        elif command.name == "artifacts":
            self._show_artifacts()
        elif command.name == "open":
            self._open_artifact(command.args[0])
        elif command.name == "help":
            self._show_help()
        elif command.name == "tasks":
            self._show_tasks()
        elif command.name == "status":
            self._show_status()
        elif command.name == "trace":
            self._focus_trace()
        elif command.name == "clear":
            self._clear_activity()
        elif command.name == "quit":
            self.exit()

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
        self._refresh_task_list_data()
        self.start_run(resume=False)

    def _select(self, task_id: str) -> None:
        if not self.controller.can_mutate():
            self._notify("任务正在运行，无法切换。")
            return
        try:
            self.controller.select_task(task_id)
        except HanCodeError as exc:
            self._notify(exc.structured_error.message)
            return
        self._rerender_activity()
        self._refresh_phase_bar()
        self._reflect_waiting_input()

    def _rerender_activity(self) -> None:
        """Re-paint the whole activity feed from the current view state."""
        try:
            from hancode.interfaces.tui.widgets.activity_log import ActivityLog

            log = self.screen.query_one("#tui-activity-log", ActivityLog)
        except Exception:
            return
        log.clear()
        for event in self.controller.state.trace_events:
            log.append_event(event)

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

    def _handle_rollback(self, args: tuple[str, ...]) -> None:
        if not args:
            self.request_rollback()
            return
        subcommand = args[0].lower()
        if subcommand == "confirm":
            self.confirm_rollback()
        elif subcommand == "cancel":
            self.cancel_rollback()
        else:
            self._notify(
                "未知的 /rollback 子命令。用法：/rollback、/rollback confirm、/rollback cancel。"
            )

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
        self._refresh_task_list_data()
        self._refresh_active_summary(task_id)

    def cancel_rollback(self) -> None:
        self._pending_rollback = None

    def _show_help(self) -> None:
        self._notify(
            "命令：/task <goal> /tasks /use <id> /run /resume /status /trace "
            "/artifacts /open <name> /rollback [confirm|cancel] /clear /quit"
        )

    def _show_tasks(self) -> None:
        try:
            self.controller.refresh_tasks()
        except HanCodeError as exc:
            self._notify(exc.structured_error.message)
            return
        tasks = self.controller.state.tasks
        if not tasks:
            self._notify("当前项目没有任务。使用 /task <goal> 创建。")
            return
        self._refresh_task_list()
        self._notify(
            "任务：" + ", ".join(f"{t.task_id}({t.status.value})" for t in tasks)
        )

    def _show_status(self) -> None:
        task_id = self.controller.state.active_task_id
        if task_id is None:
            self._notify("当前没有选中的任务。使用 /use <id> 或 /task <goal>。")
            return
        try:
            summary = self._task_service.get(self._project_root, task_id)
        except HanCodeError as exc:
            self._notify(exc.structured_error.message)
            return
        self.controller.set_active_summary(summary)
        self._refresh_phase_bar()
        self._reflect_waiting_input()
        self._notify(
            f"{summary.task_id} · {summary.status.value} · phase={summary.current_phase.value} "
            f"· retry={summary.retry_budget_remaining}"
        )

    def _focus_trace(self) -> None:
        self._rerender_activity()
        try:
            from hancode.interfaces.tui.widgets.activity_log import ActivityLog

            self.screen.query_one("#tui-activity-log", ActivityLog).focus()
        except Exception:
            pass

    def _clear_activity(self) -> None:
        """Clear the on-screen activity feed only; trace.jsonl is untouched."""
        self.controller.clear_activity()
        try:
            from hancode.interfaces.tui.widgets.activity_log import ActivityLog

            self.screen.query_one("#tui-activity-log", ActivityLog).clear()
        except Exception:
            pass

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

            panel = self.screen.query_one("#tui-detail-panel", Static)
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
                    self.call_from_thread(
                        self.post_message, RunFailed(exc.structured_error)
                    )
                return
            except Exception:
                # Any unexpected error must still clear busy and never leak the
                # raw exception (which could contain sensitive detail) to the UI.
                if not worker.is_cancelled:
                    self.call_from_thread(
                        self.post_message, RunFailed(_tui_internal_error())
                    )
                return
            if not worker.is_cancelled:
                self.call_from_thread(self.post_message, RunFinished(result))

        self.run_worker(_body, thread=True, exclusive=True, group="task-run")

    # -- message handlers ------------------------------------------------

    def on_trace_arrived(self, message: TraceArrived) -> None:
        self.controller.on_trace(message.event)
        self._refresh_activity()

    def _refresh_task_list_data_only(self) -> None:
        """Update task list data only; does not touch widgets."""
        try:
            self.controller.refresh_tasks()
        except HanCodeError:
            pass

    def on_run_finished(self, message: RunFinished) -> None:
        self.controller.on_run_finished()
        self._refresh_phase_bar()
        self._reflect_waiting_input()
        self._refresh_task_list_data_only()

    def on_run_failed(self, message: RunFailed) -> None:
        self.controller.on_run_finished()
        self._notify(message.error.message)
        self._refresh_phase_bar()
        self._refresh_task_list_data_only()

    def _reflect_waiting_input(self) -> None:
        """When paused for input, surface the question and focus the composer."""
        state = self.controller.state
        summary = state.active_task
        if (
            summary is None
            or summary.status is not TaskStatus.WAITING_INPUT
            or state.pending_question is None
        ):
            self._reset_composer_placeholder()
            return
        interaction_id = state.pending_interaction_id or ""
        self._render_detail(
            f"# 等待输入\n\n{state.pending_question}\n\n"
            f"(interaction: {interaction_id})\n直接在下方输入回答。"
        )
        try:
            composer = self.screen.query_one("#tui-composer", Input)
        except Exception:
            return
        composer.placeholder = "输入你的回答并回车"
        composer.focus()

    def _reset_composer_placeholder(self) -> None:
        try:
            composer = self.screen.query_one("#tui-composer", Input)
        except Exception:
            return
        composer.placeholder = "描述你的课程项目任务，或输入 /help"

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        # Worker completion is surfaced via explicit RunFinished/RunFailed
        # messages; this hook is intentionally a no-op placeholder.
        pass

    # -- widget refresh helpers -----------------------------------------

    def _refresh_activity(self) -> None:
        try:
            from hancode.interfaces.tui.widgets.activity_log import ActivityLog

            log = self.screen.query_one("#tui-activity-log", ActivityLog)
        except Exception:
            return
        events = self.controller.state.trace_events
        if events:
            log.append_event(events[-1])

    def _refresh_phase_bar(self) -> None:
        try:
            from hancode.interfaces.tui.widgets.phase_bar import PhaseBar

            bar = self.screen.query_one("#tui-phase-bar", PhaseBar)
        except Exception:
            return
        bar.update_summary(self.controller.state.active_task)

    def _refresh_task_list_data(self) -> None:
        """Refresh the task list data from TaskService and update the ListView."""
        try:
            self.controller.refresh_tasks()
        except HanCodeError:
            return
        self._refresh_task_list()

    def _refresh_task_list(self) -> None:
        try:
            from textual.widgets import ListItem, ListView, Label

            view = self.screen.query_one("#tui-task-list", ListView)
        except Exception:
            return
        try:
            view.clear()
            for summary in self.controller.state.tasks:
                view.append(
                    ListItem(
                        Label(f"{summary.task_id} · {summary.status.value}"),
                        id=f"task-{summary.task_id}",
                    )
                )
        except Exception:
            pass

    def _notify(self, text: str) -> None:
        try:
            self.notify(text)
        except Exception:
            pass


def _tui_internal_error() -> StructuredError:
    return StructuredError(
        error_code="tui_internal_error",
        message="TUI 内部错误：任务执行意外失败。",
        phase="spec",
        denied_rule="tui_internal_error",
        suggested_fix="检查任务状态与 trace 后重试。",
    )


__all__ = ["HanCodeTuiApp"]
