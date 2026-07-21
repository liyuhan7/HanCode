"""PhaseBar widget and its pure derivation (S4-T5).

``phase_cells`` derives each phase's display state purely from a TaskSummary. The
bar never advances phases on its own — it only reflects persisted state.
"""

from __future__ import annotations

from textual.widgets import Static

from hancode.app.task_models import TaskSummary
from hancode.core.models import Phase, TaskStatus


_PHASE_ORDER: tuple[Phase, ...] = (
    Phase.SPEC,
    Phase.PLAN,
    Phase.CODE,
    Phase.TEST,
    Phase.REVIEW,
    Phase.DELIVER,
)

_GLYPH = {
    "completed": "✓",  # ✓
    "current": "▶",  # ▶
    "not_started": "·",  # ·
    "blocked": "!",
    "waiting": "?",
    "inconsistent": "×",  # ×
}


def phase_cells(summary: TaskSummary) -> tuple[tuple[str, str], ...]:
    """Return ``(phase_value, cell_state)`` for every phase in order."""
    current_index = _PHASE_ORDER.index(summary.current_phase)
    cells: list[tuple[str, str]] = []
    for index, phase in enumerate(_PHASE_ORDER):
        cells.append((phase.value, _cell_state(summary, index, current_index)))
    return tuple(cells)


def _cell_state(summary: TaskSummary, index: int, current_index: int) -> str:
    if index < current_index:
        return "completed"
    if index > current_index:
        return "not_started"
    # The current phase reflects the task status.
    if summary.status is TaskStatus.INCONSISTENT or summary.inconsistent:
        return "inconsistent"
    if summary.status is TaskStatus.WAITING_INPUT:
        return "waiting"
    if summary.status in {TaskStatus.BLOCKED, TaskStatus.FAILED}:
        return "blocked"
    if summary.status is TaskStatus.COMPLETED:
        return "completed"
    return "current"


def render_phase_bar(summary: TaskSummary | None) -> str:
    if summary is None:
        return " → ".join(
            f"{_GLYPH['not_started']} {phase.value}" for phase in _PHASE_ORDER
        )
    return " → ".join(
        f"{_GLYPH[state]} {phase_value}" for phase_value, state in phase_cells(summary)
    )


class PhaseBar(Static):
    """Renders the six-phase progress line."""

    def update_summary(self, summary: TaskSummary | None) -> None:
        self.update(render_phase_bar(summary))


__all__ = ["PhaseBar", "phase_cells", "render_phase_bar"]
