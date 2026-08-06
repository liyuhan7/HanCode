"""Textual application entry point for the HanCode TUI (S4-T1, S4-T5, S4-T6).

The app is the only Textual-aware layer. It:
- forwards composer input to :class:`TuiSessionController` and the CommandParser,
- runs AgentLoop in a background Worker (never on the UI thread),
- receives trace/run messages posted by the Worker and updates widgets.

The Worker posts :mod:`messages` — it never touches widgets directly. A single
Task Worker runs at a time (the controller's ``busy`` flag guards this).
"""

from __future__ import annotations
from typing import cast

from pathlib import Path

from textual.app import App
from textual.widgets import Input, ListView
from textual.worker import Worker, get_current_worker

from hancode.app.approval_service import ApprovalService
from hancode.app.build_service import BuildSummary
from hancode.app.config_service import ConfigService, ConfigUpdateResult
from hancode.app.inspection_service import ArtifactPreview, InspectionService
from hancode.app.interaction_service import InteractionService
from hancode.app.intervention_service import InterventionService
from hancode.app.recovery_service import RecoveryService, RecoverySummary, RollbackPreview
from hancode.app.task_service import TaskService
from hancode.runtime.pause import PauseToken
from hancode.app.task_models import TaskSummary
from hancode.core.errors import HanCodeError, StructuredError
from hancode.core.models import TaskStatus
from hancode.interfaces.tui.commands import (
    PlainTextIntent,
    TuiCommand,
    TuiCommandError,
    classify_plain_text,
    parse_command,
)
from hancode.interfaces.tui.command_actions import available_actions
from hancode.interfaces.tui.controller import TuiSessionController
from hancode.interfaces.tui.dialogs import ApprovalDialog, RejectionReasonDialog, RollbackDialog
from hancode.interfaces.tui.messages import (
    OperationFailed,
    OperationFinished,
    RunFailed,
    RunFinished,
    TaskSummaryChanged,
    TraceArrived,
)
from hancode.interfaces.tui.operations import (
    TuiIntent,
    TuiOperationError,
    TuiOperationKind,
    TuiOperation,
    TuiOperationValue,
    TuiServices,
)
from hancode.interfaces.tui.presenters import (
    CheckpointListView,
    DeliveryView,
    DetailKind,
    DiffView,
    EventDetailView,
    TestReportView,
    present_approval_detail,
    present_artifact,
    present_build,
    present_export,
    present_interaction,
    present_rollback,
    present_task,
    present_trace_event,
)
from hancode.interfaces.tui.screens.main import MainScreen
from hancode.interfaces.tui.screens.approval import (
    SOURCE_APPROVAL_CATEGORIES,
    SourceApprovalScreen,
)
from hancode.interfaces.tui.screens.config import ConfigScreen
from hancode.interfaces.tui.palette import CommandPalette
from hancode.interfaces.tui.task_drawer import TaskDrawer
from hancode.interfaces.tui.semantic_presenters import present_activity_groups
from hancode.interfaces.tui.themes import (
    DARK_THEME_NAME,
    LIGHT_THEME_NAME,
    alternate_theme,
    register_hancode_themes,
)
from hancode.interfaces.tui.view_state import DisplayMode
from hancode.interfaces.tui.widgets.activity_feed import ActivityFeed
from hancode.interfaces.tui.widgets.activity_log import ActivityLog
from hancode.interfaces.tui.widgets.inspector import Inspector
from hancode.storage.export import ExportResult
from hancode.storage.trace import TraceEvent


class _WorkerTraceObserver:
    """Posts persisted trace and summary messages without touching widgets."""

    def __init__(self, app: "HanCodeTuiApp", request_id: str) -> None:
        self._app = app
        self._request_id = request_id

    def on_trace(self, event: TraceEvent) -> None:
        self._app.call_from_thread(self._app.post_message, TraceArrived(event))

    def on_task_summary(self, summary: TaskSummary) -> None:
        self._app.call_from_thread(
            self._app.post_message,
            TaskSummaryChanged(self._request_id, summary),
        )


