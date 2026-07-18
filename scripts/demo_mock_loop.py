"""Offline deterministic demonstration of HanCode's guarded feedback loop."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import Mapping, Sequence, cast

from hancode.agent_loop import (
    AgentLoop,
    AgentRunResult,
    FeedbackBuilder as FeedbackBuilderPort,
    FilesystemAgentLoopPorts,
    Policy,
)
from hancode.config import HanCodeConfig, load_config
from hancode.context import ContextBuilder
from hancode.delivery import (
    KnowledgeCategory,
    KnowledgeItem,
    RequirementCoverage,
    RequirementStatus,
    ResultBuilder,
    write_deliverables,
    write_knowledge,
    write_review,
    write_test_report,
)
from hancode.errors import HanCodeError, StructuredError
from hancode.feedback import FeedbackBuilder as RealFeedbackBuilder
from hancode.feedback import FeedbackReport, classify_test_output
from hancode.file_tools import write_file
from hancode.llm import MockLLM
from hancode.models import Phase, TaskStatus
from hancode.state import load_state, save_state
from hancode.tool_policy import ToolPolicy
from hancode.tools import ToolRegistry, ToolResult
from hancode.trace import TraceEvent, append_trace
from hancode.workspace import init_project_workspace, init_task_workspace


TASK_ID = "task-001"
_DEMO_TEST_COMMAND = "python -m unittest discover -s tests -q"
_TEST_TIMEOUT_SECONDS = 2
_FIXTURE_DIGESTS = {
    "assignment.md": "09f143742cbba87a8c1f44d935e472854d71cef829eb8efaf84d02bf62cb5312",
    "src/calculator.py": "8a35e58ba3afe3085a142727a379eeb4f77e0e4b889fb0e1213b12bcda55587c",
    "tests/test_calculator.py": "905d45b05d9363b1f326b53aea0ff88c70c05db7e4db06b86fb58135c1d829ce",
}


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

    def run_tests(self) -> ToolResult:
        try:
            completed = subprocess.run(
                [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"],
                cwd=self._project_root,
                shell=False,
                capture_output=True,
                text=True,
                timeout=_TEST_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            result = ToolResult(
                success=False,
                action_name="run_tests",
                error_summary="Demo test command timed out.",
                stdout=_output_text(exc.stdout),
                stderr=_output_text(exc.stderr),
                timed_out=True,
            )
        else:
            result = ToolResult(
                success=completed.returncode == 0,
                action_name="run_tests",
                error_summary=(
                    None if completed.returncode == 0 else "Demo test command failed."
                ),
                exit_code=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
            )
        self.results.append(result)
        return result


def run_mock_demo(project_root: Path) -> AgentRunResult:
    """Run the complete offline demo in a prepared copy of broken_project."""
    root = _validate_fixture(project_root)
    init_project_workspace(root, "mock-demo", "HanCode", "Guarded feedback loop")
    _configure_demo(root)
    task_root = init_task_workspace(root, TASK_ID)
    initial_state = replace(load_state(task_root), goal="Implement integer addition safely.")
    save_state(task_root, initial_state)

    config = load_config(root, TASK_ID)
    ports = FilesystemAgentLoopPorts.from_project_root(root)
    registry = _tool_registry(root)
    test_runner = _DemoTestRunner(root)
    registry.register("run_tests", test_runner.run_tests)
    timeline: list[TraceEvent] = []
    runs: list[AgentRunResult] = []
    timeline.append(_append(task_root, "task_started", Phase.SPEC, "running"))

    try:
        first = _run_stage(
            root,
            config,
            ports,
            registry,
            _first_actions(),
            resume=False,
        )
        runs.append(first)
        timeline.extend(first.trace_events)
        first_report = _record_test_evidence(task_root, test_runner.results[-1], timeline)
        _write_failure_evidence(task_root, first_report, timeline)

        second = _run_stage(
            root,
            config,
            ports,
            registry,
            _retry_actions(),
            resume=True,
        )
        runs.append(second)
        timeline.extend(second.trace_events)
        _record_test_evidence(task_root, test_runner.results[-1], timeline)

        third = _run_stage(
            root,
            config,
            ports,
            registry,
            _recovery_actions(),
            resume=True,
        )
        runs.append(third)
        timeline.extend(third.trace_events)
        recovery_report = _record_test_evidence(
            task_root, test_runner.results[-1], timeline
        )
        _write_success_evidence(task_root, recovery_report, timeline)

        fourth = _run_stage(
            root,
            config,
            ports,
            registry,
            _finish_actions(),
            resume=True,
        )
        runs.append(fourth)
        timeline.extend(fourth.trace_events)

        _enter_expected_delivery_phase(task_root, fourth, timeline)
        knowledge_items = _knowledge_items(task_root)
        write_knowledge(task_root, list(knowledge_items))
        timeline.append(
            _append(
                task_root,
                "deliverable_created",
                Phase.DELIVER,
                "succeeded",
                observation={"artifact": "KNOWLEDGE.md"},
            )
        )
        write_deliverables(task_root, fourth, _covered_requirement())
        timeline.append(
            _append(
                task_root,
                "deliverable_created",
                Phase.DELIVER,
                "succeeded",
                observation={"artifact": "DELIVERABLES.md"},
            )
        )

        terminal = _run_stage(
            root,
            config,
            ports,
            registry,
            (),
            resume=False,
        )
        runs.append(terminal)
        timeline.extend(terminal.trace_events)
        return _aggregate_result(task_root, terminal, runs)
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
    loop = AgentLoop(
        llm=MockLLM(list(actions)),
        context_builder=ContextBuilder(project_root, config),
        policy=cast(Policy, ToolPolicy(config)),
        tool_registry=registry,
        feedback_builder=cast(
            FeedbackBuilderPort, RealFeedbackBuilder(config.max_observation_bytes)
        ),
        state_store=ports.state_store,
        trace_appender=_DemoTraceAppender(ports.trace_appender),
        checkpoint_manager=ports.checkpoint_manager,
        rollback_manager=ports.rollback_manager,
        mutation_guard=ports.mutation_guard,
        max_steps=max(1, len(actions)),
    )
    return loop.run(TASK_ID, resume=resume)


def _tool_registry(project_root: Path) -> ToolRegistry:
    registry = ToolRegistry()

    def demo_write_file(*, path: str, content: str) -> ToolResult:
        return write_file(project_root, path, content)

    registry.register("write_file", demo_write_file)
    return registry


def _first_actions() -> tuple[dict[str, object], ...]:
    return (
        _write_artifact(Phase.SPEC, "SPEC.md", "# SPEC\n\n实现整数加法。\n"),
        _write_artifact(Phase.PLAN, "PLAN.md", "# PLAN\n\n先写测试，再实现加法。\n"),
        _write(Phase.CODE, "assignment.md", "篡改课程要求\n"),
        _write(Phase.CODE, "src/calculator.py", _source("return left - right")),
        _finish(Phase.CODE),
        _run_tests(),
    )


def _retry_actions() -> tuple[dict[str, object], ...]:
    return (
        _finish(Phase.REVIEW),
        _write(Phase.CODE, "src/calculator.py", _source("return 0")),
        _finish(Phase.CODE),
        _run_tests(),
    )


def _recovery_actions() -> tuple[dict[str, object], ...]:
    return (
        _write(Phase.CODE, "src/calculator.py", _source("return left + right")),
        _finish(Phase.CODE),
        _run_tests(),
    )


def _finish_actions() -> tuple[dict[str, object], ...]:
    return (_finish(Phase.TEST), _finish(Phase.REVIEW))


def _write_artifact(phase: Phase, artifact: str, content: str) -> dict[str, object]:
    return _write(phase, _artifact_path(artifact), content)


def _write(phase: Phase, path: str, content: str) -> dict[str, object]:
    return {
        "type": "tool_call",
        "phase": phase.value,
        "tool_name": "write_file",
        "args": {"path": path, "content": content},
        "reason": "Execute the deterministic mock demo step.",
    }


def _finish(phase: Phase) -> dict[str, object]:
    return {
        "type": "finish_phase",
        "phase": phase.value,
        "tool_name": None,
        "args": {},
        "reason": None,
    }


def _run_tests() -> dict[str, object]:
    return {
        "type": "tool_call",
        "phase": Phase.TEST.value,
        "tool_name": "run_tests",
        "args": {},
        "reason": None,
    }


def _source(statement: str) -> str:
    return f"def add(left: int, right: int) -> int:\n    {statement}\n"


def _artifact_path(artifact: str) -> str:
    return f".hancode/tasks/{TASK_ID}/{artifact}"


def _record_test_evidence(
    task_root: Path, result: ToolResult, timeline: list[TraceEvent]
) -> FeedbackReport:
    report = classify_test_output(
        _test_output(result),
        result.exit_code if result.exit_code is not None else (0 if result.success else 1),
        result.timed_out,
    )
    timeline.append(
        _append(
            task_root,
            "test_completed",
            Phase.TEST,
            "succeeded" if result.success else "failed",
            observation={
                "exit_code": result.exit_code,
                "timed_out": result.timed_out,
                "output_sha256": hashlib.sha256(_test_output(result).encode("utf-8")).hexdigest(),
            },
        )
    )
    timeline.append(
        _append(
            task_root,
            "feedback_generated",
            Phase.TEST,
            "succeeded",
            observation={"failure_category": report.failure_category.value},
        )
    )
    return report


def _write_failure_evidence(
    task_root: Path, report: FeedbackReport, timeline: list[TraceEvent]
) -> None:
    write_test_report(task_root, report, _DEMO_TEST_COMMAND)
    timeline.append(_append(task_root, "deliverable_created", Phase.TEST, "succeeded"))
    write_review(
        task_root,
        [
            RequirementCoverage(
                requirement_id="REQ-ADD-001",
                status=RequirementStatus.PARTIAL,
                evidence="测试失败记录已生成。",
                risk="当前实现未通过加法测试。",
                is_core=True,
            )
        ],
        ["测试失败后进入重试与回退流程。"],
    )
    timeline.append(_append(task_root, "deliverable_created", Phase.REVIEW, "succeeded"))


def _write_success_evidence(
    task_root: Path, report: FeedbackReport, timeline: list[TraceEvent]
) -> None:
    write_test_report(task_root, report, _DEMO_TEST_COMMAND)
    timeline.append(_append(task_root, "deliverable_created", Phase.TEST, "succeeded"))
    write_review(task_root, list(_covered_requirement()), [])
    timeline.append(_append(task_root, "deliverable_created", Phase.REVIEW, "succeeded"))


def _covered_requirement() -> tuple[RequirementCoverage, ...]:
    return (
        RequirementCoverage(
            requirement_id="REQ-ADD-001",
            status=RequirementStatus.COVERED,
            evidence="tests/test_calculator.py::CalculatorTests.test_add_returns_the_sum_of_two_integers",
            risk=None,
            is_core=True,
        ),
    )


def _knowledge_items(task_root: Path) -> tuple[KnowledgeItem, ...]:
    return (
        KnowledgeItem(
            KnowledgeCategory.REQUIREMENT_UNDERSTANDING,
            "课程要求不可修改",
            "assignment.md 受保护，策略拒绝了写入请求。",
            Phase.CODE,
            _event_id(task_root, "policy_denied"),
        ),
        KnowledgeItem(
            KnowledgeCategory.DESIGN_DECISION,
            "业务写入必须先 checkpoint",
            "每次 source write 在执行前创建可恢复快照。",
            Phase.CODE,
            _event_id(task_root, "checkpoint_created"),
        ),
        KnowledgeItem(
            KnowledgeCategory.TESTING_EXPERIENCE,
            "失败测试应被分类后回灌",
            "真实 unittest 失败被分类为 assertion_failure。",
            Phase.TEST,
            _event_id(task_root, "feedback_generated"),
        ),
        KnowledgeItem(
            KnowledgeCategory.ERROR_FIX,
            "耗尽重试预算后回退",
            "第二次失败后恢复最新 checkpoint，再进行最小正确修复。",
            Phase.REVIEW,
            _event_id(task_root, "rollback_performed"),
        ),
        KnowledgeItem(
            KnowledgeCategory.REUSABLE_PATTERN,
            "受限离线测试器",
            "Demo 以固定 argv 和 shell=False 运行本地 unittest。",
            Phase.TEST,
            _event_id(task_root, "retry_budget_consumed"),
        ),
    )


def _event_id(task_root: Path, event_type: str) -> str:
    for line in (task_root / "trace.jsonl").read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event["event_type"] == event_type:
            return str(event["event_id"])
    raise _demo_error("mock_demo_trace_evidence_missing", "Required demo trace event is missing.")


def _test_output(result: ToolResult) -> str:
    return "\n".join(
        value
        for value in (result.error_summary, result.stdout, result.stderr)
        if isinstance(value, str) and value
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


def _enter_expected_delivery_phase(
    task_root: Path, stage: AgentRunResult, timeline: list[TraceEvent]
) -> None:
    state = load_state(task_root)
    if not _is_expected_delivery_gate(state, stage):
        raise _runtime_error(
            "mock_demo_delivery_gate_invalid",
            "Demo delivery orchestration may only continue from its expected missing-artifact gate.",
            state.current_phase,
            "expected_delivery_gate_required",
            "Inspect the retained state and trace before attempting delivery.",
        )
    save_state(task_root, replace(state, status=TaskStatus.RUNNING, current_phase=Phase.DELIVER))
    timeline.append(
        _append(
            task_root,
            "delivery_orchestration_started",
            Phase.DELIVER,
            "running",
            observation={"blocked_error_code": "max_steps_exceeded"},
        )
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


def _validate_fixture(project_root: Path) -> Path:
    if not isinstance(project_root, Path) or _is_link(project_root) or not project_root.is_dir():
        raise _demo_error(
            "mock_demo_fixture_required",
            "Mock demo requires a clean copy of examples/broken_project.",
        )
    root = project_root.resolve()
    entries = tuple(root.rglob("*"))
    files = {
        entry.relative_to(root).as_posix()
        for entry in entries
        if entry.is_file()
        and not _is_link(entry)
        and "__pycache__" not in entry.relative_to(root).parts
    }
    if (
        (root / ".hancode").exists()
        or any(_is_link(entry) for entry in entries)
        or files != set(_FIXTURE_DIGESTS)
        or any(
            _fixture_digest(root / relative_path) != digest
            for relative_path, digest in _FIXTURE_DIGESTS.items()
        )
    ):
        raise _demo_error(
            "mock_demo_fixture_required",
            "Mock demo requires a clean copy of examples/broken_project.",
        )
    return root


def _fixture_digest(path: Path) -> str:
    """Hash fixture text canonically so Git newline conversion is not semantic drift."""
    normalized = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(normalized).hexdigest()


def _configure_demo(project_root: Path) -> None:
    project_file = project_root / ".hancode" / "project.json"
    data = json.loads(project_file.read_text(encoding="utf-8"))
    data.update(
        {
            "llm_provider": "mock",
            "test_command": _DEMO_TEST_COMMAND,
            "retry_budget": 1,
            "max_trace_events": 128,
            "protected_patterns": ["assignment.md"],
            "writable_roots": ["src"],
        }
    )
    project_file.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _demo_error(error_code: str, message: str) -> HanCodeError:
    return _runtime_error(
        error_code,
        message,
        Phase.SPEC,
        "mock_demo_fixture_required",
        "Copy examples/broken_project into an empty temporary directory.",
    )


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


def _is_link(path: Path) -> bool:
    try:
        junction_probe = getattr(path, "is_junction", None)
        return path.is_symlink() or (bool(junction_probe()) if callable(junction_probe) else False)
    except (AttributeError, OSError, RuntimeError):
        return True


def _output_text(value: str | bytes | None) -> str | None:
    if value is None or isinstance(value, str):
        return value
    return value.decode("utf-8", errors="replace")


def main() -> int:
    fixture_root = Path(__file__).resolve().parents[1] / "examples" / "broken_project"
    with TemporaryDirectory(prefix="hancode-mock-demo-") as temporary_directory:
        project_root = Path(temporary_directory) / "broken_project"
        shutil.copytree(
            fixture_root,
            project_root,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        result = run_mock_demo(project_root)
        task_root = project_root / ".hancode" / "tasks" / TASK_ID
        payload = ResultBuilder().build(
            task_root,
            result,
            _covered_requirement(),
            _knowledge_items(task_root),
        ).to_dict()
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if result.status is TaskStatus.COMPLETED else 1


if __name__ == "__main__":
    raise SystemExit(main())
