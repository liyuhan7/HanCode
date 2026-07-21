"""S4-T1: TUI entry point and shell app.

These tests assert that:
- ``hancode tui`` is a registered CLI command.
- The Textual app mounts the main screen without a live Provider or workspace.
- The existing headless CLI behaviour (JSON output, --help) is unchanged.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from typer.testing import CliRunner

from hancode.interfaces import cli


runner = CliRunner()


def test_tui_command_is_registered() -> None:
    result = runner.invoke(cli.app, ["--help"])

    assert result.exit_code == 0
    assert "tui" in result.stdout


def test_existing_cli_help_is_unchanged() -> None:
    result = runner.invoke(cli.app, ["--help"])

    assert result.exit_code == 0
    for command in ("init", "demo", "export", "auth"):
        assert command in result.stdout


def test_headless_cli_output_remains_json(tmp_path: Path) -> None:
    result = runner.invoke(cli.app, ["init", str(tmp_path)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert isinstance(payload, dict)
    assert payload["command"] == "init"
    assert payload["status"] == "completed"


def test_tui_app_mounts_main_screen(tmp_path: Path) -> None:
    from hancode.interfaces.tui.app import HanCodeTuiApp
    from hancode.interfaces.tui.screens.main import MainScreen

    async def _run() -> None:
        app = HanCodeTuiApp(project_root=tmp_path)
        async with app.run_test() as pilot:
            assert isinstance(pilot.app.screen, MainScreen)

    asyncio.run(_run())
