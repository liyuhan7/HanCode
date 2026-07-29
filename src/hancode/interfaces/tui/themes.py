"""The two session-only themes for the HanCode developer workbench."""

from __future__ import annotations

from typing import Any

from textual.app import App
from textual.theme import Theme


DARK_THEME_NAME = "hancode-dark"
LIGHT_THEME_NAME = "hancode-light"


def register_hancode_themes(app: App[Any]) -> None:
    """Register deterministic themes without reading or writing user settings."""
    app.register_theme(
        Theme(
            DARK_THEME_NAME,
            primary="#5EA1FF",
            secondary="#8BB9FE",
            warning="#E5B454",
            error="#F06B6B",
            success="#49C38A",
            accent="#8BB9FE",
            foreground="#E6EDF3",
            background="#0F1419",
            surface="#171E26",
            panel="#1F2933",
            dark=True,
        )
    )
    app.register_theme(
        Theme(
            LIGHT_THEME_NAME,
            primary="#245EA8",
            secondary="#3578C8",
            warning="#946200",
            error="#B42318",
            success="#257A55",
            accent="#3578C8",
            foreground="#17202A",
            background="#F5F7FA",
            surface="#FFFFFF",
            panel="#E9EEF5",
            dark=False,
        )
    )


def alternate_theme(current: str) -> str:
    return LIGHT_THEME_NAME if current == DARK_THEME_NAME else DARK_THEME_NAME


__all__ = ["DARK_THEME_NAME", "LIGHT_THEME_NAME", "alternate_theme", "register_hancode_themes"]
