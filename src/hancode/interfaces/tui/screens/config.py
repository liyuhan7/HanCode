"""Responsive full-screen editor for .hancode/project.json."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Button,
    Footer,
    Input,
    Label,
    ListItem,
    ListView,
    Select,
    Static,
    Switch,
    Tab,
    Tabs,
)

from hancode.app.auth_service import AuthService
from hancode.app.config_service import ConfigService, ConfigUpdateResult
from hancode.app.credentials import CredentialSource, CredentialStatus
from hancode.core.errors import HanCodeError
from hancode.core.project_config import fresh_project_defaults
from hancode.interfaces.tui.config_dialogs import (
    ConfigConfirmDialog,
    CredentialEditorDialog,
    StringListEditor,
)
from hancode.interfaces.tui.config_presenters import (
    CONFIG_GROUPS,
    FIELDS_BY_GROUP,
    FIELDS_BY_KEY,
    ConfigFieldKind,
    ConfigFieldView,
)


class ConfigScreen(Screen[ConfigUpdateResult | None]):
    """Edit a normalized draft and write only after explicit confirmation."""

    BINDINGS = [
        ("ctrl+s", "save_config", "保存"),
        ("ctrl+r", "reset_group", "恢复本组默认"),
        ("ctrl+t", "toggle_config_theme", "切换主题"),
        ("escape", "close_config", "返回"),
    ]

    DEFAULT_CSS = """
    ConfigScreen { background: $background; color: $text; }
    #config-shell { height: 1fr; }
    #config-header { height: 3; padding: 0 1; background: $surface; color: $text; }
    #config-narrow-tabs { display: none; height: 3; background: $surface; }
    #config-body { height: 1fr; }
    #config-navigation { width: 24; min-width: 20; background: $surface; border-right: solid $panel; }
    #config-navigation-title { height: 3; padding: 1; color: $primary; }
    #config-navigation-list { height: 1fr; }
    #config-form { width: 1fr; padding: 0 1; }
    .config-group { display: none; height: 1fr; }
    .config-group.active { display: block; }
    .config-group-title { height: 3; padding: 1 0; color: $primary; }
    .config-field-row { height: auto; min-height: 4; margin-bottom: 1; }
    .config-field-label { height: 1; color: $text-muted; }
    .config-readonly { height: 3; padding: 1; background: $panel; }
    .config-list-button { width: 100%; }
    #config-help { width: 34; min-width: 28; padding: 1; background: $surface; border-left: solid $panel; }
    #config-help-title { height: 2; color: $primary; }
    #config-help-body { height: 1fr; }
    #config-status { height: 3; padding: 1; background: $panel; }
    #config-actions { height: 3; align-horizontal: right; padding: 0 1; background: $surface; }
    #config-actions Button { margin-left: 1; }
    ConfigConfirmDialog, CredentialEditorDialog, StringListEditor { align: center middle; }
    #config-confirm-dialog, #config-credential-dialog, #config-list-dialog {
        width: 76%; max-width: 92; height: auto; max-height: 80%;
        padding: 1 2; background: $panel; border: heavy $primary;
    }
    #config-credential-panel {
        height: auto; min-height: 8; margin: 1 0; padding: 1;
        background: $panel;
    }
    #config-credential-title { height: 1; color: $primary; }
    #config-credential-status { height: auto; min-height: 2; margin: 1 0; }
    #config-credential-actions { height: 3; }
    #config-credential-actions Button { margin-right: 1; }
    #config-credential-input { margin: 1 0; }
    #config-credential-error { height: 2; color: $error; }
    #config-list-values { height: 12; margin: 1 0; border: solid $surface; }
    .config-dialog-title { height: 2; color: $primary; }
    .config-dialog-actions { height: 3; align-horizontal: right; margin-top: 1; }
    .config-dialog-actions Button { margin-left: 1; }
    """

    def __init__(
        self,
        *,
        project_root: Path,
        config_service: ConfigService | None = None,
        auth_service: AuthService | None = None,
    ) -> None:
        super().__init__()
        self._project_root = project_root.resolve()
        self._service = config_service or ConfigService()
        self._auth_service = auth_service or AuthService()
        view = self._service.load(self._project_root)
        self._config_path = view.config_path
        self._original = view.to_dict()
        self._draft = view.to_dict()
        self._active_group = CONFIG_GROUPS[0].group_id
        self._field_errors: dict[str, str] = {}
        self._validation_error: str | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="config-shell"):
            yield Static("", id="config-header", markup=False)
            yield Tabs(
                *(Tab(group.label, id=f"config-tab-{group.group_id}") for group in CONFIG_GROUPS),
                id="config-narrow-tabs",
            )
            with Horizontal(id="config-body"):
                with Vertical(id="config-navigation"):
                    yield Static("配置分组", id="config-navigation-title", markup=False)
                    yield ListView(
                        *(
                            ListItem(
                                Label(group.label, markup=False),
                                id=f"config-nav-{group.group_id}",
                            )
                            for group in CONFIG_GROUPS
                        ),
                        id="config-navigation-list",
                    )
                with Vertical(id="config-form"):
                    for group in CONFIG_GROUPS:
                        classes = "config-group active" if group.group_id == self._active_group else "config-group"
                        with VerticalScroll(
                            id=f"config-group-{group.group_id}",
                            classes=classes,
                        ):
                            yield Static(
                                f"{group.label}\n{group.summary}",
                                markup=False,
                                classes="config-group-title",
                            )
                            for field in FIELDS_BY_GROUP[group.group_id]:
                                yield from self._compose_field(field)
                            if group.group_id == "provider":
                                yield from self._compose_credential_panel()
                with VerticalScroll(id="config-help"):
                    yield Static("字段说明", id="config-help-title", markup=False)
                    yield Static("", id="config-help-body", markup=False)
            yield Static("", id="config-status", markup=False)
            with Horizontal(id="config-actions"):
                yield Button("恢复本组默认 [Ctrl+R]", id="config-reset", variant="warning")
                yield Button("保存配置 [Ctrl+S]", id="config-save", variant="success")
                yield Button("返回 [Esc]", id="config-cancel")
            yield Footer()

    def on_mount(self) -> None:
        navigation = self.query_one("#config-navigation-list", ListView)
        navigation.index = 0
        self._refresh_provider_controls()
        self._refresh_credential_status()
        self._refresh_state()
        self._apply_layout(self.size.width)

    def on_resize(self, event: object) -> None:
        size = getattr(event, "size", self.size)
        self._apply_layout(size.width)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or ""
        if item_id.startswith("config-nav-"):
            self._show_group(item_id.removeprefix("config-nav-"))

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        tab_id = event.tab.id or ""
        if tab_id.startswith("config-tab-"):
            self._show_group(tab_id.removeprefix("config-tab-"))

    def on_input_changed(self, event: Input.Changed) -> None:
        key = _field_key(event.input.id)
        if key is None:
            return
        field = FIELDS_BY_KEY[key]
        raw = event.value.strip()
        if field.kind is ConfigFieldKind.INTEGER:
            try:
                value = int(raw)
            except ValueError:
                self._field_errors[key] = "请输入整数。"
            else:
                self._field_errors.pop(key, None)
                self._draft[key] = value
        else:
            self._field_errors.pop(key, None)
            self._draft[key] = None if field.nullable and not raw else raw
        self._refresh_state()

    def on_select_changed(self, event: Select.Changed) -> None:
        key = _field_key(event.select.id)
        if key is None:
            return
        value = event.value
        self._draft[key] = None if value is Select.BLANK or value == "" else str(value)
        if key == "llm_provider":
            self._refresh_provider_controls()
            self._refresh_credential_status()
        elif key == "credential_source":
            self._refresh_credential_status()
        self._refresh_state()

    def on_switch_changed(self, event: Switch.Changed) -> None:
        key = _field_key(event.switch.id)
        if key is not None:
            self._draft[key] = event.value
            self._refresh_state()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id == "config-save":
            self.action_save_config()
        elif button_id == "config-reset":
            self.action_reset_group()
        elif button_id == "config-cancel":
            self.action_close_config()
        elif button_id == "config-credential-update":
            self._open_credential_editor()
        elif button_id == "config-credential-clear":
            self._confirm_credential_clear()
        elif button_id.startswith("config-field-"):
            key = _field_key(button_id)
            if key is not None and FIELDS_BY_KEY[key].kind is ConfigFieldKind.STRING_LIST:
                values = tuple(cast(list[str], self._draft[key]))
                self.app.push_screen(
                    StringListEditor(title=FIELDS_BY_KEY[key].label, values=values),
                    lambda result, field_key=key: self._on_list_result(field_key, result),
                )

    def action_save_config(self) -> None:
        if self._field_errors:
            self.notify("请先修正字段格式错误。", severity="error")
            return
        try:
            self._service.validate(self._project_root, self._draft)
        except HanCodeError as exc:
            self._validation_error = exc.structured_error.message
            self._refresh_state()
            self.notify(exc.structured_error.message, severity="error")
            return

        changed = self._changed_fields()
        lines = [f"- {FIELDS_BY_KEY[key].label}" for key in changed if key in FIELDS_BY_KEY]
        summary = "\n".join(lines) if lines else "仅展开旧配置中缺失的默认字段。"
        provider = str(self._draft["llm_provider"])
        if provider in {"anthropic", "local"}:
            summary += f"\n\n注意：{provider} 适配器当前尚未实现。"
        self.app.push_screen(
            ConfigConfirmDialog(
                title="保存项目配置？",
                message=f"将更新：\n{summary}\n\n写入采用同目录原子替换。",
                confirm_label="确认保存",
            ),
            self._on_save_confirmed,
        )

    def action_reset_group(self) -> None:
        defaults = fresh_project_defaults()
        for field in FIELDS_BY_GROUP[self._active_group]:
            if field.kind is ConfigFieldKind.READONLY:
                continue
            if field.key in defaults:
                value = defaults[field.key]
                self._draft[field.key] = list(value) if isinstance(value, list) else value
            elif field.key == "project_id":
                self._draft[field.key] = self._project_root.name or "hancode-project"
            elif field.key == "course_name":
                self._draft[field.key] = "unspecified-course"
            elif field.key == "assignment_name":
                self._draft[field.key] = "unspecified-assignment"
        self._field_errors.clear()
        self._sync_group_widgets()
        self._refresh_provider_controls()
        self._refresh_credential_status()
        self._refresh_state()

    def action_toggle_config_theme(self) -> None:
        from hancode.interfaces.tui.themes import LIGHT_THEME_NAME, alternate_theme

        self.app.theme = alternate_theme(self.app.theme)
        self.notify("已切换为浅色主题。" if self.app.theme == LIGHT_THEME_NAME else "已切换为深色主题。")

    def action_close_config(self) -> None:
        if not self._changed_fields():
            self.dismiss(None)
            return
        self.app.push_screen(
            ConfigConfirmDialog(
                title="放弃未保存修改？",
                message="放弃后 project.json 保持不变。",
                confirm_label="放弃修改",
                destructive=True,
            ),
            self._on_discard_confirmed,
        )

    def _compose_field(self, field: ConfigFieldView) -> ComposeResult:
        value = self._draft[field.key]
        with Vertical(classes="config-field-row"):
            yield Label(field.label, markup=False, classes="config-field-label")
            if field.kind is ConfigFieldKind.READONLY:
                yield Static(str(value), id=field.widget_id, markup=False, classes="config-readonly")
            elif field.kind is ConfigFieldKind.TEXT:
                yield Input(
                    value="" if value is None else str(value),
                    placeholder="未配置" if field.nullable else "",
                    id=field.widget_id,
                )
            elif field.kind is ConfigFieldKind.INTEGER:
                yield Input(value=str(value), id=field.widget_id)
            elif field.kind is ConfigFieldKind.CHOICE:
                selected = "" if value is None else str(value)
                yield Select(
                    field.choices,
                    value=selected,
                    allow_blank=field.nullable,
                    id=field.widget_id,
                )
            elif field.kind is ConfigFieldKind.BOOLEAN:
                yield Switch(value=bool(value), id=field.widget_id)
            elif field.kind is ConfigFieldKind.STRING_LIST:
                count = len(cast(list[str], value))
                yield Button(
                    f"编辑列表（{count} 项）",
                    id=field.widget_id,
                    classes="config-list-button",
                )

    def _compose_credential_panel(self) -> ComposeResult:
        with Vertical(id="config-credential-panel"):
            yield Static("API 凭据", id="config-credential-title", markup=False)
            yield Static("", id="config-credential-status", markup=False)
            with Horizontal(id="config-credential-actions"):
                yield Button(
                    "录入 API Key",
                    id="config-credential-update",
                    variant="primary",
                )
                yield Button(
                    "清除 Keyring 凭据",
                    id="config-credential-clear",
                    variant="warning",
                )

    def _show_group(self, group_id: str) -> None:
        if group_id not in FIELDS_BY_GROUP:
            return
        self._active_group = group_id
        for group in CONFIG_GROUPS:
            widget = self.query_one(f"#config-group-{group.group_id}", VerticalScroll)
            widget.set_class(group.group_id == group_id, "active")
        group = next(item for item in CONFIG_GROUPS if item.group_id == group_id)
        self.query_one("#config-help-body", Static).update(
            f"{group.label}\n\n{group.summary}\n\n"
            "Enter/Space 编辑当前字段；Ctrl+S 查看变更并保存；"
            "Ctrl+R 恢复当前分组默认值。"
        )

    def _refresh_state(self) -> None:
        self._validation_error = None
        if not self._field_errors:
            try:
                self._service.validate(self._project_root, self._draft)
            except HanCodeError as exc:
                self._validation_error = exc.structured_error.message

        changed = self._changed_fields()
        provider = str(self._draft["llm_provider"])
        dirty = f"未保存修改：{len(changed)} 项" if changed else "无未保存修改"
        self.query_one("#config-header", Static).update(
            f"HanCode 项目设置 · {provider}\n.hancode/project.json · {dirty}"
        )
        if self._field_errors:
            detail = "；".join(
                f"{FIELDS_BY_KEY[key].label}：{message}"
                for key, message in self._field_errors.items()
            )
            status = f"✗ 字段格式错误：{detail}"
        elif self._validation_error:
            status = f"✗ 尚不能保存：{self._validation_error}"
        else:
            status = "✓ 配置有效。Provider/策略在下次运行生效；retry_budget 仅影响新任务。"
        self.query_one("#config-status", Static).update(status)

    def _refresh_provider_controls(self) -> None:
        provider = str(self._draft["llm_provider"])
        self.query_one(f"#{FIELDS_BY_KEY['model_name'].widget_id}").disabled = provider == "mock"
        connection_disabled = provider in {"mock", "local"}
        self.query_one(f"#{FIELDS_BY_KEY['credential_source'].widget_id}").disabled = connection_disabled
        self.query_one(f"#{FIELDS_BY_KEY['provider_base_url'].widget_id}").disabled = connection_disabled

    def _refresh_credential_status(self) -> None:
        provider = str(self._draft["llm_provider"])
        status_widget = self.query_one("#config-credential-status", Static)
        update_button = self.query_one("#config-credential-update", Button)
        clear_button = self.query_one("#config-credential-clear", Button)
        if provider in {"mock", "local"}:
            status_widget.update("此 Provider 不需要 API Key。")
            update_button.disabled = True
            clear_button.disabled = True
            return

        source = _credential_source(self._draft.get("credential_source"))
        try:
            status = self._auth_service.status(
                provider,
                source=source,
                project_root=self._project_root,
            )
        except HanCodeError as exc:
            status_widget.update(f"✗ 无法读取凭据状态：{exc.structured_error.message}")
            update_button.disabled = True
            clear_button.disabled = True
            return

        status_widget.update(_credential_status_text(status))
        external = status.source in {"env", "dotenv"}
        update_button.disabled = external
        clear_button.disabled = status.source != "keyring"
        update_button.label = "更新 API Key" if status.source == "keyring" else "录入 API Key"

    def _open_credential_editor(self) -> None:
        provider = str(self._draft["llm_provider"])
        if provider not in {"openai_compatible", "anthropic"}:
            return
        source = _credential_source(self._draft.get("credential_source"))
        try:
            status = self._auth_service.status(
                provider,
                source=source,
                project_root=self._project_root,
            )
        except HanCodeError as exc:
            self.notify(exc.structured_error.message, severity="error")
            return
        if status.source in {"env", "dotenv"}:
            self.notify("当前凭据由外部来源管理，请在来源处修改。", severity="warning")
            return
        self.app.push_screen(
            CredentialEditorDialog(provider=provider),
            self._on_credential_entered,
        )

    def _on_credential_entered(self, secret: str | None) -> None:
        if secret is None:
            return
        provider = str(self._draft["llm_provider"])
        try:
            self._auth_service.set_secret(provider, secret)
        except HanCodeError as exc:
            self.notify(exc.structured_error.message, severity="error")
            self._refresh_credential_status()
            return
        self._draft["credential_source"] = "keyring"
        source_widget = self.query_one(
            f"#{FIELDS_BY_KEY['credential_source'].widget_id}",
            Select,
        )
        source_widget.value = "keyring"
        self._refresh_credential_status()
        self._refresh_state()
        self.notify("API Key 已保存到系统 Keyring；项目配置仍需 Ctrl+S 确认保存。")

    def _confirm_credential_clear(self) -> None:
        provider = str(self._draft["llm_provider"])
        self.app.push_screen(
            ConfigConfirmDialog(
                title="清除 Keyring 凭据？",
                message=(
                    f"将从系统 Keyring 删除 {provider} 的 API Key。"
                    "\n此操作不会修改环境变量或 .env。"
                ),
                confirm_label="清除 Keyring 凭据",
                destructive=True,
            ),
            self._on_credential_clear_confirmed,
        )

    def _on_credential_clear_confirmed(self, confirmed: bool | None) -> None:
        if not confirmed:
            return
        provider = str(self._draft["llm_provider"])
        try:
            self._auth_service.clear_secret(provider, source="keyring")
        except HanCodeError as exc:
            self.notify(exc.structured_error.message, severity="error")
            return
        self._refresh_credential_status()
        self.notify("系统 Keyring 中的 API Key 已清除。")

    def _sync_group_widgets(self) -> None:
        for field in FIELDS_BY_GROUP[self._active_group]:
            if field.kind is ConfigFieldKind.READONLY:
                continue
            widget = self.query_one(f"#{field.widget_id}")
            value = self._draft[field.key]
            if isinstance(widget, Input):
                widget.value = "" if value is None else str(value)
            elif isinstance(widget, Select):
                widget.value = "" if value is None else str(value)
            elif isinstance(widget, Switch):
                widget.value = bool(value)
            elif isinstance(widget, Button):
                widget.label = f"编辑列表（{len(cast(list[str], value))} 项）"

    def _on_list_result(self, key: str, result: tuple[str, ...] | None) -> None:
        if result is None:
            return
        self._draft[key] = list(result)
        button = self.query_one(f"#{FIELDS_BY_KEY[key].widget_id}", Button)
        button.label = f"编辑列表（{len(result)} 项）"
        self._refresh_state()

    def _on_save_confirmed(self, confirmed: bool | None) -> None:
        if not confirmed:
            return
        try:
            result = self._service.save(self._project_root, self._draft)
        except HanCodeError as exc:
            self.notify(exc.structured_error.message, severity="error")
            return
        self.dismiss(result)

    def _on_discard_confirmed(self, confirmed: bool | None) -> None:
        if confirmed:
            self.dismiss(None)

    def _changed_fields(self) -> tuple[str, ...]:
        return tuple(
            key for key, value in self._draft.items() if self._original.get(key) != value
        )

    def _apply_layout(self, width: int) -> None:
        navigation = self.query_one("#config-navigation")
        help_panel = self.query_one("#config-help")
        tabs = self.query_one("#config-narrow-tabs", Tabs)
        if width >= 100:
            navigation.display = True
            navigation.styles.width = 24
            help_panel.display = True
            tabs.display = False
        elif width >= 70:
            navigation.display = True
            navigation.styles.width = 22
            help_panel.display = False
            tabs.display = False
        else:
            navigation.display = False
            help_panel.display = False
            tabs.display = True


def _field_key(widget_id: str | None) -> str | None:
    prefix = "config-field-"
    if widget_id is None or not widget_id.startswith(prefix):
        return None
    candidate = widget_id.removeprefix(prefix).replace("-", "_")
    return candidate if candidate in FIELDS_BY_KEY else None


def _credential_source(value: object) -> CredentialSource | None:
    if value in {"keyring", "env", "dotenv"}:
        return value
    return None


def _credential_status_text(status: CredentialStatus) -> str:
    if not status.configured:
        return "○ 未配置 API Key。选择“系统 Keyring”后可安全录入。"
    if status.source == "keyring":
        return f"✓ 已配置 · 系统 Keyring · {status.masked_id or '****'}"
    if status.source == "env":
        return (
            f"✓ 已配置 · 环境变量 · {status.masked_id or '****'}\n"
            "此来源只读，请在环境变量中更新或清除。"
        )
    if status.source == "dotenv":
        return (
            f"✓ 已配置 · .env · {status.masked_id or '****'}\n"
            "此来源只读，请在项目 .env 中更新或清除。"
        )
    return "○ 当前 Provider 不需要 API Key。"


__all__ = ["ConfigScreen"]
