from __future__ import annotations

from pathlib import Path

from hancode.providers.base import LLMClient
from hancode.runtime.agent_loop import AgentRunResult
from hancode.runtime.engine import run_task
from hancode.storage.workspace import init_task_workspace


class TaskService:
    """Application facade for task initialization and execution."""

    def initialize(self, project_root: Path, task_id: str) -> Path:
        return init_task_workspace(project_root, task_id)

    def run(
        self,
        project_root: Path,
        task_id: str,
        *,
        resume: bool = False,
        provider: LLMClient | None = None,
    ) -> AgentRunResult:
        return run_task(project_root, task_id, resume=resume, provider=provider)
