"""S3-R4: CLI approve / reject / approval command behavior."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from hancode.interfaces import cli
from hancode.providers.openai_compatible import OpenAICompatibleProvider
from hancode.providers.prompt_builder import PromptBuilder
from hancode.providers.transport import ProviderRequest, ProviderResponse
from hancode.runtime.engine import run_task
from hancode.storage.workspace import (
    init_project_workspace,
    init_task_workspace,
)
from hancode.tooling.factory import build_default_tool_catalog


runner = CliRunner()


class _ScriptedTransport:
    def __init__(self, responses: list[ProviderResponse]) -> None:
        self.responses = list(responses)
        self.requests: list[ProviderRequest] = []

    def send(self, request: ProviderRequest) -> ProviderResponse:
        self.requests.append(request)
        return self.responses.pop(0)


def _resp(action: dict[str, object]) -> ProviderResponse:
    return ProviderResponse(
        status_code=200,
        headers={"content-type": "application/json"},
        json_body={"choices": [{"message": {"content": json.dumps(action)}}]},
        body_size=100,
    )


def _err() -> ProviderResponse:
    return ProviderResponse(
        status_code=400,
        headers={"content-type": "application/json"},
        json_body={"error": {"message": "done"}},
        body_size=40,
    )


_WRITE = {
    "type": "tool_call",
    "phase": "spec",
    "tool_name": "write_file",
    "args": {"path": ".hancode/tasks/task-001/SPEC.md", "content": "# Spec\n"},
    "reason": "Persist the specification.",
}


def _pending(tmp_path: Path) -> None:
    init_project_workspace(tmp_path, "project-001", "Course", "Assignment")
    init_task_workspace(tmp_path, "task-001", goal="Write the spec.")
    pf = tmp_path / ".hancode" / "project.json"
    project = json.loads(pf.read_text(encoding="utf-8"))
    project["approval_mode"] = "first_source_write"
    pf.write_text(json.dumps(project), encoding="utf-8")

    from hancode.core.config import load_config

    config = load_config(tmp_path, "task-001")
    provider = OpenAICompatibleProvider(
        model_name="m",
        base_url="https://example.invalid/v1",
        credential="k",
        timeout_seconds=60,
        max_retries=0,
        max_output_tokens=2048,
        max_response_bytes=1048576,
        prompt_builder=PromptBuilder(),
        transport=_ScriptedTransport([_resp(_WRITE), _err()]),
        sleeper=lambda _: None,
        tool_catalog=build_default_tool_catalog(config),
    )
    run_task(tmp_path, "task-001", provider=provider)


def _payload(result: object) -> dict:
    return json.loads(getattr(result, "stdout"))


def test_cli_approval_shows_pending(tmp_path: Path) -> None:
    _pending(tmp_path)
    result = runner.invoke(
        cli.app,
        ["task", "approval", "task-001", "--project-root", str(tmp_path)],
    )
    assert result.exit_code == 0
    payload = _payload(result)
    assert payload["approval"]["tool_name"] == "write_file"
    assert payload["approval"]["status"] == "pending"


def test_cli_approve_transitions_task(tmp_path: Path) -> None:
    _pending(tmp_path)
    result = runner.invoke(
        cli.app,
        ["task", "approve", "task-001", "--project-root", str(tmp_path)],
    )
    assert result.exit_code == 0
    payload = _payload(result)
    assert payload["decision"] == "approved"


def test_cli_reject_with_reason(tmp_path: Path) -> None:
    _pending(tmp_path)
    result = runner.invoke(
        cli.app,
        [
            "task", "reject", "task-001",
            "--reason", "Not this approach",
            "--project-root", str(tmp_path),
        ],
    )
    assert result.exit_code == 0
    payload = _payload(result)
    assert payload["decision"] == "rejected"


def test_cli_approve_then_reject_conflict_is_nonzero_exit(tmp_path: Path) -> None:
    _pending(tmp_path)
    runner.invoke(
        cli.app, ["task", "approve", "task-001", "--project-root", str(tmp_path)]
    )
    result = runner.invoke(
        cli.app,
        ["task", "reject", "task-001", "--project-root", str(tmp_path)],
    )
    assert result.exit_code != 0


def test_cli_approve_unknown_id_is_nonzero_exit(tmp_path: Path) -> None:
    _pending(tmp_path)
    result = runner.invoke(
        cli.app,
        [
            "task", "approve", "task-001",
            "--approval-id", "apr-999999",
            "--project-root", str(tmp_path),
        ],
    )
    assert result.exit_code != 0
