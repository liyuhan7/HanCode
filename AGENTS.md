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

## Codex Operating Contract

This repository assumes a Codex agent working in the real local workspace
`D:\agent-leanring\HanCode`, not a hypothetical sandbox-only project copy.

- Use Chinese for user interaction unless the user explicitly asks for another language.
- Base decisions on real repository files, real command output, and real test results.
- Understand the current request, boundary, goal, and acceptance criteria before coding.
- Write a short task plan before implementation: scope, dependency order, files, tests, and done criteria.
- Work one small task at a time; use an isolated branch, worktree, or execution session per task.
- Prefer the minimum viable implementation first; keep module boundaries and shared interfaces stable.
- Make every change traceable: what changed, why, how it was verified, and what the result was.

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

Implementation admission and execution rules:

- Implement only work that maps to a clear `docs/PLAN.md` task card.
- Confirm the task ID, scope, allowed file range, and acceptance criteria before editing code.
- Keep changes minimal; avoid unrelated refactors and never overwrite user changes.
- Read the relevant context before modifying files.
- Do not use prompts, comments, or docs as substitutes for required harness mechanisms.
- Core mechanisms must stay deterministic, testable, and auditable through MockLLM, stubs, or other repeatable tests.
- Handle failures as structured feedback, not blind retries; keep errors explicit enough to support repair.
- Use command results as ground truth. If tests, lint, type check, or runtime verification fail, report the failure and next correction path instead of claiming success.

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
- Confirm the failing test result before writing the implementation, then rerun verification after the change.
- Required harness mechanisms must be deterministic code, not prompts, rules, or hosted-agent behavior.
- Course assignment files, teacher tests, grading scripts, and sample data are protected by policy.
- Core mechanisms must be testable with MockLLM or stubs, without network or a real LLM.
- Define stable models, states, errors, and results before spreading new interfaces across modules.
- Prefer structured errors with clear cause and repair direction over vague exceptions.
- CI quality gates should cover tests, lint, and type checking at minimum; add build or demo checks when the task needs them.
- Never commit real credentials, API keys, tokens, or secrets.
- Do not print secret values in logs, errors, README examples, tests, or agent records.
- Stay within the task scope and avoid unrelated refactors.
- Keep code and docs aligned: when task scope requires it, update plan, log, tests, README, and CI together.
- Do not claim completion without fresh verification evidence.
- "Runs once" is not enough: completion requires correct boundaries, error handling, synchronized docs, and fresh verification evidence.
- Human developers keep final authority over design tradeoffs, scope, and acceptance criteria.

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

For implementation tasks, final reporting should include what changed, why it
changed, how it was verified, the verification result, and any remaining risk
or unfinished work.

## Final Rule

HanCode must prove its core behavior through engineering mechanisms. If removing
the real LLM makes a claimed mechanism untestable, that mechanism is not
sufficiently implemented.
