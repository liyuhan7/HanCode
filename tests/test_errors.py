from __future__ import annotations

import json

from hancode.core.errors import HanCodeError, StructuredError
from hancode.core.models import Phase


def test_structured_error_has_required_spec_fields() -> None:
    error = StructuredError(
        error_code="policy_denied",
        message="Writing protected course files is not allowed.",
        phase=Phase.CODE.value,
        denied_rule="protected_file_write",
        suggested_fix="Change the plan instead of editing teacher tests.",
    )

    assert error.error_code == "policy_denied"
    assert error.message == "Writing protected course files is not allowed."
    assert error.phase == "code"
    assert error.denied_rule == "protected_file_write"
    assert error.suggested_fix == "Change the plan instead of editing teacher tests."


def test_structured_error_serializes_to_dict() -> None:
    error = StructuredError(
        error_code="invalid_phase",
        message="Unknown phase.",
        phase="plan",
        denied_rule=None,
        suggested_fix="Use one of spec, plan, code, test, review, deliver.",
    )

    payload = error.to_dict()

    assert payload == {
        "error_code": "invalid_phase",
        "message": "Unknown phase.",
        "phase": "plan",
        "denied_rule": None,
        "suggested_fix": "Use one of spec, plan, code, test, review, deliver.",
    }
    assert json.loads(json.dumps(payload)) == payload


def test_hancode_error_wraps_structured_error() -> None:
    structured = StructuredError(
        error_code="state_inconsistent",
        message="state.json conflicts with task artifacts.",
        phase=Phase.REVIEW.value,
        denied_rule=None,
        suggested_fix="Review the task workspace before continuing.",
    )

    error = HanCodeError(structured)

    assert str(error) == "state_inconsistent: state.json conflicts with task artifacts."
    assert error.structured_error is structured
    assert error.to_dict()["phase"] == "review"
