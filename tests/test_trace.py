from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from hancode.errors import HanCodeError
from hancode.models import Phase
from hancode.trace import append_trace
from hancode.workspace import init_project_workspace, init_task_workspace


def test_trace_appends_jsonl_event_with_event_id(tmp_path: Path) -> None:
    task_root = _init_task(tmp_path)

    event = append_trace(
        task_root,
        event_type="task_started",
        task_id="task-001",
        phase=Phase.SPEC,
        status="running",
        timestamp=datetime(2026, 7, 13, 10, 0, tzinfo=UTC),
    )

    assert event.event_id == "evt-000001"
    assert event.seq == 1
    assert event.phase is Phase.SPEC
    assert json.loads((task_root / "trace.jsonl").read_text(encoding="utf-8")) == {
        "event_id": "evt-000001",
        "seq": 1,
        "event_type": "task_started",
        "task_id": "task-001",
        "phase": "spec",
        "timestamp": "2026-07-13T10:00:00+00:00",
        "status": "running",
        "action": None,
        "observation": None,
        "error_summary": None,
        "state_transition": None,
    }


def test_trace_event_has_monotonic_seq(tmp_path: Path) -> None:
    task_root = _init_task(tmp_path)

    first = append_trace(
        task_root,
        event_type="task_started",
        task_id="task-001",
        phase=Phase.SPEC,
        status="running",
    )
    second = append_trace(
        task_root,
        event_type="phase_started",
        task_id="task-001",
        phase=Phase.PLAN,
        status="running",
    )

    assert (first.event_id, first.seq) == ("evt-000001", 1)
    assert (second.event_id, second.seq) == ("evt-000002", 2)


def test_trace_redacts_nested_secret_like_values(tmp_path: Path) -> None:
    task_root = _init_task(tmp_path)
    action = {
        **_tool_action(),
        "args": {
            "headers": {"Authorization": "Bearer trace-secret-value"},
            "api_key": "trace-api-key-value",
        },
    }
    observation = {"details": [{"password": "trace-password-value"}]}

    append_trace(
        task_root,
        event_type="tool_called",
        task_id="task-001",
        phase=Phase.CODE,
        status="running",
        action=action,
        observation=observation,
    )

    trace_text = (task_root / "trace.jsonl").read_text(encoding="utf-8")
    assert "trace-secret-value" not in trace_text
    assert "trace-api-key-value" not in trace_text
    assert "trace-password-value" not in trace_text
    assert action["args"]["headers"]["Authorization"] == "Bearer trace-secret-value"
    assert observation["details"][0]["password"] == "trace-password-value"


def test_trace_truncates_large_content(tmp_path: Path) -> None:
    task_root = _init_task(tmp_path)
    content = "x" * 4097

    append_trace(
        task_root,
        event_type="tool_completed",
        task_id="task-001",
        phase=Phase.CODE,
        status="succeeded",
        action=_tool_action(),
        observation={"content": content},
    )

    stored_content = json.loads(
        (task_root / "trace.jsonl").read_text(encoding="utf-8")
    )["observation"]["content"]
    assert stored_content == {"summary": "[CONTENT_OMITTED]", "char_count": 4097}
    assert content == "x" * 4097


def test_trace_rejects_malformed_existing_jsonl(tmp_path: Path) -> None:
    task_root = _init_task(tmp_path)
    (task_root / "trace.jsonl").write_text("not-json\n", encoding="utf-8")

    with pytest.raises(HanCodeError) as exc_info:
        append_trace(
            task_root,
            event_type="task_started",
            task_id="task-001",
            phase=Phase.SPEC,
            status="running",
        )

    assert exc_info.value.to_dict() == {
        "error_code": "trace_parse_error",
        "message": "Existing task trace is invalid.",
        "phase": "spec",
        "denied_rule": "valid_trace_required",
        "suggested_fix": "Repair or restore trace.jsonl before continuing.",
    }


@pytest.mark.parametrize(
    "persisted_event",
    [
        {"event_id": "evt-000000", "seq": 0},
        {"event_id": "evt-000007", "seq": 1},
    ],
)
def test_trace_rejects_invalid_existing_sequence(
    tmp_path: Path, persisted_event: dict[str, object]
) -> None:
    task_root = _init_task(tmp_path)
    (task_root / "trace.jsonl").write_text(
        json.dumps(persisted_event) + "\n", encoding="utf-8"
    )

    with pytest.raises(HanCodeError) as exc_info:
        append_trace(
            task_root,
            event_type="task_started",
            task_id="task-001",
            phase=Phase.SPEC,
            status="running",
        )

    assert exc_info.value.to_dict()["error_code"] == "trace_parse_error"


