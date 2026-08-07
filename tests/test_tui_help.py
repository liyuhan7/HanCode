"""Regression coverage for the structured /help overlay."""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual.widget import Widget
from textual.widgets import Input, ListView, Static

from hancode.interfaces.tui.app import HanCodeTuiApp
from hancode.interfaces.tui.help import HelpScreen


def _command_text(item: Widget) -> str:
    return str(item.query_one(Static).render())


def test_help_overlay_opens_filters_and_closes(tmp_path: Path) -> None:
    async def _run() -> None:
        app = HanCodeTuiApp(project_root=tmp_path)
        async with app.run_test(size=(140, 40)) as pilot:
            app.submit_input("/help")
            await pilot.pause()

            assert isinstance(app.screen, HelpScreen)
            assert app.screen.query_one("#tui-help-categories")
            commands_widget = app.screen.query_one("#tui-help-commands", ListView)
            assert len(commands_widget.children) == 6
            assert "/task <goal>" in _command_text(commands_widget.children[0])
            title = app.screen.query_one("#tui-help-section-title", Static)
            assert "快速开始" in str(title.render())

            await pilot.press("down")
            await pilot.pause()
            assert "任务流程" in str(title.render())
            await pilot.press("down")
            await pilot.pause()
            assert "审查与交付" in str(title.render())
            await pilot.press("up")
            await pilot.pause()
            assert "任务流程" in str(title.render())

            categories_widget = app.screen.query_one("#tui-help-categories", ListView)
            categories_widget.focus()
            await pilot.press("right")
            await pilot.pause()
            assert app.screen.focused is commands_widget
            await pilot.press("left")
            await pilot.pause()
            assert app.screen.focused is categories_widget

            commands_widget.focus()
            await pilot.press("down", "down")
            await pilot.pause()
            assert commands_widget.index == 2
            assert "/approve" in _command_text(commands_widget.children[2])

            search = app.screen.query_one("#tui-help-search", Input)
            search.value = "delivery"
            await pilot.pause()
            commands = app.screen.query_one("#tui-help-commands", ListView)
            assert len(commands.children) == 1
            assert "/delivery" in _command_text(commands.children[0])
            assert "/task <goal>" not in _command_text(commands.children[0])

            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, HelpScreen)

    asyncio.run(_run())
