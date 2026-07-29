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
from textual.widgets import Footer, Header, Input, ListView, Static, TabbedContent, TabPane

from hancode.interfaces.tui.widgets.activity_log import ActivityLog
from hancode.interfaces.tui.widgets.activity_feed import ActivityFeed
from hancode.interfaces.tui.widgets.inspector import Inspector
from hancode.interfaces.tui.widgets.phase_bar import PhaseBar


COMPACT_WIDTH_THRESHOLD = 100
NARROW_WIDTH_THRESHOLD = 70


def is_compact_width(width: int) -> bool:
    """Whether the terminal is narrow enough to use a stacked compact layout."""
    return width < COMPACT_WIDTH_THRESHOLD


def layout_mode(width: int) -> str:
    if width < NARROW_WIDTH_THRESHOLD:
        return "narrow"
    if width < COMPACT_WIDTH_THRESHOLD:
        return "medium"
    return "wide"


class MainScreen(Screen[None]):
    """Top-level screen holding the HanCode session layout."""

    DEFAULT_CSS = """
    #tui-task-header { height: 3; padding: 0 1; background: $surface; color: $text; }
    #tui-body { height: 1fr; }
    #tui-task-list { width: 24; border: round $primary; }
    #tui-center { width: 3fr; border: round $primary; }
    #tui-detail-panel { width: 2fr; border: round $secondary; padding: 0 1; }
    #tui-activity-feed, #tui-activity-log { height: 1fr; }
    #tui-narrow-tabs { display: none; height: 1fr; }
    #tui-narrow-tabs ListView { height: 1fr; }
    #tui-narrow-inspector, #tui-narrow-change { height: 1fr; padding: 0 1; }
    """

    def __init__(self, *, project_root: Path) -> None:
        super().__init__()
        self._project_root = project_root

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static("HanCode · 选择或创建任务", markup=False, id="tui-task-header")
        yield PhaseBar(id="tui-phase-bar")
        with Horizontal(id="tui-body"):
            yield ListView(id="tui-task-list")
            with Vertical(id="tui-center"):
                yield ActivityFeed(id="tui-activity-feed")
                yield ActivityLog(id="tui-activity-log")
            yield Inspector("", markup=False, id="tui-detail-panel")
        with TabbedContent(id="tui-narrow-tabs"):
            with TabPane("进展", id="tui-tab-progress"):
                yield ActivityFeed(id="tui-activity-feed-narrow")
                yield ActivityLog(id="tui-activity-log-narrow")
            with TabPane("改动", id="tui-tab-change"):
                yield Inspector("使用 /diff 查看改动", markup=False, id="tui-narrow-change")
            with TabPane("状态", id="tui-tab-status"):
                yield Inspector("", markup=False, id="tui-narrow-inspector")
            with TabPane("任务", id="tui-tab-tasks"):
                yield ListView(id="tui-task-list-narrow")
        yield Input(
            placeholder="描述你的课程项目任务，或输入 /help",
            id="tui-composer",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.call_after_refresh(self._apply_layout, self.size.width)

    def on_resize(self, event: object) -> None:
        size = getattr(event, "size", None)
        width = getattr(size, "width", None)
        if not isinstance(width, int):
            return
        self._apply_layout(width)

    def _apply_layout(self, width: int) -> None:
        mode = layout_mode(width)
        body = self.query_one("#tui-body", Horizontal)
        task_list = self.query_one("#tui-task-list", ListView)
        center = self.query_one("#tui-center", Vertical)
        detail = self.query_one("#tui-detail-panel", Inspector)
        tabs = self.query_one("#tui-narrow-tabs", TabbedContent)
        if mode == "narrow":
            body.styles.display = "none"
            tabs.styles.display = "block"
        else:
            body.styles.display = "block"
            tabs.styles.display = "none"
            body.styles.layout = "horizontal"
            task_list.styles.height = "1fr"
            task_list.styles.width = 24
            task_list.styles.display = "block" if mode == "wide" else "none"
            center.styles.height = "1fr"
            center.styles.width = "3fr"
            detail.styles.height = "1fr"
            detail.styles.width = "2fr"
