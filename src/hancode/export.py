"""Deterministic export of task delivery artifacts."""

from __future__ import annotations

from dataclasses import dataclass
import os
import shutil
from pathlib import Path
import tempfile

from hancode.errors import HanCodeError, StructuredError
from hancode.state import load_state, reconcile_state
from hancode.workspace import task_path


_EXPORT_ARTIFACTS = (
    "SPEC.md",
    "PLAN.md",
    "TEST_REPORT.md",
    "REVIEW.md",
    "KNOWLEDGE.md",
    "DELIVERABLES.md",
)


@dataclass(frozen=True, slots=True)
class ExportResult:
    """The files copied by one export operation."""

    task_id: str
    output_dir: Path
    artifacts: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "output_dir": str(self.output_dir),
            "artifacts": list(self.artifacts),
        }


def export_task_artifacts(
    project_root: Path,
    task_id: str,
    output_dir: Path,
) -> ExportResult:
    """Copy state-declared delivery artifacts into a new output directory."""
    root = project_root.resolve()
    if not root.is_dir():
        raise _export_error(
            "export_project_root_invalid",
            "Project root must be an existing directory.",
            "Use an existing project directory for export.",
        )

    task_root = task_path(root, task_id)
    if not task_root.is_dir():
        raise _export_error(
            "export_task_missing",
            "Task workspace does not exist.",
            "Initialize the requested task before exporting its artifacts.",
        )
    try:
        state = reconcile_state(task_root, load_state(task_root))
    except HanCodeError:
        raise _export_error(
            "export_state_invalid",
            "Task state is invalid and cannot be exported.",
            "Repair state.json before exporting task artifacts.",
        ) from None
    if state.inconsistent:
        raise _export_error(
            "export_state_inconsistent",
            "Task state and delivery artifacts are inconsistent.",
            "Reconcile task artifacts before exporting.",
        )

    artifact_names = tuple(
        name for name in _EXPORT_ARTIFACTS if state.artifacts.get(name, False)
    )
    if not artifact_names:
        raise _export_error(
            "export_artifacts_missing",
            "The task has no delivery artifacts to export.",
            "Complete at least one delivery artifact before exporting.",
        )
    sources = tuple(task_root / name for name in artifact_names)
    if any(_is_link(source) or not source.is_file() for source in sources):
        raise _export_error(
            "export_state_inconsistent",
            "A state-declared delivery artifact is missing or linked.",
            "Restore regular artifact files before exporting.",
        )

    raw_output = Path(os.path.abspath(output_dir))
    _validate_output_target(root, raw_output)
    output = raw_output.resolve()
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        raise _export_error(
            "export_output_unavailable",
            "The export destination parent cannot be created.",
            "Choose a writable destination outside the task workspace.",
        ) from None

    staging: Path | None = None
    try:
        staging = Path(tempfile.mkdtemp(prefix=".hancode-export-", dir=output.parent))
        for name, source in zip(artifact_names, sources):
            shutil.copy2(source, staging / name)
        if _is_link(output) or output.exists():
            raise _export_error(
                "export_output_exists",
                "Export destination already exists.",
                "Choose a new output directory; existing files are never overwritten.",
            )
        staging.rename(output)
        staging = None
    except HanCodeError:
        raise
    except OSError:
        raise _export_error(
            "export_copy_failed",
            "Delivery artifacts could not be exported atomically.",
            "Check destination permissions and retry with a new output directory.",
        ) from None
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)

    return ExportResult(task_id=task_id, output_dir=output, artifacts=artifact_names)


def _validate_output_target(project_root: Path, output: Path) -> None:
    if _has_link_component(output):
        raise _export_error(
            "export_output_link_not_allowed",
            "Export destination contains a symbolic link or junction.",
            "Choose a destination path whose existing components are regular directories.",
        )
    hancode_root = (project_root / ".hancode").resolve()
    resolved_output = output.resolve()
    if resolved_output == hancode_root or hancode_root in resolved_output.parents:
        raise _export_error(
            "export_output_inside_workspace",
            "Export destination must not be inside the runtime workspace.",
            "Choose a destination outside .hancode.",
        )
    if output.exists():
        raise _export_error(
            "export_output_exists",
            "Export destination already exists.",
            "Choose a new output directory; existing files are never overwritten.",
        )


def _has_link_component(path: Path) -> bool:
    return any(_is_link(component) for component in (path, *path.parents))


def _is_link(path: Path) -> bool:
    try:
        junction_probe = getattr(path, "is_junction", None)
        return path.is_symlink() or (
            bool(junction_probe()) if callable(junction_probe) else False
        )
    except (AttributeError, OSError, RuntimeError):
        return True


def _export_error(error_code: str, message: str, suggested_fix: str) -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code=error_code,
            message=message,
            phase="deliver",
            denied_rule="delivery_export_boundary",
            suggested_fix=suggested_fix,
        )
    )
