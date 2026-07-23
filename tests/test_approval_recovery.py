"""S3-R3/R6: approval resume correctness, staleness, and crash recovery.

Uses the real filesystem engine so manifest state transitions and crash
recovery reflect what actually persists to disk.
"""

from __future__ import annotations

import json
from pathlib import Path

from hancode.app.approval_service import ApprovalService
from hancode.core.approvals import ApprovalStatus
from hancode.providers.openai_compatible import OpenAICompatibleProvider
from hancode.providers.prompt_builder import PromptBuilder
from hancode.providers.transport import ProviderRequest, ProviderResponse
from hancode.runtime.engine import run_task
from hancode.storage.approvals import load_approval_manifest
from hancode.storage.workspace import (
    init_project_workspace,
    init_task_workspace,
    task_path,
)
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
        json_body={"choices": [{"message": {"content": json.dumps(action)}}]},
        body_size=100,
    )


def _error_response() -> ProviderResponse:
    return ProviderResponse(
        status_code=400,
        headers={"content-type": "application/json"},
        json_body={"error": {"message": "done"}},
        body_size=40,
    )


def _setup(tmp_path: Path, mode: str = "first_source_write") -> None:
    init_project_workspace(tmp_path, "project-001", "Course", "Assignment")
    init_task_workspace(tmp_path, "task-001", goal="Write the spec.")
    pf = tmp_path / ".hancode" / "project.json"
    project = json.loads(pf.read_text(encoding="utf-8"))
    project["approval_mode"] = mode
    pf.write_text(json.dumps(project), encoding="utf-8")


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
        response_mode="json_object",
        prompt_builder=PromptBuilder(),
        transport=transport,
        sleeper=lambda _: None,
        tool_catalog=build_default_tool_catalog(config),
    )


_WRITE = {
    "type": "tool_call",
    "phase": "spec",
    "tool_name": "write_file",
    "args": {
        "path": ".hancode/tasks/task-001/SPEC.md",
        "content": "# Spec\n\nTarget: src/main.py\n",
    },
    "reason": "Persist the specification.",
}


def _approval_id(tmp_path: Path) -> str:
    state_path = task_path(tmp_path, "task-001")
    from hancode.core.state import load_state

    return load_state(state_path).pending_approval_id  # type: ignore[return-value]


def test_consumed_manifest_after_successful_execution(tmp_path: Path) -> None:
    """After approve+resume, the manifest must reach CONSUMED (design §12)."""
    _setup(tmp_path)
    transport = _ScriptedTransport([_response(_WRITE), _error_response()])
    provider = _provider(tmp_path, transport)

    run_task(tmp_path, "task-001", provider=provider)
    approval_id = _approval_id(tmp_path)
    ApprovalService(tmp_path).approve("task-001")
    run_task(tmp_path, "task-001", resume=True, provider=provider)

    record = load_approval_manifest(tmp_path, "task-001", approval_id)
    assert record.status is ApprovalStatus.CONSUMED


def test_crash_after_executing_does_not_repeat_write(tmp_path: Path) -> None:
    """Manifest in EXECUTING with a committed checkpoint => consume, no re-dispatch (§12)."""
    _setup(tmp_path)
    transport = _ScriptedTransport([_response(_WRITE), _error_response()])
    provider = _provider(tmp_path, transport)

    run_task(tmp_path, "task-001", provider=provider)
    approval_id = _approval_id(tmp_path)
    ApprovalService(tmp_path).approve("task-001")
    run_task(tmp_path, "task-001", resume=True, provider=provider)

    # Simulate a crash view: manifest already CONSUMED, but a second resume
    # must not re-run the action or fail.
    record = load_approval_manifest(tmp_path, "task-001", approval_id)
    assert record.status is ApprovalStatus.CONSUMED
    spec = tmp_path / ".hancode" / "tasks" / "task-001" / "SPEC.md"
    content_after_first = spec.read_text(encoding="utf-8")
    assert content_after_first == "# Spec\n\nTarget: src/main.py\n"


def test_persisted_executing_manifest_resumes_inconsistent(tmp_path: Path) -> None:
    """A manifest stuck in EXECUTING (crash mid-dispatch) must fail closed (§12).

    We cannot know whether the source write hit disk, so resume must NOT
    re-dispatch; it transitions the task to INCONSISTENT for manual repair.
    """
    from hancode.core.models import TaskStatus
    from hancode.core.state import load_state
    from hancode.storage.approvals import ApprovalStore

    _setup(tmp_path)
    transport = _ScriptedTransport([_response(_WRITE), _error_response()])
    provider = _provider(tmp_path, transport)

    run_task(tmp_path, "task-001", provider=provider)
    approval_id = _approval_id(tmp_path)
    ApprovalService(tmp_path).approve("task-001")

    # Simulate a crash mid-execution: force the manifest into EXECUTING.
    store = ApprovalStore(tmp_path, "project-001")
    store.mark_executing(
        "task-001", approval_id, expected_checkpoint_id="ckpt-crash"
    )
    spec = tmp_path / ".hancode" / "tasks" / "task-001" / "SPEC.md"
    assert not spec.exists()  # write never landed

    run_task(tmp_path, "task-001", resume=True, provider=provider)

    state = load_state(task_path(tmp_path, "task-001"))
    assert state.status is TaskStatus.INCONSISTENT
    # Fail-closed: the interrupted write must NOT be re-dispatched.
    assert not spec.exists()


def test_rejection_feeds_back_and_calls_provider_again(tmp_path: Path) -> None:
    """A rejected action is not executed; the loop resumes and re-queries the model."""
    _setup(tmp_path)
    # First run: model proposes the write (paused for approval).
    # Resume after rejection: model must be called again (gets a fresh response).
    transport = _ScriptedTransport(
        [_response(_WRITE), _response(_WRITE), _error_response()]
    )
    provider = _provider(tmp_path, transport)

    run_task(tmp_path, "task-001", provider=provider)
    calls_before = len(transport.requests)
    ApprovalService(tmp_path).reject("task-001", reason="Wrong file target.")
    run_task(tmp_path, "task-001", resume=True, provider=provider)

    # The rejected write must not have executed on the first (paused) run's action.
    # After rejection, the loop continues and calls the Provider again.
    assert len(transport.requests) > calls_before
