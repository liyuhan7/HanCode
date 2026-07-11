from __future__ import annotations

from copy import deepcopy

import pytest

from hancode.actions import Action, parse_action
from hancode.llm import MockLLM, MockLLMExhausted
from hancode.models import Phase


def _read_file_action(path: str) -> dict[str, object]:
    return {
        "type": "tool_call",
        "phase": "code",
        "tool_name": "read_file",
        "args": {"path": path},
        "reason": None,
    }


def test_mock_llm_returns_actions_in_input_order() -> None:
    llm = MockLLM([_read_file_action("README.md"), _read_file_action("docs/PLAN.md")])

    first = llm.next_action({"step": 1})
    second = llm.next_action({"step": 2})

    assert first == _read_file_action("README.md")
    assert second == _read_file_action("docs/PLAN.md")


def test_mock_llm_records_deep_copied_contexts() -> None:
    context = {"task": {"id": "T9"}}
    llm = MockLLM([_read_file_action("README.md")])

    llm.next_action(context)

    assert llm.contexts == ({"task": {"id": "T9"}},)


def test_mock_llm_is_deterministic() -> None:
    actions = [_read_file_action("README.md"), _read_file_action("docs/PLAN.md")]
    first = MockLLM(actions)
    second = MockLLM(actions)
    contexts = [{"step": 1}, {"step": 2}]

    assert [first.next_action(context) for context in contexts] == [
        second.next_action(context) for context in contexts
    ]
    assert first.contexts == second.contexts == tuple(contexts)


def test_mock_llm_returns_raw_action_that_action_parser_can_parse() -> None:
    llm = MockLLM([_read_file_action("README.md")])

    raw_action = llm.next_action({"phase": "code"})

    assert parse_action(raw_action, Phase.CODE) == Action.from_values(
        type="tool_call",
        phase="code",
        tool_name="read_file",
        args={"path": "README.md"},
        reason=None,
    )


def test_mock_llm_returns_malformed_raw_actions_without_schema_validation() -> None:
    malformed_action = {
        "type": "not-a-registered-action",
        "args": {"payload": {"id": "raw-value"}},
    }
    llm = MockLLM([malformed_action])

    returned = llm.next_action({"phase": "code"})

    assert returned == malformed_action
    assert returned is not malformed_action


def test_mock_llm_exhaustion_has_stable_diagnostic_fields() -> None:
    llm = MockLLM([])

    with pytest.raises(MockLLMExhausted, match="^MockLLM action sequence exhausted\\.$") as raised:
        llm.next_action({"step": 1})

    assert str(raised.value) == "MockLLM action sequence exhausted."
    assert raised.value.error_code == "mock_llm_exhausted"
    assert raised.value.suggested_fix == "Provide another mock action or stop the loop as blocked."


def test_exhausted_mock_llm_call_still_records_context() -> None:
    llm = MockLLM([])

    with pytest.raises(MockLLMExhausted):
        llm.next_action({"step": 1, "state": {"status": "running"}})

    assert llm.contexts == ({"step": 1, "state": {"status": "running"}},)


def test_mock_llm_isolates_input_actions_and_returned_actions() -> None:
    actions = [_read_file_action("README.md")]
    original = deepcopy(actions)
    llm = MockLLM(actions)
    actions[0]["args"] = {"path": "changed-after-construction.md"}

    returned = llm.next_action({})
    assert returned == original[0]
    assert isinstance(returned["args"], dict)
    returned["args"]["path"] = "changed-after-return.md"

    assert actions != original
    assert original == [_read_file_action("README.md")]
    assert returned != original[0]


def test_mock_llm_keeps_later_action_deeply_isolated_from_earlier_return() -> None:
    shared_args = {"payload": {"path": "README.md"}}
    llm = MockLLM(
        [
            {"type": "tool_call", "args": shared_args},
            {"type": "tool_call", "args": shared_args},
        ]
    )

    first = llm.next_action({})
    assert isinstance(first["args"], dict)
    assert isinstance(first["args"]["payload"], dict)
    first["args"]["payload"]["path"] = "changed-through-first-return.md"
    second = llm.next_action({})

    assert second["args"] == {"payload": {"path": "README.md"}}


def test_mock_llm_isolates_input_context_and_public_history() -> None:
    context = {"task": {"id": "T9"}}
    llm = MockLLM([_read_file_action("README.md")])

    llm.next_action(context)
    context["task"] = {"id": "changed-by-caller"}
    history = llm.contexts
    history[0]["task"] = {"id": "changed-through-history"}

    assert llm.contexts == ({"task": {"id": "T9"}},)
