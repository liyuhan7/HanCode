"""ActivityLog widget and its pure formatter (S4-T5).

Each TraceEvent renders as one independent line. Unknown event types are shown
(never dropped). All rendering is plain text — no Rich markup is interpolated
from event content, to avoid markup/ANSI injection from user or model text.
"""

from __future__ import annotations

from textual.widgets import RichLog

from hancode.storage.trace import TraceEvent


_LABELS = {
    "phase_started": "PHASE start",
    "phase_completed": "PHASE done",
    "interaction_requested": "ASK  agent asks",
    "interaction_answered": "ASK  answer submitted",
    "interaction_resumed": "ASK  resumed",
    "tool_called": "TOOL called",
    "tool_completed": "TOOL ok",
    "tool_failed": "TOOL failed",
    "policy_denied": "POLICY denied",
    "checkpoint_created": "CKPT created",
    "rollback_completed": "ROLLBACK done",
    "rollback_performed": "ROLLBACK done",
    "test_failed": "TEST failed",
    "retry_budget_consumed": "RETRY consumed",
    "run_completed": "RUN completed",
}


def format_event(event: TraceEvent) -> str:
    """Render one trace event as a single plain-text log line."""
    label = _LABELS.get(event.event_type)
    tool = ""
    if isinstance(event.action, dict):
        name = event.action.get("tool_name")
        if isinstance(name, str) and name:
            tool = f" {name}"
    if label is None:
        # Unknown events are still shown, keyed by their raw type.
        return f"[{event.phase.value}] {event.event_type} {event.status}{tool}"
    return f"[{event.phase.value}] {label}{tool}"


class ActivityLog(RichLog):
    """Append-only activity feed."""

    def append_event(self, event: TraceEvent) -> None:
        # markup=False keeps model/user text from being interpreted as markup.
        self.write(format_event(event))


__all__ = ["ActivityLog", "format_event"]
