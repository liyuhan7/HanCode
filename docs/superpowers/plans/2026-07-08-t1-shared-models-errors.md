# T1 Shared Models And Errors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement HanCode's shared phase, status, result, risk, and structured error primitives for later harness modules.

**Architecture:** Keep T1 as a small foundation layer: `models.py` owns reusable enums and serializable operation results, while `errors.py` owns structured error payloads and exceptions. Use standard-library `Enum` and `dataclass` so later modules can reuse the types without adding runtime complexity.

**Tech Stack:** Python 3.11+ project target, standard-library `dataclasses`, `enum`, and `typing`; pytest for tests; ruff and mypy for quality gates.

## Global Constraints

- Current task is `docs/PLAN.md` T1 only.
- Allowed implementation files: `src/hancode/models.py`, `src/hancode/errors.py`.
- Allowed tests: `tests/test_models.py`, `tests/test_errors.py`.
- Required phases: `spec`, `plan`, `code`, `test`, `review`, `deliver`.
- Required task statuses: `created`, `running`, `blocked`, `failed`, `completed`, `inconsistent`.
- `OperationResult.status` must use a restricted operation status enum, not arbitrary strings such as `ok`.
- Structured errors must include `code`, `message`, `hint`, and `details`.
- No workspace, config, phase gate, agent loop, tool execution, checkpoint, or feedback behavior belongs in T1.

---

### Task 1: Shared T1 Foundation Types

**Files:**
- Create: `src/hancode/models.py`
- Create: `src/hancode/errors.py`
- Create: `tests/test_models.py`
- Create: `tests/test_errors.py`
- Modify after verification: `docs/PLAN.md`
- Modify after verification: `docs/AGENT_LOG.md`

**Interfaces:**
- Produces: `Phase(str, Enum)` with values `spec`, `plan`, `code`, `test`, `review`, `deliver`.
- Produces: `TaskStatus(str, Enum)` with values `created`, `running`, `blocked`, `failed`, `completed`, `inconsistent`.
- Produces: `OperationStatus(str, Enum)` with values `succeeded`, `blocked`, `failed`.
- Produces: `Risk(level: str, message: str, mitigation: str | None = None).to_dict()`.
- Produces: `StructuredError(code: str, message: str, hint: str, details: Mapping[str, object] | None = None).to_dict()`.
- Produces: `HanCodeError(structured_error: StructuredError)`.
- Produces: `OperationResult(status: OperationStatus, message: str, error: StructuredError | None = None, data: Mapping[str, object] | None = None, risks: Sequence[Risk] = ())`.

- [ ] **Step 1: Write the failing tests**

```python
def test_operation_result_rejects_unknown_status() -> None:
    with pytest.raises(ValueError):
        OperationResult.from_values(status="ok", message="done")
```

- [ ] **Step 2: Run tests to verify red**

Run:

```powershell
python -m pytest tests/test_models.py tests/test_errors.py -v
```

Expected: fail because `hancode.models` and `hancode.errors` are not implemented yet.

- [ ] **Step 3: Write minimal implementation**

Implement the exact interfaces above with dataclasses, enum validation, and `to_dict()` helpers. Keep JSON-oriented output primitive: strings, dicts, lists, and `None`.

- [ ] **Step 4: Run T1 verification**

Run:

```powershell
python -m pytest tests/test_models.py tests/test_errors.py -v
python -m ruff check src/hancode/models.py src/hancode/errors.py tests/test_models.py tests/test_errors.py
python -m mypy src/hancode/models.py src/hancode/errors.py
```

Expected: pytest and ruff pass. If mypy fails because of the current local cache or Python interpreter baseline issue, rerun with an isolated cache and record both results.

- [ ] **Step 5: Update process docs**

Update `docs/PLAN.md` T1 with final status, verification result, and commit hash after the commit exists. Update `docs/AGENT_LOG.md` with task context, red evidence, green evidence, verification commands, human intervention, and risks.

- [ ] **Step 6: Commit**

Use Chinese after the colon:

```powershell
git add src/hancode/models.py src/hancode/errors.py tests/test_models.py tests/test_errors.py docs/PLAN.md docs/AGENT_LOG.md docs/superpowers/plans/2026-07-08-t1-shared-models-errors.md
git commit -m "feat: 完成 T1 共享模型与结构化错误"
```
