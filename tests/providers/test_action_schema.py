from __future__ import annotations

import pytest

from hancode.core.actions import ParseError, parse_action
from hancode.core.models import Phase
from hancode.providers.action_schema import build_action_schema
from hancode.providers.base import ToolDescriptor


def _make_catalog() -> tuple[ToolDescriptor, ...]:
    return (
        ToolDescriptor(
            name="read_file",
            description="Read a file inside the allowed workspace.",
            args_schema={"type": "object", "properties": {"path": {"type": "string"}}},
        ),
        ToolDescriptor(
            name="list_files",
            description="List files in the project workspace.",
            args_schema={"type": "object"},
        ),
        ToolDescriptor(
            name="write_file",
            description="Write a file inside the allowed workspace.",
            args_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
            },
        ),
    )


def test_schema_includes_tool_call_branch() -> None:
    schema = build_action_schema(
        phase=Phase.SPEC, tool_catalog=_make_catalog()
    )
    branches = schema["oneOf"]
    tool_call_branches = [
        b
        for b in branches
        if b["properties"]["type"]["const"] == "tool_call"
    ]
    assert len(tool_call_branches) == 1
    branch = tool_call_branches[0]
    assert branch["properties"]["phase"]["const"] == "spec"
    assert "read_file" in branch["properties"]["tool_name"]["enum"]
    assert "write_file" in branch["properties"]["tool_name"]["enum"]


def test_schema_exposes_tool_argument_schemas() -> None:
    schema = build_action_schema(
        phase=Phase.SPEC, tool_catalog=_make_catalog()
    )
    tool_call_branch = next(
        b for b in schema["oneOf"] if b["properties"]["type"]["const"] == "tool_call"
    )
    argument_schemas = tool_call_branch["properties"]["args"]["oneOf"]
    assert any(
        argument_schema["properties"].get("path") == {"type": "string"}
        for argument_schema in argument_schemas
    )


def test_schema_includes_finish_phase_branch() -> None:
    schema = build_action_schema(
        phase=Phase.PLAN, tool_catalog=_make_catalog()
    )
    branches = schema["oneOf"]
    finish_branches = [
        b
        for b in branches
        if b["properties"]["type"]["const"] == "finish_phase"
    ]
    assert len(finish_branches) == 1
    branch = finish_branches[0]
    assert branch["properties"]["phase"]["const"] == "plan"
    assert branch["properties"]["tool_name"] == {"type": "null"}
    assert branch["properties"]["args"] == {"type": "object", "maxProperties": 0}


def test_schema_includes_final_branch() -> None:
    schema = build_action_schema(
        phase=Phase.DELIVER, tool_catalog=_make_catalog()
    )
    branches = schema["oneOf"]
    final_branches = [
        b for b in branches if b["properties"]["type"]["const"] == "final"
    ]
    assert len(final_branches) == 1
    branch = final_branches[0]
    assert branch["properties"]["phase"]["const"] == "deliver"


def test_schema_excludes_ask_user_in_stage_two() -> None:
    schema = build_action_schema(
        phase=Phase.SPEC,
        tool_catalog=_make_catalog(),
        interaction_enabled=False,
    )
    branches = schema["oneOf"]
    type_consts = [b["properties"]["type"]["const"] for b in branches]
    assert "ask_user" not in type_consts


def test_schema_includes_ask_user_when_interaction_enabled() -> None:
    schema = build_action_schema(
        phase=Phase.SPEC,
        tool_catalog=_make_catalog(),
        interaction_enabled=True,
    )
    branches = schema["oneOf"]
    type_consts = [b["properties"]["type"]["const"] for b in branches]
    assert "ask_user" in type_consts


def test_schema_rejects_unknown_tool_by_exclusion() -> None:
    schema = build_action_schema(
        phase=Phase.SPEC, tool_catalog=_make_catalog()
    )
    branches = schema["oneOf"]
    tool_call_branch = next(
        b for b in branches if b["properties"]["type"]["const"] == "tool_call"
    )
    enum_tools = set(tool_call_branch["properties"]["tool_name"]["enum"])
    assert "unknown_tool" not in enum_tools
    assert "run_shell" not in enum_tools


def test_schema_uses_current_phase_constant() -> None:
    for phase in Phase:
        schema = build_action_schema(
            phase=phase, tool_catalog=_make_catalog()
        )
        for branch in schema["oneOf"]:
            assert branch["properties"]["phase"]["const"] == phase.value


def test_schema_requires_reason_non_empty() -> None:
    schema = build_action_schema(
        phase=Phase.SPEC, tool_catalog=_make_catalog()
    )
    for branch in schema["oneOf"]:
        reason_schema = branch["properties"]["reason"]
        assert reason_schema["type"] == "string"
        assert reason_schema["minLength"] == 1


def test_schema_forbids_additional_properties() -> None:
    schema = build_action_schema(
        phase=Phase.SPEC, tool_catalog=_make_catalog()
    )
    for branch in schema["oneOf"]:
        assert branch["additionalProperties"] is False


@pytest.mark.parametrize("phase", list(Phase))
def test_schema_examples_are_accepted_by_parse_action(phase: Phase) -> None:
    catalog = _make_catalog()
    build_action_schema(phase=phase, tool_catalog=catalog)

    tool_call_example = {
        "type": "tool_call",
        "phase": phase.value,
        "tool_name": "read_file",
        "args": {"path": "src/main.py"},
        "reason": "Reading the main source file.",
    }
    result = parse_action(dict(tool_call_example), phase)
    assert not isinstance(result, ParseError), (
        f"tool_call example rejected by parse_action: {result}"
    )

    finish_example = {
        "type": "finish_phase",
        "phase": phase.value,
        "tool_name": None,
        "args": {},
        "reason": f"Finishing {phase.value} phase.",
    }
    result = parse_action(dict(finish_example), phase)
    assert not isinstance(result, ParseError), (
        f"finish_phase example rejected by parse_action: {result}"
    )

    final_example = {
        "type": "final",
        "phase": phase.value,
        "tool_name": None,
        "args": {},
        "reason": "Task complete.",
    }
    result = parse_action(dict(final_example), phase)
    assert not isinstance(result, ParseError), (
        f"final example rejected by parse_action: {result}"
    )


def test_schema_write_file_example_passes_parse_action() -> None:
    catalog = _make_catalog()
    build_action_schema(phase=Phase.CODE, tool_catalog=catalog)

    write_example = {
        "type": "tool_call",
        "phase": "code",
        "tool_name": "write_file",
        "args": {"path": "src/main.py", "content": "print('hello')"},
        "reason": "Creating the main source file.",
    }
    result = parse_action(write_example, Phase.CODE)
    assert not isinstance(result, ParseError), (
        f"write_file example rejected by parse_action: {result}"
    )
