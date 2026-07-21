"""Main screen for the HanCode TUI shell (S4-T1, extended in S4-T5).

Holds the session layout: task list, phase bar, activity log, detail panel and
composer. Live wiring to the controller and background Worker is added by the
app layer. Rendering helpers here stay pure so layout choices are testable.
"""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, ListView, Static

from hancode.interfaces.tui.widgets.activity_log import ActivityLog
from hancode.interfaces.tui.widgets.phase_bar import PhaseBar


COMPACT_WIDTH_THRESHOLD = 100


def is_compact_width(width: int) -> bool:
    """Whether the terminal is narrow enough to use a stacked compact layout."""
    return width < COMPACT_WIDTH_THRESHOLD


class MainScreen(Screen[None]):
    """Top-level screen holding the HanCode session layout."""

    def __init__(self, *, project_root: Path) -> None:
        super().__init__()
        self._project_root = project_root

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield PhaseBar(id="tui-phase-bar")
        with Horizontal(id="tui-body"):
            yield ListView(id="tui-task-list")
            with Vertical(id="tui-center"):
                yield ActivityLog(id="tui-activity-log")
            yield Static("", id="tui-detail-panel")
        yield Input(
            placeholder="描述你的课程项目任务，或输入 /help",
            id="tui-composer",
        )
        yield Footer()
