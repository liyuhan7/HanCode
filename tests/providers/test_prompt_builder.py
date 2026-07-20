from __future__ import annotations

import json

from hancode.core.models import Phase
from hancode.providers.base import ToolDescriptor
from hancode.providers.prompt_builder import ChatMessage, PromptBuilder, ProviderPrompt


def _make_catalog() -> tuple[ToolDescriptor, ...]:
    return (
        ToolDescriptor(
            name="read_file",
            description="Read a file inside the allowed workspace.",
            args_schema={"type": "object", "properties": {"path": {"type": "string"}}},
        ),
        ToolDescriptor(
            name="list_files",
            description="List files in the project workspace.",
            args_schema={"type": "object"},
        ),
    )


def _make_context(
    *,
    phase: Phase = Phase.SPEC,
    goal: str = "Generate SPEC.md for the assignment.",
    **extra: object,
) -> dict[str, object]:
    context: dict[str, object] = {
        "task_id": "task-001",
        "phase": phase.value,
        "goal": goal,
        "sections": {},
        "context_risks": [],
        "truncation": {"applied": False, "omitted_sections": [], "truncated_sections": []},
    }
    context.update(extra)
    return context


def test_prompt_builder_returns_provider_prompt() -> None:
    builder = PromptBuilder()
    prompt = builder.build(
        context=_make_context(),
        tool_catalog=_make_catalog(),
    )
    assert isinstance(prompt, ProviderPrompt)
    assert len(prompt.messages) >= 2
    assert isinstance(prompt.messages[0], ChatMessage)
    assert prompt.messages[0].role == "system"
    assert prompt.messages[1].role == "user"


def test_prompt_system_message_contains_harness_contract() -> None:
    builder = PromptBuilder()
    prompt = builder.build(
        context=_make_context(),
        tool_catalog=_make_catalog(),
    )
    system_content = prompt.messages[0].content
    assert "exactly one structured Action" in system_content
    assert "Do not wrap" in system_content or "Do not wrap the response in Markdown" in system_content
    assert "Do not execute tools yourself" in system_content


def test_prompt_system_message_contains_current_phase() -> None:
    builder = PromptBuilder()
    prompt = builder.build(
        context=_make_context(phase=Phase.CODE),
        tool_catalog=_make_catalog(),
    )
    system_content = prompt.messages[0].content
    assert "code" in system_content


def test_prompt_user_message_contains_task_goal() -> None:
    builder = PromptBuilder()
    prompt = builder.build(
        context=_make_context(goal="Analyze the assignment requirements."),
        tool_catalog=_make_catalog(),
    )
    user_content = prompt.messages[1].content
    assert "Analyze the assignment requirements." in user_content


def test_prompt_user_message_contains_available_tools() -> None:
    builder = PromptBuilder()
    prompt = builder.build(
        context=_make_context(),
        tool_catalog=_make_catalog(),
    )
    user_content = prompt.messages[1].content
    assert "read_file" in user_content
    assert "list_files" in user_content
    assert "Read a file inside the allowed workspace." in user_content


def test_prompt_user_message_contains_action_schema() -> None:
    builder = PromptBuilder()
    prompt = builder.build(
        context=_make_context(),
        tool_catalog=_make_catalog(),
    )
    user_content = prompt.messages[1].content
    assert "tool_call" in user_content
    assert "finish_phase" in user_content
    assert "final" in user_content


def test_prompt_excludes_ask_user_in_stage_two() -> None:
    builder = PromptBuilder()
    prompt = builder.build(
        context=_make_context(),
        tool_catalog=_make_catalog(),
        interaction_enabled=False,
    )
    user_content = prompt.messages[1].content
    assert "ask_user" not in user_content


def test_prompt_serialization_is_deterministic() -> None:
    builder = PromptBuilder()
    context = _make_context()
    catalog = _make_catalog()

    prompt1 = builder.build(context=context, tool_catalog=catalog)
    prompt2 = builder.build(context=context, tool_catalog=catalog)

    assert prompt1.messages == prompt2.messages
    assert json.dumps(prompt1.action_schema, sort_keys=True) == json.dumps(
        prompt2.action_schema, sort_keys=True
    )


def test_prompt_does_not_contain_credential() -> None:
    builder = PromptBuilder()
    context = _make_context()
    context["api_key"] = "sk-secret-value-12345"  # type: ignore[assignment]
    prompt = builder.build(
        context=context,
        tool_catalog=_make_catalog(),
    )
    for message in prompt.messages:
        assert "sk-secret-value-12345" not in message.content
        assert "api_key" not in message.content


def test_prompt_user_message_is_valid_json() -> None:
    builder = PromptBuilder()
    prompt = builder.build(
        context=_make_context(),
        tool_catalog=_make_catalog(),
    )
    user_content = prompt.messages[1].content
    parsed = json.loads(user_content)
    assert isinstance(parsed, dict)
    assert "instruction" in parsed
    assert "context" in parsed
    assert "available_tools" in parsed
    assert "output_contract" in parsed


def test_prompt_system_message_contains_phase_instruction() -> None:
    builder = PromptBuilder()
    prompt = builder.build(
        context=_make_context(phase=Phase.SPEC),
        tool_catalog=_make_catalog(),
    )
    system_content = prompt.messages[0].content
    assert "SPEC.md" in system_content or "spec" in system_content.lower()


def test_prompt_system_message_for_code_phase() -> None:
    builder = PromptBuilder()
    prompt = builder.build(
        context=_make_context(phase=Phase.CODE),
        tool_catalog=_make_catalog(),
    )
    system_content = prompt.messages[0].content
    assert "implement" in system_content.lower() or "code" in system_content.lower()


def test_prompt_system_message_for_test_phase() -> None:
    builder = PromptBuilder()
    prompt = builder.build(
        context=_make_context(phase=Phase.TEST),
        tool_catalog=_make_catalog(),
    )
    system_content = prompt.messages[0].content
    assert "test" in system_content.lower()
