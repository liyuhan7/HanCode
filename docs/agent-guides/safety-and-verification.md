# Safety And Verification Guide

Use this guide when touching credentials, paths, tools, shell commands,
verification, logs, or completion status.

## Credential Safety

Never commit real credentials, API keys, tokens, passwords, or secrets.

Credential-related behavior must obey these rules:

- Prefer operating-system credential storage through `keyring`.
- Use `.env` only as a local development fallback.
- Do not commit `.env`.
- Do not print secret values in logs, terminal output, errors, tests, README examples, screenshots, or `AGENT_LOG.md`.
- Credential status checks may report presence or absence, not the secret value.
- Credential update commands must not echo secret values.
- Credential clear commands should remove stored credentials.
- Test credentials must be fake placeholders.

Before committing, check that no real credential appears in:

- source code
- documentation
- tests
- logs
- `.env`
- terminal transcripts
- screenshots
- README examples
- `AGENT_LOG.md`

## Workspace Safety

All file operations must be scoped to the configured workspace.

The harness must not read, write, delete, or modify files outside the configured
workspace unless an explicit, tested policy allows it.

Tools should return structured results with:

- success flag
- action name
- output or error summary
- exit code, if applicable
- stdout, if applicable
- stderr, if applicable

Do not allow tool execution to silently fail.

Do not allow tools to leak secrets through logs, exceptions, or test snapshots.

## Dangerous Actions

Dangerous actions may include:

- editing business code before SPEC and PLAN exist
- editing business code outside code phase
- modifying or deleting assignment instructions without explicit user request
- deleting teacher-provided tests, grading scripts, or sample data
- bypassing tests or grading scripts
- writing outside the workspace
- reading sensitive files
- deleting files
- destructive shell commands
- commands containing `rm -rf /`
- commands that remove project history
- commands that access secrets
- external publishing
- network actions when disabled
- system-level configuration changes

Guardrails must block or require approval before execution.

## Course Project Artifacts

Course-project tasks should maintain:

- `SPEC.md`
- `PLAN.md`
- `REVIEW.md`
- `TEST_REPORT.md`
- `KNOWLEDGE.md`
- `DELIVERABLES.md`
- `trace.jsonl`
- checkpoint manifests

`KNOWLEDGE.md` and `DELIVERABLES.md` are required delivery artifacts. If tests
are skipped, `TEST_REPORT.md` must record the reason and risk.

## Verification Commands

Prefer these commands when relevant:

```powershell
python -m pytest
python -m ruff check src tests
python -m mypy src
```

If `make` is available and configured, use:

```powershell
make check
```

When Docker distribution exists, verify:

```powershell
docker build -t hancode .
docker run --rm hancode --help
```

For documentation-only changes, verify by reading changed files with:

```powershell
Get-Content -Raw -Encoding UTF8 <path>
```

Also check `git status --short`.

## Completion Criteria

Do not claim completion without fresh verification evidence.

Do not mark a task as complete unless all relevant conditions are met:

- required tests were written before implementation
- expected failing tests were observed
- implementation makes the tests pass
- relevant verification commands were run
- results were checked
- `PLAN.md` was updated when required
- `AGENT_LOG.md` was updated when required
- no real credentials were introduced
- no unrelated files were modified
- any workflow deviation was recorded
- spec compliance review passed
- code quality review passed

A task is not complete merely because an agent says it is complete.

Completion requires evidence.

For documentation-only map changes, tests are not required unless runtime code
or validation scripts changed.
