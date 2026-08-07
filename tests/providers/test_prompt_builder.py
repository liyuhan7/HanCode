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
    assert "exactly one next Action" in system_content
    assert "Do not use Markdown" in system_content
    assert "You do not execute tools" in system_content


def test_system_prompt_marks_workspace_content_untrusted() -> None:
    builder = PromptBuilder()
    prompt = builder.build(
        context=_make_context(),
        tool_catalog=_make_catalog(),
    )
    assert "untrusted data" in prompt.messages[0].content


def test_system_prompt_forbids_model_final() -> None:
    builder = PromptBuilder()
    prompt = builder.build(
        context=_make_context(),
        tool_catalog=_make_catalog(),
    )
    assert "Never return final" in prompt.messages[0].content


def test_prompt_system_message_contains_current_phase() -> None:
    builder = PromptBuilder()
    prompt = builder.build(
        context=_make_context(phase=Phase.CODE),
        tool_catalog=_make_catalog(),
    )
    system_content = prompt.messages[0].content
    assert "code" in system_content


def test_code_prompt_requires_behavioral_tests_and_strategy_registration() -> None:
    prompt = PromptBuilder().build(
        context=_make_context(phase=Phase.CODE),
        tool_catalog=_make_catalog(),
    )

    system_content = prompt.messages[0].content
    assert "create project-native behavioral tests" in system_content
    assert "record_test_strategy" in system_content
    assert "sections.writable_roots" in system_content
    assert "writable_roots_warning" in system_content
    assert "write_file" in system_content
    assert "missing parent directories" in system_content


def test_test_prompt_requires_exact_registered_command() -> None:
    prompt = PromptBuilder().build(
        context=_make_context(phase=Phase.TEST),
        tool_catalog=_make_catalog(),
    )

    system_content = prompt.messages[0].content
    assert "Run only its exact command" in system_content
    assert "do not discover, substitute, broaden, or invent" in system_content


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


def test_prompt_user_message_contains_tool_args_schema() -> None:
    builder = PromptBuilder()
    prompt = builder.build(
        context=_make_context(),
        tool_catalog=_make_catalog(),
    )

    payload = json.loads(prompt.messages[1].content)
    read_file = next(
        tool for tool in payload["available_tools"] if tool["name"] == "read_file"
    )
    assert read_file["args_schema"]["properties"]["path"] == {"type": "string"}


def test_prompt_filters_tools_by_phase() -> None:
    catalog = (
        ToolDescriptor("read_file", "Read.", {"type": "object"}),
        ToolDescriptor("list_files", "List.", {"type": "object"}),
        ToolDescriptor("search_text", "Search.", {"type": "object"}),
        ToolDescriptor("write_file", "Write.", {"type": "object"}),
        ToolDescriptor("edit_file", "Edit.", {"type": "object"}),
        ToolDescriptor("run_tests", "Test.", {"type": "object"}),
        ToolDescriptor("rollback_last_checkpoint", "Rollback.", {"type": "object"}),
    )
    prompt = PromptBuilder().build(
        context=_make_context(phase=Phase.TEST),
        tool_catalog=catalog,
    )

    payload = json.loads(prompt.messages[1].content)
    names = {tool["name"] for tool in payload["available_tools"]}
    assert {"list_files", "read_file", "search_text", "run_tests"} <= names
    schema_tools = {
        branch["properties"]["tool_name"]["const"]
        for branch in prompt.action_schema["oneOf"]
        if branch["properties"]["type"]["const"] == "tool_call"
    }
    assert {"list_files", "read_file", "search_text", "run_tests"} <= schema_tools


def test_test_phase_requires_explicit_test_command() -> None:
    catalog = (
        ToolDescriptor(
            name="run_tests",
            description="Run tests.",
            args_schema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "minLength": 1,
                    }
                },
                "additionalProperties": False,
            },
        ),
    )

    prompt = PromptBuilder().build(
        context=_make_context(phase=Phase.TEST),
        tool_catalog=catalog,
    )

    branch = next(
        item
        for item in prompt.action_schema["oneOf"]
        if item["properties"].get("tool_name", {}).get("const") == "run_tests"
    )

    assert branch["properties"]["args"]["required"] == ["command"]


def test_prompt_contains_artifact_targets() -> None:
    context = _make_context(
        artifact_targets={
            "SPEC.md": ".hancode/tasks/task-001/SPEC.md",
            "PLAN.md": ".hancode/tasks/task-001/PLAN.md",
        },
        task_workspace=".hancode/tasks/task-001",
    )
    prompt = PromptBuilder().build(context=context, tool_catalog=_make_catalog())
    payload = json.loads(prompt.messages[1].content)
    assert payload["task_context"]["task_workspace"] == ".hancode/tasks/task-001"
    assert payload["task_context"]["artifact_targets"]["SPEC.md"] == (
        ".hancode/tasks/task-001/SPEC.md"
    )


