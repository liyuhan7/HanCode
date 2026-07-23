"""ActivityLog widget and its pure formatter (S4-T5).

Each TraceEvent renders as one independent line. Unknown event types are shown
(never dropped). All rendering is plain text — no Rich markup is interpolated
from event content, to avoid markup/ANSI injection from user or model text.
"""

from __future__ import annotations

from textual.widgets import RichLog

from hancode.interfaces.tui.presenters import ActivityItemView, present_trace_event
from hancode.storage.trace import TraceEvent

def format_event(event: TraceEvent | ActivityItemView) -> str:
    """Render one trace event as a single plain-text log line."""
    view = event if isinstance(event, ActivityItemView) else present_trace_event(event)
    return f"[{view.phase}] {view.label}"


class ActivityLog(RichLog):
    """Append-only activity feed."""

    def append_event(self, event: TraceEvent | ActivityItemView) -> None:
        # markup=False keeps model/user text from being interpreted as markup.
        self.write(format_event(event))


__all__ = ["ActivityLog", "format_event"]
