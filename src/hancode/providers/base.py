from __future__ import annotations

from typing import Protocol


class LLMClient(Protocol):
    """Minimal provider boundary consumed by the runtime loop."""

    def next_action(self, context: dict[str, object]) -> dict[str, object]: ...
