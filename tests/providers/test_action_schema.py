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
    assert {branch["properties"]["tool_name"]["const"] for branch in tool_call_branches} == {
        "read_file",
        "list_files",
        "write_file",
    }
    assert all(branch["properties"]["phase"]["const"] == "spec" for branch in tool_call_branches)


def test_schema_exposes_tool_argument_schemas() -> None:
    schema = build_action_schema(
        phase=Phase.SPEC, tool_catalog=_make_catalog()
    )
    read_branch = next(
        b
        for b in schema["oneOf"]
        if b["properties"].get("tool_name", {}).get("const") == "read_file"
    )
    assert read_branch["properties"]["args"]["properties"]["path"] == {
        "type": "string"
    }


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


def test_schema_does_not_expose_final() -> None:
    schema = build_action_schema(
        phase=Phase.DELIVER, tool_catalog=_make_catalog()
    )
    branches = schema["oneOf"]
    action_types = {
        branch["properties"]["type"]["const"] for branch in branches
    }
    assert "final" not in action_types
    assert "finish_phase" in action_types


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
    tool_names = {
        branch["properties"]["tool_name"]["const"]
        for branch in branches
        if branch["properties"]["type"]["const"] == "tool_call"
    }
    assert "unknown_tool" not in tool_names
    assert "run_shell" not in tool_names


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
        assert "reason" in branch["required"], (
            f"Branch {branch['properties']['type']['const']} "
            f"({branch['properties'].get('tool_name', {}).get('const', 'N/A')}) "
            "must require reason"
        )
        reason_schema = branch["properties"]["reason"]
        tool_name = branch["properties"].get("tool_name", {})
        if tool_name.get("const") in {"write_file", "edit_file"}:
            assert reason_schema["type"] == "string"
            assert reason_schema["minLength"] == 1
            assert reason_schema["maxLength"] == 1024
        else:
            assert reason_schema["oneOf"] == [
                {"type": "string", "minLength": 1, "maxLength": 1024},
                {"type": "null"},
            ]


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


def _minimal_args(args_schema: dict[str, object]) -> dict[str, object]:
    """Build minimal valid args from an args property schema."""
    props = args_schema.get("properties", {})
    if not isinstance(props, dict):
        return {}
    req = args_schema.get("required", [])
    if not isinstance(req, list):
        req = []
    max_prop = args_schema.get("maxProperties")
    if max_prop == 0:
        return {}
    result: dict[str, object] = {}

    def _fill_one(name: str, prop: object) -> object:
        if not isinstance(prop, dict):
            return ""
        if prop.get("type") == "string":
            return "x"
        if prop.get("type") == "boolean":
            return True
        if prop.get("type") == "array":
            return []
        if "enum" in prop and isinstance(prop["enum"], list) and prop["enum"]:
            return prop["enum"][0]
        if "oneOf" in prop and isinstance(prop["oneOf"], list):
            for sub in prop["oneOf"]:
                if not isinstance(sub, dict):
                    continue
                if sub.get("type") == "string":
                    return "x"
                if sub.get("type") == "null":
                    return None
            return None
        return ""

    for name in req:
        if name in props:
            result[name] = _fill_one(name, props[name])
    if not result and props:
        for name in props:
            result[name] = _fill_one(name, props[name])
    return result


def test_every_schema_valid_action_is_accepted_by_parse_action() -> None:
    """Every payload matching one schema branch must be accepted by parse_action."""
    catalog = _make_catalog()
    for phase in Phase:
        schema = build_action_schema(
            phase=phase,
            tool_catalog=catalog,
            interaction_enabled=True,
        )
        for branch in schema["oneOf"]:
            props = branch["properties"]
            phase_value = props["phase"]["const"]
            type_const = props["type"]["const"]

            if type_const == "tool_call":
                tool_name = props["tool_name"]["const"]
                args = _minimal_args(props["args"])
                reason_schema = props["reason"]
                if "oneOf" in reason_schema:
                    reason: str | None = None
                else:
                    reason = "test"
                payload = {
                    "type": "tool_call",
                    "phase": phase_value,
                    "tool_name": tool_name,
                    "args": args,
                    "reason": reason,
                }
            elif type_const == "finish_phase":
                payload = {
                    "type": "finish_phase",
                    "phase": phase_value,
                    "tool_name": None,
                    "args": {},
                    "reason": None,
                }
            elif type_const == "ask_user":
                payload = {
                    "type": "ask_user",
                    "phase": phase_value,
                    "tool_name": None,
                    "args": {"question": "test?"},
                    "reason": None,
                }
            else:
                continue

            # Payload is constructed to match the schema branch; parse_action must accept
            result = parse_action(dict(payload), phase)
            assert not isinstance(result, ParseError), (
                f"Schema-valid payload for {type_const} "
                f"(tool={payload.get('tool_name')}) "
                f"at phase {phase_value} was rejected by parse_action: {result}"
            )
