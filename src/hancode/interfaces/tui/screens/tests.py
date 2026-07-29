"""Full-screen safe test-report inspection surface."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static


class TestReportScreen(Screen[None]):
    BINDINGS = [("escape", "dismiss_screen", "返回")]

    def __init__(self, content: str) -> None:
        super().__init__()
        self._content = content

    def compose(self) -> ComposeResult:
        yield Static(self._content, markup=False, id="tui-test-screen-content")

    def action_dismiss_screen(self) -> None:
        self.app.pop_screen()


__all__ = ["TestReportScreen"]
