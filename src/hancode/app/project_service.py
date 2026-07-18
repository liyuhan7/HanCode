from __future__ import annotations

from pathlib import Path

from hancode.storage.workspace import init_project_workspace


class ProjectService:
    """Application facade for project workspace lifecycle operations."""

    def initialize(
        self,
        project_root: Path,
        project_id: str,
        course_name: str,
        assignment_name: str,
    ) -> Path:
        return init_project_workspace(
            project_root,
            project_id,
            course_name,
            assignment_name,
        )