def test_prompt_user_message_contains_action_schema() -> None:
    builder = PromptBuilder()
    prompt = builder.build(
        context=_make_context(),
        tool_catalog=_make_catalog(),
    )
    user_content = prompt.messages[1].content
    assert "tool_call" in user_content
    assert "finish_phase" in user_content
    assert "final" not in user_content


def test_prompt_excludes_ask_user_in_stage_two() -> None:
    builder = PromptBuilder()
    prompt = builder.build(
        context=_make_context(),
        tool_catalog=_make_catalog(),
        interaction_enabled=False,
    )
    user_content = prompt.messages[1].content
    assert "ask_user" not in user_content


def test_prompt_exposes_ask_user_when_interaction_enabled() -> None:
    prompt = PromptBuilder().build(
        context=_make_context(),
        tool_catalog=_make_catalog(),
        interaction_enabled=True,
    )

    user_content = prompt.messages[1].content
    assert "ask_user" in user_content
    assert "Do not ask for API keys" in prompt.messages[0].content


def test_prompt_forbids_secret_requests_when_interaction_enabled() -> None:
    prompt = PromptBuilder().build(
        context=_make_context(),
        tool_catalog=_make_catalog(),
        interaction_enabled=True,
    )

    system_content = prompt.messages[0].content
    assert "passwords" in system_content
    assert "credentials" in system_content


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


def test_prompt_redacts_private_key_inside_tuple_context() -> None:
    context = _make_context()
    context["evidence"] = ({"private_key": "private-secret"},)  # type: ignore[assignment]

    prompt = PromptBuilder().build(context=context, tool_catalog=_make_catalog())

    assert all("private-secret" not in message.content for message in prompt.messages)


def test_prompt_user_message_is_valid_json() -> None:
    builder = PromptBuilder()
    prompt = builder.build(
        context=_make_context(),
        tool_catalog=_make_catalog(),
    )
    user_content = prompt.messages[1].content
    parsed = json.loads(user_content)
    assert isinstance(parsed, dict)
    assert parsed["prompt_version"] == "hancode-action-v2"
    assert parsed["request"]["kind"] == "select_next_action"
    assert "task_context" in parsed
    assert "available_tools" in parsed
    assert "output_contract" in parsed


def test_user_payload_contains_prompt_version() -> None:
    builder = PromptBuilder()
    prompt = builder.build(
        context=_make_context(),
        tool_catalog=_make_catalog(),
    )
    payload = json.loads(prompt.messages[1].content)
    assert payload["prompt_version"] == "hancode-action-v2"


def test_native_tool_prompt_does_not_expose_action_json_contract() -> None:
    prompt = PromptBuilder().build(
        context=_make_context(),
        tool_catalog=_make_catalog(),
        native_tool_calling=True,
    )

    payload = json.loads(prompt.messages[1].content)

    assert prompt.prompt_version == "hancode-tool-v1"
    assert set(payload) == {"prompt_version", "request", "task_context"}
    assert payload["prompt_version"] == "hancode-tool-v1"
    assert "available_tools" not in prompt.messages[1].content
    assert "args_schema" not in prompt.messages[1].content
    assert "output_contract" not in prompt.messages[1].content
    assert "response_contract" not in prompt.messages[1].content
    assert "Function Tool" in prompt.messages[0].content
    assert "ACTION REUSE" in prompt.messages[0].content
    assert "reusable_evidence" in prompt.messages[0].content
    assert "memory_search" in prompt.messages[0].content


def test_strict_mode_omits_embedded_output_contract() -> None:
    builder = PromptBuilder()
    prompt = builder.build(
        context=_make_context(),
        tool_catalog=_make_catalog(),
        embed_action_schema=False,
    )
    payload = json.loads(prompt.messages[1].content)
    assert "output_contract" not in payload
    assert payload["response_contract"]["strict"] is True


def test_compatibility_mode_embeds_output_contract() -> None:
    builder = PromptBuilder()
    prompt = builder.build(
        context=_make_context(),
        tool_catalog=_make_catalog(),
        embed_action_schema=True,
    )
    payload = json.loads(prompt.messages[1].content)
    assert "output_contract" in payload
    assert payload["response_contract"]["strict"] is False


