"""Textual messages posted from the background run Worker (S4-T5).

The Worker never touches widgets. It communicates by posting these messages,
which the app handles on the main thread to update the view state.
"""

from __future__ import annotations

from textual.message import Message

from hancode.app.task_models import TaskSummary
from hancode.core.errors import StructuredError
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


__all__ = ["TraceArrived", "RunFinished", "RunFailed", "TaskSummaryChanged"]
