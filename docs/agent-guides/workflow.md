# Workflow Guide

Use this guide when planning, sequencing, or completing work.

## Rules File Boundary

Agent rules, prompts, configuration files, skill files, and documentation are
development aids. They do not count as delivered harness implementation.

Any required harness mechanism must be implemented in source code and verified
by tests. A rule file can guide an agent, but it cannot replace deterministic
guardrail, parser, feedback, memory, configuration, or credential code.

## Phase Gate

The repository is currently in specification and planning.

Before implementation code begins, all must be complete:

1. `docs/SPEC.md`
2. `docs/PLAN.md`
3. cold-start validation by a different coding agent
4. revisions recorded in `docs/SPEC_PROCESS.md`

Before this gate, work may update only:

- project rules
- specs
- plans
- process notes
- logs
- README planning sections
- documentation placeholders

Do not create or modify implementation modules under `src/hancode/` before the
gate passes.

## Required Superpowers Flow

The assignment expects this sequence:

1. `brainstorming`
2. `writing-plans`
3. `using-git-worktrees`
4. `subagent-driven-development` or `executing-plans`
5. `test-driven-development`
6. `requesting-code-review`
7. `finishing-a-development-branch`

If you deviate, record the deviation and reason in `docs/AGENT_LOG.md`.

Do not skip directly from idea to implementation. Do not implement code before
`docs/SPEC.md`, `docs/PLAN.md`, and cold-start validation are complete.

## Brainstorming And SPEC Evidence

`docs/SPEC_PROCESS.md` must record how the spec and plan were generated with agent
collaboration.

It should include:

- key brainstorming questions
- which questions changed the original design
- at least 3 rounds of important iteration
- AI suggestions the student accepted
- AI suggestions the student overruled or corrected
- why those choices were made
- before/after diffs for important revisions

## Cold-Start Validation

Before implementation, use a different coding agent from the main development
agent in a fresh session.

Provide only:

- `docs/SPEC.md`
- `docs/PLAN.md`

Do not provide:

- previous chat history
- hidden context
- oral clarification
- memory from the main agent session

Ask the second agent to attempt 1-2 tasks and pause when uncertain rather than
guessing.

Record in `docs/SPEC_PROCESS.md`:

- second agent used
- tasks attempted
- context provided
- where the agent paused
- what it misunderstood
- whether the issue was caused by unclear spec or agent error
- how `docs/SPEC.md` or `docs/PLAN.md` was revised
- before/after differences for important revisions

## Git, Worktree, And PR Discipline

After the phase gate passes, use a separate git worktree and feature branch for
each independent feature or major task.

Each implementation task should map to:

- one `docs/PLAN.md` task
- one focused subagent session
- one feature branch or worktree
- one pull request or clearly recorded merge decision

Do not batch unrelated features into one commit or pull request.

Each commit or pull request description should record:

- the `docs/PLAN.md` task ID
- the subagent or tool used
- the tests run
- human modifications made after agent output
- known limitations or follow-up items

After a task is completed, update `docs/PLAN.md` with final status, commit hash,
verification result, and remaining notes if any.

Avoid working directly on `main` except for repository bootstrap or
documentation-only corrections.

## TDD Rules

For implementation tasks:

1. write the failing test
2. run it and confirm expected failure
3. write minimal implementation
4. run the test and confirm pass
5. refactor
6. rerun relevant verification

Do not backfill tests after implementation.

A task is not TDD-compliant unless the expected failing test was observed before
implementation.

Record meaningful TDD evidence in `docs/AGENT_LOG.md`, especially for core harness
mechanisms.

## Review Gate

Each implementation task needs two checks.

Spec compliance review checks whether the change:

- satisfies the relevant `docs/SPEC.md` requirement
- matches the `docs/PLAN.md` task scope
- avoids implementing unstated features
- preserves the harness boundary
- includes deterministic tests for the mechanism
- avoids relying on prompt-only behavior for required mechanisms

Code quality review checks whether the change:

- keeps module responsibilities clear
- avoids duplicating logic
- has readable names and simple control flow
- handles errors explicitly
- avoids leaking secrets
- remains testable without a real LLM where required
- avoids unnecessary dependencies
- avoids unrelated file changes

Critical findings must be fixed before moving to the next task.

## Documentation Evidence

After task completion, update:

- `docs/PLAN.md` with status, commit hash, and verification result
- `docs/AGENT_LOG.md` with agent activity, prompts/context, human intervention, and lessons
- `docs/SPEC_PROCESS.md` for spec or plan iteration evidence

`docs/AGENT_LOG.md` entries should include timestamp, task ID, Superpowers skill
used, agent used, key prompt or context choices, subagent output summary, commit
hash or PR link, human intervention, and lesson learned.

Do not document an implementation as complete before it is implemented and
verified.

## Agent Behavior Rules

When working in this repository, agents must:

- read the relevant `docs/SPEC.md` and `docs/PLAN.md` sections before making changes
- stay within the current task scope
- avoid unrelated refactoring
- avoid unnecessary dependencies
- explain assumptions when requirements are unclear
- prefer small, reviewable changes
- run or request the relevant verification command
- report failures honestly
- avoid claiming completion without evidence

When uncertain, ask a focused question or record an assumption rather than
silently inventing project behavior.