def test_trace_write_failure_blocks_high_risk_action(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_root = _init_task(tmp_path)
    trace_path = task_root / "trace.jsonl"
    original_open = Path.open

    def fail_append(
        path: Path, mode: str = "r", *args: object, **kwargs: object
    ) -> object:
        if path == trace_path and mode == "a":
            raise OSError("write denied: trace-secret-value")
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_append)

    with pytest.raises(HanCodeError) as exc_info:
        append_trace(
            task_root,
            event_type="tool_called",
            task_id="task-001",
            phase=Phase.CODE,
            status="running",
            action=_tool_action(),
        )

    assert exc_info.value.to_dict() == {
        "error_code": "trace_write_error",
        "message": "Trace event could not be persisted.",
        "phase": "code",
        "denied_rule": "trace_persistence_required",
        "suggested_fix": (
            "Restore task trace write access before continuing with high-risk actions."
        ),
    }
    assert "trace-secret-value" not in str(exc_info.value)


@pytest.mark.parametrize(
    "trace_lines",
    [
        ('{"event_id": "evt-000001", "seq": 1}', "not-json", '{"event_id": "evt-000002", "seq": 2}'),
        ('{"event_id": "evt-000001", "seq": 1}', '{"event_id": "evt-000001", "seq": 1}'),
    ],
)
def test_trace_rejects_invalid_history_before_append(
    tmp_path: Path, trace_lines: tuple[str, ...]
) -> None:
    task_root = _init_task(tmp_path)
    (task_root / "trace.jsonl").write_text("\n".join(trace_lines) + "\n", encoding="utf-8")

    with pytest.raises(HanCodeError) as exc_info:
        append_trace(
            task_root,
            event_type="task_started",
            task_id="task-001",
            phase=Phase.SPEC,
            status="running",
        )

    assert exc_info.value.to_dict()["error_code"] == "trace_parse_error"


def test_trace_serialization_failure_returns_structured_error(tmp_path: Path) -> None:
    task_root = _init_task(tmp_path)

    with pytest.raises(HanCodeError) as exc_info:
        append_trace(
            task_root,
            event_type="task_started",
            task_id="task-001",
            phase=Phase.SPEC,
            status="running",
            observation={"unsupported": {"not-json-serializable"}},
        )

    assert exc_info.value.to_dict()["error_code"] == "trace_write_error"
    assert "not-json-serializable" not in str(exc_info.value)


def test_trace_redacts_secret_like_text_values(tmp_path: Path) -> None:
    task_root = _init_task(tmp_path)

    append_trace(
        task_root,
        event_type="task_started",
        task_id="task-001",
        phase=Phase.SPEC,
        status="running",
        observation={
            "output": "Authorization: Bearer trace-bearer-secret",
            "content": "OPENAI_API_KEY=trace-api-secret",
        },
        error_summary="token=trace-token-secret",
    )

    trace_text = (task_root / "trace.jsonl").read_text(encoding="utf-8")
    assert "trace-bearer-secret" not in trace_text
    assert "trace-api-secret" not in trace_text
    assert "trace-token-secret" not in trace_text


def test_trace_redacts_cookie_aws_and_bearer_values(tmp_path: Path) -> None:
    task_root = _init_task(tmp_path)

    append_trace(
        task_root,
        event_type="task_started",
        task_id="task-001",
        phase=Phase.SPEC,
        status="running",
        observation={
            "cookie": "session=trace-cookie-secret",
            "content": "AWS_ACCESS_KEY_ID=trace-aws-secret",
            "output": "Bearer trace-bearer-secret",
        },
    )

    trace_text = (task_root / "trace.jsonl").read_text(encoding="utf-8")
    assert "trace-cookie-secret" not in trace_text
    assert "trace-aws-secret" not in trace_text
    assert "trace-bearer-secret" not in trace_text


def test_trace_rejects_tool_event_without_auditable_action(tmp_path: Path) -> None:
    task_root = _init_task(tmp_path)

    with pytest.raises(HanCodeError) as exc_info:
        append_trace(
            task_root,
            event_type="tool_called",
            task_id="task-001",
            phase=Phase.CODE,
            status="running",
        )

    assert exc_info.value.to_dict() == {
        "error_code": "invalid_trace_event",
        "message": "Trace event is invalid.",
        "phase": "code",
        "denied_rule": "auditable_tool_event_required",
        "suggested_fix": "Record tool name, arguments, reason, and policy decision.",
    }


