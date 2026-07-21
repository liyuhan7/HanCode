"""S3-R3/R6: end-to-end approval gate through the real engine wiring.

These tests drive the engine (create_agent_loop/run_task) — not a hand-built
AgentLoop — so they prove the approval components are actually wired in, and
that the approval round trip (pause -> approve -> execute exact action) holds
without a second Provider call.
"""

from __future__ import annotations

import json
from pathlib import Path

from hancode.app.approval_service import ApprovalService
from hancode.core.models import TaskStatus
from hancode.providers.openai_compatible import OpenAICompatibleProvider
from hancode.providers.prompt_builder import PromptBuilder
from hancode.providers.transport import ProviderRequest, ProviderResponse
from hancode.runtime.engine import run_task
from hancode.storage.workspace import init_project_workspace, init_task_workspace
from hancode.tooling.factory import build_default_tool_catalog


class _ScriptedTransport:
    def __init__(self, responses: list[ProviderResponse]) -> None:
        self.responses = list(responses)
        self.requests: list[ProviderRequest] = []

    def send(self, request: ProviderRequest) -> ProviderResponse:
        self.requests.append(request)
        return self.responses.pop(0)


def _response(action: dict[str, object]) -> ProviderResponse:
    return ProviderResponse(
        status_code=200,
        headers={"content-type": "application/json"},
        json_body={
            "choices": [
                {"message": {"content": json.dumps(action, ensure_ascii=False)}}
            ]
        },
        body_size=100,
    )


def _error_response() -> ProviderResponse:
    return ProviderResponse(
        status_code=400,
        headers={"content-type": "application/json"},
        json_body={"error": {"message": "script complete"}},
        body_size=40,
    )


def _setup(tmp_path: Path, approval_mode: str = "first_source_write") -> None:
    init_project_workspace(tmp_path, "project-001", "Course", "Assignment")
    init_task_workspace(tmp_path, "task-001", goal="Write the spec.")
    project_file = tmp_path / ".hancode" / "project.json"
    project = json.loads(project_file.read_text(encoding="utf-8"))
    project["approval_mode"] = approval_mode
    project_file.write_text(json.dumps(project), encoding="utf-8")


def _provider(tmp_path: Path, transport: _ScriptedTransport) -> OpenAICompatibleProvider:
    from hancode.core.config import load_config

    config = load_config(tmp_path, "task-001")
    return OpenAICompatibleProvider(
        model_name="test-model",
        base_url="https://example.invalid/v1",
        credential="test-key",
        timeout_seconds=60,
        max_retries=0,
        max_output_tokens=2048,
        max_response_bytes=1048576,
        prompt_builder=PromptBuilder(),
        transport=transport,
        sleeper=lambda _: None,
        tool_catalog=build_default_tool_catalog(config),
    )


_WRITE_SPEC = {
    "type": "tool_call",
    "phase": "spec",
    "tool_name": "write_file",
    "args": {
        "path": ".hancode/tasks/task-001/SPEC.md",
        "content": "# Spec\n\nTarget: src/main.py\n",
    },
    "reason": "Persist the specification.",
}


def test_engine_wires_approval_and_pauses_before_write(tmp_path: Path) -> None:
    _setup(tmp_path)
    transport = _ScriptedTransport([_response(_WRITE_SPEC), _error_response()])

    first = run_task(tmp_path, "task-001", provider=_provider(tmp_path, transport))

    spec = tmp_path / ".hancode" / "tasks" / "task-001" / "SPEC.md"
    assert first.status is TaskStatus.WAITING_APPROVAL
    assert first.final_state.pending_approval_id == "apr-000001"
    assert not spec.exists()  # no write before approval (design §3.3)
    assert len(transport.requests) == 1


def test_approved_action_executes_without_second_provider_call(tmp_path: Path) -> None:
    _setup(tmp_path)
    transport = _ScriptedTransport([_response(_WRITE_SPEC), _error_response()])
    provider = _provider(tmp_path, transport)

    run_task(tmp_path, "task-001", provider=provider)
    assert len(transport.requests) == 1

    ApprovalService(tmp_path).approve("task-001")
    run_task(tmp_path, "task-001", resume=True, provider=provider)

    spec = tmp_path / ".hancode" / "tasks" / "task-001" / "SPEC.md"
    assert spec.is_file()  # exact approved action executed
    assert "Target: src/main.py" in spec.read_text(encoding="utf-8")
    # The Provider must NOT be called again on approval resume (design §10).
    assert len(transport.requests) == 1


def test_rejected_action_is_not_executed(tmp_path: Path) -> None:
    _setup(tmp_path)
    transport = _ScriptedTransport(
        [_response(_WRITE_SPEC), _response(_WRITE_SPEC), _error_response()]
    )
    provider = _provider(tmp_path, transport)

    run_task(tmp_path, "task-001", provider=provider)
    ApprovalService(tmp_path).reject("task-001", reason="Not now.")
    run_task(tmp_path, "task-001", resume=True, provider=provider)

    spec = tmp_path / ".hancode" / "tasks" / "task-001" / "SPEC.md"
    assert not spec.exists()  # rejection means the action never runs


def test_trace_does_not_leak_action_content(tmp_path: Path) -> None:
    _setup(tmp_path)
    transport = _ScriptedTransport([_response(_WRITE_SPEC), _error_response()])
    provider = _provider(tmp_path, transport)

    run_task(tmp_path, "task-001", provider=provider)
    ApprovalService(tmp_path).approve("task-001")
    run_task(tmp_path, "task-001", resume=True, provider=provider)

    trace = (
        tmp_path / ".hancode" / "tasks" / "task-001" / "trace.jsonl"
    ).read_text(encoding="utf-8")
    assert "approval_requested" in trace
    assert "Target: src/main.py" not in trace  # no file content in trace
