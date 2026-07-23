"""Offline deterministic demonstration of HanCode's guarded feedback loop."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Mapping, Sequence

from hancode.runtime.agent_loop import AgentRunResult, FilesystemAgentLoopPorts
from hancode.runtime.engine import create_agent_loop
from hancode.app.delivery_service import DeliveryService
from hancode.core.config import HanCodeConfig, load_config
from hancode.core.delivery_evidence import DeliveryResult
from hancode.core.errors import HanCodeError, StructuredError
from hancode.providers.mock import MockLLM
from hancode.core.models import Phase, TaskStatus
from hancode.tooling.test_tools import run_tests
from hancode.tooling.factory import build_default_tool_registry
from hancode.core.state import load_state, save_state
from hancode.tooling.registry import ToolRegistry, ToolResult
from hancode.storage.trace import TraceEvent, append_trace
from hancode.storage.workspace import init_project_workspace, init_task_workspace
from hancode.demo_support import actions as _demo_actions
from hancode.demo_support.actions import (
    build_finish_actions,
    build_first_actions,
    build_delivery_actions,
    build_recovery_actions,
    build_retry_actions,
)
from hancode.demo_support.fixture import (
    DEMO_FIXTURE_DIGESTS,
    PACKAGED_FIXTURE_ROOT,
    copy_packaged_fixture,
    configure_demo,
    fixture_error,
    fixture_digest,
    is_link,
    validate_fixture,
)


TASK_ID = "task-001"
_DEMO_TEST_COMMAND = "python -m unittest discover -s tests -q"
_TEST_TIMEOUT_SECONDS = 2

_FIXTURE_DIGESTS = DEMO_FIXTURE_DIGESTS
_PACKAGED_FIXTURE_ROOT = PACKAGED_FIXTURE_ROOT
_artifact_path = _demo_actions._artifact_path
_finish = _demo_actions._finish
_run_tests = _demo_actions._run_tests
_source = _demo_actions._source
_write = _demo_actions._write
_write_artifact = _demo_actions._write_artifact
_first_actions = build_first_actions
_retry_actions = build_retry_actions
_recovery_actions = build_recovery_actions
_finish_actions = build_finish_actions
_delivery_actions = build_delivery_actions
_validate_fixture = validate_fixture
_fixture_digest = fixture_digest
_configure_demo = configure_demo
_is_link = is_link
_copy_packaged_fixture = copy_packaged_fixture


class _DemoTraceAppender:
    """Persist real trace events while preserving one AgentLoop run's local sequence."""

    def __init__(self, delegate: object) -> None:
        self._delegate = delegate
        self._logical_seq = 0

    def append(
        self,
        task_id: str,
        *,
        event_type: str,
        phase: Phase,
        status: str,
        action: Mapping[str, object] | None = None,
        observation: Mapping[str, object] | None = None,
        error_summary: str | None = None,
        state_transition: Mapping[str, object] | None = None,
    ) -> TraceEvent:
        append = getattr(self._delegate, "append")
        persisted = append(
            task_id,
            event_type=event_type,
            phase=phase,
            status=status,
            action=action,
            observation=observation,
            error_summary=error_summary,
            state_transition=state_transition,
        )
        if not isinstance(persisted, TraceEvent):
            raise _demo_error(
                "mock_demo_trace_adapter_invalid",
                "Filesystem trace adapter returned an invalid event.",
            )
        self._logical_seq += 1
        return replace(
            persisted,
            event_id=f"evt-{self._logical_seq:06d}",
            seq=self._logical_seq,
        )


class _DemoTestRunner:
    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root
        self.results: list[ToolResult] = []

    def run_tests(self, command: str | None) -> ToolResult:
        result = run_tests(
            self._project_root,
            command or _DEMO_TEST_COMMAND,
            timeout_seconds=_TEST_TIMEOUT_SECONDS,
        )
        self.results.append(result)
        return result


