"""Test report artifact entry point."""

from pathlib import Path

from hancode.delivery_support import result as _result
from hancode.runtime.feedback import FeedbackReport


def write_test_report(task_root: Path, report: FeedbackReport, command: str) -> Path:
    return _result._write_test_report_impl(task_root, report, command)

__all__ = ["write_test_report"]
