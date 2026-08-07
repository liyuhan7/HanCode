"""Structured help overlay for the HanCode TUI."""

from __future__ import annotations

from dataclasses import dataclass

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import Input, Label, ListItem, ListView, Static


@dataclass(frozen=True, slots=True)
class HelpCommand:
    syntax: str
    description: str


@dataclass(frozen=True, slots=True)
class HelpSection:
    section_id: str
    label: str
    commands: tuple[HelpCommand, ...]


HELP_SECTIONS = (
    HelpSection(
        "quickstart",
        "快速开始",
        (
            HelpCommand("/task <goal>", "创建并运行一个任务"),
            HelpCommand("/tasks", "查看任务列表"),
            HelpCommand("/use <id>", "切换当前任务"),
            HelpCommand("/run", "运行当前任务"),
            HelpCommand("/status", "查看当前任务状态"),
            HelpCommand("/help", "打开帮助中心"),
        ),
    ),
    HelpSection(
        "workflow",
        "任务流程",
        (
            HelpCommand("/resume", "继续暂停或等待中的任务"),
            HelpCommand("/pause", "在安全点暂停当前任务"),
            HelpCommand("/approve", "批准当前待确认操作"),
            HelpCommand("/reject <reason>", "拒绝操作并记录原因"),
        ),
    ),
    HelpSection(
        "review",
        "审查与交付",
        (
            HelpCommand("/diff [task|latest] [path]", "查看任务或最新改动"),
            HelpCommand("/test", "查看最近一次测试结果"),
            HelpCommand("/checkpoints", "查看可恢复的检查点"),
            HelpCommand("/delivery", "查看交付状态与阻塞项"),
            HelpCommand("/trace [event-id]", "查看运行事件记录"),
            HelpCommand("/artifacts", "查看可交付产物"),
            HelpCommand("/open <name>", "打开指定交付文档"),
            HelpCommand("/build", "查看或执行项目构建"),
            HelpCommand("/export <directory>", "导出允许的交付产物"),
            HelpCommand("/rollback [confirm|cancel]", "恢复到最近检查点"),
        ),
    ),
    HelpSection(
        "interface",
        "界面与设置",
        (
            HelpCommand("/view [focus|inspect]", "切换聚焦或检查视图"),
            HelpCommand("/theme [dark|light]", "切换深色或浅色主题"),
            HelpCommand("/config", "打开项目设置"),
            HelpCommand("/clear", "清空当前活动视图"),
            HelpCommand("/quit", "退出 HanCode"),
        ),
    ),
)


class HelpScreen(ModalScreen[None]):
    """Searchable, category-based help instead of a single command dump."""

    BINDINGS = [("escape", "dismiss_help", "关闭")]

    def __init__(self) -> None:
        super().__init__()
        self._section_index = 0
        self._section_id = HELP_SECTIONS[0].section_id
        self._query = ""
        self._command_index = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="tui-help-dialog"):
            yield Static("帮助中心  /help", id="tui-help-title", markup=False)
            with Horizontal(id="tui-help-search-row"):
                yield Input(placeholder="搜索命令或功能…", id="tui-help-search")
                yield Static(
                    "Tab 切换区域   ←→ 切换列表   ↑↓ 浏览   Enter 查看   Esc 关闭",
                    id="tui-help-search-hint",
                    markup=False,
                )
            with Horizontal(id="tui-help-body"):
                with ListView(id="tui-help-categories"):
                    for section in HELP_SECTIONS:
                        yield ListItem(
                            Label(section.label),
                            id=f"help-category-{section.section_id}",
                        )
                with Vertical(id="tui-help-content"):
                    yield Static("", id="tui-help-section-title", markup=False)
                    yield ListView(id="tui-help-commands")
            with Horizontal(id="tui-help-footer"):
                yield Static("完整命令列表", id="tui-help-footer-list", markup=False)
                yield Static("Esc  关闭帮助", id="tui-help-footer-close", markup=False)

    def on_mount(self) -> None:
        self._render_help()
        self.query_one("#tui-help-search", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "tui-help-search":
            self._query = event.value.strip().casefold()
            self._render_help()

    def on_key(self, event: Key) -> None:
        if event.key == "up":
            if self._commands_have_focus():
                return
            self._move_category(-1)
            event.stop()
        elif event.key == "down":
            if self._commands_have_focus():
                return
            self._move_category(1)
            event.stop()
        elif event.key == "left":
            if self._commands_have_focus():
                self.query_one("#tui-help-categories", ListView).focus()
                event.stop()
        elif event.key == "right":
            if self._categories_have_focus():
                self.query_one("#tui-help-commands", ListView).focus()
                event.stop()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or ""
        if not item_id.startswith("help-category-"):
            return
        self._section_index = next(
            index
            for index, section in enumerate(HELP_SECTIONS)
            if section.section_id == item_id.removeprefix("help-category-")
        )
        self._section_id = item_id.removeprefix("help-category-")
        self._command_index = 0
        self._render_help()

    def action_dismiss_help(self) -> None:
        self.dismiss(None)

    def _move_category(self, delta: int) -> None:
        self._section_index = (self._section_index + delta) % len(HELP_SECTIONS)
        self._section_id = HELP_SECTIONS[self._section_index].section_id
        self._command_index = 0
        categories = self.query_one("#tui-help-categories", ListView)
        categories.index = self._section_index
        self._render_help()

    def _render_help(self) -> None:
        section = next(
            section for section in HELP_SECTIONS if section.section_id == self._section_id
        )
        source = (
            tuple(command for item in HELP_SECTIONS for command in item.commands)
            if self._query
            else section.commands
        )
        commands = tuple(
            command
            for command in source
            if not self._query
            or self._query in command.syntax.casefold()
            or self._query in command.description.casefold()
        )
        title = section.label if not self._query else "搜索结果"
        self.query_one("#tui-help-section-title", Static).update(title)
        command_view = self.query_one("#tui-help-commands", ListView)
        command_view.clear()
        if not commands:
            command_view.append(
                ListItem(
                    Static(
                        "[yellow]没有匹配的命令[/]\n\n试试搜索 command、任务或状态。",
                        markup=True,
                    ),
                    disabled=True,
                )
            )
            command_view.index = 0
            return
        self._command_index = min(self._command_index, len(commands) - 1)
        for command in commands:
            command_view.append(
                ListItem(
                    Static(
                        f"[bold #83d89a]{escape(command.syntax)}[/]\n"
                        f"{escape(command.description)}",
                        markup=True,
                    )
                )
            )
        command_view.index = self._command_index

    def _commands_have_focus(self) -> bool:
        focused = self.focused
        return isinstance(focused, ListView) and focused.id == "tui-help-commands"

    def _categories_have_focus(self) -> bool:
        focused = self.focused
        return isinstance(focused, ListView) and focused.id == "tui-help-categories"


__all__ = ["HelpCommand", "HelpSection", "HELP_SECTIONS", "HelpScreen"]
