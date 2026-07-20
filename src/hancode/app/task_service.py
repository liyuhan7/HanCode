from __future__ import annotations

import re
from pathlib import Path

from hancode.app.task_models import TaskSummary
from hancode.core.errors import HanCodeError, StructuredError
from hancode.core.state import load_state, reconcile_state
from hancode.providers.base import LLMClient
from hancode.runtime.agent_loop import AgentRunResult
from hancode.runtime.engine import run_task
from hancode.storage.workspace import (
    init_task_workspace,
    list_task_ids,
    task_path,
)

_TASK_ID_PATTERN = re.compile(r"^task-(\d+)$")


class TaskService:
    """Application facade for task initialization and execution."""

    def initialize(
        self,
        project_root: Path,
        task_id: str,
        *,
        goal: str | None = None,
    ) -> Path:
        return init_task_workspace(project_root, task_id, goal=goal)

    def create(
        self,
        project_root: Path,
        goal: str,
        *,
        task_id: str | None = None,
    ) -> TaskSummary:
        selected_task_id = (
            _next_task_id(project_root) if task_id is None else task_id.strip()
        )
        task_root = init_task_workspace(
            project_root,
            selected_task_id,
            goal=goal,
            allow_existing=False,
        )
        state = load_state(task_root)
        return TaskSummary.from_state(state)

    def get(self, project_root: Path, task_id: str) -> TaskSummary:
        root = task_path(project_root, task_id)
        if not root.is_dir():
            raise HanCodeError(
                StructuredError(
                    error_code="task_not_found",
                    message=f"Task workspace does not exist: {task_id}.",
                    phase="spec",
                    denied_rule="existing_task_required",
                    suggested_fix="Create the task before querying its status.",
                )
            )
        state = reconcile_state(root, load_state(root))
        return TaskSummary.from_state(state)

    def list_tasks(self, project_root: Path) -> tuple[TaskSummary, ...]:
        return tuple(
            self.get(project_root, task_id)
            for task_id in list_task_ids(project_root)
        )

    def run(
        self,
        project_root: Path,
        task_id: str,
        *,
        resume: bool = False,
        provider: LLMClient | None = None,
    ) -> AgentRunResult:
        return run_task(project_root, task_id, resume=resume, provider=provider)

    def resume(
        self,
        project_root: Path,
        task_id: str,
        *,
        provider: LLMClient | None = None,
    ) -> AgentRunResult:
        return self.run(project_root, task_id, resume=True, provider=provider)


def _next_task_id(project_root: Path) -> str:
    existing_ids = list_task_ids(project_root)
    numbers = [
        int(match.group(1))
        for task_id in existing_ids
        if (match := _TASK_ID_PATTERN.fullmatch(task_id)) is not None
    ]
    next_number = max(numbers, default=0) + 1
    return f"task-{next_number:03d}"
