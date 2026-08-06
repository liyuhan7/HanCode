"""Focused modals used by the project configuration center."""

from __future__ import annotations

import shutil
import subprocess
import sys

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, ListItem, ListView, Static


class ConfigConfirmDialog(ModalScreen[bool]):
    BINDINGS = [("escape", "cancel", "取消")]

    def __init__(
        self,
        *,
        title: str,
        message: str,
        confirm_label: str,
        destructive: bool = False,
    ) -> None:
        super().__init__()
        self._title = title
        self._message = message
        self._confirm_label = confirm_label
        self._destructive = destructive

    def compose(self) -> ComposeResult:
        with Vertical(id="config-confirm-dialog"):
            yield Static(self._title, markup=False, classes="config-dialog-title")
            yield Static(self._message, markup=False)
            with Horizontal(classes="config-dialog-actions"):
                yield Button(
                    self._confirm_label,
                    id="config-confirm-yes",
                    variant="error" if self._destructive else "success",
                )
                yield Button("继续编辑", id="config-confirm-no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "config-confirm-yes":
            self.dismiss(True)
        elif event.button.id == "config-confirm-no":
            self.dismiss(False)

    def action_cancel(self) -> None:
        self.dismiss(False)


class CredentialInput(Input):
    """Input that can read an external terminal clipboard on Ctrl+V."""

    BINDINGS = [
        *Input.BINDINGS,
        Binding("ctrl+shift+v", "paste", "Paste from system clipboard", show=False),
        Binding("shift+insert", "paste", "Paste from system clipboard", show=False),
    ]

    def action_paste(self) -> None:
        clipboard = _read_system_clipboard()
        if clipboard is None:
            super().action_paste()
            return
        if not clipboard:
            return
        self.replace(clipboard.splitlines()[0], *self.selection)


class CredentialEditorDialog(ModalScreen[str | None]):
    """Collect one credential without ever rendering it as plain text."""

    BINDINGS = [("escape", "cancel", "取消")]

    def __init__(self, *, provider: str) -> None:
        super().__init__()
        self._provider = provider

    def compose(self) -> ComposeResult:
        with Vertical(id="config-credential-dialog"):
            yield Static("保存 API 凭据", markup=False, classes="config-dialog-title")
            yield Static(
                f"Provider：{self._provider}\n"
                "凭据只写入操作系统 Keyring，不会进入 project.json、日志或 Trace。",
                markup=False,
            )
            yield CredentialInput(
                placeholder="输入 API Key",
                password=True,
                id="config-credential-input",
            )
            yield Static("", id="config-credential-error", markup=False)
            with Horizontal(classes="config-dialog-actions"):
                yield Button(
                    "保存到系统 Keyring",
                    id="config-credential-save",
                    variant="success",
                )
                yield Button("取消", id="config-credential-cancel")

    def on_mount(self) -> None:
        self.query_one("#config-credential-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "config-credential-save":
            field = self.query_one("#config-credential-input", Input)
            value = field.value.strip()
            if not value:
                self.query_one("#config-credential-error", Static).update(
                    "API Key 不能为空。"
                )
                return
            field.value = ""
            self.dismiss(value)
        elif event.button.id == "config-credential-cancel":
            self.action_cancel()

    def action_cancel(self) -> None:
        self.query_one("#config-credential-input", Input).value = ""
        self.dismiss(None)


def _read_system_clipboard() -> str | None:
    """Read the OS clipboard without invoking a shell or logging its content."""
    if sys.platform == "win32":
        commands = (
            ("powershell.exe", "-NoProfile", "-NonInteractive", "-Command", "Get-Clipboard -Raw"),
            ("pwsh", "-NoProfile", "-NonInteractive", "-Command", "Get-Clipboard -Raw"),
        )
    elif sys.platform == "darwin":
        commands = (("pbpaste",),)
    else:
        commands = (
            ("wl-paste", "--no-newline"),
            ("xclip", "-selection", "clipboard", "-o"),
            ("xsel", "--clipboard", "--output"),
        )

    for command in commands:
        if shutil.which(command[0]) is None:
            continue
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=1.0,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0:
            return result.stdout
    return None


class StringListEditor(ModalScreen[tuple[str, ...] | None]):
    BINDINGS = [("escape", "cancel", "取消")]

    def __init__(self, *, title: str, values: tuple[str, ...]) -> None:
        super().__init__()
        self._title = title
        self._values = list(values)

    def compose(self) -> ComposeResult:
        with Vertical(id="config-list-dialog"):
            yield Static(self._title, markup=False, classes="config-dialog-title")
            yield ListView(id="config-list-values")
            yield Input(placeholder="输入新的相对路径或 glob 规则", id="config-list-input")
            with Horizontal(classes="config-dialog-actions"):
                yield Button("添加", id="config-list-add", variant="primary")
                yield Button("删除选中项", id="config-list-remove", variant="warning")
                yield Button("完成", id="config-list-done", variant="success")
                yield Button("取消", id="config-list-cancel")

    def on_mount(self) -> None:
        self._refresh_values()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "config-list-add":
            field = self.query_one("#config-list-input", Input)
            value = field.value.strip()
            if value and value not in self._values:
                self._values.append(value)
                field.value = ""
                self._refresh_values()
        elif button_id == "config-list-remove":
            view = self.query_one("#config-list-values", ListView)
            if view.index is not None and 0 <= view.index < len(self._values):
                del self._values[view.index]
                self._refresh_values()
        elif button_id == "config-list-done":
            self.dismiss(tuple(self._values))
        elif button_id == "config-list-cancel":
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _refresh_values(self) -> None:
        view = self.query_one("#config-list-values", ListView)
        view.clear()
        for value in self._values:
            view.append(ListItem(Label(value, markup=False)))


__all__ = ["ConfigConfirmDialog", "CredentialEditorDialog", "StringListEditor"]