def run_mock_demo(project_root: Path) -> AgentRunResult:
    """Run the complete offline demo in a prepared copy of broken_project."""
    root = validate_fixture(project_root)
    init_project_workspace(root, "mock-demo", "HanCode", "Guarded feedback loop")
    configure_demo(root)
    task_root = init_task_workspace(root, TASK_ID)
    initial_state = replace(load_state(task_root), goal="Implement integer addition safely.")
    save_state(task_root, initial_state)

    config = load_config(root, TASK_ID)
    ports = FilesystemAgentLoopPorts.from_project_root(root)
    test_runner = _DemoTestRunner(root)
    registry = _tool_registry(config, test_runner)
    timeline: list[TraceEvent] = []
    runs: list[AgentRunResult] = []
    timeline.append(_append(task_root, "task_started", Phase.SPEC, "running"))

    try:
        first = _run_stage(
            root,
            config,
            ports,
            registry,
            build_first_actions(),
            resume=False,
        )
        runs.append(first)
        timeline.extend(first.trace_events)

        second = _run_stage(
            root,
            config,
            ports,
            registry,
            build_retry_actions(),
            resume=True,
        )
        runs.append(second)
        timeline.extend(second.trace_events)

        third = _run_stage(
            root,
            config,
            ports,
            registry,
            build_recovery_actions(),
            resume=True,
        )
        runs.append(third)
        timeline.extend(third.trace_events)

        fourth = _run_stage(
            root,
            config,
            ports,
            registry,
            build_finish_actions(),
            resume=True,
        )
        runs.append(fourth)
        timeline.extend(fourth.trace_events)

        fifth = _run_stage(
            root,
            config,
            ports,
            registry,
            build_delivery_actions(),
            resume=True,
        )
        runs.append(fifth)
        timeline.extend(fifth.trace_events)
        return _aggregate_result(task_root, fifth, runs)
    except HanCodeError as exc:
        return _failed_demo_result(task_root, runs, timeline, exc.structured_error)
    except Exception:
        error = StructuredError(
            error_code="mock_demo_internal_error",
            message="Mock demo stopped because an internal step failed.",
            phase=load_state(task_root).current_phase.value,
            denied_rule="mock_demo_completion_required",
            suggested_fix="Inspect the retained trace and repair the failed demo adapter.",
        )
        return _failed_demo_result(task_root, runs, timeline, error)


def _run_stage(
    project_root: Path,
    config: HanCodeConfig,
    ports: FilesystemAgentLoopPorts,
    registry: ToolRegistry,
    actions: Sequence[dict[str, object]],
    *,
    resume: bool,
) -> AgentRunResult:
    loop = create_agent_loop(
        project_root,
        TASK_ID,
        provider=MockLLM(list(actions)),
        tool_registry=registry,
        trace_appender=_DemoTraceAppender(ports.trace_appender),
        max_steps=max(1, len(actions)),
    )
    return loop.run(TASK_ID, resume=resume)


def _tool_registry(config: HanCodeConfig, test_runner: _DemoTestRunner) -> ToolRegistry:
    return build_default_tool_registry(
        config,
        run_tests_tool=test_runner.run_tests,
    )


def _append(
    task_root: Path,
    event_type: str,
    phase: Phase,
    status: str,
    *,
    observation: dict[str, object] | None = None,
) -> TraceEvent:
    return append_trace(
        task_root,
        event_type=event_type,
        task_id=TASK_ID,
        phase=phase,
        status=status,
        observation=observation,
    )


def _aggregate_result(
    task_root: Path,
    terminal: AgentRunResult,
    runs: Sequence[AgentRunResult],
) -> AgentRunResult:
    return replace(
        terminal,
        steps=sum(run.steps for run in runs),
        tool_calls=tuple(tool for run in runs for tool in run.tool_calls),
        risks=tuple(risk for run in runs for risk in run.risks),
        trace_events=_read_trace_events(task_root),
    )


