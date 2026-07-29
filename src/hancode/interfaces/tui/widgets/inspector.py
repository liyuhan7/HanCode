"""Structured, plain-text Inspector widget for the TUI workbench."""

from __future__ import annotations

from textual.widgets import Static


class Inspector(Static):
    """A stable Inspector target; presenters provide all display values."""

    def update_content(self, content: str) -> None:
        self.update(content)


__all__ = ["Inspector"]
