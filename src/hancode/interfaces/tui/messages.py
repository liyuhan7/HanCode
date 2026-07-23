"""Textual messages posted from the background run Worker (S4-T5).

The Worker never touches widgets. It communicates by posting these messages,
which the app handles on the main thread to update the view state.
"""

from __future__ import annotations

from textual.message import Message

from hancode.app.task_models import TaskSummary
from hancode.core.errors import StructuredError
from hancode.interfaces.tui.operations import TuiOperationError, TuiOperationResult
from hancode.runtime.agent_loop import AgentRunResult
from hancode.storage.trace import TraceEvent


class TraceArrived(Message):
    def __init__(self, event: TraceEvent) -> None:
        super().__init__()
        self.event = event


class RunFinished(Message):
    def __init__(self, result: AgentRunResult) -> None:
        super().__init__()
        self.result = result


class RunFailed(Message):
    def __init__(self, error: StructuredError) -> None:
        super().__init__()
        self.error = error


class TaskSummaryChanged(Message):
    def __init__(self, summary: TaskSummary) -> None:
        super().__init__()
        self.summary = summary


class OperationFinished(Message):
    """A query or other non-run operation completed in a Worker."""

    def __init__(self, result: TuiOperationResult) -> None:
        super().__init__()
        self.result = result


class OperationFailed(Message):
    """A Worker operation failed with a request-scoped structured error."""

    def __init__(self, error: TuiOperationError) -> None:
        super().__init__()
        self.error = error


__all__ = [
    "TraceArrived",
    "RunFinished",
    "RunFailed",
    "TaskSummaryChanged",
    "OperationFinished",
    "OperationFailed",
]
