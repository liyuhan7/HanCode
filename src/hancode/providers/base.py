from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Literal, Mapping, Protocol

from hancode.core.models import Phase
from hancode.providers.tool_schema import StrictSchemaProjection


ProviderActionMode = Literal[
    "auto",
    "native_tools_strict",
    "native_tools",
    "json_object",
    "json_schema",
]


@dataclass(frozen=True, slots=True)
class ToolDescriptor:
    name: str
    description: str
    args_schema: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ProviderToolDefinition:
    name: str
    description: str
    request_schema: Mapping[str, object]
    original_args_schema: Mapping[str, object]
    projection: StrictSchemaProjection

    @property
    def parameters(self) -> Mapping[str, object]:
        """Compatibility alias for the pre-S6 native request schema."""
        return self.request_schema


@dataclass(frozen=True, slots=True)
class ProviderEvent:
    kind: Literal["mode_fallback"]
    phase: Phase
    # Capability-profile labels are richer than ProviderActionMode (e.g. the
    # intermediate native states native_tools_no_parallel / native_tools_basic),
    # so the fallback event carries plain strings.
    from_mode: str
    to_mode: str
    reason_code: str


class ProviderEventSink(Protocol):
    def emit(self, event: ProviderEvent) -> None: ...


def build_provider_tool_definitions(
    tool_catalog: tuple[ToolDescriptor, ...],
    *,
    interaction_enabled: bool = False,
) -> tuple[ProviderToolDefinition, ...]:
    """Build native function definitions from the shared ToolSpec-derived catalog."""
    definitions: list[ProviderToolDefinition] = []
    for tool in tool_catalog:
        original_args_schema = deepcopy(dict(tool.args_schema))
        parameters = deepcopy(dict(original_args_schema))
        raw_properties = parameters.get("properties")
        properties = dict(raw_properties) if isinstance(raw_properties, Mapping) else {}
        properties["reason"] = (
            {"type": "string", "minLength": 1, "maxLength": 1024}
            if tool.name in {"write_file", "edit_file"}
            else {
                "oneOf": [
                    {"type": "string", "minLength": 1, "maxLength": 1024},
                    {"type": "null"},
                ]
            }
        )
        raw_required = parameters.get("required")
        required = [item for item in raw_required if isinstance(item, str)] if isinstance(raw_required, list) else []
        if "reason" not in required:
            required.append("reason")
        parameters["type"] = "object"
        parameters["properties"] = properties
        parameters["required"] = required
        parameters["additionalProperties"] = False
        parameters.pop("maxProperties", None)
        definitions.append(
            ProviderToolDefinition(
                name=tool.name,
                description=tool.description,
                request_schema=parameters,
                original_args_schema=original_args_schema,
                projection=StrictSchemaProjection.project(parameters),
            )
        )
    definitions.append(_control_tool_definition(
        "finish_phase",
        "Finish the current phase when its gate is satisfied.",
        {"type": "object", "maxProperties": 0},
        {"type": "string", "minLength": 1, "maxLength": 1024},
    ))
    if interaction_enabled:
        definitions.append(_control_tool_definition(
            "ask_user",
            "Ask the user one precise question when required information is missing.",
            {
                "type": "object",
                "required": ["question"],
                "properties": {"question": {"type": "string", "minLength": 1, "maxLength": 2048}},
                "additionalProperties": False,
            },
            {
                "oneOf": [
                    {"type": "string", "minLength": 1, "maxLength": 1024},
                    {"type": "null"},
                ]
            },
        ))
    return tuple(definitions)


def _control_tool_definition(
    name: str,
    description: str,
    original_args_schema: Mapping[str, object],
    reason_schema: Mapping[str, object],
) -> ProviderToolDefinition:
    request_schema = deepcopy(dict(original_args_schema))
    raw_properties = request_schema.get("properties")
    properties = dict(raw_properties) if isinstance(raw_properties, Mapping) else {}
    properties["reason"] = deepcopy(dict(reason_schema))
    raw_required = request_schema.get("required")
    required = [item for item in raw_required if isinstance(item, str)] if isinstance(raw_required, list) else []
    if "reason" not in required:
        required.append("reason")
    request_schema.update({
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    })
    request_schema.pop("maxProperties", None)
    return ProviderToolDefinition(
        name=name,
        description=description,
        request_schema=request_schema,
        original_args_schema=deepcopy(dict(original_args_schema)),
        projection=StrictSchemaProjection.project(request_schema),
    )


class LLMClient(Protocol):
    """Minimal provider boundary consumed by the runtime loop."""

    def next_action(self, context: dict[str, object]) -> dict[str, object]: ...