class HanCodeTuiApp(App[None]):
    """Interactive terminal session for the HanCode harness."""

    TITLE = "HanCode"
    CSS = """
    CommandPalette { align: center middle; }
    #tui-command-palette { width: 70%; max-width: 84; height: 70%; background: $panel; border: heavy $primary; padding: 1 2; }
    #tui-command-palette-list { height: 1fr; }
    ApprovalDialog, RollbackDialog { align: center middle; }
    #tui-approval-dialog, #tui-rollback-dialog {
        width: 76%; max-width: 92; height: auto; max-height: 80%;
        background: $panel; border: heavy $primary; padding: 1 2;
    }
    """
    BINDINGS = [
        ("f2", "toggle_display_mode", "聚焦/检查"),
        ("ctrl+k", "open_palette", "操作菜单"),
        ("ctrl+t", "toggle_theme", "切换主题"),
    ]

    def __init__(
        self,
        *,
        project_root: Path,
        task_service: TaskService | None = None,
        interaction_service: InteractionService | None = None,
        inspection_service: InspectionService | None = None,
        recovery_service: RecoveryService | None = None,
        approval_service: ApprovalService | None = None,
        config_service: ConfigService | None = None,
        intervention_service: InterventionService | None = None,
        services: TuiServices | None = None,
    ) -> None:
        super().__init__()
        register_hancode_themes(self)
        self.theme = DARK_THEME_NAME
        self._project_root = project_root
        self._pending_rollback: RollbackPreview | None = None
        self._approval_modal_open = False
        self._rollback_modal_open = False
        self._drawer_requested = False
        self._config_service = config_service or ConfigService()
        self._intervention_service = intervention_service or InterventionService()
        self._active_pause_token: PauseToken | None = None
        self._pause_request_id: str | None = None
        self.controller = TuiSessionController(
            project_root,
            services=services,
            task_service=task_service,
            interaction_service=interaction_service,
            approval_service=approval_service,
            inspection_service=inspection_service,
            recovery_service=recovery_service,
        )

    def on_mount(self) -> None:
        self.push_screen(MainScreen(project_root=self._project_root), self._on_ready)

    def _on_ready(self, _screen: object = None) -> None:
        """Load the task list once the main screen is mounted."""
        # Startup is the one synchronous refresh: it avoids leaving a Query
        # Worker pending when the user quits immediately after launch.
        if self._sync_value(TuiIntent(kind=TuiOperationKind.LIST_TASKS)) is not None:
            self._refresh_task_list()
        self._render_activity_views()
        self._refresh_header()
        self._apply_display_mode()

    def action_open_palette(self) -> None:
        self.push_screen(CommandPalette(available_actions(self.controller.state)), self._on_palette_result)

    def action_toggle_theme(self) -> None:
        self.theme = alternate_theme(self.theme)
        self._notify("已切换为浅色主题。" if self.theme == LIGHT_THEME_NAME else "已切换为深色主题。")

    def action_toggle_display_mode(self) -> None:
        current = self.controller.state.display_mode
        next_mode = DisplayMode.INSPECT if current is DisplayMode.FOCUS else DisplayMode.FOCUS
        self.controller.set_display_mode(next_mode)
        self._apply_display_mode()
        self._notify("已切换到检查视图。" if next_mode is DisplayMode.INSPECT else "已切换到聚焦视图。")

    def _on_palette_result(self, command: str | None) -> None:
        if command is not None:
            self.submit_input(command)

    def on_input_submitted(self, event: "Input.Submitted") -> None:
        if event.input.id == "tui-composer":
            value = event.value
            event.input.value = ""
            self.submit_input(value)

    def on_list_view_selected(self, event: "ListView.Selected") -> None:
        item_id = event.item.id
        if item_id is None or not item_id.startswith("task-"):
            return
        task_id = item_id[len("task-") :]
        # Guard: _refresh_task_list preserves the visual highlight by setting
        # view.index, which fires ListView.Selected.  If the highlighted item
        # already matches the active task, skip _select to avoid a cascading
        # event chain (select → _reflect_waiting_input → _render_detail).
        if task_id == self.controller.state.active_task_id:
            return
        if not self.controller.can_mutate():
            if task_id == self.controller.state.running_task_id:
                self._select(task_id)
                return
            self._notify("任务正在运行，无法切换。")
            return
        self._select(task_id)

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
        elif command.name == "pause":
            self.request_pause()
        elif command.name == "task":
            self._create_and_run(command.args[0])
        elif command.name == "use":
            self._select(command.args[0])
        elif command.name == "rollback":
            self._handle_rollback(command.args)
        elif command.name == "approve":
            self.submit_approval()
        elif command.name == "reject":
            self.submit_rejection(" ".join(command.args).strip() or None)
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
        elif command.name == "diff":
            self._show_diff(command.args)
        elif command.name == "test":
            self._show_test_report()
        elif command.name == "checkpoints":
            self._show_checkpoints()
        elif command.name == "delivery":
            self._show_delivery()
        elif command.name == "export":
            self._export(command.args[0])
        elif command.name == "build":
            self._build()
        elif command.name == "trace":
            self._focus_trace(command.args[0] if command.args else None)
        elif command.name == "clear":
            self._clear_activity()
        elif command.name == "config":
            self._open_config()
        elif command.name == "view":
            self.controller.set_display_mode(DisplayMode(command.args[0]))
            self._apply_display_mode()
        elif command.name == "theme":
            self.theme = DARK_THEME_NAME if command.args[0] == "dark" else LIGHT_THEME_NAME
        elif command.name == "quit":
            self.exit()

    def _handle_plain_text(self, text: str) -> None:
        state = self.controller.state
        run_control_active = (
            state.busy
            and state.active_task_id == state.running_task_id
            and self._active_pause_token is not None
            and self._pause_request_id == state.current_request_id
        )
        intent = classify_plain_text(
            text,
            has_active_task=state.active_task_id is not None,
            waiting_input=bool(state.pending_interaction_id),
            waiting_approval=bool(state.pending_approval_id),
            busy=run_control_active,
        )
        if intent is PlainTextIntent.CREATE_TASK:
            self._create_and_run(text)
        elif intent is PlainTextIntent.ANSWER:
            self.submit_answer(text)
        elif intent is PlainTextIntent.STEER:
            self.submit_steering(text)
        elif intent is PlainTextIntent.APPROVAL_REQUIRES_COMMAND:
            self._notify("该操作正在等待你的批准。请输入 /approve 批准，或 /reject <理由> 拒绝。")
        else:
            self._notify("当前 Task 不在等待输入状态。使用 /task <goal> 或 /run、/resume。")

    def submit_steering(self, text: str) -> None:
        """Submit Runtime Steering to the running task without a second worker.

        The steering is persisted to the intervention store; the running Agent
        worker picks it up on its next turn via the shared, path-locked log.
        """
        state = self.controller.state
        waiting_approval = state.pending_approval_id is not None and not state.busy
        if not (
            state.busy
            and state.active_task_id == state.running_task_id
            and self._active_pause_token is not None
            and self._pause_request_id == state.current_request_id
        ) and not waiting_approval:
            self._notify("当前没有正在运行的任务。")
            return
        task_id = state.running_task_id
        if waiting_approval:
            task_id = state.active_task_id
            if task_id is None or not self.controller.can_mutate():
                self._notify("任务正在运行，请稍后。")
                return
        assert task_id is not None
        try:
            result = self._intervention_service.submit(
                self._project_root, task_id, text
            )
        except HanCodeError as exc:
            self._notify(exc.structured_error.message)
            return
        self._notify(
            f"已接收新要求（#{result.sequence}），将在下一个安全点生效。"
        )
        if waiting_approval:
            self.start_run(resume=True)

    def _sync_value(self, intent: TuiIntent) -> TuiOperationValue:
        """Adapt Controller sync errors into a user-facing TUI notice."""
        try:
            return self.controller.execute_sync(intent)
        except HanCodeError as exc:
            self._notify(exc.structured_error.message)
            return None

    def _start_query(self, intent: TuiIntent) -> None:
        """Dispatch a read-only operation to a background Query Worker."""
        operation = self.controller.dispatch(intent)
        if operation is None:
            error = self.controller.state.last_error
            self._notify(error.message if error is not None else "查询被拒绝。")
            return
        try:
            self.controller.begin_operation(operation)
        except HanCodeError as exc:
            self._notify(exc.structured_error.message)
            return
        self._run_query_worker(operation)

    def _create_and_run(self, goal: str) -> None:
        if not self.controller.can_mutate():
            self._notify("任务正在运行，请稍后。")
            return
        summary = self._sync_value(TuiIntent(kind=TuiOperationKind.CREATE_TASK, goal=goal))
        if summary is None:
            return
        summary = cast(TaskSummary, summary)
        self.controller.set_active_summary(summary)
        self._refresh_task_list_data_only()
        self.start_run(resume=False)

    def _select(self, task_id: str) -> None:
        if not self.controller.can_mutate():
            if task_id != self.controller.state.running_task_id:
                self._notify("任务正在运行，无法切换。")
                return
        self._start_query(
            TuiIntent(kind=TuiOperationKind.SELECT_TASK, task_id=task_id)
        )

    def _rerender_activity(self) -> None:
        """Re-paint the whole activity feed from the current view state."""
        self._render_activity_views()

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
        operation = self.controller.dispatch(
            TuiIntent(
                kind=TuiOperationKind.RUN_TASK,
                task_id=task_id,
                resume=resume,
            )
        )
        if operation is None:
            error = self.controller.state.last_error
            self._notify(error.message if error is not None else "操作被拒绝。")
            return
        self.controller.begin_operation(operation)
        pause_token = PauseToken()
        self._active_pause_token = pause_token
        self._pause_request_id = operation.request_id
        self._run_worker(operation, pause_token=pause_token)

    def request_pause(self) -> None:
        state = self.controller.state
        token = self._active_pause_token
        if (
            token is None
            or self._pause_request_id != state.current_request_id
            or not state.busy
            or state.active_task_id != state.running_task_id
        ):
            self._notify("当前没有正在运行的任务。")
            return
        token.request()
        self._notify("暂停请求已提交，等待当前操作到达安全点。")

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
        if (
            self._sync_value(
                TuiIntent(
                    kind=TuiOperationKind.ANSWER_INTERACTION,
                    task_id=task_id,
                    answer=answer,
                    interaction_id=interaction_id,
                )
            )
            is None
        ):
            return
        self._notify(f"Answer submitted · {len(answer.strip())} chars")
        self.start_run(resume=True)

    # -- approval decisions (explicit, then auto-resume) -----------------

    def submit_approval(self) -> None:
        """Approve the pending request, then auto-resume so the action runs."""
        self._decide_approval(approved=True, reason=None)

    def submit_rejection(self, reason: str | None) -> None:
        """Reject the pending request; the loop will treat it as feedback."""
        self._decide_approval(approved=False, reason=reason)

    def _decide_approval(
        self,
        *,
        approved: bool,
        reason: str | None,
        approval_id_override: str | None = None,
    ) -> None:
        state = self.controller.state
        task_id = state.active_task_id
        approval_id = state.pending_approval_id
        if task_id is None or approval_id is None:
            self._notify("当前没有待批准的操作。")
            return
        if approval_id_override is not None and approval_id_override != approval_id:
            self._notify("Approval 已过期，未执行任何决策。")
            return
        if not self.controller.can_mutate():
            self._notify("任务正在运行，请稍后。")
            return
        operation_kind = TuiOperationKind.APPROVE if approved else TuiOperationKind.REJECT
        if (
            self._sync_value(
                TuiIntent(
                    kind=operation_kind,
                    task_id=task_id,
                    approval_id=approval_id,
                    reason=reason,
                )
            )
            is None
        ):
            return
        self._notify(f"Approval {'approved' if approved else 'rejected'} · {approval_id}")
        # Auto-resume: on approval the loop executes the action; on rejection it
        # consumes the decision as feedback and continues.
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
        preview = self._sync_value(
            TuiIntent(kind=TuiOperationKind.PREVIEW_ROLLBACK, task_id=task_id)
        )
        if preview is None:
            return
        preview = cast(RollbackPreview, preview)
        if not preview.available or preview.checkpoint_id is None:
            self._notify("没有可回退的 checkpoint。")
            return
        self._pending_rollback = preview
        view = present_rollback(preview)
        if self.is_running and not self._rollback_modal_open:
            self._rollback_modal_open = True
            self.push_screen(RollbackDialog(view), self._on_rollback_modal_result)
        else:
            files = "\n".join(f"- {name}" for name in view.files)
            self._notify(
                f"Rollback {task_id} to {view.checkpoint_id}?\n"
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
        summary = self._sync_value(
            TuiIntent(
                kind=TuiOperationKind.ROLLBACK,
                task_id=task_id,
                expected_checkpoint_id=preview.checkpoint_id,
            )
        )
        if summary is None:
            return
        summary = cast(RecoverySummary, summary)
        self._notify(
            f"Rolled back to {summary.checkpoint_id} · {len(summary.restored_files)} files restored"
        )
        self._refresh_task_list_data_only()
        self._refresh_active_summary(task_id)

    def cancel_rollback(self) -> None:
        self._pending_rollback = None

    def _on_rollback_modal_result(self, result: str | None) -> None:
        self._rollback_modal_open = False
        if result == "confirm":
            self.confirm_rollback()
        else:
            self.cancel_rollback()

    def _show_help(self) -> None:
        self._notify(
            "命令：/task <goal> /tasks /use <id> /run /resume /pause /approve "
            "/reject <理由> /status /diff [task|latest] [path] /test "
            "/checkpoints /delivery /trace [event-id] /artifacts /open <name> "
            "/export <directory> /build /rollback [confirm|cancel] /view [focus|inspect] "
            "/theme [dark|light] /config /clear /quit"
        )

    def _open_config(self) -> None:
        if not self.controller.can_mutate():
            self._notify("任务正在运行，暂时不能修改项目设置。")
            return
        self.push_screen(
            ConfigScreen(
                project_root=self._project_root,
                config_service=self._config_service,
            ),
            self._on_config_closed,
        )

    def _on_config_closed(self, result: ConfigUpdateResult | None) -> None:
        if result is None:
            return
        message = f"项目设置已保存，共修改 {len(result.changed_fields)} 项。"
        if result.next_command is not None:
            message += f" 下一步：{result.next_command}"
        self._notify(message)

    def _show_tasks(self) -> None:
        self._drawer_requested = True
        self._start_query(TuiIntent(kind=TuiOperationKind.LIST_TASKS))

    def _on_task_drawer_result(self, task_id: str | None) -> None:
        if task_id is not None:
            self._select(task_id)

    def _show_status(self) -> None:
        task_id = self.controller.state.active_task_id
        if task_id is None:
            self._notify("当前没有选中的任务。使用 /use <id> 或 /task <goal>。")
            return
        self._start_query(
            TuiIntent(kind=TuiOperationKind.GET_STATUS, task_id=task_id)
        )

    def _show_diff(self, args: tuple[str, ...]) -> None:
        task_id = self.controller.state.active_task_id
        if task_id is None:
            self._notify("请先选择一个任务。")
            return
        scope = args[0] if args else "task"
        path = args[1] if len(args) > 1 else None
        self._start_query(
            TuiIntent(
                kind=TuiOperationKind.DIFF,
                task_id=task_id,
                diff_scope=scope,
                diff_path=path,
            )
        )

    def _show_test_report(self) -> None:
        task_id = self.controller.state.active_task_id
        if task_id is None:
            self._notify("请先选择一个任务。")
            return
        self._start_query(TuiIntent(kind=TuiOperationKind.TEST_REPORT, task_id=task_id))

    def _show_checkpoints(self) -> None:
        task_id = self.controller.state.active_task_id
        if task_id is None:
            self._notify("请先选择一个任务。")
            return
        self._start_query(TuiIntent(kind=TuiOperationKind.CHECKPOINTS, task_id=task_id))

    def _show_delivery(self) -> None:
        task_id = self.controller.state.active_task_id
        if task_id is None:
            self._notify("请先选择一个任务。")
            return
        self._start_query(TuiIntent(kind=TuiOperationKind.DELIVERY, task_id=task_id))

    def _export(self, output_dir: str) -> None:
        task_id = self.controller.state.active_task_id
        if task_id is None:
            self._notify("请先选择一个任务。")
            return
        if not self.controller.can_mutate():
            self._notify("任务正在运行，无法导出。")
            return
        operation = self.controller.dispatch(
            TuiIntent(
                kind=TuiOperationKind.EXPORT,
                task_id=task_id,
                export_output_dir=Path(output_dir),
            )
        )
        if operation is None:
            error = self.controller.state.last_error
            self._notify(error.message if error is not None else "导出被拒绝。")
            return
        self.controller.begin_operation(operation)
        self._run_worker(operation)

    def _build(self) -> None:
        task_id = self.controller.state.active_task_id
        if task_id is None:
            self._notify("请先选择一个任务。")
            return
        if not self.controller.can_mutate():
            self._notify("任务正在运行，无法执行 Build。")
            return
        operation = self.controller.dispatch(
            TuiIntent(kind=TuiOperationKind.BUILD, task_id=task_id)
        )
        if operation is None:
            error = self.controller.state.last_error
            self._notify(error.message if error is not None else "Build 被拒绝。")
            return
        self.controller.begin_operation(operation)
        self._run_worker(operation)

    def _focus_trace(self, event_id: str | None = None) -> None:
        task_id = self.controller.state.active_task_id
        if task_id is None:
            self._notify("当前没有选中的任务。")
            return
        self._start_query(
            TuiIntent(kind=TuiOperationKind.TRACE, task_id=task_id, event_id=event_id)
        )

    def _focus_activity(self) -> None:
        try:
            if self.controller.state.display_mode is DisplayMode.FOCUS:
                self.screen.query_one("#tui-activity-feed", ActivityFeed).focus()
            else:
                self.screen.query_one("#tui-activity-log", ActivityLog).focus()
        except Exception:
            pass

    def _clear_activity(self) -> None:
        """Clear the on-screen activity feed only; trace.jsonl is untouched."""
        self.controller.clear_activity()
        self._render_activity_views()

    def _show_artifacts(self) -> None:
        task_id = self.controller.state.active_task_id
        if task_id is None:
            self._notify("请先选择一个任务。")
            return
        self._start_query(TuiIntent(kind=TuiOperationKind.LIST_ARTIFACTS, task_id=task_id))

    def _render_artifact_list(self) -> None:
        summary = self.controller.state.active_task
        if summary is None:
            self._notify("当前任务不可用。")
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
        self._start_query(
            TuiIntent(
                kind=TuiOperationKind.READ_ARTIFACT,
                task_id=task_id,
                artifact_name=name,
            )
        )

    def _refresh_active_summary(self, task_id: str) -> None:
        self._start_query(
            TuiIntent(kind=TuiOperationKind.GET_STATUS, task_id=task_id)
        )

    def _render_detail(self, text: str) -> None:
        try:
            for panel in self.screen.query(Inspector):
                panel.update_content(text)
        except Exception:
            return

    def _render_activity_views(self) -> None:
        """Synchronise semantic and raw panes from the immutable event buffer."""
        events = self.controller.state.trace_events
        groups = present_activity_groups(events)
        try:
            for feed in self.screen.query(ActivityFeed):
                feed.update_groups(groups)
            for log in self.screen.query(ActivityLog):
                log.clear()
                for event in events:
                    log.append_event(present_trace_event(event))
        except Exception:
            return
        self._apply_display_mode()

    def _apply_display_mode(self) -> None:
        focus = self.controller.state.display_mode is DisplayMode.FOCUS
        try:
            for feed in self.screen.query(ActivityFeed):
                feed.styles.display = "block" if focus else "none"
            for log in self.screen.query(ActivityLog):
                log.styles.display = "none" if focus else "block"
        except Exception:
            return

    def _refresh_header(self) -> None:
        try:
            from textual.widgets import Static
            from hancode.interfaces.tui.copy.zh_cn import PHASE_LABELS, STATUS_LABELS

            header = self.screen.query_one("#tui-task-header", Static)
        except Exception:
            return
        summary = self.controller.state.active_task
        if summary is None:
            header.update("HanCode  ·  选择或创建任务  ·  Ctrl+K 操作菜单  ·  Ctrl+T 主题")
            return
        goal = present_task(summary).goal or "未填写任务目标"
        goal = goal.replace("\n", " ")[:52]
        header.update(
            f"HanCode  ·  {summary.task_id} · {goal}  ·  "
            f"{STATUS_LABELS.get(summary.status.value, summary.status.value)} · "
            f"{PHASE_LABELS.get(summary.current_phase.value, summary.current_phase.value)}"
        )

    def _run_worker(
        self, operation: TuiOperation, *, pause_token: PauseToken | None = None
    ) -> None:
        self._run_operation_worker(
            operation,
            group="task-mutation",
            exclusive=True,
            trace_observer=_WorkerTraceObserver(self, operation.request_id),
            pause_token=pause_token,
        )

    def _run_query_worker(self, operation: TuiOperation) -> None:
        """Run a read-only operation without blocking the Textual thread."""
        self._run_operation_worker(
            operation,
            group="task-query",
            exclusive=False,
        )

    def _run_operation_worker(
        self,
        operation: TuiOperation,
        *,
        group: str,
        exclusive: bool,
        trace_observer: _WorkerTraceObserver | None = None,
        pause_token: PauseToken | None = None,
    ) -> None:
        """Execute one operation and publish only request-scoped messages."""

        def _body() -> None:
            worker = get_current_worker()
            try:
                if trace_observer is None:
                    result = (
                        self.controller.execute(operation, pause_token=pause_token)
                        if pause_token is not None
                        else self.controller.execute(operation)
                    )
                else:
                    result = (
                        self.controller.execute(
                            operation,
                            trace_observer=trace_observer,
                            pause_token=pause_token,
                        )
                        if pause_token is not None
                        else self.controller.execute(
                            operation,
                            trace_observer=trace_observer,
                        )
                    )
            except TuiOperationError as exc:
                if not worker.is_cancelled:
                    self.call_from_thread(self.post_message, OperationFailed(exc))
                return
            except HanCodeError as exc:
                if not worker.is_cancelled:
                    self.call_from_thread(
                        self.post_message,
                        OperationFailed(_operation_error(operation, exc.structured_error)),
                    )
                return
            except Exception:
                if not worker.is_cancelled:
                    self.call_from_thread(
                        self.post_message,
                        OperationFailed(_operation_error(operation, _tui_internal_error())),
                    )
                return
            if not worker.is_cancelled:
                self.call_from_thread(self.post_message, OperationFinished(result))

        self.run_worker(_body, thread=True, exclusive=exclusive, group=group)

    # -- message handlers ------------------------------------------------

    def on_trace_arrived(self, message: TraceArrived) -> None:
        self.controller.on_trace(message.event)
        self._render_activity_views()

    def on_task_summary_changed(self, message: TaskSummaryChanged) -> None:
        """Render a current mutation snapshot without changing interaction focus."""

        if not self.controller.apply_live_summary(message.request_id, message.summary):
            return
        self._refresh_phase_bar()
        self._refresh_task_list()
        self._refresh_header()
        if self.controller.state.detail_kind is DetailKind.TASK:
            self._render_active_task_detail()

    def on_operation_finished(self, message: OperationFinished) -> None:
        """Apply every Worker result through the request-scoped Controller gate."""

        if not self.controller.apply_result(message.result):
            return
        kind = message.result.kind
        if kind is TuiOperationKind.RUN_TASK:
            self._clear_pause_token(message.result.request_id)
            self._refresh_phase_bar()
            self._refresh_task_list_data_only()
            self._refresh_header()
        elif kind is TuiOperationKind.LIST_TASKS:
            self._refresh_task_list()
            self._reflect_waiting_input()
            if self._drawer_requested:
                self._drawer_requested = False
                self.push_screen(TaskDrawer(self.controller.state.tasks), self._on_task_drawer_result)
        elif kind is TuiOperationKind.SELECT_TASK:
            self._rerender_activity()
            self._refresh_phase_bar()
            self._refresh_header()
            self._reflect_waiting_input()
        elif kind is TuiOperationKind.TRACE:
            self._rerender_activity()
            if isinstance(self.controller.state.detail, EventDetailView):
                self._render_inspection_detail()
            else:
                self._focus_activity()
        elif kind is TuiOperationKind.GET_STATUS:
            self._refresh_phase_bar()
            self._refresh_task_list_data_only()
            self._refresh_header()
        elif kind is TuiOperationKind.LIST_ARTIFACTS:
            self._render_artifact_list()
        elif kind in {TuiOperationKind.DIFF, TuiOperationKind.TEST_REPORT, TuiOperationKind.CHECKPOINTS, TuiOperationKind.DELIVERY}:
            self._render_inspection_detail()
        elif kind is TuiOperationKind.GET_APPROVAL:
            self._render_approval_detail(message.result.value)
        elif kind is TuiOperationKind.READ_ARTIFACT:
            if isinstance(message.result.value, ArtifactPreview):
                view = present_artifact(message.result.value)
                self._render_detail(f"# {view.name}\n\n{view.content}")
        elif kind is TuiOperationKind.EXPORT:
            if isinstance(message.result.value, ExportResult):
                export_view = present_export(message.result.value)
                self._render_detail(
                    "\n".join(
                        (
                            "# Export",
                            f"Task: {export_view.task_id}",
                            f"Directory: {export_view.output_dir}",
                            f"Artifacts: {', '.join(export_view.artifacts) or 'none'}",
                        )
                    )
                )
                self._notify(
                    f"已导出 {len(export_view.artifacts)} 个交付物到 {export_view.output_dir}。"
                )
        elif kind is TuiOperationKind.BUILD:
            if isinstance(message.result.value, BuildSummary):
                build_view = present_build(message.result.value)
                self._render_detail(
                    "\n".join(
                        (
                            "# Build",
                            f"Status: {build_view.status}",
                            f"Command: {build_view.command}",
                            f"Exit code: {build_view.exit_code}",
                            f"Timed out: {'yes' if build_view.timed_out else 'no'}",
                        )
                    )
                )
                self._notify(f"Build {build_view.status}: {build_view.command}")
                if self.is_running:
                    self._start_query(
                        TuiIntent(
                            kind=TuiOperationKind.GET_STATUS,
                            task_id=message.result.task_id,
                        )
                    )

    def on_operation_failed(self, message: OperationFailed) -> None:
        """Apply a Worker error only when its request is still current."""

        if not self.controller.apply_error(message.error):
            return
        self._clear_pause_token(message.error.request_id)
        self._notify(message.error.structured_error.message)
        if message.error.kind is TuiOperationKind.RUN_TASK:
            self._refresh_phase_bar()
            self._reflect_waiting_input()
            self._refresh_task_list_data_only()

    def _clear_pause_token(self, request_id: str) -> None:
        if self._pause_request_id == request_id:
            self._active_pause_token = None
            self._pause_request_id = None

    def _refresh_task_list_data_only(self) -> None:
        """Update task list data only; does not touch widgets."""
        # Message handlers are also exercised directly by unit tests and by
        # the compatibility path before the Textual app has started.  A query
        # Worker requires a running event loop, so defer the UI refresh until
        # the app lifecycle is active.
        if not self.is_running:
            return
        self._start_query(TuiIntent(kind=TuiOperationKind.LIST_TASKS))

    def on_run_finished(self, message: RunFinished) -> None:
        task_id = self.controller.on_run_finished(refresh_status=False)
        self._refresh_phase_bar()
        self._refresh_header()
        self._reflect_waiting_input()
        if task_id is not None:
            self._start_query(
                TuiIntent(kind=TuiOperationKind.GET_STATUS, task_id=task_id)
            )

    def on_run_failed(self, message: RunFailed) -> None:
        task_id = self.controller.on_run_finished(refresh_status=False)
        self._notify(message.error.message)
        self._refresh_phase_bar()
        self._refresh_header()
        self._reflect_waiting_input()
        if task_id is not None:
            self._start_query(
                TuiIntent(kind=TuiOperationKind.GET_STATUS, task_id=task_id)
            )

    def _reflect_waiting_input(self) -> None:
        """When paused for input/approval, surface the prompt and focus composer."""
        state = self.controller.state
        summary = state.active_task
        if (
            summary is not None
            and summary.status is TaskStatus.WAITING_APPROVAL
            and state.pending_approval_id is not None
        ):
            self._reflect_waiting_approval()
            return
        if (
            summary is None
            or summary.status is not TaskStatus.WAITING_INPUT
            or state.pending_question is None
        ):
            self._reset_composer_placeholder()
            self._render_active_task_detail()
            return
        view = present_interaction(summary)
        if view is None:
            self._reset_composer_placeholder()
            self._render_active_task_detail()
            return
        self._render_detail(
            f"# 等待输入\n\n{view.question}\n\n"
            f"(interaction: {view.interaction_id})\n直接在下方输入回答。"
        )
        try:
            composer = self.screen.query_one("#tui-composer", Input)
        except Exception:
            return
        composer.placeholder = "输入你的回答并回车"
        composer.focus()

    def _reflect_waiting_approval(self) -> None:
        """Render the pending-approval panel and prompt for an explicit decision."""
        state = self.controller.state
        task_id = state.active_task_id
        if task_id is None:
            return
        if state.active_query == TuiOperationKind.GET_APPROVAL.value:
            return
        self._start_query(
            TuiIntent(
                kind=TuiOperationKind.GET_APPROVAL,
                task_id=task_id,
            )
        )

    def _render_approval_detail(self, detail: object) -> None:
        if not isinstance(detail, dict):
            self._notify("当前 Approval 详情不可用。")
            return
        view = present_approval_detail(detail)
        if view is None:
            self._notify("当前 Approval 详情不可用。")
            return
        targets_text = "\n".join(f"- {target}" for target in view.targets) or "(none)"
        preview_text = (
            f"\n\n修改预览:\n{view.diff_preview}"
            if view.diff_preview.strip()
            else ""
        )
        self._render_detail(
            f"# 等待批准\n\n"
            f"操作: {view.tool_name or '?'}\n\n"
            f"目标文件:\n{targets_text}\n\n"
            f"(approval: {view.approval_id})\n\n"
            f"输入 `/approve` 批准，或 `/reject <理由>` 拒绝。"
            f"{preview_text}"
        )
        if self.is_running and not self._approval_modal_open:
            self._approval_modal_open = True
            decision_screen = (
                SourceApprovalScreen(view)
                if view.category in SOURCE_APPROVAL_CATEGORIES
                else ApprovalDialog(view)
            )
            self.push_screen(decision_screen, self._on_approval_modal_result)
        try:
            composer = self.screen.query_one("#tui-composer", Input)
        except Exception:
            return
        composer.placeholder = "/approve 批准，或 /reject <理由> 拒绝"
        composer.focus()

    def _on_approval_modal_result(self, result: str | None) -> None:
        self._approval_modal_open = False
        if result == "approve":
            self._decide_approval(approved=True, reason=None)
        elif result == "reject":
            self.push_screen(RejectionReasonDialog(), self._on_rejection_reason)

    def _on_rejection_reason(self, reason: str | None) -> None:
        if reason is not None:
            self._decide_approval(approved=False, reason=reason)

    def _reset_composer_placeholder(self) -> None:
        try:
            composer = self.screen.query_one("#tui-composer", Input)
        except Exception:
            return
        summary = self.controller.state.active_task
        if summary is None:
            composer.placeholder = "描述你希望 HanCode 完成的开发任务……"
        elif summary.status is TaskStatus.COMPLETED:
            composer.placeholder = "查看交付结果，或输入新的开发任务……"
        elif summary.latest_test_status == "failed":
            composer.placeholder = "输入修复建议，或选择继续分析……"
        else:
            composer.placeholder = "输入补充要求、问题或命令……"

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        # Worker completion is surfaced via explicit OperationFinished and
        # OperationFailed messages; this hook is intentionally a no-op.
        pass

    def _render_active_task_detail(self) -> None:
        """Render a safe summary when the active task is not waiting for input."""
        summary = self.controller.state.active_task

        if summary is None:
            self._render_detail("")
            return

        view = present_task(summary)
        strategy_line = (
            "测试策略：已登记\n"
            if view.test_strategy_registered
            else "测试策略：未登记\n"
        )
        from hancode.interfaces.tui.copy.zh_cn import PHASE_LABELS, STATUS_LABELS

        checkpoint = view.latest_checkpoint or "尚无"
        test_status = STATUS_LABELS.get(view.latest_test_status, view.latest_test_status or "未知")
        build_status = STATUS_LABELS.get(view.latest_build_status, view.latest_build_status or "未知")
        builds_run = ", ".join(view.builds_run) or "尚未执行"

        self._render_detail(
            strategy_line
            +
            f"任务概览\n\n"
            f"任务：{view.task_id}\n"
            f"目标：{view.goal or '未填写'}\n"
            f"状态：{STATUS_LABELS.get(view.status, view.status)} ({view.status})\n"
            f"当前阶段：{PHASE_LABELS.get(view.current_phase, view.current_phase)}\n\n"
            f"已修改文件：{len(view.files_changed)}\n"
            f"测试结果：{test_status}\n"
            f"构建状态：{build_status}\n"
            f"最近检查点：{checkpoint}\n"
            f"剩余重试：{view.retry_budget_remaining}\n"
            f"{_test_failure_label(view.latest_test_status, view.latest_remediation_digest)}：{view.latest_test_failure_digest or '无'}\n"
            f"修复决策：{view.latest_remediation_digest or '无'}\n"
            f"修复已应用：{'是' if view.remediation_applied else '否'}\n"
            f"已执行构建：{builds_run}"
        )

    def _render_inspection_detail(self) -> None:
        detail = self.controller.state.detail
        if isinstance(detail, DiffView):
            lines = [
                "代码改动",
                f"范围：{detail.scope}",
                f"检查点：{', '.join(detail.checkpoint_ids) or '尚无'}",
            ]
            for file_view in detail.files:
                marker = {"created": "A", "modified": "M", "deleted": "D"}.get(
                    file_view.change_type, "?"
                )
                if file_view.drifted:
                    marker = "!"
                suffix = " · 二进制文件" if file_view.binary else ""
                lines.append(f"{marker} {file_view.path}{suffix}")
                if file_view.unified_diff:
                    lines.extend(("", file_view.unified_diff))
            if detail.risks:
                lines.extend(("", "风险：", *[f"! {risk}" for risk in detail.risks]))
            if detail.truncated:
                lines.append("[Diff 预览已截断]")
            self._render_detail("\n".join(lines))
            return
        if isinstance(detail, TestReportView):
            lines = [
                "测试结果",
                f"状态：{detail.status}",
                f"命令：{detail.command or '未知'}",
                f"通过：{detail.passed_count if detail.passed_count is not None else '未知'}",
                f"失败：{detail.failed_count if detail.failed_count is not None else '未知'}",
                f"失败分类：{detail.failure_category or '未记录'}",
                f"摘要：{detail.summary or '当前测试报告未记录具体失败用例。'}",
                f"下一步：{detail.next_action_hint or '查看测试报告原文后继续分析。'}",
                "",
                "测试报告原文（已脱敏）：",
                detail.content,
            ]
            if detail.truncated:
                lines.append("[测试报告已截断]")
            self._render_detail("\n".join(lines))
            return
        if isinstance(detail, CheckpointListView):
            lines = ["检查点"]
            for checkpoint_view in detail.checkpoints:
                files = f"{len(checkpoint_view.files)} 个文件"
                rollback = " · 可恢复" if checkpoint_view.rollback_available else ""
                lines.append(
                    f"{checkpoint_view.checkpoint_id} {checkpoint_view.status} "
                    f"{files}{rollback} · {checkpoint_view.phase}"
                )
                lines.append(f"  {checkpoint_view.reason}")
            self._render_detail("\n".join(lines))
            return
        if isinstance(detail, DeliveryView):
            lines = [
                "交付结果",
                f"状态：{detail.status}",
                f"测试：{detail.latest_test_status}",
                f"构建：{detail.latest_build_status}",
                f"知识条目：{detail.knowledge_count}",
                f"可导出：{'是' if detail.export_ready else '否'}",
            ]
            if detail.requirement_coverage:
                lines.extend(("", "需求覆盖："))
                lines.extend(
                    f"{'*' if item.is_core else '-'} {item.requirement_id}: {item.status}"
                    for item in detail.requirement_coverage
                )
            if detail.blockers:
                lines.extend(("", "阻塞项：", *[f"! {blocker}" for blocker in detail.blockers]))
            self._render_detail("\n".join(lines))
            return
        if isinstance(detail, EventDetailView):
            self._render_detail(
                "\n".join(
                    (
                        "# Event",
                        f"事件 ID：{detail.event_id}",
                        f"序号：{detail.seq}",
                        f"类型：{detail.event_type}",
                        f"阶段：{detail.phase}",
                        f"状态：{detail.status}",
                        f"工具：{detail.tool_name or '无'}",
                        f"目标：{detail.target_path or '无'}",
                        f"错误：{detail.error_summary or '无'}",
                    )
                )
            )

    # -- widget refresh helpers -----------------------------------------

    def _refresh_activity(self) -> None:
        self._render_activity_views()

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
        """Update task labels in-place to avoid Textual layout cascade."""
        try:
            from textual.widgets import Label, ListItem, ListView
        except Exception:
            return
        tasks = self.controller.state.tasks
        try:
            views = tuple(self.screen.query(ListView))
        except Exception:
            return
        for view in views:
            if view.id not in {"tui-task-list", "tui-task-list-narrow"}:
                continue
            old_count = len(view.children)
            for index, summary in enumerate(tasks):
                label = _task_label(summary)
                if index < old_count:
                    item = view.children[index]
                    for child in item.walk_children():
                        if isinstance(child, Label):
                            child.update(label)
                            break
                else:
                    view.append(ListItem(Label(label), id=f"task-{summary.task_id}"))
            while len(view.children) > len(tasks):
                view.children[-1].remove()

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


def _test_failure_label(test_status: str, remediation_digest: str | None) -> str:
    if test_status == "failed":
        return "活动失败证据"
    if test_status == "none" and remediation_digest:
        return "修复中失败证据"
    return "最近已解决失败"


def _task_label(summary: TaskSummary) -> str:
    from hancode.interfaces.tui.copy.zh_cn import PHASE_LABELS, STATUS_LABELS

    status = STATUS_LABELS.get(summary.status.value, summary.status.value)
    phase = PHASE_LABELS.get(summary.current_phase.value, summary.current_phase.value)
    goal = (summary.goal or "未填写目标").replace("\n", " ")[:28]
    return f"{summary.task_id} · {status} ({summary.status.value})\n{phase} · {goal}"




def _operation_error(
    operation: TuiOperation,
    structured_error: StructuredError,
) -> TuiOperationError:
    return TuiOperationError(
        operation.request_id,
        operation.kind,
        operation.task_id,
        structured_error,
    )


__all__ = ["HanCodeTuiApp"]