def _is_expected_delivery_gate(state: object, stage: AgentRunResult) -> bool:
    if not isinstance(state, type(stage.final_state)):
        return False
    if (
        state.status is not TaskStatus.BLOCKED
        or state.current_phase is not Phase.REVIEW
        or state.inconsistent
        or state.rollback_required
        or state.latest_test_status != "passed"
        or not state.rollback_done
        or not all(state.phase_completed[phase] for phase in ("code", "test", "review"))
        or not all(state.artifacts[artifact] for artifact in ("SPEC.md", "PLAN.md", "TEST_REPORT.md", "REVIEW.md"))
        or state.artifacts["KNOWLEDGE.md"]
        or state.artifacts["DELIVERABLES.md"]
    ):
        return False
    return (
        stage.status is TaskStatus.BLOCKED
        and stage.final_state == state
        and stage.error is not None
        and stage.error.error_code == "max_steps_exceeded"
        and stage.error.phase == Phase.REVIEW.value
        and stage.error.denied_rule == "max_steps_limit"
    )


def _read_trace_events(task_root: Path) -> tuple[TraceEvent, ...]:
    events: list[TraceEvent] = []
    for line in (task_root / "trace.jsonl").read_text(encoding="utf-8").splitlines():
        data = json.loads(line)
        events.append(
            TraceEvent(
                event_id=str(data["event_id"]),
                seq=int(data["seq"]),
                event_type=str(data["event_type"]),
                task_id=str(data["task_id"]),
                phase=Phase(str(data["phase"])),
                timestamp=datetime.fromisoformat(str(data["timestamp"])),
                status=str(data["status"]),
                action=data["action"],
                observation=data["observation"],
                error_summary=data["error_summary"],
                state_transition=data["state_transition"],
            )
        )
    return tuple(events)


def _failed_demo_result(
    task_root: Path,
    runs: Sequence[AgentRunResult],
    timeline: list[TraceEvent],
    error: StructuredError,
) -> AgentRunResult:
    state = load_state(task_root)
    blocked_state = replace(state, status=TaskStatus.BLOCKED)
    save_state(task_root, blocked_state)
    try:
        timeline.append(_append(task_root, "task_blocked", blocked_state.current_phase, "failed"))
    except HanCodeError:
        pass
    try:
        trace_events = _read_trace_events(task_root)
    except (OSError, TypeError, ValueError, KeyError):
        trace_events = ()
        error = _runtime_error(
            "mock_demo_trace_read_failed",
            "Mock demo failed and its persisted trace could not be read.",
            blocked_state.current_phase,
            "persisted_trace_required",
            "Repair trace storage before retrying the demo.",
        ).structured_error
    return AgentRunResult(
        status=TaskStatus.BLOCKED,
        steps=sum(run.steps for run in runs),
        tool_calls=tuple(tool for run in runs for tool in run.tool_calls),
        risks=tuple(risk for run in runs for risk in run.risks),
        final_observation=None,
        error=error,
        final_state=blocked_state,
        retry_budget_remaining=blocked_state.retry_budget_remaining,
        trace_events=trace_events,
    )


def _demo_error(error_code: str, message: str) -> HanCodeError:
    return fixture_error(error_code, message)


def _runtime_error(
    error_code: str,
    message: str,
    phase: Phase,
    denied_rule: str,
    suggested_fix: str,
) -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code=error_code,
            message=message,
            phase=phase.value,
            denied_rule=denied_rule,
            suggested_fix=suggested_fix,
        )
    )


def run_packaged_mock_demo() -> DeliveryResult:
    """Run the offline demo using the fixture bundled with the package."""
    with TemporaryDirectory(prefix="hancode-mock-demo-") as temporary_directory:
        project_root = Path(temporary_directory) / "broken_project"
        copy_packaged_fixture(project_root)
        run_mock_demo(project_root)
        return DeliveryService().get_result(project_root, TASK_ID)


def main() -> int:
    result = run_packaged_mock_demo()
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0 if result.status is TaskStatus.COMPLETED else 1


if __name__ == "__main__":
    raise SystemExit(main())
