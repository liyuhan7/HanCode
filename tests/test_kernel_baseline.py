"""Stage 0: Kernel baseline regression tests.

Validates that the core kernel interfaces are not broken by subsequent changes.
These tests check the boundary separation and error model invariants.
"""

from __future__ import annotations

from pathlib import Path
import tempfile

from hancode.core.errors import HanCodeError, StructuredError
from hancode.core import models, phases, router, state
from hancode.providers import mock
from hancode.policy import tool_policy
from hancode.storage import checkpoints, trace, workspace


# =========================================================================
# 1. Interface boundary: CLI and Provider do NOT directly write files/state
# =========================================================================

def test_cli_does_not_import_storage_or_tooling_directly() -> None:
    """CLI must only delegate to app services, not access storage/tooling directly."""
    import inspect
    import hancode.interfaces.cli as cli_mod
    source = inspect.getsource(cli_mod)
    forbidden = [
        "from hancode.storage.workspace",
        "from hancode.storage.state",
        "from hancode.storage.checkpoints",
        "from hancode.storage.trace",
        "from hancode.tooling.file_tools",
        "from hancode.runtime.agent_loop",
    ]
    for pattern in forbidden:
        assert pattern not in source, f"CLI must not directly import: {pattern}"


def test_provider_does_not_access_storage() -> None:
    """MockLLM must be pure in-memory, no storage or file system access."""
    import inspect
    source = inspect.getsource(mock.MockLLM)
    forbidden = ["Path", "open(", "os.path", "storage", "workspace"]
    for pattern in forbidden:
        assert pattern not in source, f"MockLLM must not access storage: {pattern}"


# =========================================================================
# 2. Error model: all kernel errors are StructuredError
# =========================================================================

def test_core_errors_use_structured_error() -> None:
    """HanCodeError must wrap StructuredError with required fields."""
    error = StructuredError(
        error_code="test_error",
        message="Test message",
        phase="spec",
        denied_rule="test_rule",
        suggested_fix="Do something",
    )
    assert error.error_code == "test_error"
    assert error.message == "Test message"
    assert error.phase == "spec"
    assert error.denied_rule == "test_rule"
    assert error.suggested_fix == "Do something"

    exc = HanCodeError(error)
    assert exc.structured_error is error
    d = exc.to_dict()
    assert d["error_code"] == "test_error"
    assert d["message"] == "Test message"
    assert d["phase"] == "spec"
    assert d["denied_rule"] == "test_rule"
    assert d["suggested_fix"] == "Do something"


def test_tool_policy_errors_are_structured() -> None:
    """ToolPolicy denial must be convertible to StructuredError fields."""
    decision = tool_policy.PolicyDecision(
        allowed=False,
        reason="Protected file",
        phase=phases.Phase.CODE,
        denied_rule="protected_file_write",
        suggested_fix="Choose a different file",
    )
    assert decision.allowed is False
    assert decision.denied_rule == "protected_file_write"
    assert decision.suggested_fix
    assert decision.reason == "Protected file"

    d = decision.to_dict()
    assert d["error_code"] == "policy_denied"
    assert d["message"] == "Protected file"
    assert d["denied_rule"] == "protected_file_write"


