from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Mapping

import pytest

from hancode.runtime.agent_loop import AgentLoop, InMemoryMutationGuard
from hancode.core.actions import Action
from hancode.storage.checkpoints import CheckpointManifest, RollbackResult
from hancode.core.config import HanCodeConfig, load_config
from hancode.providers.mock import MockLLM
from hancode.core.models import Phase, TaskStatus
from hancode.policy.path_policy import PathClassifier, PathZone
from hancode.core.state import TaskState
from hancode.policy.tool_policy import ToolPolicy
from hancode.tooling.registry import ToolResult
from hancode.storage.trace import TraceEvent
from hancode.storage.workspace import init_project_workspace


@pytest.mark.parametrize(
    "target",
    [
        "assignment",
        "assignment.pdf",
        "requirements.md",
        "requirements",
        "requirements.pdf",
        "requirements.txt",
        "requirements/week-1.md",
        "rubric.md",
        "rubric",
        "rubric.pdf",
        "rubric/criteria.md",
        "course_constraints.md",
        "course_constraints",
        "course_constraints.pdf",
        "course_constraints/runtime.md",
    ],
)
def test_default_protection_covers_course_documents(tmp_path: Path, target: str) -> None:
    classifier = PathClassifier(_default_config(tmp_path))

    assert classifier.classify(target) is PathZone.PROTECTED


@pytest.mark.parametrize(
    "target",
    [
        "course/tests/teacher_solution.py",
        "course/teacher_tests/test_hidden.py",
        "course/grading/check.py",
        "course/samples/input.csv",
        "course/sample_data/fixture.json",
        "course/.env.production",
        "course/credentials/local.json",
        "course/secrets/token.txt",
    ],
)
def test_default_protection_covers_nested_course_and_credential_files(
    tmp_path: Path, target: str
) -> None:
    classifier = PathClassifier(_default_config(tmp_path))

    assert classifier.classify(target) is PathZone.PROTECTED


@pytest.mark.parametrize(
    "target",
    [
        "credentials/local.json",
        "secrets/config.yaml",
        "certificates/client.pem",
        "keys/id_rsa",
        "private.key",
        "server.crt",
        "client.cer",
        "bundle.der",
        "identity.p12",
        "identity.pfx",
        "access.token",
        "id_rsa",
    ],
)
def test_default_protection_matches_file_tool_credential_paths(
    tmp_path: Path, target: str
) -> None:
    classifier = PathClassifier(_default_config(tmp_path))

    assert classifier.classify(target) is PathZone.PROTECTED


def test_default_protection_normalizes_case_and_backslashes(tmp_path: Path) -> None:
    classifier = PathClassifier(_default_config(tmp_path))

    assert classifier.classify("COURSE\\RUBRIC\\CRITERIA.MD") is PathZone.PROTECTED


def test_protected_course_document_overrides_writable_root(tmp_path: Path) -> None:
    config = replace(_default_config(tmp_path), writable_roots=(tmp_path.resolve(),))
    classifier = PathClassifier(config)

    assert classifier.classify("course/requirements.pdf") is PathZone.PROTECTED


@pytest.mark.parametrize(
    "target", ["requirements-lock.txt", "course/requirements-lock.pdf"]
)
def test_course_document_protection_does_not_match_prefixes(
    tmp_path: Path, target: str
) -> None:
    config = replace(_default_config(tmp_path), writable_roots=(tmp_path.resolve(),))
    classifier = PathClassifier(config)

    assert classifier.classify(target) is PathZone.SOURCE


@pytest.mark.parametrize(
    ("tool_name", "args"),
    [
        ("write_file", {"path": "requirements.md", "content": ""}),
        (
            "edit_file",
            {
                "path": "course/rubric.md",
                "old_string": "criterion",
                "new_string": "changed criterion",
            },
        ),
    ],
)
def test_protected_write_is_denied_before_registry_dispatch(
    tmp_path: Path, tool_name: str, args: dict[str, str]
) -> None:
    config = replace(_default_config(tmp_path), writable_roots=(tmp_path.resolve(),))
    registry = SpyToolRegistry()
    loop = AgentLoop(
        llm=MockLLM(
            [
                {
                    "type": "tool_call",
                    "phase": "code",
                    "tool_name": tool_name,
                    "args": args,
                    "reason": "Update course file.",
                }
            ]
        ),
        context_builder=StubContextBuilder(),
        policy=RealToolPolicyAdapter(ToolPolicy(config)),
        tool_registry=registry,
        feedback_builder=StubFeedbackBuilder(),
        state_store=StubStateStore(_code_state()),
        trace_appender=StubTraceAppender(),
        checkpoint_manager=StubCheckpointManager(),
        rollback_manager=StubRollbackManager(),
        max_steps=1,
        mutation_guard=InMemoryMutationGuard(),
    )

    result = loop.run("task-001")

    assert result.status is TaskStatus.BLOCKED
    assert result.error is not None
    assert result.error.to_dict() == {
        "error_code": "policy_denied",
        "message": "Target path is a protected course or credential file.",
        "phase": "code",
        "denied_rule": "protected_path",
        "suggested_fix": "Modify allowed source code instead; do not change course evaluation or credential files.",
    }
    assert registry.actions == []


