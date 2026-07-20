"""Application service for answering persisted human interactions."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Callable

from hancode.app.task_models import TaskSummary
from hancode.core.config import load_config
from hancode.core.errors import HanCodeError, StructuredError
from hancode.core.interactions import InteractionRecord, InteractionStatus
from hancode.core.models import Phase, TaskStatus
from hancode.core.state import load_state, reconcile_state, save_state
from hancode.storage.task_lock import FilesystemTaskMutationGuard, TaskMutationGuard
from hancode.storage.trace import append_trace
from hancode.storage.workspace import task_path
from hancode.tooling.file_tools import redact_text


GuardFactory = Callable[[Path], TaskMutationGuard]


class InteractionService:
    """Read and update task interactions without invoking a provider."""

    def __init__(self, *, guard_factory: GuardFactory = FilesystemTaskMutationGuard) -> None:
        self._guard_factory = guard_factory

    def get_pending(self, project_root: Path, task_id: str) -> InteractionRecord | None:
        root = task_path(project_root, task_id)
        state = reconcile_state(root, load_state(root))
        if state.inconsistent or state.status is TaskStatus.INCONSISTENT:
            raise _interaction_error(
                "interaction_state_invalid",
                "The task state is inconsistent and cannot accept interaction input.",
                state.current_phase,
                "Reconcile the task state before reading its pending interaction.",
            )
        interaction = _pending_record(state)
        if interaction is None or interaction.status is not InteractionStatus.WAITING:
            return None
        return interaction

    def answer(
        self,
        project_root: Path,
        task_id: str,
        answer: str,
        *,
        interaction_id: str | None = None,
    ) -> TaskSummary:
        root = task_path(project_root, task_id)
        initial_state = load_state(root)
        phase = initial_state.current_phase
        with self._guard_factory(project_root).acquire(task_id, phase):
            state = reconcile_state(root, load_state(root))
            if state.inconsistent or state.status is TaskStatus.INCONSISTENT:
                raise _interaction_error(
                    "interaction_state_invalid",
                    "The task state is inconsistent and cannot accept interaction input.",
                    state.current_phase,
                    "Reconcile the task state before answering the interaction.",
                )
            interaction = _pending_record(state)
            if interaction is None:
                raise _interaction_error(
                    "interaction_not_pending",
                    "The task has no pending interaction.",
                    state.current_phase,
                    "Run the task until it requests user input.",
                )
            if interaction_id is not None and interaction_id != interaction.interaction_id:
                raise _interaction_error(
                    "interaction_id_mismatch",
                    "The supplied interaction ID does not match the pending interaction.",
                    state.current_phase,
                    "Use the interaction ID reported by task status.",
                )
            if not isinstance(answer, str) or not answer.strip():
                raise _interaction_error(
                    "interaction_answer_required",
                    "Interaction answers must be non-empty.",
                    state.current_phase,
                    "Provide a non-empty answer.",
                )

            safe_answer = redact_text(answer.strip())
            if not safe_answer.strip() or safe_answer.strip() == "[REDACTED]":
                raise _interaction_error(
                    "interaction_answer_contains_only_sensitive_content",
                    "The interaction answer contains only sensitive content.",
                    state.current_phase,
                    "Do not provide credentials through ASK_USER; use hancode auth login.",
                )
            config = load_config(project_root, task_id)
            if len(answer) > config.max_interaction_answer_chars:
                raise _interaction_error(
                    "interaction_answer_too_long",
                    "The interaction answer exceeds the configured length limit.",
                    state.current_phase,
                    "Shorten the answer to the configured character limit.",
                )

            if interaction.status is InteractionStatus.ANSWERED:
                if safe_answer != interaction.answer:
                    raise _interaction_error(
                        "interaction_answer_conflict",
                        "A different answer was already recorded for this interaction.",
                        state.current_phase,
                        "Reuse the original answer or start a new interaction.",
                    )
                return TaskSummary.from_state(state)

            answered = replace(
                interaction,
                answer=safe_answer,
                status=InteractionStatus.ANSWERED,
            )
            updated = replace(
                state,
                status=TaskStatus.WAITING_INPUT,
                interactions=tuple(
                    answered if item.interaction_id == interaction.interaction_id else item
                    for item in state.interactions
                ),
            )
            save_state(root, updated)
            try:
                append_trace(
                    root,
                    event_type="interaction_answered",
                    task_id=task_id,
                    phase=state.current_phase,
                    status="succeeded",
                    observation={
                        "interaction_id": interaction.interaction_id,
                        "answer_length": len(answer.strip()),
                        "redacted": safe_answer != answer.strip(),
                    },
                )
            except HanCodeError:
                try:
                    save_state(root, state)
                except HanCodeError:
                    raise _interaction_error(
                        "interaction_persistence_inconsistent",
                        "The interaction answer was recorded but the audit trace could not be written, and state rollback also failed.",
                        state.current_phase,
                        "Manually verify the task state and trace before retrying.",
                    )
                raise
            return TaskSummary.from_state(updated)


def _pending_record(state: object) -> InteractionRecord | None:
    pending_id = getattr(state, "pending_interaction_id", None)
    interactions = getattr(state, "interactions", ())
    if not isinstance(pending_id, str):
        return None
    for interaction in interactions:
        if (
            isinstance(interaction, InteractionRecord)
            and interaction.interaction_id == pending_id
        ):
            return interaction
    return None


def _interaction_error(
    error_code: str,
    message: str,
    phase: Phase,
    suggested_fix: str,
) -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code=error_code,
            message=message,
            phase=phase.value,
            denied_rule=error_code,
            suggested_fix=suggested_fix,
        )
    )


__all__ = ["InteractionService"]
