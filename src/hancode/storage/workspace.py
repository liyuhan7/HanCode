from __future__ import annotations

import json
import os
from pathlib import Path, PureWindowsPath
import stat

from hancode.core.errors import HanCodeError, StructuredError


_PROJECT_MARKDOWN_FILES = {
    "project_memory.md": "# Project Memory\n",
    "course_context.md": "# Course Context\n",
    "experience.md": "# Experience\n",
}
_TASK_ARTIFACTS = (
    "SPEC.md",
    "PLAN.md",
    "TEST_REPORT.md",
    "REVIEW.md",
    "KNOWLEDGE.md",
    "DELIVERABLES.md",
)


def init_project_workspace(
    project_root: Path,
    project_id: str,
    course_name: str,
    assignment_name: str,
) -> Path:
    _project_root, workspace = _workspace_paths(project_root)
    workspace.mkdir(exist_ok=True)
    (workspace / "tasks").mkdir(exist_ok=True)

    project_data = {
        "workspace_version": 1,
        "project_id": project_id,
        "course_name": course_name,
        "assignment_name": assignment_name,
        "project_root": ".",
    }
    project_file = workspace / "project.json"
    if not project_file.exists():
        project_file.write_text(
            json.dumps(project_data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    for filename, content in _PROJECT_MARKDOWN_FILES.items():
        path = workspace / filename
        if not path.exists():
            path.write_text(content, encoding="utf-8")

    return workspace


def task_path(project_root: Path, task_id: str) -> Path:
    _project_root, workspace = _workspace_paths(project_root)
    workspace_root = workspace.resolve()
    tasks_root_path = workspace / "tasks"
    tasks_root = tasks_root_path.resolve()
    task_id_path = Path(task_id)
    candidate_path = tasks_root_path / task_id_path
    if _is_link(candidate_path):
        raise _workspace_boundary_error()
    candidate = candidate_path.resolve()

    if (
        task_id_path.is_absolute()
        or PureWindowsPath(task_id).is_absolute()
        or not candidate.is_relative_to(tasks_root)
        or not candidate.is_relative_to(workspace_root)
    ):
        raise HanCodeError(
            StructuredError(
                error_code="workspace_path_outside_project_root",
                message="Task workspace path must stay inside the project workspace.",
                phase="spec",
                denied_rule="workspace_root_boundary",
                suggested_fix="Use a relative task ID without parent-directory segments.",
            )
        )

    if len(task_id_path.parts) != 1 or task_id_path.name in {"", ".", ".."}:
        raise HanCodeError(
            StructuredError(
                error_code="invalid_task_id",
                message="Task ID must be a single non-empty path component.",
                phase="spec",
                denied_rule="valid_task_id_required",
                suggested_fix="Use a task ID without path separators or dot segments.",
            )
        )

    return candidate


def init_task_workspace(
    project_root: Path,
    task_id: str,
    *,
    goal: str | None = None,
    allow_existing: bool = True,
) -> Path:
    _project_root, workspace = _workspace_paths(project_root)
    required_files = [
        workspace / "project.json",
        *(workspace / filename for filename in _PROJECT_MARKDOWN_FILES),
    ]
    if not (workspace / "tasks").is_dir() or any(
        _is_link(path) or not path.is_file() for path in required_files
    ):
        raise HanCodeError(
            StructuredError(
                error_code="project_workspace_not_initialized",
                message="Project workspace is not initialized.",
                phase="spec",
                denied_rule="project_workspace_required",
                suggested_fix=(
                    "Initialize the project workspace before creating a task workspace."
                ),
            )
        )

    load_project_metadata(workspace / "project.json")
    # Load the validated project configuration so each new task starts with
    # the configured retry budget rather than a duplicated hard-coded default.
    from hancode.core.config import load_config

    retry_budget = load_config(project_root).retry_budget
    task_workspace = task_path(project_root, task_id)
    checkpoints_dir = task_workspace / "checkpoints"
    if _is_link(checkpoints_dir):
        raise _workspace_file_link_error("checkpoints")

    normalized_goal = _normalize_goal(goal)

    if not allow_existing and task_workspace.exists():
        raise HanCodeError(
            StructuredError(
                error_code="task_already_exists",
                message=f"Task workspace already exists: {task_id}.",
                phase="spec",
                denied_rule="unique_task_id_required",
                suggested_fix="Use another task ID or resume the existing task.",
            )
        )

    task_workspace.mkdir(exist_ok=True)
    checkpoints_dir.mkdir(exist_ok=True)

    for filename in ("trace.jsonl", "history.jsonl"):
        path = task_workspace / filename
        if _is_link(path):
            raise _workspace_file_link_error(filename)
        if not path.exists():
            path.write_text("", encoding="utf-8")

    state_file = task_workspace / "state.json"
    if _is_link(state_file):
        raise _workspace_file_link_error("state.json")
    if not state_file.exists():
        initial_state = {
            "schema_version": 1,
            "task_id": task_id,
            "goal": normalized_goal,
            "status": "created",
            "current_phase": "spec",
            "files_changed": [],
            "latest_checkpoint": None,
            "checkpoint_seq": 0,
            "tests_run": [],
            "latest_test_status": "none",
            "test_status_consumed": False,
            "retry_budget_remaining": retry_budget,
            "inconsistent": False,
            "source_edits_this_phase": 0,
            "rollback_required": False,
            "rollback_done": False,
            "pending_checkpoint_recovery_id": None,
            "phase_completed": {
                "spec": False,
                "plan": False,
                "code": False,
                "test": False,
                "review": False,
                "deliver": False,
            },
            "artifacts": {artifact: False for artifact in _TASK_ARTIFACTS},
        }
        state_file.write_text(
            json.dumps(initial_state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return task_workspace


def list_task_ids(project_root: Path) -> tuple[str, ...]:
    """Return sorted task IDs for a project workspace.

    Fails closed when the project is not initialized, or when the tasks
    directory or any task state is invalid.
    """
    _project_root, workspace = _workspace_paths(project_root)
    required_files = [
        workspace / "project.json",
        *(workspace / filename for filename in _PROJECT_MARKDOWN_FILES),
    ]
    if not (workspace / "tasks").is_dir() or any(
        _is_link(path) or not path.is_file() for path in required_files
    ):
        raise HanCodeError(
            StructuredError(
                error_code="project_workspace_not_initialized",
                message="Project workspace is not initialized.",
                phase="spec",
                denied_rule="project_workspace_required",
                suggested_fix=(
                    "Initialize the project workspace before listing tasks."
                ),
            )
        )
    load_project_metadata(workspace / "project.json")
    tasks_dir = workspace / "tasks"
    if _is_link(tasks_dir):
        raise _workspace_boundary_error()

    task_ids: list[str] = []
    for entry in sorted(tasks_dir.iterdir()):
        if not entry.is_dir():
            continue
        if _is_link(entry):
            raise _workspace_boundary_error()
        state_file = entry / "state.json"
        if _is_link(state_file) or not state_file.is_file():
            raise HanCodeError(
                StructuredError(
                    error_code="task_list_failed",
                    message=(
                        "Task directory is missing a valid state.json: "
                        f"{entry.name}."
                    ),
                    phase="spec",
                    denied_rule="valid_task_state_required",
                    suggested_fix=(
                        "Remove the broken task directory or repair its state.json."
                    ),
                )
            )
        task_ids.append(entry.name)

    return tuple(task_ids)


def _normalize_goal(goal: str | None) -> str | None:
    if goal is None:
        return None
    if not isinstance(goal, str):
        raise HanCodeError(
            StructuredError(
                error_code="task_goal_required",
                message="Task goal must be a non-empty string.",
                phase="spec",
                denied_rule="non_empty_task_goal_required",
                suggested_fix="Provide a non-empty natural-language task goal.",
            )
        )
    stripped = goal.strip()
    if not stripped:
        raise HanCodeError(
            StructuredError(
                error_code="task_goal_required",
                message="Task goal must not be empty or blank.",
                phase="spec",
                denied_rule="non_empty_task_goal_required",
                suggested_fix="Provide a non-empty natural-language task goal.",
            )
        )
    return stripped


def _workspace_paths(project_root: Path) -> tuple[Path, Path]:
    project_root = project_root.resolve()
    workspace = project_root / ".hancode"
    if _is_link(workspace):
        raise _workspace_link_error()
    if _is_link(workspace / "tasks"):
        raise _workspace_boundary_error()
    return project_root, workspace


def _is_link(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        if is_junction is not None and is_junction():
            return True
        try:
            attributes = getattr(os.lstat(path), "st_file_attributes", 0)
        except FileNotFoundError:
            return False
        reparse_attribute = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        return bool(attributes & reparse_attribute)
    except (AttributeError, OSError, RuntimeError):
        return True


def _workspace_link_error() -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code="workspace_link_not_allowed",
            message="Project workspace links are not allowed for task state storage.",
            phase="spec",
            denied_rule="canonical_workspace_root_required",
            suggested_fix="Replace .hancode and .hancode/tasks links with directories inside the project.",
        )
    )


def _workspace_boundary_error() -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code="workspace_path_outside_project_root",
            message="Task workspace path must stay inside the project workspace.",
            phase="spec",
            denied_rule="workspace_root_boundary",
            suggested_fix="Use a relative task ID without parent-directory segments.",
        )
    )


def _workspace_file_link_error(filename: str) -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code="workspace_file_link_not_allowed",
            message=f"Task workspace file must not be a link: {filename}.",
            phase="spec",
            denied_rule="canonical_task_file_required",
            suggested_fix="Replace the task workspace link with a regular file or directory inside the task.",
        )
    )


def load_project_metadata(project_file: Path) -> dict[str, object]:
    if _is_link(project_file):
        raise _workspace_file_link_error(project_file.name)
    try:
        metadata = json.loads(project_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        metadata = None

    required_text_fields = ("project_id", "course_name", "assignment_name")
    if (
        not isinstance(metadata, dict)
        or metadata.get("workspace_version") != 1
        or metadata.get("project_root") != "."
        or any(
            not isinstance(metadata.get(field), str) or not metadata[field]
            for field in required_text_fields
        )
    ):
        raise HanCodeError(
            StructuredError(
                error_code="invalid_project_workspace",
                message="Project workspace metadata is invalid.",
                phase="spec",
                denied_rule="valid_project_metadata_required",
                suggested_fix="Repair project.json before creating a task workspace.",
            )
        )
    return metadata
