# Harness Boundary Guide

Use this guide when designing or implementing HanCode mechanisms.

## Boundary

The delivered harness kernel must be implemented by this repository's own code.

Rules, prompts, configuration files, skill files, and documentation do not count
as harness implementation.

Hosted coding-agent behavior or external framework behavior must not become the
delivered product's core mechanism.

The project may use external coding agents and Superpowers to help develop the
code, but those tools must not become the delivered harness kernel.

## Required Mechanisms

HanCode must implement these mechanisms as deterministic source code in this
repository:

- WorkspaceSpec and WorkspaceRouter
- agent loop
- LLM abstraction with MockLLM support
- action schema and parser
- tool dispatcher
- file tools
- shell command tool
- guardrails
- feedback sensors
- memory
- ContextBuilder
- TraceLogger
- CheckpointManager and rollback
- Knowledge Delivery
- configuration loading and validation
- credential handling
- CLI entry point
- mechanism demo

All six harness dimensions need a minimal runnable implementation:

- decision / loop
- tools
- memory
- governance
- feedback
- configuration

The main contribution is workspace-scoped course-project context and reversible
coding state.

## Disallowed Shortcuts

Do not implement the delivered harness kernel by relying on:

- LangChain `AgentExecutor`
- AutoGen
- CrewAI
- LlamaIndex agent runners
- hosted coding-agent SDK runners
- framework-provided agent loops
- framework-provided memory as the product's memory
- framework skill systems as the product's mechanism layer
- prompt-only guardrails
- prompt-only self-checking

Allowed dependencies are low-level building blocks:

- HTTP clients
- LLM provider APIs for a single call
- parsers
- validation libraries
- CLI helpers
- keyring libraries
- subprocess utilities
- file-system utilities
- test tools

## Mechanism Test Standard

If a claimed mechanism cannot be tested after replacing the real LLM with a
MockLLM or stub, it is not sufficiently implemented.

Core mechanisms must be testable without network access and without a real LLM:

- agent loop
- action parsing
- tool dispatch
- guardrail decisions
- feedback injection
- memory retrieval
- stop conditions

Do not use tests that depend on provider behavior, network availability, model
intelligence, timing-sensitive behavior, or nondeterministic output.

## Action Protocol

The delivered harness must not depend on free-form natural language actions.

Model-produced actions must use a deterministic schema.

Malformed actions, unknown action types, missing required fields, invalid paths,
and invalid command payloads must be rejected by code.

The loop must not execute an action until it passes:

1. parsing
2. validation
3. guardrail review
4. tool-dispatch authorization

Expected action families include:

- `read_file`
- `write_file`
- `edit_file`
- `list_files`
- `search_text`
- `run_command`
- `run_tests`
- `rollback_last_checkpoint`
- `remember`
- `finish`

Adding an action requires:

1. updating the action schema
2. adding parser tests
3. adding guardrail behavior if the action can affect the outside world
4. adding tool-dispatch tests
5. documenting the action in `SPEC.md`

## Tool Dispatch

The tool layer should return structured results, including:

- success flag
- action name
- output or error summary
- exit code, if applicable
- stdout, if applicable
- stderr, if applicable

Do not allow tool execution to silently fail.

Do not allow tools to leak secrets through logs, exceptions, or test snapshots.

## Guardrails

Guardrails classify actions as:

- allow
- block
- require human approval

They must be deterministic code and unit-tested. A prompt saying "be safe" is
not sufficient.

Dangerous actions may include:

- editing business code before SPEC and PLAN exist
- editing business code outside code phase
- modifying or deleting assignment instructions without explicit user request
- deleting teacher-provided tests, grading scripts, or sample data
- bypassing tests or grading scripts
- writing outside the workspace
- reading sensitive files
- deleting important files
- running destructive shell commands
- commands containing `rm -rf /`
- commands that remove project history
- commands that access secrets
- commands that publish artifacts externally
- commands that perform network actions when disabled
- commands that modify system-level configuration

## Feedback Loop

Feedback must come from objective signals produced by deterministic tools or
sensors.

Valid feedback signals may include:

- pytest result
- command exit code
- stdout
- stderr
- lint result
- type-check result
- structured failure classification

The feedback system should convert raw tool output into a structured feedback
report that makes clear:

- whether the check passed
- what failed
- where it failed, if available
- what signal was observed
- what summary should be fed back into the next loop iteration

The mechanism demo must show, under MockLLM:

1. a dangerous action blocked by guardrail code
2. an injected failure converted into feedback
3. the agent changing its next action after feedback
4. the main contribution mechanism working deterministically

Do not rely on the real LLM to "self-check" as the only feedback mechanism.

## Memory Requirements

Memory may store:

- course context
- grading rubric
- submission format
- course knowledge points
- project conventions
- accepted design decisions
- previous failure summaries
- known test commands
- repeated error patterns
- user-approved preferences relevant to the coding task

Retrieve memory on demand. Do not inject the whole memory store into every LLM
request.

Memory behavior must be testable without a real LLM.

Do not store real secrets in memory.

## Knowledge Delivery

Deliver phase must produce course-project artifacts, including `KNOWLEDGE.md`
and `DELIVERABLES.md`. `KNOWLEDGE.md` should record course concepts, key design
decisions, mistakes, fixes, and reusable lessons. It must not be an empty or
generic summary.

## Configuration Requirements

Configuration should be explicit and validated.

Configuration may include:

- workspace path
- allowed tools
- test command
- lint command
- type-check command
- guardrail policy
- memory location
- model provider choice
- credential source
- maximum loop iterations

Invalid configuration should fail clearly.

Do not silently fall back to unsafe defaults.

Configuration files do not count as implementation. The config loader and
validation logic must be implemented in code.
