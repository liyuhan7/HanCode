"""HanCode terminal interaction layer (Textual REPL/TUI).

The TUI is a presentation layer only. It drives the harness exclusively through
application services (:mod:`hancode.app`) and never touches the AgentLoop,
ToolRegistry, state files, or trace files directly.
"""

from __future__ import annotations

__all__ = ["HanCodeTuiApp"]


def __getattr__(name: str) -> object:
    if name == "HanCodeTuiApp":
        from hancode.interfaces.tui.app import HanCodeTuiApp

        return HanCodeTuiApp
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
