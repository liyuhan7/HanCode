from __future__ import annotations

from copy import deepcopy
from typing import ClassVar

from hancode.providers.base import LLMClient

__all__ = ["LLMClient", "MockLLMExhausted", "MockLLM"]


class MockLLMExhausted(RuntimeError):
    error_code: ClassVar[str] = "mock_llm_exhausted"
    suggested_fix: ClassVar[str] = "Provide another mock action or stop the loop as blocked."


class MockLLM:
    """Deterministic offline provider used by tests and the demo."""

    def __init__(self, actions: list[dict[str, object]]) -> None:
        self._actions = deepcopy(actions)
        self._contexts: list[dict[str, object]] = []
        self._next_action_index = 0

    @property
    def contexts(self) -> tuple[dict[str, object], ...]:
        return tuple(deepcopy(self._contexts))

    def next_action(self, context: dict[str, object]) -> dict[str, object]:
        self._contexts.append(deepcopy(context))
        if self._next_action_index >= len(self._actions):
            raise MockLLMExhausted("MockLLM action sequence exhausted.")

        action = deepcopy(self._actions[self._next_action_index])
        self._next_action_index += 1
        return action
