from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol


@dataclass(frozen=True, slots=True)
class ToolDescriptor:
    name: str
    description: str
    args_schema: Mapping[str, object]


class LLMClient(Protocol):
    """Minimal provider boundary consumed by the runtime loop."""

    def next_action(self, context: dict[str, object]) -> dict[str, object]: ...
