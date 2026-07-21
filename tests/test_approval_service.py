"""S3-R4: ApprovalService idempotency, conflict detection, and validation.

The service's public contract (its docstrings) promises idempotent approve/
reject and conflict detection across decisions. These tests pin that contract.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hancode.app.approval_service import ApprovalService
from hancode.core.approvals import ApprovalStatus
from hancode.core.errors import HanCodeError
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


def _error() -> ProviderResponse:
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


def _pending_task(tmp_path: Path) -> str:
    """Create a task and run it to a pending-approval state."""
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
        transport=_ScriptedTransport([_response(_WRITE), _error()]),
        sleeper=lambda _: None,
        tool_catalog=build_default_tool_catalog(config),
    )
    run_task(tmp_path, "task-001", provider=provider)
    from hancode.core.state import load_state

    return load_state(task_path(tmp_path, "task-001")).pending_approval_id  # type: ignore[return-value]


def test_approve_is_idempotent(tmp_path: Path) -> None:
    approval_id = _pending_task(tmp_path)
    service = ApprovalService(tmp_path)

    service.approve("task-001")
    # A second approve must succeed (idempotent), not raise.
    service.approve("task-001")

    record = load_approval_manifest(tmp_path, "task-001", approval_id)
    assert record.status is ApprovalStatus.APPROVED


def test_reject_is_idempotent(tmp_path: Path) -> None:
    approval_id = _pending_task(tmp_path)
    service = ApprovalService(tmp_path)

    service.reject("task-001", reason="No.")
    service.reject("task-001", reason="Still no.")

    record = load_approval_manifest(tmp_path, "task-001", approval_id)
    assert record.status is ApprovalStatus.REJECTED
    # The first rejection reason is preserved; the repeat does not overwrite it.
    assert record.rejection_reason == "No."


def test_approve_then_reject_conflicts(tmp_path: Path) -> None:
    _pending_task(tmp_path)
    service = ApprovalService(tmp_path)

    service.approve("task-001")
    with pytest.raises(HanCodeError) as exc:
        service.reject("task-001", reason="changed my mind")
    assert exc.value.structured_error.error_code == "approval_decision_conflict"


def test_reject_then_approve_conflicts(tmp_path: Path) -> None:
    _pending_task(tmp_path)
    service = ApprovalService(tmp_path)

    service.reject("task-001", reason="no")
    with pytest.raises(HanCodeError) as exc:
        service.approve("task-001")
    assert exc.value.structured_error.error_code == "approval_decision_conflict"


def test_decide_with_wrong_approval_id_is_rejected(tmp_path: Path) -> None:
    _pending_task(tmp_path)
    service = ApprovalService(tmp_path)

    with pytest.raises(HanCodeError) as exc:
        service.approve("task-001", approval_id="apr-999999")
    assert exc.value.structured_error.error_code in {
        "approval_not_found",
        "approval_id_mismatch",
    }


def test_get_pending_returns_none_when_no_approval(tmp_path: Path) -> None:
    init_project_workspace(tmp_path, "project-001", "Course", "Assignment")
    init_task_workspace(tmp_path, "task-001", goal="g")
    service = ApprovalService(tmp_path)

    assert service.get_pending("task-001") is None


def test_get_pending_exposes_targets_without_content(tmp_path: Path) -> None:
    _pending_task(tmp_path)
    service = ApprovalService(tmp_path)

    pending = service.get_pending("task-001")
    assert pending is not None
    assert pending["tool_name"] == "write_file"
    assert pending["status"] == "pending"
    # The pending view exposes the target path so the human can review it.
    assert ".hancode/tasks/task-001/SPEC.md" in pending["targets"]
