"""Application service for submitting Runtime Steering during a run (S17)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from hancode.core.config import load_config
from hancode.core.errors import HanCodeError, StructuredError
from hancode.core.interventions import InterventionRecord
from hancode.core.state import load_state
from hancode.storage.interventions import InterventionStore
from hancode.storage.workspace import task_path


@dataclass(frozen=True, slots=True)
class SteeringSubmission:
    """Result of a successful steering submission (no steering body echoed)."""

    intervention_id: str
    sequence: int
    revision: int


class InterventionService:
    """Persist user steering for the active run without invoking a provider.

    The service validates run identity and input length, then delegates to the
    :class:`InterventionStore`, which owns secret redaction, sensitive-only
    rejection and the append-only log. It never starts a worker and never
    echoes the steering body into a return value or trace.
    """

    def __init__(self, *, store_factory: type[InterventionStore] = InterventionStore) -> None:
        self._store_factory = store_factory

    def submit(
        self, project_root: Path, task_id: str, content: str
    ) -> SteeringSubmission:
        root = task_path(project_root, task_id)
        if not root.is_dir():
            raise _steering_error(
                "task_not_found",
                f"Task workspace does not exist: {task_id}.",
                "existing_task_required",
                "Create the task before submitting steering.",
            )
        state = load_state(root)
        run_id = state.active_run_id
        if not run_id:
            raise _steering_error(
                "steering_no_active_run",
                "The task has no active run to steer.",
                "active_run_required",
                "Start or resume the task before submitting steering.",
            )
        if not isinstance(content, str) or not content.strip():
            raise _steering_error(
                "steering_content_required",
                "Steering content must be non-empty.",
                "steering_content_required",
                "Type a concrete instruction to steer the run.",
            )
        config = load_config(project_root, task_id)
        if len(content) > config.max_interaction_answer_chars:
            raise _steering_error(
                "steering_content_too_long",
                "The steering content exceeds the configured length limit.",
                "steering_content_length",
                "Shorten the steering instruction to the configured character limit.",
            )
        store = self._store_factory(project_root)
        record: InterventionRecord = store.submit(task_id, run_id, content)
        return SteeringSubmission(
            intervention_id=record.intervention_id,
            sequence=record.sequence,
            revision=record.sequence,
        )


def _steering_error(
    error_code: str, message: str, denied_rule: str, suggested_fix: str
) -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code=error_code,
            message=message,
            phase="unknown",
            denied_rule=denied_rule,
            suggested_fix=suggested_fix,
        )
    )


__all__ = ["InterventionService", "SteeringSubmission"]
