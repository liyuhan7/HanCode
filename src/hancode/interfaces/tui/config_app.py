"""Standalone Textual host for project configuration."""

from __future__ import annotations

from pathlib import Path

from textual.app import App

from hancode.app.config_service import ConfigService, ConfigUpdateResult
from hancode.interfaces.tui.screens.config import ConfigScreen
from hancode.interfaces.tui.themes import DARK_THEME_NAME, register_hancode_themes


class ConfigTuiApp(App[ConfigUpdateResult | None]):
    TITLE = "HanCode 项目设置"

    def __init__(
        self,
        *,
        project_root: Path,
        config_service: ConfigService | None = None,
    ) -> None:
        super().__init__()
        register_hancode_themes(self)
        self.theme = DARK_THEME_NAME
        self._project_root = project_root
        self._config_service = config_service

    def on_mount(self) -> None:
        self.push_screen(
            ConfigScreen(
                project_root=self._project_root,
                config_service=self._config_service,
            ),
            self._on_config_closed,
        )

    def _on_config_closed(self, result: ConfigUpdateResult | None) -> None:
        self.exit(result)


__all__ = ["ConfigTuiApp"]