class StubStateStore:
    def __init__(self, state: TaskState) -> None:
        self._state = state

    def load(self, task_id: str) -> TaskState:
        assert task_id == "task-001"
        return self._state

    def save(self, task_id: str, state: TaskState) -> None:
        assert task_id == state.task_id == "task-001"
        self._state = state


class StubTraceAppender:
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
        raise AssertionError("Read-only protection flow must not append trace events.")


class StubCheckpointManager:
    def create(
        self, task_id: str, files: list[Path], reason: str
    ) -> CheckpointManifest:
        raise AssertionError("Read-only protection flow must not create checkpoints.")

    def commit(self, task_id: str, checkpoint_id: str) -> CheckpointManifest:
        raise AssertionError("Read-only protection flow must not commit checkpoints.")


class StubRollbackManager:
    def rollback_last(self, task_id: str) -> RollbackResult:
        raise AssertionError("Read-only protection flow must not roll back checkpoints.")


@dataclass
class PolicyDecisionView:
    allowed: bool
    reason: str
    requires_checkpoint: bool
    denied_rule: str | None
    suggested_fix: str


class RealToolPolicyAdapter:
    """Expose a real ToolPolicy through AgentLoop's mutable decision protocol."""

    def __init__(self, policy: ToolPolicy) -> None:
        self._policy = policy

    def evaluate(
        self, *, action: Action, phase: Phase, state: TaskState
    ) -> PolicyDecisionView:
        decision = self._policy.evaluate(action=action, phase=phase, state=state)
        return PolicyDecisionView(
            allowed=decision.allowed,
            reason=decision.reason,
            requires_checkpoint=decision.requires_checkpoint,
            denied_rule=decision.denied_rule,
            suggested_fix=decision.suggested_fix,
        )


class StubContextBuilder:
    def build(
        self, *, task_id: str, phase: Phase, state: TaskState
    ) -> dict[str, object]:
        return {"task_id": task_id, "phase": phase.value}


class SpyToolRegistry:
    def __init__(self) -> None:
        self.actions: list[object] = []

    def dispatch(self, action: object) -> ToolResult:
        self.actions.append(action)
        return ToolResult(success=True, action_name="unexpected")


class StubFeedbackBuilder:
    def from_parse_error(self, error: object) -> object:
        return {"kind": "parse_error"}

    def from_policy_denial(self, decision: object) -> object:
        return {"kind": "policy_denial"}

    def from_tool_result(self, result: object, *, phase: Phase) -> object:
        return {"kind": "tool_result"}

    def from_checkpoint_manifest(self, manifest: CheckpointManifest) -> object:
        return {"kind": "checkpoint"}

    def from_rollback_result(self, result: RollbackResult, *, phase: Phase) -> object:
        return {"kind": "rollback"}


def _default_config(project_root: Path) -> HanCodeConfig:
    init_project_workspace(
        project_root,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Coding Agent Harness",
    )
    return load_config(project_root)


def _code_state() -> TaskState:
    return TaskState(
        schema_version=1,
        task_id="task-001",
        goal="Protect course files.",
        status=TaskStatus.CREATED,
        current_phase=Phase.CODE,
        files_changed=(),
        latest_checkpoint=None,
        checkpoint_seq=0,
        tests_run=(),
        latest_test_status="none",
        test_status_consumed=False,
        retry_budget_remaining=2,
        inconsistent=False,
        source_edits_this_phase=0,
        rollback_required=False,
        rollback_done=False,
        phase_completed={phase.value: phase is not Phase.CODE for phase in Phase},
        artifacts={
            "SPEC.md": True,
            "PLAN.md": True,
            "TEST_REPORT.md": False,
            "REVIEW.md": False,
            "KNOWLEDGE.md": False,
            "DELIVERABLES.md": False,
        },
    )
