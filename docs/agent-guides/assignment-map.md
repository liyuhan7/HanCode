# Assignment Map

Use this guide when checking whether work still satisfies the AI4SE assignment.
The assignment files remain authoritative.

## Project Type

HanCode selects project A: Coding Agent Harness.

The complete requirement set is:

1. `docs/AI4SE_Final_Project_通用要求.md`
2. `docs/AI4SE_Final_Project_A_Coding_Agent_Harness (1).md`

The project must demonstrate engineering depth around an LLM, especially the
harness layer: decision loop, actions, tools, context, memory, governance,
feedback, configuration, credentials, and distribution.

The assignment's core question is not "can an AI write code?" It is whether the
student can define what should be built, drive agentic development without
losing control, verify correctness, and own final engineering judgment.

## Project Identity

HanCode is a lightweight coding-agent harness for student course projects.

It should show:

- self-implemented agent loop
- action parsing and tool dispatch
- deterministic guardrails, including course-file protection
- feedback-driven self-correction with failure classification
- checkpoint-based rollback and retry-budget recovery
- phase-gated coding workflow
- workspace-scoped course-project context (supporting dimension)
- knowledge-oriented delivery
- MockLLM unit tests
- safe credential handling
- Python package distribution, with Docker only as an optional MockLLM demo image

The main contribution is a deterministic feedback loop and reversible coding
state: `run_tests` produces objective signals, FeedbackBuilder classifies
failures and feeds them back, CheckpointManager snapshots before edits, and
retry budget drives forced rollback. Workspace-scoped memory is a supporting
dimension at the minimum runnable level: Project Workspace manages course-project
context and long-term experience; Task Workspace manages task SPEC, PLAN, Trace,
Checkpoint, and learning artifacts; Phase Mode governs requirements, planning,
coding, testing, review, and delivery.

Depth matters more than code volume. There is no required line-count floor. A
small project with well-designed credentials, distribution, and mechanism tests
is better than a large wrapper around an existing framework.

## Required Deliverables

Final submission should include:

- `docs/SPEC.md`
- `docs/PLAN.md`
- `docs/SPEC_PROCESS.md`
- full source code with clean commit / PR history
- self-implemented harness kernel
- MockLLM unit tests for core mechanisms
- deterministic mechanism demo from assignment A.6
- Python package distribution artifact, with optional Docker demo image if time allows
- `README.md`
- `docs/AGENT_LOG.md`
- CI config with a `unit-test` job; use `.gitlab-ci.yml` for course submission and optionally mirror it under `.github/workflows/` if this repository keeps GitHub CI
- `REFLECTION.md`

Optional deliverables include:

- live deployment URL
- 5-10 minute demo video link

The repository must not contain real credentials anywhere.

## SPEC Requirements

`docs/SPEC.md` must be generated from the brainstorming process and contain:

- problem statement: what problem HanCode solves, target users, and why it is worth building
- at least 5 INVEST-style user stories
- functional spec by module, including input, behavior, output, boundary conditions, and error handling
- non-functional requirements: performance, security, usability, and observability
- credential threat model and countermeasures
- system architecture: component diagram, data flow, external dependencies, LLM provider, and external tools
- data model: main entities, fields, relationships, and constraints
- credential and distribution design: storage, enter/update/clear flow, distribution form, target platforms, and safe key setup
- technology choices and rationale: language, libraries, LLM provider, distribution, deployment platform
- acceptance criteria: objective "done" criteria per feature
- risks and open questions

For the Coding Agent Harness project, `docs/SPEC.md` must also include a dedicated
domain and mechanism design section. It must clearly answer:

- what the coding domain's actions and tools are
- what objective feedback signals exist
- what dangerous actions must be blocked or paused
- what memory is needed across sessions
- which dimension is the main contribution
- why that dimension was chosen
- how every required mechanism will become code
- how course assignment files, teacher tests, grading scripts, and sample data are protected
- how TEST_REPORT, REVIEW, KNOWLEDGE, and DELIVERABLES are produced

## PLAN Requirements

`docs/PLAN.md` must be produced from the writing-plans workflow.

It must split the project into tasks small enough for one focused subagent
session. Each task should include:

- task ID
- goal
- involved files
- expected implementation notes
- expected failing tests
- verification commands
- dependencies
- parallelization notes
- final commit hash after completion

Avoid vague tasks such as:

- "implement agent"
- "finish backend"
- "add tests"
- "improve safety"

Prefer concrete mechanism-level tasks such as:

- "implement MockLLM scripted response interface"
- "parse valid and invalid action JSON"
- "block shell commands containing `rm -rf /`"
- "convert pytest failure output into FeedbackReport"
- "reject edit_file before SPEC and PLAN exist"
- "protect teacher tests and grading scripts"
- "generate KNOWLEDGE and DELIVERABLES in deliver phase"

## Distribution Requirements

The planned MVP distribution format is Python package: wheel / sdist. Docker is
only an optional MockLLM demo image unless `docs/SPEC.md` is revised.

Distribution documentation must explain:

- how to get the project
- how to build it
- how to run it
- how to configure credentials safely on the target machine
- target platforms and known limitations

If Docker demo distribution is implemented, CI may build the image or at least
verify the Docker build, but this must not replace Python package build
verification.

The final README must be usable by a new user on a clean machine.

## CI Requirements

CI should run on push and pull request.

CI should include:

- dependency installation
- lint
- type check
- test suite

CI must include a `unit-test` job that runs the MockLLM core tests without real
LLM credentials or network. When Docker demo distribution is implemented, CI
may also include Docker build verification.

Do not bypass CI failures without recording the reason.

## Academic And Dependency Rules

This is an individual project. The student remains responsible for design,
review, final decisions, and submission.

If third-party code or libraries are used, respect their licenses and list them
in `README.md`.

If a core algorithm or core mechanism is handwritten by the student, mark it
with a short comment when appropriate.

`REFLECTION.md` must be 1500-2500 words and student-written. AI assistance may
be used for polishing only when disclosed.

Do not present AI-generated reflection text as the student's own reflection.
