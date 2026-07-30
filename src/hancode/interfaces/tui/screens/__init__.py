"""Textual screens for the HanCode TUI."""
from hancode.interfaces.tui.screens.approval import SourceApprovalScreen
from hancode.interfaces.tui.screens.config import ConfigScreen
from hancode.interfaces.tui.screens.diff import DiffScreen
from hancode.interfaces.tui.screens.tests import TestReportScreen

__all__ = [
    "ConfigScreen",
    "DiffScreen",
    "SourceApprovalScreen",
    "TestReportScreen",
]
