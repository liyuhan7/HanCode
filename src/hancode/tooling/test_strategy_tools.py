"""Tool adapter for recording Agent-authored test strategies."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from hancode.core.config import HanCodeConfig
from hancode.core.errors import HanCodeError
from hancode.core.test_strategy import TestCoverageItem
from hancode.policy.path_policy import PathClassifier, PathZone
from hancode.storage.test_strategies import TestStrategyStore
from hancode.tooling.file_tools import redact_text
from hancode.tooling.registry import ToolResult


def record_test_strategy(
    config: HanCodeConfig,
    *,
    command: str,
    framework: str,
    test_files: Sequence[str],
    coverage: Sequence[Mapping[str, object]],
) -> ToolResult:
    if config.task_root is None:
        return _failed("A task workspace is required.")

    classifier = PathClassifier(config)
    if any(classifier.classify(path) is PathZone.PROTECTED for path in test_files):
        return _failed("Protected test files cannot be registered.")

    try:
        coverage_items = tuple(
            TestCoverageItem(
                requirement=_required_text(item, "requirement"),
                verification=_required_text(item, "verification"),
            )
            for item in coverage
        )
        strategy = TestStrategyStore(config.project_root).record(
            config.task_root.name,
            command=command,
            framework=framework,
            test_files=test_files,
            coverage=coverage_items,
        )
    except (HanCodeError, TypeError, ValueError):
        return _failed("Test strategy is invalid.")

    return ToolResult(
        success=True,
        action_name="record_test_strategy",
        output={
            "test_strategy_digest": strategy.digest,
            "command": redact_text(strategy.command),
            "framework": strategy.framework,
            "test_files": [item.path for item in strategy.test_files],
            "coverage_count": len(strategy.coverage),
        },
        mutation_applied=True,
    )


def _required_text(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-empty")
    return value


def _failed(message: str) -> ToolResult:
    return ToolResult(
        success=False,
        action_name="record_test_strategy",
        error_summary=message,
        mutation_applied=False,
    )
