"""Review artifact entry point."""

from pathlib import Path

from hancode.delivery_support import result as _result
from hancode.delivery_support.result import RequirementCoverage


def write_review(
    task_root: Path,
    coverage: list[RequirementCoverage],
    risks: list[str],
) -> Path:
    return _result._write_review_impl(task_root, coverage, risks)

__all__ = ["write_review"]
