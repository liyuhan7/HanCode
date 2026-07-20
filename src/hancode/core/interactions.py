"""Domain model for persisted human-in-the-loop interactions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re

from hancode.core.models import Phase


class InteractionStatus(str, Enum):
    WAITING = "waiting"
    ANSWERED = "answered"


@dataclass(frozen=True, slots=True)
class InteractionRecord:
    interaction_id: str
    phase: Phase
    question: str
    answer: str | None
    status: InteractionStatus

    def __post_init__(self) -> None:
        if not re.fullmatch(r"ask-\d{6}", self.interaction_id):
            raise ValueError("interaction_id must match ask-XXXXXX")
        if not isinstance(self.phase, Phase):
            raise ValueError("interaction phase must be a Phase")
        if not isinstance(self.question, str) or not self.question.strip():
            raise ValueError("interaction question must be non-empty")
        if not isinstance(self.status, InteractionStatus):
            raise ValueError("interaction status must be InteractionStatus")
        if self.status is InteractionStatus.WAITING and self.answer is not None:
            raise ValueError("waiting interaction cannot have an answer")
        if self.status is InteractionStatus.ANSWERED and (
            not isinstance(self.answer, str) or not self.answer.strip()
        ):
            raise ValueError("answered interaction requires an answer")

    def to_dict(self) -> dict[str, object]:
        return {
            "interaction_id": self.interaction_id,
            "phase": self.phase.value,
            "question": self.question,
            "answer": self.answer,
            "status": self.status.value,
        }
