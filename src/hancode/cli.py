"""Headless command-line entry point for HanCode."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from hancode.demo import run_packaged_mock_demo
from hancode.errors import HanCodeError, StructuredError
from hancode.export import export_task_artifacts
from hancode.workspace import init_project_workspace


app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="HanCode deterministic Coding Agent Harness.",
)


@app.command()
def init(
    project_root: Path = typer.Argument(Path("."), help="Project root to initialize."),
    project_id: str | None = typer.Option(None, help="Stable project identifier."),
    course_name: str | None = typer.Option(None, help="Course name."),
    assignment_name: str | None = typer.Option(None, help="Assignment name."),
) -> None:
    """Initialize the project workspace."""
    try:
        root = project_root.resolve()
        if not root.is_dir():
            raise _cli_error(
                "cli_project_root_invalid",
                "Project root must be an existing directory.",
                "Use an existing project directory as the CLI argument.",
            )
        workspace = init_project_workspace(
            root,
            _non_empty_or_default(project_id, root.name or "hancode-project"),
            _non_empty_or_default(course_name, "unspecified-course"),
            _non_empty_or_default(assignment_name, "unspecified-assignment"),
        )
        _emit(
            {
                "command": "init",
                "status": "completed",
                "workspace": str(workspace),
            }
        )
    except HanCodeError as exc:
        raise typer.Exit(_handle_error(exc)) from None
    except OSError:
        raise typer.Exit(
            _handle_error(
                _cli_error(
                    "cli_workspace_initialization_failed",
                    "Project workspace could not be initialized.",
                    "Check the project directory permissions and retry.",
                )
            )
        ) from None


@app.command()
def demo(
    provider: str = typer.Option("mock", "--provider", help="LLM provider mode."),
) -> None:
    """Run the deterministic offline demo."""
    if provider != "mock":
        raise typer.Exit(
            _handle_error(
                _cli_error(
                    "cli_unknown_provider",
                    f"Unknown provider: {provider}.",
                    "Use --provider mock for the offline deterministic demo.",
                    denied_rule="supported_provider_required",
                ),
                exit_code=1,
            )
        )
    try:
        result = run_packaged_mock_demo()
        _emit(result.to_dict())
        raise typer.Exit(0 if result.status.value == "completed" else 1)
    except typer.Exit:
        raise
    except HanCodeError as exc:
        raise typer.Exit(_handle_error(exc)) from None
    except Exception:
        raise typer.Exit(
            _handle_error(
                _cli_error(
                    "cli_internal_error",
                    "The CLI encountered an unrecoverable internal error.",
                    "Inspect the local workspace and retry after resolving the reported boundary.",
                    denied_rule="internal_error_boundary",
                ),
                exit_code=3,
            )
        ) from None


@app.command("export")
def export_command(
    task: str = typer.Option(..., "--task", help="Task ID to export."),
    out: Path = typer.Option(..., "--out", help="New output directory."),
    project_root: Path = typer.Option(
        Path("."), "--project-root", help="Project root containing .hancode."
    ),
) -> None:
    """Export state-declared task delivery artifacts."""
    try:
        result = export_task_artifacts(project_root, task, out)
        _emit({"command": "export", "status": "completed", **result.to_dict()})
    except HanCodeError as exc:
        raise typer.Exit(_handle_error(exc)) from None
    except OSError:
        raise typer.Exit(
            _handle_error(
                _cli_error(
                    "cli_export_failed",
                    "The task artifacts could not be exported.",
                    "Check the project and destination paths before retrying.",
                )
            )
        ) from None


def _emit(payload: dict[str, object]) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _handle_error(error: HanCodeError, *, exit_code: int | None = None) -> int:
    _emit({"status": "failed", "error": error.to_dict()})
    if exit_code is not None:
        return exit_code
    if error.structured_error.error_code.startswith(("trace_", "checkpoint_", "rollback_")):
        return 3
    return 2


def _non_empty_or_default(value: str | None, default: str) -> str:
    if value is None:
        return default
    if not value.strip():
        raise _cli_error(
            "cli_metadata_required",
            "Project metadata options must not be empty.",
            "Provide non-empty values for project metadata options.",
        )
    return value.strip()


def _cli_error(
    error_code: str,
    message: str,
    suggested_fix: str,
    *,
    denied_rule: str = "cli_input_required",
) -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code=error_code,
            message=message,
            phase="cli",
            denied_rule=denied_rule,
            suggested_fix=suggested_fix,
        )
    )
