"""Real-time trace observation for the TUI (S4-T2).

The audit trace is the source of truth. UI real-time display is a downstream
optimization layered on top via :class:`ObservedTraceAppender`, which decorates
an existing :class:`~hancode.runtime.agent_loop.TraceAppender`.

Ordering guarantee: the event is persisted by the inner appender first; only
after persistence succeeds is the observer notified. An observer failure is
swallowed so that UI problems can never turn a safe harness run into an
``INCONSISTENT`` one, and the observer never receives an unpersisted event.
"""

from __future__ import annotations

from typing import Mapping, Protocol, runtime_checkable

from hancode.core.models import Phase
from hancode.runtime.agent_loop import TraceAppender
from hancode.storage.trace import TraceEvent


@runtime_checkable
class TraceObserver(Protocol):
    """Receives trace events after they are persisted."""

    def on_trace(self, event: TraceEvent) -> None: ...


class ObservedTraceAppender:
    """Wrap a :class:`TraceAppender`, notifying an observer after persistence."""

    def __init__(self, inner: TraceAppender, observer: TraceObserver) -> None:
        self._inner = inner
        self._observer = observer

    def append(
        self,
        task_id: str,
        *,
        event_type: str,
        phase: Phase,
        status: str,
        action: Mapping[str, object] | None = None,
        observation: Mapping[str, object] | None = None,
        error_summary: str | None = None,
        state_transition: Mapping[str, object] | None = None,
    ) -> TraceEvent:
        event = self._inner.append(
            task_id,
            event_type=event_type,
            phase=phase,
            status=status,
            action=action,
            observation=observation,
            error_summary=error_summary,
            state_transition=state_transition,
        )
        try:
            self._observer.on_trace(event)
        except Exception:
            # A UI observer failure must never change the harness result or
            # make a persisted-and-safe run look inconsistent.
            pass
        return event


__all__ = ["TraceObserver", "ObservedTraceAppender"]
