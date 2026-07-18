"""Final deliverables artifact entry point."""

from pathlib import Path
from typing import Sequence

from hancode.delivery_support import result as _result
from hancode.delivery_support.result import RequirementCoverage
from hancode.runtime.agent_loop import AgentRunResult


def write_deliverables(
    task_root: Path,
    result: AgentRunResult,
    coverage: Sequence[RequirementCoverage] = (),
) -> Path:
    return _result._write_deliverables_impl(task_root, result, coverage)

__all__ = ["write_deliverables"]
