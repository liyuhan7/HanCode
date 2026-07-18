from __future__ import annotations

from pathlib import Path

from hancode.storage.export import ExportResult, export_task_artifacts


class DeliveryService:
    """Application facade for state-authorized delivery export."""

    def export(self, project_root: Path, task_id: str, output_dir: Path) -> ExportResult:
        return export_task_artifacts(project_root, task_id, output_dir)
