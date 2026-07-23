from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping, Protocol


ProviderResponseMode = Literal[
    "json_object",
    "json_schema",
]


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    response_mode: ProviderResponseMode

    @property
    def supports_strict_json_schema(self) -> bool:
        return self.response_mode == "json_schema"


@dataclass(frozen=True, slots=True)
class ToolDescriptor:
    name: str
    description: str
    args_schema: Mapping[str, object]


class LLMClient(Protocol):
    """Minimal provider boundary consumed by the runtime loop."""

    def next_action(self, context: dict[str, object]) -> dict[str, object]: ...
