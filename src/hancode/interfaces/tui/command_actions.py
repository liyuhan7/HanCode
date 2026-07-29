"""Single source of display metadata for palette and contextual actions."""

from __future__ import annotations

from dataclasses import dataclass

from hancode.interfaces.tui.view_state import TuiViewState


@dataclass(frozen=True, slots=True)
class CommandActionView:
    action_id: str
    label: str
    command: str
    shortcut: str | None
    enabled: bool
    disabled_reason: str | None


def available_actions(state: TuiViewState) -> tuple[CommandActionView, ...]:
    has_task = state.active_task_id is not None
    actions = [
        _action("new", "创建任务", "/task 新任务目标", None, not has_task, "请先完成或切换当前任务。"),
        _action("tasks", "查看任务列表", "/tasks", None, True, None),
        _action("run", "运行当前任务", "/run", "R", has_task and not state.busy, "没有可运行的任务。"),
        _action("resume", "继续当前任务", "/resume", None, has_task and not state.busy, "当前任务不可继续。"),
        _action("diff", "查看代码改动", "/diff", None, has_task, "请先选择任务。"),
        _action("test", "查看测试结果", "/test", None, has_task, "请先选择任务。"),
        _action("delivery", "查看交付结果", "/delivery", None, has_task, "请先选择任务。"),
        _action("rollback", "恢复检查点", "/rollback", None, has_task and not state.busy, "任务运行时不能恢复检查点。"),
        _action("approval", "批准当前请求", "/approve", None, state.pending_approval_id is not None and not state.busy, "当前没有待确认操作。"),
        _action("reject", "拒绝当前请求", "/reject", None, state.pending_approval_id is not None and not state.busy, "当前没有待确认操作。"),
        _action("inspect", "切换检查视图", "/view inspect", "F2", True, None),
        _action("theme", "切换深浅主题", "/theme light", "Ctrl+T", True, None),
    ]
    return tuple(actions)


def _action(
    action_id: str,
    label: str,
    command: str,
    shortcut: str | None,
    enabled: bool,
    disabled_reason: str | None,
) -> CommandActionView:
    return CommandActionView(action_id, label, command, shortcut, enabled, disabled_reason)


__all__ = ["CommandActionView", "available_actions"]
