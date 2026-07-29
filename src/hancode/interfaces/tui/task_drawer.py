"""Task navigation drawer used by medium-width workbench layouts."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, ListItem, ListView, Static

from hancode.app.task_models import TaskSummary
from hancode.interfaces.tui.copy.zh_cn import PHASE_LABELS, STATUS_LABELS


class TaskDrawer(ModalScreen[str | None]):
    BINDINGS = [("escape", "close_drawer", "关闭")]

    def __init__(self, tasks: tuple[TaskSummary, ...]) -> None:
        super().__init__()
        self._tasks = tasks

    def compose(self) -> ComposeResult:
        with Vertical(id="tui-task-drawer"):
            yield Static("任务导航", markup=False)
            items = []
            for task in self._tasks:
                status = STATUS_LABELS.get(task.status.value, task.status.value)
                phase = PHASE_LABELS.get(task.current_phase.value, task.current_phase.value)
                goal = (task.goal or "未填写目标").replace("\n", " ")[:36]
                items.append(ListItem(Label(f"{task.task_id} · {status}\n{phase} · {goal}"), id=f"drawer-{task.task_id}"))
            yield ListView(*items, id="tui-task-drawer-list")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        task_id = event.item.id.removeprefix("drawer-") if event.item.id else None
        self.dismiss(task_id)

    def action_close_drawer(self) -> None:
        self.dismiss(None)


__all__ = ["TaskDrawer"]
