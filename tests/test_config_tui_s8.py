from __future__ import annotations

import asyncio
from pathlib import Path

from textual.app import App
from textual.widgets import Button, Input, Static, Tabs

from hancode.app.auth_service import AuthService
from hancode.app.config_service import ConfigService
from hancode.app.config_service import ConfigUpdateResult
from hancode.app.credentials import CredentialProvider
from hancode.interfaces.tui.config_dialogs import ConfigConfirmDialog
from hancode.interfaces.tui.config_dialogs import CredentialEditorDialog
from hancode.interfaces.tui.config_app import ConfigTuiApp
from hancode.interfaces.tui.config_presenters import (
    CONFIG_GROUPS,
    FIELDS_BY_GROUP,
    ConfigFieldKind,
)
from hancode.interfaces.tui.app import HanCodeTuiApp
from hancode.interfaces.tui.command_actions import available_actions
from hancode.interfaces.tui.commands import parse_command
from hancode.interfaces.tui.screens.config import ConfigScreen
from hancode.interfaces.tui.screens.main import MainScreen
from hancode.interfaces.tui.view_state import TuiViewState
from hancode.storage.workspace import init_project_workspace


class FakeCredentialStore:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service_name: str, username: str) -> str | None:
        return self.values.get((service_name, username))

    def set_password(self, service_name: str, username: str, password: str) -> None:
        self.values[(service_name, username)] = password

    def delete_password(self, service_name: str, username: str) -> None:
        self.values.pop((service_name, username), None)


def _initialize(project_root: Path) -> None:
    init_project_workspace(
        project_root,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Harness",
    )


def _configure_remote_provider(project_root: Path, source: str = "keyring") -> None:
    service = ConfigService()
    values = service.load(project_root).to_dict()
    values.update(
        {
            "llm_provider": "openai_compatible",
            "model_name": "gpt-example",
            "credential_source": source,
            "provider_base_url": "https://api.example.com/v1",
        }
    )
    service.save(project_root, values)


def test_config_presenter_exposes_runtime_memory_limits() -> None:
    assert any(group.group_id == "memory" and group.label == "运行时记忆" for group in CONFIG_GROUPS)
    fields = FIELDS_BY_GROUP["memory"]

    assert tuple(field.key for field in fields) == (
        "max_memory_blob_bytes",
        "max_memory_task_bytes",
        "max_memory_recent_events",
        "max_memory_file_entries",
        "max_memory_hot_contents",
    )
    assert all(field.kind is ConfigFieldKind.INTEGER for field in fields)


def test_config_tui_mounts_all_groups_in_wide_layout(tmp_path: Path) -> None:
    _initialize(tmp_path)
    app = ConfigTuiApp(project_root=tmp_path)

    async def _run() -> None:
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()

            assert isinstance(app.screen, ConfigScreen)
            assert len(app.screen.query(".config-group")) == 7
            assert app.screen.query_one("#config-navigation").display is True
            assert app.screen.query_one("#config-help").display is True
            assert app.screen.query_one("#config-narrow-tabs", Tabs).display is False

    asyncio.run(_run())


def test_config_tui_uses_tabs_in_narrow_layout(tmp_path: Path) -> None:
    _initialize(tmp_path)
    app = ConfigTuiApp(project_root=tmp_path)

    async def _run() -> None:
        async with app.run_test(size=(60, 28)) as pilot:
            await pilot.pause()

            assert app.screen.query_one("#config-navigation").display is False
            assert app.screen.query_one("#config-help").display is False
            assert app.screen.query_one("#config-narrow-tabs", Tabs).display is True

    asyncio.run(_run())


def test_config_screen_saves_only_after_change_confirmation(tmp_path: Path) -> None:
    _initialize(tmp_path)

    class HostApp(App[None]):
        def __init__(self) -> None:
            super().__init__()
            self.result: ConfigUpdateResult | None = None

        def on_mount(self) -> None:
            self.push_screen(
                ConfigScreen(project_root=tmp_path),
                self._on_config_closed,
            )

        def _on_config_closed(self, result: ConfigUpdateResult | None) -> None:
            self.result = result

    app = HostApp()

    async def _run() -> None:
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            field = app.screen.query_one("#config-field-course-name", Input)
            field.value = "软件工程"
            await pilot.pause()

            await pilot.press("ctrl+s")
            await pilot.pause()
            assert isinstance(app.screen, ConfigConfirmDialog)

            await pilot.click("#config-confirm-yes")
            await pilot.pause()
            assert app.result is not None
            assert app.result.changed_fields == ("course_name",)

    asyncio.run(_run())


