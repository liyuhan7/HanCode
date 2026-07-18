"""Knowledge artifact entry point."""

from pathlib import Path

from hancode.delivery_support import result as _result
from hancode.delivery_support.result import KnowledgeItem


def write_knowledge(task_root: Path, items: list[KnowledgeItem]) -> Path:
    return _result._write_knowledge_impl(task_root, items)

__all__ = ["write_knowledge"]
