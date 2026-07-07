# HanCode Agent Map

This file is a map, not a manual. Read it first, then open only the detailed
agent guide that matches the current task.

## Project Identity

HanCode is an AI4SE final project, category A: Coding Agent Harness.

Goal: build a lightweight coding-agent harness for student course projects with
workspace-scoped execution, phase-gated coding, trace logging,
checkpoint-based rollback, and knowledge-oriented delivery.

Main contribution: workspace-scoped course-project context and reversible coding
state. Project Workspace manages course-project context and long-term
experience; Task Workspace manages task SPEC, PLAN, Trace, Checkpoint, and
learning artifacts; Phase Mode governs each course-project stage.

## Source Priority

When instructions conflict, follow this order:

1. `AI4SE_Final_Project_0_通用要求.md`
2. `AI4SE_Final_Project_A_Coding_Agent_Harness.md`
3. `SPEC.md`
4. `PLAN.md`
5. `README.md`
6. `AGENT_LOG.md`
7. this map

## Read On Demand

Use these detailed guides only when relevant:

- Assignment and deliverables: `docs/agent-guides/assignment-map.md`
- Workflow, phase gates, TDD, cold-start validation: `docs/agent-guides/workflow.md`
- Harness boundary and mechanism design: `docs/agent-guides/harness-boundary.md`
- Credentials, workspace safety, verification, completion: `docs/agent-guides/safety-and-verification.md`

If a guide conflicts with the assignment files, the assignment files win.

## Current Phase Gate

This repository is still in specification and planning.

Do not write implementation code until all are complete:

1. `SPEC.md`
2. `PLAN.md`
3. cold-start validation by a different coding agent
4. revision evidence recorded in `SPEC_PROCESS.md`

Before that gate passes, only update planning/configuration documentation such
as rules, specs, plans, process notes, logs, README planning text, and
documentation placeholders.

Do not create or modify implementation modules under `src/hancode/` for the
harness kernel before the gate passes.

## Default Workflow

Use the required Superpowers sequence unless the user explicitly scopes the task
as a small documentation/configuration edit:

1. `brainstorming`
2. `writing-plans`
3. `using-git-worktrees`
4. `subagent-driven-development` or `executing-plans`
5. `test-driven-development`
6. `requesting-code-review`
7. `finishing-a-development-branch`

Record necessary workflow deviations in `AGENT_LOG.md`.

## Non-Negotiables

- Implementation tasks use TDD: failing test first, then minimal code, then refactor.
- Required harness mechanisms must be deterministic code, not prompts, rules, or hosted-agent behavior.
- Course assignment files, teacher tests, grading scripts, and sample data are protected by policy.
- Core mechanisms must be testable with MockLLM or stubs, without network or a real LLM.
- Never commit real credentials, API keys, tokens, or secrets.
- Do not print secret values in logs, errors, README examples, tests, or agent records.
- Stay within the task scope and avoid unrelated refactors.
- Do not claim completion without fresh verification evidence.

## Task Routing

- Editing `SPEC.md`: read assignment files and `workflow.md`.
- Editing `PLAN.md`: read `SPEC.md`, assignment files, and `workflow.md`.
- Designing implementation mechanisms: read `harness-boundary.md`.
- Touching credentials, tools, shell commands, paths, logs, or verification: read `safety-and-verification.md`.
- Completing a task: update `PLAN.md` and `AGENT_LOG.md` when the task type requires it.

## Verification Shortcuts

Prefer these commands when relevant:

```powershell
python -m pytest
python -m ruff check src tests
python -m mypy src
```

For documentation-only changes, verify by reading changed files with
`Get-Content -Raw -Encoding UTF8`, checking required phrases, and confirming
`git status --short`.

## Final Rule

HanCode must prove its core behavior through engineering mechanisms. If removing
the real LLM makes a claimed mechanism untestable, that mechanism is not
sufficiently implemented.
