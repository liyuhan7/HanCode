from __future__ import annotations

import pytest

from hancode.core.interactions import InteractionRecord, InteractionStatus
from hancode.core.models import Phase, TaskStatus


def test_waiting_interaction_requires_no_answer() -> None:
    record = InteractionRecord(
        interaction_id="ask-000001",
        phase=Phase.SPEC,
        question="Which framework should be used?",
        answer=None,
        status=InteractionStatus.WAITING,
    )

    assert record.status is InteractionStatus.WAITING
    assert record.answer is None


def test_waiting_interaction_rejects_answer() -> None:
    with pytest.raises(ValueError, match="waiting interaction cannot have an answer"):
        InteractionRecord(
            interaction_id="ask-000001",
            phase=Phase.SPEC,
            question="Which framework should be used?",
            answer="FastAPI",
            status=InteractionStatus.WAITING,
        )


def test_answered_interaction_requires_non_empty_answer() -> None:
    with pytest.raises(ValueError, match="answered interaction requires an answer"):
        InteractionRecord(
            interaction_id="ask-000001",
            phase=Phase.SPEC,
            question="Which framework should be used?",
            answer="   ",
            status=InteractionStatus.ANSWERED,
        )


def test_answered_interaction_accepts_answer() -> None:
    record = InteractionRecord(
        interaction_id="ask-000001",
        phase=Phase.SPEC,
        question="Which framework should be used?",
        answer="FastAPI",
        status=InteractionStatus.ANSWERED,
    )

    assert record.answer == "FastAPI"


@pytest.mark.parametrize("interaction_id", ["ask-1", "ask-0000001", "ask-x00001"])
def test_interaction_id_requires_six_digits(interaction_id: str) -> None:
    with pytest.raises(ValueError, match="interaction_id"):
        InteractionRecord(
            interaction_id=interaction_id,
            phase=Phase.SPEC,
            question="Question",
            answer=None,
            status=InteractionStatus.WAITING,
        )


def test_interaction_requires_non_empty_question() -> None:
    with pytest.raises(ValueError, match="question"):
        InteractionRecord(
            interaction_id="ask-000001",
            phase=Phase.SPEC,
            question=" ",
            answer=None,
            status=InteractionStatus.WAITING,
        )


def test_waiting_input_status_exists() -> None:
    assert TaskStatus.WAITING_INPUT.value == "waiting_input"
