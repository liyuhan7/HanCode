"""State-aware command palette that dispatches existing slash commands."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, ListItem, ListView, Static

from hancode.interfaces.tui.command_actions import CommandActionView


class CommandPalette(ModalScreen[str | None]):
    BINDINGS = [("escape", "dismiss_palette", "关闭")]

    def __init__(self, actions: tuple[CommandActionView, ...]) -> None:
        super().__init__()
        self._actions = actions

    def compose(self) -> ComposeResult:
        with Vertical(id="tui-command-palette"):
            yield Static("操作菜单", markup=False)
            items = []
            for action in self._actions:
                suffix = "" if action.enabled else f"（{action.disabled_reason}）"
                key = f" · {action.shortcut}" if action.shortcut else ""
                items.append(ListItem(Label(f"{action.label}{key}{suffix}"), id=f"palette-{action.action_id}", disabled=not action.enabled))
            yield ListView(*items, id="tui-command-palette-list")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        action_id = event.item.id.removeprefix("palette-") if event.item.id else ""
        selected = next((item for item in self._actions if item.action_id == action_id), None)
        self.dismiss(None if selected is None or not selected.enabled else selected.command)

    def action_dismiss_palette(self) -> None:
        self.dismiss(None)


__all__ = ["CommandPalette"]