def test_trace_rejects_failed_tool_event_without_error_summary(tmp_path: Path) -> None:
    task_root = _init_task(tmp_path)

    with pytest.raises(HanCodeError) as exc_info:
        append_trace(
            task_root,
            event_type="tool_failed",
            task_id="task-001",
            phase=Phase.CODE,
            status="failed",
            action=_tool_action(),
        )

    assert exc_info.value.to_dict()["denied_rule"] == "auditable_tool_event_required"


def test_trace_rejects_task_id_outside_task_root(tmp_path: Path) -> None:
    task_root = _init_task(tmp_path)

    with pytest.raises(HanCodeError) as exc_info:
        append_trace(
            task_root,
            event_type="task_started",
            task_id="task-002",
            phase=Phase.SPEC,
            status="running",
        )

    assert exc_info.value.to_dict()["error_code"] == "trace_task_identity_mismatch"


def test_trace_rejects_history_for_another_task(tmp_path: Path) -> None:
    task_root = _init_task(tmp_path)
    (task_root / "trace.jsonl").write_text(
        '{"event_id": "evt-000001", "seq": 1, "task_id": "task-002"}\n',
        encoding="utf-8",
    )

    with pytest.raises(HanCodeError) as exc_info:
        append_trace(
            task_root,
            event_type="task_started",
            task_id="task-001",
            phase=Phase.SPEC,
            status="running",
        )

    assert exc_info.value.to_dict()["error_code"] == "trace_parse_error"


@pytest.mark.parametrize(
    ("action", "status"),
    [
        (
            {
                "tool_name": "write_file",
                "args": {"path": "src/main.py"},
                "reason": "Update source code.",
                "policy_decision": {},
            },
            "running",
        ),
        (
            {
                "tool_name": "write_file",
                "args": {"path": "src/main.py"},
                "reason": "Update source code.",
                "policy_decision": {
                    "allowed": True,
                    "message": "Action is allowed.",
                    "phase": "code",
                    "denied_rule": None,
                    "suggested_fix": "",
                },
            },
            "unknown",
        ),
    ],
)
def test_trace_rejects_tool_event_without_complete_decision_or_status(
    tmp_path: Path, action: dict[str, object], status: str
) -> None:
    task_root = _init_task(tmp_path)

    with pytest.raises(HanCodeError) as exc_info:
        append_trace(
            task_root,
            event_type="tool_called",
            task_id="task-001",
            phase=Phase.CODE,
            status=status,
            action=action,
        )

    assert exc_info.value.to_dict()["denied_rule"] == "auditable_tool_event_required"


def test_trace_normalizes_non_string_payload_keys(tmp_path: Path) -> None:
    task_root = _init_task(tmp_path)

    append_trace(
        task_root,
        event_type="task_started",
        task_id="task-001",
        phase=Phase.SPEC,
        status="running",
        observation={1: "safe"},  # type: ignore[dict-item]
    )

    event = json.loads((task_root / "trace.jsonl").read_text(encoding="utf-8"))
    assert event["observation"] == {"1": "safe"}


def test_trace_rejects_non_string_error_summary(tmp_path: Path) -> None:
    task_root = _init_task(tmp_path)

    with pytest.raises(HanCodeError) as exc_info:
        append_trace(
            task_root,
            event_type="task_started",
            task_id="task-001",
            phase=Phase.SPEC,
            status="running",
            error_summary=1,  # type: ignore[arg-type]
        )

    assert exc_info.value.to_dict()["error_code"] == "invalid_trace_payload"


def test_trace_rejects_task_root_outside_workspace_layout(tmp_path: Path) -> None:
    task_root = tmp_path / "outside" / "task-001"
    task_root.mkdir(parents=True)
    (task_root / "trace.jsonl").write_text("", encoding="utf-8")

    with pytest.raises(HanCodeError) as exc_info:
        append_trace(
            task_root,
            event_type="task_started",
            task_id="task-001",
            phase=Phase.SPEC,
            status="running",
        )

    assert exc_info.value.to_dict()["error_code"] == "invalid_trace_task_root"


