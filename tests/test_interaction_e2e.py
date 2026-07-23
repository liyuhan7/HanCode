from __future__ import annotations

import json
from pathlib import Path

from hancode.app.interaction_service import InteractionService
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


def test_interaction_round_trip_pauses_answers_resumes_and_keeps_trace_safe(
    tmp_path: Path,
) -> None:
    init_project_workspace(tmp_path, "project-001", "Course", "Assignment")
    init_task_workspace(tmp_path, "task-001", goal="Write the spec.")
    project_file = tmp_path / ".hancode" / "project.json"
    project = json.loads(project_file.read_text(encoding="utf-8"))
    project["interaction_mode"] = "ask_user"
    project_file.write_text(json.dumps(project), encoding="utf-8")

    transport = _ScriptedTransport(
        [
            _response(
                {
                    "type": "ask_user",
                    "phase": "spec",
                    "tool_name": None,
                    "args": {"question": "Which target should be documented?"},
                    "reason": "The target is ambiguous.",
                }
            ),
            _response(
                {
                    "type": "tool_call",
                    "phase": "spec",
                    "tool_name": "write_file",
                    "args": {
                        "path": ".hancode/tasks/task-001/SPEC.md",
                        "content": "# Spec\n\nTarget: src/main.py\n",
                    },
                    "reason": "Persist the selected specification.",
                }
            ),
            _response(
                {
                    "type": "finish_phase",
                    "phase": "spec",
                    "tool_name": None,
                    "args": {},
                    "reason": None,
                }
            ),
            _error_response(),
        ]
    )
    from hancode.core.config import load_config

    config = load_config(tmp_path, "task-001")
    provider = OpenAICompatibleProvider(
        model_name="test-model",
        base_url="https://example.invalid/v1",
        credential="test-key",
        timeout_seconds=60,
        max_retries=0,
        max_output_tokens=2048,
        max_response_bytes=1048576,
        response_mode="json_object",
        prompt_builder=PromptBuilder(),
        transport=transport,
        sleeper=lambda _: None,
        tool_catalog=build_default_tool_catalog(config),
        interaction_enabled=True,
    )

    first = run_task(tmp_path, "task-001", provider=provider)

    assert first.status is TaskStatus.WAITING_INPUT
    assert first.final_state.pending_interaction_id == "ask-000001"
    assert not (tmp_path / ".hancode" / "tasks" / "task-001" / "SPEC.md").exists()

    InteractionService().answer(tmp_path, "task-001", "src/main.py")
    second = run_task(tmp_path, "task-001", resume=True, provider=provider)

    assert second.status is TaskStatus.BLOCKED
    assert second.error is not None
    assert second.error.error_code == "provider_request_rejected"
    assert "src/main.py" in transport.requests[1].json_body["messages"][1]["content"]
    assert (tmp_path / ".hancode" / "tasks" / "task-001" / "SPEC.md").is_file()
    trace = (
        tmp_path / ".hancode" / "tasks" / "task-001" / "trace.jsonl"
    ).read_text(encoding="utf-8")
    assert "src/main.py" not in trace
    assert "interaction_requested" in trace
