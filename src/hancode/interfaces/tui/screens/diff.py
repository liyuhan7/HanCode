"""Full-screen safe Diff inspection surface."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static


class DiffScreen(Screen[None]):
    BINDINGS = [("escape", "dismiss_screen", "返回"), ("j", "next_file", "下一文件"), ("k", "previous_file", "上一文件")]

    def __init__(self, content: str) -> None:
        super().__init__()
        self._content = content

    def compose(self) -> ComposeResult:
        yield Static(self._content, markup=False, id="tui-diff-screen-content")

    def action_dismiss_screen(self) -> None:
        self.app.pop_screen()

    def action_next_file(self) -> None:
        pass

    def action_previous_file(self) -> None:
        pass


__all__ = ["DiffScreen"]