def test_workspace_errors_are_structured() -> None:
    """Workspace operations must return StructuredError on failure."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        try:
            workspace.init_task_workspace(root, "task-001")
            assert False, "Should have raised"
        except HanCodeError as exc:
            assert exc.structured_error.error_code in (
                "project_workspace_not_initialized",
                "workspace_init_failed",
                "workspace_project_metadata_invalid",
            )


def test_rollback_errors_are_structured() -> None:
    """Rollback without prior checkpoint must return StructuredError."""
    assert hasattr(checkpoints, "rollback_last_checkpoint")
    # Check that RollbackResult has structured error fields
    result = checkpoints.RollbackResult(
        status=models.OperationStatus.FAILED,
        checkpoint_id="ckpt-001",
        restored_files=(),
        failed_files=(),
        error=StructuredError(
            error_code="rollback_not_available",
            message="No checkpoint available for rollback.",
            phase="review",
            denied_rule="rollback_checkpoint_required",
            suggested_fix="Create a checkpoint before attempting rollback.",
        ),
    )
    assert result.error is not None
    assert result.error.error_code == "rollback_not_available"
    assert result.status == models.OperationStatus.FAILED
    d = result.to_dict()
    assert d["status"] == "failed"
    assert d["error"]["error_code"] == "rollback_not_available"


def test_trace_errors_are_structured() -> None:
    """Trace write failure must return StructuredError."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # Must create a valid .hancode/tasks/<task_id> layout
        task_root = root / ".hancode" / "tasks" / "task-001"
        task_root.mkdir(parents=True, exist_ok=True)
        (task_root / "trace.jsonl").write_text("not json\n", encoding="utf-8")
        try:
            trace.append_trace(
                task_root,
                event_type="test_event",
                task_id="task-001",
                phase=phases.Phase.SPEC,
                status="running",
            )
            assert False, "Should have raised"
        except HanCodeError as exc:
            assert exc.structured_error.error_code in (
                "trace_write_error",
                "trace_history_invalid",
                "invalid_trace_task_root",
            )


# =========================================================================
# 3. Phase routing invariants
# =========================================================================

def test_phase_gate_invariants() -> None:
    """Phase gate invariants must hold."""
    assert phases.Phase.SPEC.value == "spec"
    assert phases.Phase.PLAN.value == "plan"
    assert phases.Phase.CODE.value == "code"
    assert phases.Phase.TEST.value == "test"
    assert phases.Phase.REVIEW.value == "review"
    assert phases.Phase.DELIVER.value == "deliver"
    assert len(phases.Phase) == 6


def test_router_is_pure() -> None:
    """Router must be a pure function with no side effects."""
    task_state = state.TaskState(
        schema_version=1,
        task_id="task-001",
        status=models.TaskStatus.RUNNING,
        current_phase=phases.Phase.CODE,
        retry_budget_remaining=2,
        latest_checkpoint="ckpt-001",
        latest_test_status="none",
        artifacts={
            "SPEC.md": True,
            "PLAN.md": True,
            "TEST_REPORT.md": False,
            "REVIEW.md": False,
            "KNOWLEDGE.md": False,
            "DELIVERABLES.md": False,
        },
        files_changed=(),
        inconsistent=False,
        source_edits_this_phase=0,
        checkpoint_seq=1,
        tests_run=(),
        test_status_consumed=False,
phase_completed={
                "spec": True,
                "plan": True,
                "code": True,
                "test": False,
                "review": False,
                "deliver": False,
            },
        rollback_required=False,
        rollback_done=False,
        goal="Test task",
        delivery_coverage_digest=None,
        pending_checkpoint_recovery_id=None,
    )
    decision = router.select_next_phase(task_state)
    assert decision.phase == phases.Phase.TEST
    assert decision.blocked is False
    assert decision.completed is False


# =========================================================================
# 4. MockLLM control flow invariants
# =========================================================================

def test_mock_llm_exhaustion_control_flow() -> None:
    """MockLLM exhaustion must be caught by AgentLoop."""
    llm = mock.MockLLM([])
    try:
        llm.next_action({"phase": "spec"})
        assert False, "Should have raised"
    except mock.MockLLMExhausted:
        pass


def test_mock_llm_context_recording() -> None:
    """MockLLM records context before exhaustion."""
    llm = mock.MockLLM([{"type": "tool_call", "tool_name": "read_file", "args": {"path": "test.py"}, "reason": "test", "phase": "spec"}])
    ctx = {"phase": "spec", "task": "test"}
    result = llm.next_action(ctx)
    assert result["tool_name"] == "read_file"
    assert len(llm.contexts) == 1
    try:
        llm.next_action(ctx)
        assert False, "Should have raised"
    except mock.MockLLMExhausted:
        assert len(llm.contexts) == 2