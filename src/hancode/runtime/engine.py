from __future__ import annotations

from pathlib import Path
from typing import cast

from hancode.core.config import load_config
from hancode.providers.base import LLMClient
from hancode.providers.factory import create_provider_adapter
from hancode.policy.approval_policy import ApprovalPolicy
from hancode.policy.tool_policy import ToolPolicy
from hancode.runtime.agent_loop import (
    AgentLoop,
    AgentRunResult,
    ApprovalPolicyPort,
    ApprovalRequestBuilderPort,
    ApprovalStore as ApprovalStorePort,
    FeedbackBuilder as FeedbackBuilderPort,
    FilesystemAgentLoopPorts,
    MutationGuard,
    Policy,
    TraceAppender,
    ToolRegistry as ToolRegistryPort,
)
from hancode.runtime.approval_request import ApprovalRequestBuilder
from hancode.runtime.context import ContextBuilder
from hancode.runtime.feedback import FeedbackBuilder
from hancode.runtime.observation import ObservedTraceAppender, TraceObserver
from hancode.storage.approvals import ApprovalStore
from hancode.storage.workspace import load_project_metadata
from hancode.tooling.factory import build_default_tool_registry


def create_agent_loop(
    project_root: Path,
    task_id: str,
    *,
    provider: LLMClient | None = None,
    tool_registry: ToolRegistryPort | None = None,
    trace_appender: TraceAppender | None = None,
    trace_observer: TraceObserver | None = None,
    mutation_guard: MutationGuard | None = None,
    max_steps: int | None = None,
) -> AgentLoop:
    """Build the standard filesystem-backed AgentLoop with injectable seams."""
    config = load_config(project_root, task_id)
    ports = FilesystemAgentLoopPorts.from_project_root(project_root)
    llm = provider if provider is not None else create_provider_adapter(config)
    registry = (
        tool_registry
        if tool_registry is not None
        else build_default_tool_registry(config)
    )
    selected_trace_appender = trace_appender or ports.trace_appender
    if trace_observer is not None:
        selected_trace_appender = cast(
            TraceAppender,
            ObservedTraceAppender(selected_trace_appender, trace_observer),
        )
    selected_mutation_guard = mutation_guard or ports.mutation_guard
    selected_max_steps = config.max_steps if max_steps is None else max_steps

    # Approval gate: only active when the project enables it and rollback
    # confirmation is not needed otherwise. The store/builder are cheap to
    # construct, so wire them whenever approvals could ever fire.
    approval_policy: ApprovalPolicyPort | None = None
    approval_store: ApprovalStorePort | None = None
    approval_request_builder: ApprovalRequestBuilderPort | None = None
    if config.approval_mode != "disabled" or config.confirm_agent_rollback:
        try:
            metadata = load_project_metadata(
                project_root / ".hancode" / "project.json"
            )
            project_id = str(metadata.get("project_id", "unknown"))
        except Exception:
            project_id = "unknown"
        approval_policy = cast(ApprovalPolicyPort, ApprovalPolicy(config))
        approval_store = cast(ApprovalStorePort, ApprovalStore(project_root, project_id))
        approval_request_builder = cast(
            ApprovalRequestBuilderPort, ApprovalRequestBuilder(config)
        )

    return AgentLoop(
        llm=llm,
        context_builder=ContextBuilder(project_root, config),
        policy=cast(Policy, ToolPolicy(config)),
        tool_registry=registry,
        feedback_builder=cast(
            FeedbackBuilderPort, FeedbackBuilder(config.max_observation_bytes)
        ),
        state_store=ports.state_store,
        trace_appender=selected_trace_appender,
        checkpoint_manager=ports.checkpoint_manager,
        rollback_manager=ports.rollback_manager,
        mutation_guard=selected_mutation_guard,
        max_steps=selected_max_steps,
        approval_policy=approval_policy,
        approval_store=approval_store,
        approval_request_builder=approval_request_builder,
        project_root=project_root,
    )


def run_task(
    project_root: Path,
    task_id: str,
    *,
    resume: bool = False,
    provider: LLMClient | None = None,
    trace_observer: TraceObserver | None = None,
) -> AgentRunResult:
    """Create and execute the standard AgentLoop for one task."""
    loop = create_agent_loop(
        project_root, task_id, provider=provider, trace_observer=trace_observer
    )
    return loop.run(task_id, resume=resume)
