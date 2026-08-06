"""LearningEvidenceCollector — Collect step of the S14 delivery pipeline.

Collects only facts from validated learning evidence, the derived traceability
matrix, and authoritative task state. It performs no writes and does not mutate
state. Legacy delivery evidence remains available through the existing store.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from hancode.app.learning_service import LearningService
from hancode.core.learning_evidence import LearningSnapshot
from hancode.core.state import TaskState, load_state, reconcile_state
from hancode.runtime.traceability_builder import TraceabilityMatrix, build_traceability
from hancode.storage.workspace import task_path


@dataclass(frozen=True, slots=True)
class CollectedDelivery:
    task_id: str
    state: TaskState
    snapshot: LearningSnapshot
    matrix: TraceabilityMatrix
    build_required: bool
    latest_build_status: str


def collect_learning_delivery(
    project_root: Path,
    task_id: str,
    *,
    service: LearningService | None = None,
) -> CollectedDelivery:
    learning_service = service or LearningService()
    task_root = task_path(project_root, task_id)
    state = reconcile_state(task_root, load_state(task_root))
    snapshot = learning_service.load_snapshot(project_root, task_id)
    matrix = build_traceability(snapshot)

    build_required = False
    latest_build_status = state.latest_build_status
    try:
        from hancode.core.config import load_config

        config = load_config(project_root, task_id)
        build_required = config.build_command is not None
    except Exception:  # noqa: BLE001 - config is optional for pure collection
        build_required = False

    return CollectedDelivery(
        task_id=task_id,
        state=state,
        snapshot=snapshot,
        matrix=matrix,
        build_required=build_required,
        latest_build_status=latest_build_status,
    )


__all__ = ["CollectedDelivery", "collect_learning_delivery"]
