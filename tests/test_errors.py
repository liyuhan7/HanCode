from __future__ import annotations

import json

from hancode.errors import HanCodeError, StructuredError


def test_structured_error_has_code_message_hint() -> None:
    error = StructuredError(
        code="policy_denied",
        message="Writing protected course files is not allowed.",
        hint="Change the plan instead of editing teacher tests.",
    )

    assert error.code == "policy_denied"
    assert error.message == "Writing protected course files is not allowed."
    assert error.hint == "Change the plan instead of editing teacher tests."
    assert error.details == {}


def test_structured_error_serializes_to_dict() -> None:
    error = StructuredError(
        code="invalid_phase",
        message="Unknown phase.",
        hint="Use one of spec, plan, code, test, review, deliver.",
        details={"phase": "deploy"},
    )

    payload = error.to_dict()

    assert payload == {
        "code": "invalid_phase",
        "message": "Unknown phase.",
        "hint": "Use one of spec, plan, code, test, review, deliver.",
        "details": {"phase": "deploy"},
    }
    assert json.loads(json.dumps(payload)) == payload


def test_hancode_error_wraps_structured_error() -> None:
    structured = StructuredError(
        code="state_inconsistent",
        message="state.json conflicts with task artifacts.",
        hint="Review the task workspace before continuing.",
        details={"task_id": "task-001"},
    )

    error = HanCodeError(structured)

    assert str(error) == "state_inconsistent: state.json conflicts with task artifacts."
    assert error.structured_error is structured
    assert error.to_dict()["details"] == {"task_id": "task-001"}
