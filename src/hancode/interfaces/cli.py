"""Headless command-line entry point for HanCode."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from hancode.app.auth_service import AuthService
from hancode.app.delivery_service import DeliveryService
from hancode.app.project_service import ProjectService
from hancode.app.task_service import TaskService
from hancode.app.credentials import CredentialProvider
from hancode.core.models import TaskStatus
from hancode.demo_support.runner import run_packaged_mock_demo
from hancode.core.errors import HanCodeError, StructuredError


app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="HanCode deterministic Coding Agent Harness.",
)
auth_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Manage provider credentials without exposing secret values.",
)
task_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Create, inspect, run, and resume HanCode tasks.",
)
app.add_typer(auth_app, name="auth")
app.add_typer(task_app, name="task")
credential_provider = CredentialProvider()
project_service = ProjectService()
task_service = TaskService()
delivery_service = DeliveryService()


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
        workspace = project_service.initialize(
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


@auth_app.command("status")
def auth_status(
    provider: str = typer.Option(..., "--provider", help="Credential provider."),
) -> None:
    """Show provider credential status without returning the secret."""
    try:
        status = _auth_service().status(provider)
        _emit(
            {
                "command": "auth status",
                "credential": status.to_dict(),
                "status": "completed",
            }
        )
    except HanCodeError as exc:
        raise typer.Exit(_handle_error(exc, exit_code=1)) from None


@auth_app.command("login")
def auth_login(
    provider: str = typer.Option(..., "--provider", help="Credential provider."),
) -> None:
    """Store a provider credential using hidden terminal input."""
    _set_auth_credential("auth login", provider)


@auth_app.command("update")
def auth_update(
    provider: str = typer.Option(..., "--provider", help="Credential provider."),
) -> None:
    """Replace a provider credential using hidden terminal input."""
    _set_auth_credential("auth update", provider)


@auth_app.command("clear")
def auth_clear(
    provider: str = typer.Option(..., "--provider", help="Credential provider."),
) -> None:
    """Clear the provider credential from the secure store."""
    try:
        auth_service = _auth_service()
        current_status = auth_service.status(provider)
        if current_status.source in {"env", "dotenv"}:
            raise _cli_error(
                "credential_external_source_requires_manual_clear",
                "The active credential is managed outside the secure store.",
                "Unset the mapped environment variable or remove the local .env value, then retry.",
                denied_rule="external_credential_source_manual_clear",
            )
        if provider not in {"mock", "local"} and not _confirm_clear():
            raise _cli_error(
                "credential_clear_cancelled",
                "Credential clearing was cancelled.",
                "Confirm the clear operation to remove the keyring credential.",
                denied_rule="credential_clear_confirmation_required",
            )
        auth_service.clear_secret(provider)
        status = auth_service.status(provider)
        _emit(
            {
                "command": "auth clear",
                "credential": status.to_dict(),
                "status": "completed",
            }
        )
    except HanCodeError as exc:
        raise typer.Exit(_handle_error(exc, exit_code=1)) from None


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
        result = delivery_service.export(project_root, task, out)
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


# =========================================================================
# Stage 1: Task lifecycle commands
# =========================================================================


@task_app.command("create")
def task_create(
    goal: str = typer.Argument(..., help="Natural-language task goal."),
    task_id: str | None = typer.Option(None, "--task-id", help="Explicit task ID."),
    project_root: Path = typer.Option(
        Path("."), "--project-root", help="Project root containing .hancode."
    ),
) -> None:
    """Create a new task with a non-empty goal."""
    try:
        summary = task_service.create(project_root, goal, task_id=task_id)
        _emit(
            {
                "command": "task create",
                "status": "completed",
                "task": summary.to_dict(),
            }
        )
    except HanCodeError as exc:
        raise typer.Exit(_handle_error(exc)) from None


@task_app.command("run")
def task_run(
    task_id: str = typer.Argument(..., help="Task ID to run."),
    project_root: Path = typer.Option(
        Path("."), "--project-root", help="Project root containing .hancode."
    ),
) -> None:
    """Run an existing task (resume=False)."""
    try:
        result = task_service.run(project_root, task_id, resume=False)
        _emit_task_result("task run", result)
    except HanCodeError as exc:
        raise typer.Exit(_handle_error(exc)) from None


@task_app.command("resume")
def task_resume(
    task_id: str = typer.Argument(..., help="Task ID to resume."),
    project_root: Path = typer.Option(
        Path("."), "--project-root", help="Project root containing .hancode."
    ),
) -> None:
    """Resume a blocked or recoverable task (resume=True)."""
    try:
        result = task_service.resume(project_root, task_id)
        _emit_task_result("task resume", result)
    except HanCodeError as exc:
        raise typer.Exit(_handle_error(exc)) from None


@task_app.command("status")
def task_status(
    task_id: str = typer.Argument(..., help="Task ID to inspect."),
    project_root: Path = typer.Option(
        Path("."), "--project-root", help="Project root containing .hancode."
    ),
) -> None:
    """Show the current status of a task."""
    try:
        summary = task_service.get(project_root, task_id)
        _emit(
            {
                "command": "task status",
                "status": "completed",
                "task": summary.to_dict(),
            }
        )
    except HanCodeError as exc:
        raise typer.Exit(_handle_error(exc)) from None


@task_app.command("list")
def task_list(
    project_root: Path = typer.Option(
        Path("."), "--project-root", help="Project root containing .hancode."
    ),
) -> None:
    """List all tasks in the project."""
    try:
        summaries = task_service.list_tasks(project_root)
        _emit(
            {
                "command": "task list",
                "status": "completed",
                "tasks": [s.to_dict() for s in summaries],
            }
        )
    except HanCodeError as exc:
        raise typer.Exit(_handle_error(exc)) from None


@app.command("run")
def run_command(
    goal: str = typer.Argument(..., help="Natural-language task goal."),
    task_id: str | None = typer.Option(None, "--task-id", help="Explicit task ID."),
    project_root: Path = typer.Option(
        Path("."), "--project-root", help="Project root containing .hancode."
    ),
) -> None:
    """Create a task and immediately run it."""
    try:
        task = task_service.create(project_root, goal, task_id=task_id)
        result = task_service.run(project_root, task.task_id, resume=False)
        _emit_task_result("run", result, task_summary=task.to_dict())
    except HanCodeError as exc:
        raise typer.Exit(_handle_error(exc)) from None


def _set_auth_credential(command: str, provider: str) -> None:
    try:
        auth_service = _auth_service()
        status = auth_service.status(provider)
        if status.provider in {"mock", "local"}:
            raise _cli_error(
                "credential_not_required",
                "This provider does not accept stored credentials.",
                "Use a remote provider when storing a credential.",
                denied_rule="provider_credential_not_required",
            )
        secret = typer.prompt("Credential", hide_input=True, err=True)
        auth_service.set_secret(provider, secret)
        status = auth_service.status(provider)
        _emit(
            {
                "command": command,
                "credential": status.to_dict(),
                "status": "completed",
            }
        )
    except HanCodeError as exc:
        raise typer.Exit(_handle_error(exc, exit_code=1)) from None


def _confirm_clear() -> bool:
    typer.echo("Clear the stored credential? [y/N]: ", err=True, nl=False)
    answer = typer.get_text_stream("stdin").readline()
    typer.echo("", err=True)
    return answer.strip().lower() in {"y", "yes"}


def _auth_service() -> AuthService:
    return AuthService(credential_provider)


def _emit(payload: dict[str, object]) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _emit_task_result(
    command: str,
    result: object,
    *,
    task_summary: dict[str, object] | None = None,
) -> None:
    """Emit a structured task run result with exit code."""
    from hancode.app.task_models import TaskRunSummary

    summary = TaskRunSummary.from_result(result)  # type: ignore[arg-type]
    task_dict = task_summary if task_summary is not None else summary.task.to_dict()
    status_value = summary.task.status.value
    _emit(
        {
            "command": command,
            "status": status_value,
            "task": task_dict,
            "run": summary.to_dict(),
        }
    )
    raise typer.Exit(_task_exit_code(summary.task.status))


def _task_exit_code(status: TaskStatus) -> int:
    if status is TaskStatus.COMPLETED:
        return 0
    if status in {TaskStatus.BLOCKED, TaskStatus.FAILED}:
        return 1
    if status is TaskStatus.INCONSISTENT:
        return 3
    return 1


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