def test_config_screen_escape_discards_draft_without_writing(tmp_path: Path) -> None:
    _initialize(tmp_path)
    config_path = tmp_path / ".hancode" / "project.json"
    before = config_path.read_bytes()

    class HostApp(App[None]):
        def on_mount(self) -> None:
            self.push_screen(ConfigScreen(project_root=tmp_path))

    app = HostApp()

    async def _run() -> None:
        async with app.run_test(size=(90, 32)) as pilot:
            await pilot.pause()
            app.screen.query_one("#config-field-course-name", Input).value = "不会保存"
            await pilot.pause()

            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, ConfigConfirmDialog)
            await pilot.click("#config-confirm-yes")
            await pilot.pause()

    asyncio.run(_run())
    assert config_path.read_bytes() == before


def test_main_tui_opens_and_closes_config_without_losing_state(tmp_path: Path) -> None:
    _initialize(tmp_path)
    app = HanCodeTuiApp(project_root=tmp_path)

    async def _run() -> None:
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            before = app.controller.state

            app.submit_input("/config")
            await pilot.pause()
            assert isinstance(app.screen, ConfigScreen)

            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, MainScreen)
            assert app.controller.state == before

    asyncio.run(_run())


def test_config_action_is_disabled_while_worker_is_busy(tmp_path: Path) -> None:
    state = TuiViewState.initial(tmp_path).with_busy(True, running_task_id="task-001")
    action = next(item for item in available_actions(state) if item.action_id == "config")

    assert parse_command("/config").name == "config"  # type: ignore[union-attr]
    assert action.enabled is False
    assert action.disabled_reason == "任务运行时不能修改项目设置。"


def test_config_screen_stores_hidden_api_key_in_keyring_only(tmp_path: Path) -> None:
    _initialize(tmp_path)
    _configure_remote_provider(tmp_path)
    config_path = tmp_path / ".hancode" / "project.json"
    before = config_path.read_bytes()
    store = FakeCredentialStore()
    auth_service = AuthService(
        CredentialProvider(
            keyring_backend=store,
            environ={},
            dotenv_path=tmp_path / ".env",
        )
    )

    class HostApp(App[None]):
        def on_mount(self) -> None:
            self.push_screen(
                ConfigScreen(project_root=tmp_path, auth_service=auth_service)
            )

    app = HostApp()
    secret = "fake-config-screen-secret-4f2a"

    async def _run() -> None:
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, ConfigScreen)
            screen._show_group("provider")
            screen._open_credential_editor()
            await pilot.pause()

            assert isinstance(app.screen, CredentialEditorDialog)
            field = app.screen.query_one("#config-credential-input", Input)
            assert field.password is True
            field.value = secret
            await pilot.click("#config-credential-save")
            await pilot.pause()

            assert isinstance(app.screen, ConfigScreen)
            assert store.get_password("hancode", "openai_compatible") == secret
            assert app.screen._draft["credential_source"] == "keyring"
            rendered = str(
                app.screen.query_one("#config-credential-status", Static).render()
            )
            assert "****4f2a" in rendered
            assert secret not in rendered
            assert config_path.read_bytes() == before

            app.screen._confirm_credential_clear()
            await pilot.pause()
            assert isinstance(app.screen, ConfigConfirmDialog)
            await pilot.click("#config-confirm-yes")
            await pilot.pause()
            assert isinstance(app.screen, ConfigScreen)
            assert store.get_password("hancode", "openai_compatible") is None
            assert "未配置 API Key" in str(
                app.screen.query_one("#config-credential-status", Static).render()
            )

    asyncio.run(_run())


def test_config_screen_treats_environment_credential_as_read_only(
    tmp_path: Path,
) -> None:
    _initialize(tmp_path)
    _configure_remote_provider(tmp_path, source="env")
    auth_service = AuthService(
        CredentialProvider(
            keyring_backend=FakeCredentialStore(),
            environ={"OPENAI_API_KEY": "environment-secret-8b3c"},
            dotenv_path=tmp_path / ".env",
        )
    )

    class HostApp(App[None]):
        def on_mount(self) -> None:
            self.push_screen(
                ConfigScreen(project_root=tmp_path, auth_service=auth_service)
            )

    app = HostApp()

    async def _run() -> None:
        async with app.run_test(size=(90, 32)) as pilot:
            await pilot.pause()
            status = str(
                app.screen.query_one("#config-credential-status", Static).render()
            )
            assert "环境变量" in status
            assert "****8b3c" in status
            assert "environment-secret-8b3c" not in status
            assert app.screen.query_one(
                "#config-credential-update", Button
            ).disabled
            assert app.screen.query_one(
                "#config-credential-clear", Button
            ).disabled

    asyncio.run(_run())
