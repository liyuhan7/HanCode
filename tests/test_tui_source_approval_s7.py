"""S7-R4 full-screen source approval presentation."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from textual.widgets import Collapsible

from hancode.interfaces.tui.app import HanCodeTuiApp
from hancode.interfaces.tui.dialogs import ApprovalDialog
from hancode.interfaces.tui.presenters import ApprovalView
from hancode.interfaces.tui.screens.approval import SourceApprovalScreen


def _source_view() -> ApprovalView:
    return ApprovalView(
        approval_id="apr-001",
        tool_name="write_file",
        category="source_write",
        risk_level="high",
        reason="创建页面结构和响应式样式。",
        targets=("src/index.html", "src/style.css"),
        diff_preview="\n".join(
            f"+ line {index}: " + ("safe content " * 10)
            for index in range(1, 90)
        ),
    )


@pytest.mark.parametrize("size", [(120, 36), (90, 32), (60, 28)])
def test_source_approval_keeps_actions_visible_and_diff_scrollable(
    size: tuple[int, int],
) -> None:
    async def _run() -> None:
        app = HanCodeTuiApp(project_root=Path("."))
        async with app.run_test(size=size) as pilot:
            app.push_screen(SourceApprovalScreen(_source_view()))
            await pilot.pause()

            screen = app.screen
            buttons = list(screen.query("#source-approval-actions Button"))
            assert len(buttons) == 3
            assert all(
                button.region.y + button.region.height <= screen.size.height
                for button in buttons
            )
            assert screen.query_one(
                "#source-approval-technical", Collapsible
            ).collapsed

            diff = screen.query_one("#source-approval-diff")
            assert diff.virtual_size.height > diff.region.height
            await pilot.press("j")
            await pilot.pause()
            assert diff.scroll_y > 0

    asyncio.run(_run())


@pytest.mark.parametrize(
    ("key", "expected"),
    [("y", "approve"), ("n", "reject"), ("escape", None)],
)
def test_source_approval_returns_explicit_decision(
    key: str, expected: str | None
) -> None:
    results: list[str | None] = []

    async def _run() -> None:
        app = HanCodeTuiApp(project_root=Path("."))
        async with app.run_test(size=(120, 36)) as pilot:
            app.push_screen(SourceApprovalScreen(_source_view()), results.append)
            await pilot.pause()
            assert app.focused is not None
            assert app.focused.id == "source-approval-approve"
            await pilot.press(key)
            await pilot.pause()

    asyncio.run(_run())
    assert results == [expected]


def test_app_routes_only_source_categories_to_full_screen() -> None:
    async def _run() -> None:
        app = HanCodeTuiApp(project_root=Path("."))
        async with app.run_test(size=(120, 36)) as pilot:
            source_detail = {
                "approval_id": "apr-source",
                "tool_name": "write_file",
                "category": "source_write",
                "risk_level": "high",
                "reason": "创建源码文件。",
                "targets": [{"path": "src/main.py"}],
                "preview": {"unified_diff": "+print('safe')"},
            }
            app._render_approval_detail(source_detail)
            await pilot.pause()
            assert isinstance(app.screen, SourceApprovalScreen)
            await pilot.press("escape")
            await pilot.pause()

            test_detail = {
                "approval_id": "apr-test",
                "tool_name": "run_tests",
                "category": "run_tests",
                "risk_level": "high",
                "reason": "运行本次测试。",
                "targets": [],
                "preview": {},
            }
            app._render_approval_detail(test_detail)
            await pilot.pause()
            assert isinstance(app.screen, ApprovalDialog)
            dialog = app.screen.query_one("#tui-approval-dialog")
            assert dialog.region.height < app.screen.size.height

    asyncio.run(_run())
