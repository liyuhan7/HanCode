"""Stage 2: FakeTransport → AgentLoop → Tool integration tests."""

from __future__ import annotations

import json
from pathlib import Path

from hancode.app.task_service import TaskService
from hancode.core.config import load_config
from hancode.core.models import TaskStatus
from hancode.providers.openai_compatible import OpenAICompatibleProvider
from hancode.providers.prompt_builder import PromptBuilder
from hancode.providers.transport import FakeTransport, ProviderResponse
from hancode.storage.workspace import init_project_workspace
from hancode.tooling.factory import build_default_tool_catalog


def _make_project(tmp_path: Path) -> Path:
    init_project_workspace(
        tmp_path,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="HanCode",
    )
    project_file = tmp_path / ".hancode" / "project.json"
    data = json.loads(project_file.read_text(encoding="utf-8"))
    data.update(
        {
            "llm_provider": "openai_compatible",
            "model_name": "test-model",
            "credential_source": "env",
            "provider_base_url": "https://example.invalid/v1",
        }
    )
    project_file.write_text(json.dumps(data), encoding="utf-8")
    (tmp_path / ".hancode" / "course_context.md").write_text(
        "# Course Context\n\nComplete the assignment.\n",
        encoding="utf-8",
    )
    return tmp_path


def _action_response(action: dict[str, object]) -> ProviderResponse:
    return ProviderResponse(
        status_code=200,
        headers={"content-type": "application/json"},
        json_body={
            "choices": [
                {"message": {"content": json.dumps(action)}}
            ]
        },
        body_size=200,
    )


def _finish_phase_response(phase: str) -> ProviderResponse:
    return _action_response(
        {
            "type": "finish_phase",
            "phase": phase,
            "tool_name": None,
            "args": {},
            "reason": f"Finishing {phase} phase.",
        }
    )


def _make_provider(
    project_root: Path,
    transport: FakeTransport,
    *,
    max_retries: int | None = None,
) -> OpenAICompatibleProvider:
    config = load_config(project_root)
    return OpenAICompatibleProvider(
        model_name=config.model_name or "test-model",
        base_url=config.provider_base_url or "",
        credential="test-key",
        timeout_seconds=config.provider_timeout_seconds,
        max_retries=max_retries if max_retries is not None else config.provider_max_retries,
        max_output_tokens=config.provider_max_output_tokens,
        max_response_bytes=config.provider_max_response_bytes,
        prompt_builder=PromptBuilder(),
        transport=transport,
        sleeper=lambda _: None,
        tool_catalog=build_default_tool_catalog(config),
    )


def test_fake_transport_provider_runs_through_agent_loop(
    tmp_path: Path,
) -> None:
    project_root = _make_project(tmp_path)
    service = TaskService()
    service.create(project_root, "Generate SPEC.md")

    transport = FakeTransport(
        [
            _finish_phase_response("spec"),
            _finish_phase_response("plan"),
        ]
    )
    provider = _make_provider(project_root, transport)

    result = service.run(
        project_root, "task-001", resume=False, provider=provider
    )

    assert result.status in (TaskStatus.BLOCKED, TaskStatus.COMPLETED)
    assert len(transport.requests) > 0
    assert transport.requests[0].url.endswith("/chat/completions")
    assert "Bearer test-key" in transport.requests[0].headers.get("Authorization", "")


def test_fake_transport_no_real_network_access(
    tmp_path: Path,
) -> None:
    project_root = _make_project(tmp_path)
    service = TaskService()
    service.create(project_root, "Generate SPEC.md")

    transport = FakeTransport([_finish_phase_response("spec")])
    provider = _make_provider(project_root, transport, max_retries=0)

    service.run(project_root, "task-001", resume=False, provider=provider)

    assert all(
        "example.invalid" in req.url for req in transport.requests
    )
    assert all(req.url.startswith("https://") for req in transport.requests)


def test_fake_transport_credential_not_in_request_body(
    tmp_path: Path,
) -> None:
    project_root = _make_project(tmp_path)
    service = TaskService()
    service.create(project_root, "Generate SPEC.md")

    transport = FakeTransport([_finish_phase_response("spec")])
    provider = _make_provider(project_root, transport, max_retries=0)

    service.run(project_root, "task-001", resume=False, provider=provider)

    for req in transport.requests:
        body_str = json.dumps(req.json_body)
        assert "test-key" not in body_str