def test_trace_rejects_task_root_without_valid_project_metadata(tmp_path: Path) -> None:
    task_root = tmp_path / ".hancode" / "tasks" / "task-001"
    task_root.mkdir(parents=True)
    (task_root / "trace.jsonl").write_text("", encoding="utf-8")

    with pytest.raises(HanCodeError) as exc_info:
        append_trace(
            task_root,
            event_type="task_started",
            task_id="task-001",
            phase=Phase.SPEC,
            status="running",
        )

    assert exc_info.value.to_dict()["error_code"] == "invalid_trace_task_root"


@pytest.mark.parametrize(
    ("observation", "state_transition"),
    [(["not-a-mapping"], None), (None, 1)],
)
def test_trace_rejects_non_mapping_payloads(
    tmp_path: Path, observation: object, state_transition: object
) -> None:
    task_root = _init_task(tmp_path)

    with pytest.raises(HanCodeError) as exc_info:
        append_trace(
            task_root,
            event_type="task_started",
            task_id="task-001",
            phase=Phase.SPEC,
            status="running",
            observation=observation,  # type: ignore[arg-type]
            state_transition=state_transition,  # type: ignore[arg-type]
        )

    assert exc_info.value.to_dict()["error_code"] == "invalid_trace_payload"


@pytest.mark.parametrize(
    ("event_type", "status", "policy_decision"),
    [
        (
            "tool_completed",
            "failed",
            {
                "allowed": True,
                "message": "Action is allowed.",
                "phase": "code",
                "denied_rule": None,
                "suggested_fix": "",
            },
        ),
        (
            "tool_called",
            "running",
            {
                "allowed": True,
                "message": "Action is allowed.",
                "phase": "code",
                "denied_rule": 1,
                "suggested_fix": "",
            },
        ),
    ],
)
def test_trace_rejects_inconsistent_tool_event_details(
    tmp_path: Path,
    event_type: str,
    status: str,
    policy_decision: dict[str, object],
) -> None:
    task_root = _init_task(tmp_path)

    with pytest.raises(HanCodeError) as exc_info:
        append_trace(
            task_root,
            event_type=event_type,
            task_id="task-001",
            phase=Phase.CODE,
            status=status,
            action={**_tool_action(), "policy_decision": policy_decision},
        )

    assert exc_info.value.to_dict()["denied_rule"] == "auditable_tool_event_required"


def test_trace_omits_content_values_from_observations(tmp_path: Path) -> None:
    task_root = _init_task(tmp_path)
    protected_content = "teacher hidden expected result"

    append_trace(
        task_root,
        event_type="tool_completed",
        task_id="task-001",
        phase=Phase.CODE,
        status="succeeded",
        action=_tool_action(),
        observation={"content": protected_content},
    )

    trace_text = (task_root / "trace.jsonl").read_text(encoding="utf-8")
    assert protected_content not in trace_text
    assert json.loads(trace_text)["observation"]["content"] == {
        "summary": "[CONTENT_OMITTED]",
        "char_count": len(protected_content),
    }


def test_trace_omits_content_field_aliases_recursively(tmp_path: Path) -> None:
    task_root = _init_task(tmp_path)
    protected_content = "teacher hidden expected result"

    append_trace(
        task_root,
        event_type="tool_completed",
        task_id="task-001",
        phase=Phase.CODE,
        status="succeeded",
        action={
            **_tool_action(),
            "args": {"response_body": protected_content},
        },
        observation={"tool_output": protected_content},
    )

    trace_text = (task_root / "trace.jsonl").read_text(encoding="utf-8")
    assert protected_content not in trace_text
    event = json.loads(trace_text)
    assert event["action"]["args"]["response_body"] == {
        "summary": "[CONTENT_OMITTED]",
        "char_count": len(protected_content),
    }
    assert event["observation"]["tool_output"] == {
        "summary": "[CONTENT_OMITTED]",
        "char_count": len(protected_content),
    }


def _init_task(project_root: Path) -> Path:
    init_project_workspace(
        project_root,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )
    return init_task_workspace(project_root, "task-001")


def _tool_action() -> dict[str, object]:
    return {
        "tool_name": "write_file",
        "args": {"path": "src/main.py"},
        "reason": "Update source code.",
        "policy_decision": _policy_decision(),
    }


def _policy_decision() -> dict[str, object]:
    return {
        "allowed": True,
        "message": "Action is allowed.",
        "phase": "code",
        "denied_rule": None,
        "suggested_fix": "",
    }
