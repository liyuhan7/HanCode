# HanCode Agent Map

This file is a map, not a manual. Read it first, then open only the detailed
agent guide that matches the current task.

## Project Identity

HanCode is an AI4SE final project, category A: Coding Agent Harness.

Goal: build a lightweight coding-agent harness for student course projects with
phase-gated coding, deterministic test-feedback, trace logging,
checkpoint-based rollback, and knowledge-oriented delivery.

Main contribution: deterministic feedback loop and reversible coding state.
Code changes must create checkpoints, tests provide objective feedback,
FeedbackBuilder classifies failures and feeds observations back into the loop,
and exhausted retry budget forces rollback. Workspace-scoped memory is a
supporting dimension: Project Workspace manages course-project context and
long-term experience; Task Workspace manages task SPEC, PLAN, Trace,
Checkpoint, and learning artifacts; Phase Mode governs each course-project
stage.

## Source Priority

When instructions conflict, follow this order:

1. `docs/AI4SE_Final_Project_通用要求.md`
2. `docs/AI4SE_Final_Project_A_Coding_Agent_Harness (1).md`
3. `docs/SPEC.md`
4. `docs/PLAN.md`
5. `README.md`
6. `docs/AGENT_LOG.md`
7. this map

## Read On Demand

Use these detailed guides only when relevant:

- Assignment and deliverables: `docs/agent-guides/assignment-map.md`
- Workflow, phase gates, TDD, cold-start validation: `docs/agent-guides/workflow.md`
- Harness boundary and mechanism design: `docs/agent-guides/harness-boundary.md`
- Credentials, workspace safety, verification, completion: `docs/agent-guides/safety-and-verification.md`

If a guide conflicts with the assignment files, the assignment files win.

## Current Phase Gate

The specification, plan, and cold-start validation evidence are now recorded.
Formal implementation may begin, starting from `docs/PLAN.md` task T1.

Implementation code is allowed only when it is scoped to a `docs/PLAN.md` task
and follows the required task workflow:

1. read the task card and referenced SPEC / architecture sections
2. create or use an isolated worktree / branch / execution session
3. write the failing test first and record the red result
4. implement the minimum code
5. rerun verification
6. update `docs/PLAN.md` and `docs/AGENT_LOG.md`
7. request review before moving to the next task

Do not batch unrelated tasks into one implementation pass. The cold-start review
found extra constraints for T1 / T2; follow the current task cards rather than
copying the demo implementation directly.

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

Record necessary workflow deviations in `docs/AGENT_LOG.md`.

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

- Editing `docs/SPEC.md`: read assignment files and `docs/agent-guides/workflow.md`.
- Editing `docs/PLAN.md`: read `docs/SPEC.md`, assignment files, and `docs/agent-guides/workflow.md`.
- Designing implementation mechanisms: read `docs/系统架构.md` and `docs/agent-guides/harness-boundary.md`.
- Touching credentials, tools, shell commands, paths, logs, or verification: read `docs/agent-guides/safety-and-verification.md`.
- Completing a task: update `docs/PLAN.md` and `docs/AGENT_LOG.md` when the task type requires it.

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
