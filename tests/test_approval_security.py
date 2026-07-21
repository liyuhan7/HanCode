"""S3-R6: ApprovalRequestBuilder security boundaries.

The builder is the choke point where an untrusted, model-proposed action is
turned into a human-facing approval record. It must (design §): deny payloads
that look like credentials, bound payload size, and redact sensitive diffs from
the preview rather than surfacing them to the human reviewer or persisting them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hancode.core.actions import Action, ActionType
from hancode.core.config import load_config
from hancode.core.errors import HanCodeError
from hancode.core.state import load_state
from hancode.policy.approval_policy import ApprovalPolicy
from hancode.runtime.approval_request import ApprovalRequestBuilder
from hancode.storage.workspace import (
    init_project_workspace,
    init_task_workspace,
    task_path,
)


def _prepare(tmp_path: Path):
    init_project_workspace(tmp_path, "project-001", "Course", "Assignment")
    init_task_workspace(tmp_path, "task-001", goal="g")
    pf = tmp_path / ".hancode" / "project.json"
    project = json.loads(pf.read_text(encoding="utf-8"))
    project["approval_mode"] = "all_source_writes"
    pf.write_text(json.dumps(project), encoding="utf-8")
    config = load_config(tmp_path, "task-001")
    state = load_state(task_path(tmp_path, "task-001"))
    return config, state, ApprovalRequestBuilder(config)


def _build(tmp_path: Path, config, state, builder, *, target: str, content: str):
    action = Action(
        type=ActionType.TOOL_CALL,
        phase=state.current_phase,
        tool_name="write_file",
        args={"path": target, "content": content},
        reason="write target",
    )
    requirement = ApprovalPolicy(config).evaluate(
        action=action,
        policy_decision=_Allowed(),
        state=state,
    )
    return builder.build(
        project_id="project-001",
        task_id="task-001",
        state=state,
        action=action,
        requirement=requirement,
        project_root=tmp_path,
    )


class _Allowed:
    def __init__(self) -> None:
        self.allowed = True
        self.reason = "ok"
        self.requires_checkpoint = True
        self.suggested_fix = "n/a"
        self.denied_rule = None


def test_sensitive_args_are_denied_before_building(tmp_path: Path) -> None:
    config, state, builder = _prepare(tmp_path)
    with pytest.raises(HanCodeError) as exc:
        _build(
            tmp_path, config, state, builder,
            target="config.py",
            content="AWS_SECRET_ACCESS_KEY = 'abc123'\n",
        )
    assert exc.value.structured_error.error_code == "approval_sensitive_payload_denied"


def test_oversized_payload_is_denied(tmp_path: Path) -> None:
    config, state, builder = _prepare(tmp_path)
    # Shrink the limit so a modest payload trips it deterministically.
    from dataclasses import replace as dc_replace

    tiny = dc_replace(config, max_approval_payload_bytes=64)
    builder = ApprovalRequestBuilder(tiny)
    with pytest.raises(HanCodeError) as exc:
        _build(
            tmp_path, tiny, state, builder,
            target="big.txt",
            content="x" * 500,
        )
    assert exc.value.structured_error.error_code == "approval_payload_too_large"


def test_sensitive_diff_is_redacted_not_surfaced(tmp_path: Path) -> None:
    config, state, builder = _prepare(tmp_path)
    # An existing file whose *old* content holds a secret: the new content is
    # clean (so args pass), but the diff would expose the secret → redact it.
    target = tmp_path / "settings.py"
    target.write_text("password = 'hunter2secret'\n", encoding="utf-8")
    record = _build(
        tmp_path, config, state, builder,
        target="settings.py",
        content="clean = True\n",
    )
    assert record.preview.redacted is True
    assert "hunter2secret" not in (record.preview.unified_diff or "")


def test_clean_action_builds_without_redaction(tmp_path: Path) -> None:
    config, state, builder = _prepare(tmp_path)
    record = _build(
        tmp_path, config, state, builder,
        target="notes.txt",
        content="just some plain notes\n",
    )
    assert record.preview.redacted is False
    assert record.action.tool_name == "write_file"
    # The persisted record round-trips through its own dict form.
    assert record.to_dict()["status"] == "pending"