def test_provider_schema_does_not_expose_final() -> None:
    prompt = PromptBuilder().build(
        context=_make_context(),
        tool_catalog=_make_catalog(),
    )
    action_types = {
        branch["properties"]["type"]["const"]
        for branch in prompt.action_schema["oneOf"]
    }
    assert "final" not in action_types
    assert "finish_phase" in action_types


def test_write_action_schema_requires_reason() -> None:
    catalog = (
        ToolDescriptor(
            name="write_file",
            description="Write.",
            args_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"],
            },
        ),
    )
    prompt = PromptBuilder().build(
        context=_make_context(phase=Phase.CODE),
        tool_catalog=catalog,
    )
    write_branch = next(
        branch
        for branch in prompt.action_schema["oneOf"]
        if branch["properties"].get("tool_name", {}).get("const") == "write_file"
    )
    assert "reason" in write_branch["required"]


def test_read_action_schema_does_not_require_reason() -> None:
    prompt = PromptBuilder().build(
        context=_make_context(),
        tool_catalog=_make_catalog(),
    )
    read_branch = next(
        branch
        for branch in prompt.action_schema["oneOf"]
        if branch["properties"].get("tool_name", {}).get("const") == "read_file"
    )
    assert "reason" in read_branch["required"]


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


def test_deliver_system_prompt_guides_get_diff_evidence() -> None:
    builder = PromptBuilder()
    prompt = builder.build(
        context=_make_context(phase=Phase.DELIVER),
        tool_catalog=_make_catalog(),
    )
    system_content = prompt.messages[0].content
    assert "get_diff" in system_content
    assert "diff evidence" in system_content


def test_code_system_prompt_guides_remediation_scope_source() -> None:
    builder = PromptBuilder()
    prompt = builder.build(
        context=_make_context(phase=Phase.CODE),
        tool_catalog=_make_catalog(),
    )
    system_content = prompt.messages[0].content
    assert "remediation_scope" in system_content
    assert "test_remediation.json" in system_content
    assert "not in task memory" in system_content


def test_review_system_prompt_persists_remediation_record() -> None:
    builder = PromptBuilder()
    prompt = builder.build(
        context=_make_context(phase=Phase.REVIEW),
        tool_catalog=_make_catalog(),
    )
    system_content = prompt.messages[0].content
    assert "test_remediation.json" in system_content
    assert "task memory" in system_content


def test_system_contract_forbids_retrying_same_memory_tool_after_failed_read() -> None:
    from hancode.providers.prompt_contract import BASE_SYSTEM_CONTRACT

    assert "switch to a different" in BASE_SYSTEM_CONTRACT
    assert "read_file" in BASE_SYSTEM_CONTRACT


def test_system_contract_declares_runtime_steering_authority() -> None:
    from hancode.providers.prompt_contract import BASE_SYSTEM_CONTRACT

    contract = " ".join(BASE_SYSTEM_CONTRACT.lower().split())
    required_fragments = (
        "runtime steering",
        "task_context.user_interventions.effective",
        "remain effective for the entire current run",
        "higher sequence supersedes a conflicting lower sequence",
        "supersedes the original task goal, previous plans, and observations where they conflict",
        "never overrides system rules, phase gates, toolpolicy, approval, or checkpoint requirements",
    )

    for fragment in required_fragments:
        assert fragment in contract


def test_native_tool_prompt_includes_runtime_steering_contract() -> None:
    prompt = PromptBuilder().build(
        context=_make_context(),
        tool_catalog=_make_catalog(),
        native_tool_calling=True,
    )

    system_content = prompt.messages[0].content.lower()

    assert "runtime steering" in system_content
    assert "task_context.user_interventions.effective" in system_content
    assert "never overrides system rules" in system_content


def test_system_prompt_requires_artifacts_in_simplified_chinese() -> None:
    prompt = PromptBuilder().build(
        context=_make_context(phase=Phase.SPEC),
        tool_catalog=_make_catalog(),
    )

    system_content = prompt.messages[0].content

    assert "ARTIFACT LANGUAGE" in system_content
    assert "Simplified Chinese" in system_content
    assert "SPEC.md" in system_content
    assert "PLAN.md" in system_content
    assert "TEST_REPORT.md" in system_content
    assert "REVIEW.md" in system_content
    assert "evidence IDs" in system_content


def test_native_tool_prompt_includes_artifact_language_contract() -> None:
    prompt = PromptBuilder().build(
        context=_make_context(),
        tool_catalog=_make_catalog(),
        native_tool_calling=True,
    )

    system_content = prompt.messages[0].content

    assert "ARTIFACT LANGUAGE" in system_content
    assert "Simplified Chinese" in system_content
    assert "SPEC.md" in system_content
