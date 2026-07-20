# HanCode 实现计划

> 状态：冷启动后实现准备完成
> 项目类型：A · Coding Agent Harness
> 项目定位：面向学生课程项目的轻量级 Coding Agent Harness
> 实现原则：`docs/SPEC.md`、`docs/PLAN.md`、冷启动验证和 `docs/SPEC_PROCESS.md` 修订记录已完成；正式实现从 T1 开始逐任务 TDD 推进。
> Agentic workers：实现任务必须按任务卡逐项执行，并采用 TDD：先红、再绿、再重构。
> M1 分组策略：T1-T7 合并为 M1 基础骨架里程碑，统一在 `feature/M1` 分支开发，单次 PR 合并。M1 内各任务仍按 TDD 逐个推进并独立提交。

---

## 1. 项目定位

HanCode 是一个为学生课程项目调校的 Coding Agent Harness。它的核心不是让 AI 更快替学生完成作业，而是让 AI 辅助课程项目开发过程可控、可追踪、可回退、可复盘、可沉淀。

HanCode 的主线保持为：

* Feedback Loop：管理测试信号分类与反馈回灌，驱动 Agent 针对性修复。
* Checkpoint Rollback：管理代码修改前快照与失败后的可回退恢复。
* Tool Policy：管理工具权限、路径边界和课程文件保护。
* Phase Mode：管理 spec、plan、code、test、review、deliver 六阶段权限。
* Workspace 分层：管理项目级上下文与任务级上下文隔离。
* Knowledge Delivery：管理最终复盘、错误记录和知识沉淀。

HanCode 的核心交付不是 prompt、规则文件或宿主 Coding Agent 的能力，而是本仓库自实现的 Harness kernel。

---

## 2. 全局规则

* 遵循工作流：brainstorming -> writing-plans -> using-git-worktrees -> subagent-driven-development / executing-plans -> test-driven-development -> requesting-code-review -> finishing-a-development-branch。
* `docs/SPEC.md`、`docs/PLAN.md`、冷启动验证和 `docs/SPEC_PROCESS.md` 修订记录已完成；现在可以按任务卡修改 `src/hancode/` 下对应 harness kernel 模块。
* 实现任务必须使用 TDD：先写失败测试并观察红色结果，再写最小实现，再重构。
* 每个里程碑使用独立 worktree / 分支、单次 PR 合并：
  * M1（T1-T7）→ `feature/M1`
  * M2（T8-T10）→ `feature/M2`
  * M3（T11-T15）→ `feature/M3`
  * M4（T16-T18）→ `feature/M4`
  * M5（T19-T21）→ `feature/M5`
  * M6（T22-T23）→ `feature/M6`
  * M7（T24-T27）→ `feature/M7`
* 里程碑内各任务仍按 TDD 逐个推进、独立提交。
* 每个任务完成后更新本文件状态、提交 hash、验证结果，并在 `docs/AGENT_LOG.md` 记录过程证据。
* 核心机制测试不得依赖网络、真实 LLM、真实 API key 或宿主 Coding Agent 能力。
* 不得提交真实凭据，不得在日志、trace、README、测试快照或错误信息中打印 secret。
* 不引入 LangChain `AgentExecutor`、AutoGen、CrewAI、LlamaIndex agent runner 或宿主 Coding Agent runner 充当交付 harness 内核。
* `state.json` 是唯一机器状态源；Markdown 产物可读可编辑，但不作为状态机唯一依据。
* `docs/SPEC.md` 是需求契约；`docs/系统架构.md` 是实现组织参考；二者冲突时以 `docs/SPEC.md` 为准。
* 每个任务的“非目标 / 边界”必须遵守，避免一次任务扩大范围。

---

## 3. MVP 与 post-MVP 边界

### 3.1 MVP 必须完成

* Python 3.11+ 包结构、CLI 入口和 MockLLM 模式。
* Project Workspace / Task Workspace 文件系统隔离。
* `spec -> plan -> code -> test -> review -> deliver` 六阶段路由与门禁。
* Action schema、ActionParser、MockLLM、AgentLoop。
* ToolRegistry、ToolExecutor、FileTools。
* PathClassifier、ToolPolicy、课程文件保护和受限测试命令。
* TraceLogger、CheckpointManager、Rollback、retry budget。
* FeedbackBuilder 的确定性失败分类与 observation 回灌。
* ContextBuilder 的 phase-based 最小上下文选择。
* TEST_REPORT、REVIEW、KNOWLEDGE、DELIVERABLES 生成。
* MockLLM 机制演示：policy denial、测试失败反馈、retry、强制 rollback。
* Python package build 与 CI unit-test job。

### 3.2 post-MVP

* 单 task 单活跃 runner 的并发锁。
* 跨会话 observation 恢复与完整上下文重放；T21 已提供显式 `run(task_id, resume=True)` 的 blocked 恢复入口，但恢复时重新构造上下文。
* pending checkpoint 的启动崩溃恢复。
* `confirm_before_write` 写前人工确认。
* Docker demo image。
* 复杂 TUI。
* WebUI。
* 多语言测试命令扩展。
* 完整 Git 分支管理。
* 真实 LLM provider smoke test 作为 CI 必需项。

---

## 4. 任务状态图例

| 标记  | 含义           |
| --- | ------------ |
| [ ] | 未开始          |
| [~] | 进行中          |
| [x] | 已完成          |
| [!] | 阻塞           |
| [>] | 延后到 post-MVP |

---

## 5. 任务依赖图

```text
M0 规划与冷启动
  T0 规划文档一致性与冷启动验证准备

M1 基础骨架（含 Action Schema）
  T1 共享模型与错误类型
    -> T2 Workspace 初始化
    -> T3 ConfigLoader
    -> T4 StateStore
    -> T5 Phase 枚举与 PhaseGate
    -> T6 WorkspaceRouter
    -> T7 Action Schema

M2 ActionParser 与 Loop 基础
  T8 ActionParser
    -> T9 MockLLM
    -> T10 AgentLoop 最小循环骨架

M3 Tool 与 Governance
  T11 ToolResult 与 ToolRegistry
    -> T12 FileTools 最小读写
    -> T13 PathClassifier
    -> T14 ToolPolicy 基础规则
    -> T15 Course File Protection

M4 Trace 与可恢复状态
  T16 TraceLogger
    -> T17 CheckpointManager
    -> T18 RollbackManager

M5 Context 与 Feedback
  T19 ContextBuilder
  T20 FeedbackBuilder 失败分类
    -> T21 AgentLoop 集成 feedback / retry / rollback

M6 Delivery 与 Demo
  T22 Delivery Artifacts 生成
    -> T23 MockLLM 机制 Demo

M7 CLI / 凭据 / CI
  T24 CLI 最小入口
    -> T25 CredentialProvider
    -> T26 Package Build 与 CI
    -> T27 README 运行与分发文档
```

### 5.1 并行建议

```text
T3 ConfigLoader 与 T4 StateStore 可在 T1 后并行。
T7 Action Schema 与 T11 ToolResult / ToolRegistry 可在 T1 后并行（T7 属于 M1，T11 属于 M3）。
T16 TraceLogger 可在 T1 / T4 后提前做，不必等待完整 AgentLoop。
T19 ContextBuilder 可在 T2 / T4 / T5 后独立推进。
T20 FeedbackBuilder 可在 T11 后独立推进，不必等待完整 AgentLoop。
T24 CLI 可先实现 --help / init 骨架，demo 命令等 T23 后接入。
```

---

## 6. 里程碑

| 里程碑           | 完成条件                                                                    | 对应任务    |
| ------------- | ----------------------------------------------------------------------- | ------- |
| M0 计划可冷启动     | 陌生 agent 仅凭 `docs/SPEC.md` + `docs/PLAN.md` 可尝试 1-2 个任务，并把问题记录到 `docs/SPEC_PROCESS.md` | T0      |
| M1 骨架可跑       | workspace、config、state、phase、router、action schema 可独立测试；缺 SPEC / PLAN 时拒绝进入 code | T1-T7   |
| M2 最小 loop 可跑 | MockLLM 能驱动 parse -> policy -> tool -> observation 的受控链路                | T8-T15  |
| M3 可恢复状态成立    | trace、checkpoint、rollback 可独立测试，secret 不泄露                              | T16-T18 |
| M4 主贡献闭环成立    | 测试失败 -> feedback -> retry -> rollback 可在 MockLLM 下确定性复现                 | T19-T21 |
| M5 Demo 可证明机制 | MockLLM demo 生成 trace、TEST_REPORT、REVIEW、KNOWLEDGE、DELIVERABLES         | T22-T23 |
| M6 可交付        | CLI、凭据边界、package build、CI、README 完成                                     | T24-T27 |

---

# 7. 任务卡片

---

## T0：规划文档一致性与冷启动验证准备

| 元信息           | 值          |
| ------------- | ---------- |
| 状态            | [x] 已完成    |
| 依赖            | 无          |
| 可并行           | 不并行；实现前置任务 |
| Worktree / PR | 当前规划分支     |
| 主贡献相关         | 否          |
| Commit        | 未提交；本轮为规划文档修订 |
| 验证            | UTF-8 读取、锚点扫描、路径一致性扫描、git status |
| 备注            | OpenCode + GLM-5.2 已完成扩展上下文冷启动验证；暴露问题已回写 T1 / T2 任务卡 |

### 目标

确保 `docs/SPEC.md`、`docs/PLAN.md`、`docs/SPEC_PROCESS.md`、`docs/AGENT_LOG.md`、`README.md`、`AGENTS.md` 的路径、术语、任务编号和 Source of Truth 一致，并准备冷启动验证。

### 涉及文件

* `docs/PLAN.md`
* `docs/SPEC_PROCESS.md`
* `docs/AGENT_LOG.md`
* `README.md`
* `AGENTS.md`

### SPEC 依据

* 通用项目要求中的规划、过程记录和冷启动验证要求。
* A 类 Coding Agent Harness 对 SPEC、PLAN、MockLLM 测试和自实现机制的要求。

### 接口契约

```text
输入：`docs/SPEC.md`、`docs/系统架构.md`、课程通用要求、A 类 Harness 要求。
输出：可执行、可追溯、可冷启动验证的 `docs/PLAN.md`。
不变量：实现任务不得在冷启动验证完成前修改 src/hancode/ harness kernel。
错误处理：若冷启动 agent 无法执行某任务，记录到 `docs/SPEC_PROCESS.md` 并修订 SPEC / PLAN。
```

### 预期失败测试 / 文档检查

* `test_plan_contains_fine_grained_tasks`
* `test_source_of_truth_paths_are_consistent`
* `test_plan_has_cold_start_validation_section`
* `test_plan_tasks_use_fixed_card_fields`

### 实现要点

* 将粗粒度任务拆为机制级任务。
* 每个任务包含目标、涉及文件、SPEC 依据、接口契约、预期失败测试、验证步骤、完成判定、非目标。
* 冷启动验证前不新增 runtime 实现模块。

### 验证步骤

```powershell
Get-Content -Raw -Encoding UTF8 docs/PLAN.md
Select-String -Path docs/PLAN.md -Pattern '## T1','## T27','# 8. 需求→任务追溯','# 9. 冷启动验证结果'
git status --short
```

### 完成判定

* `docs/PLAN.md` 可被陌生 agent 直接用于执行任务。
* 文档中路径、术语和任务编号一致。
* `docs/SPEC_PROCESS.md` 中记录冷启动验证结果和修订点。

### 非目标 / 边界

* 不实现 harness kernel。
* 不改 `src/hancode/`。
* 不启动真实 LLM。

---

# M1：基础骨架

---

## T1：共享模型与错误类型

| 元信息           | 值                     |
| ------------- | --------------------- |
| 状态            | [x] 已完成               |
| 依赖            | T0                    |
| 可并行           | 不并行；后续模块依赖共享类型        |
| Worktree / PR | `feature/M1`         |
| 主贡献相关         | 否，基础支撑                |
| Commit        | 已合并到 `main`            |

### 目标

建立跨模块共享的基础数据结构和结构化错误格式，避免后续各模块重复定义 status、phase、error、result。

### 涉及文件

* `src/hancode/models.py`
* `src/hancode/errors.py`
* `tests/test_models.py`
* `tests/test_errors.py`

### SPEC 依据

* `state.json` 状态约束。
* Trace、ToolResult、PolicyDecision、FeedbackReport、AgentRunResult 等结构化输出要求。
* `docs/SPEC.md` §10.21.5「结构化错误与策略拒绝」字段契约。
* 核心机制必须可测试、可序列化、可审查。

### 接口契约

```python
class Phase(str, Enum): ...
class TaskStatus(str, Enum): ...
class StructuredError: ...
class OperationResult: ...
class Risk: ...
```

输入：枚举值、错误字段、结果字段。
输出：统一模型对象，可序列化为 dict / JSON。
不变量：Phase 只能包含 spec、plan、code、test、review、deliver；TaskStatus 只能包含 created、running、blocked、failed、completed、inconsistent。
错误处理：未知枚举值应被拒绝或触发明确错误。

### 预期失败测试

* `test_task_status_allows_only_defined_values`
* `test_phase_allows_only_six_project_phases`
* `test_structured_error_has_required_spec_fields`
* `test_operation_result_serializes_to_dict`
* `test_operation_result_rejects_unknown_status`

### 实现要点

* 优先使用标准库 `dataclass`、`Enum`。
* 必要时使用 pydantic，但不引入复杂依赖。
* `StructuredError` 顶层字段必须与 `docs/SPEC.md` §10.21.5 对齐：至少包含 `error_code`、`message`、`phase`、`denied_rule`、`suggested_fix`；policy denial、parse failure、tool failure、credential error 复用同一套字段名，不得并行引入 `code` / `hint` / `rule_id` 等旧契约。
* 冷启动验证发现 `OperationResult.status` 若使用任意字符串会污染后续 AgentLoop / ToolResult / ResultBuilder 状态边界；正式实现必须使用受限状态类型。若表示任务状态，复用 `TaskStatus`；若表示操作状态，定义独立 enum，不允许 `"ok"` 这类未声明状态。
* `OperationResult.to_dict()` 必须能递归序列化枚举、共享 dataclass、list / tuple / mapping 等嵌套共享模型，避免后续 ToolResult / AgentRunResult 在 JSON 导出时残留不可序列化对象。

### 验证步骤

```powershell
python -m pytest tests/test_models.py tests/test_errors.py -v
python -m ruff check src/hancode/models.py src/hancode/errors.py tests/test_models.py tests/test_errors.py
python -m mypy src/hancode/models.py src/hancode/errors.py
```

### 完成判定

* 共享模型测试全绿。
* 后续模块能复用同一套 phase、status、error、result。
* 所有策略拒绝、解析失败、工具失败和凭据错误都复用统一的顶层错误字段。
* 嵌套共享模型可稳定序列化为 dict / JSON。

### 实际验证

* Red：`$env:PYTHONPATH='src'; python -m pytest tests/test_models.py tests/test_errors.py -v` 失败，原因为 `ModuleNotFoundError: No module named 'hancode.errors'`。
* Green：`$env:PYTHONPATH='src'; python -m pytest tests/test_models.py tests/test_errors.py -v` 通过，8 passed。
* 全量测试：`$env:PYTHONPATH='src'; python -m pytest` 通过，27 passed；当前 worktree 下 pytest cache 写入有 warning。
* Lint：`python -m ruff check src/hancode/models.py src/hancode/errors.py tests/test_models.py tests/test_errors.py` 通过；当前 worktree 下 ruff cache 写入有 warning。
* Type check：标准 `python -m mypy src/hancode/models.py src/hancode/errors.py` 因 mypy 2.2.0 sqlite cache `disk I/O error` 失败；使用 `$env:PYTHONPATH='src'; python -m mypy src/hancode/models.py src/hancode/errors.py --cache-dir $env:TEMP\hancode-mypy-cache-t1 --show-traceback` 通过，no issues found in 2 source files。
* 环境备注：当前 `python` 为 3.10.11，低于项目 `pyproject.toml` 的 Python 3.11+ 目标；本轮未修改解释器配置。
* 2026-07-09 两阶段评审先发现当前 commit `895065e` 仍实现旧版错误字段 `code` / `hint` / `details`，且 `OperationResult` 未保证嵌套共享模型递归 JSON 序列化；随后已在当前工作树返工并重新验证。
* 返工验证：`$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests/test_errors.py tests/test_models.py -v -p no:cacheprovider` 先红后绿，最终 8 passed。
* 返工验证：`$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m ruff check src/hancode/models.py src/hancode/errors.py tests/test_models.py tests/test_errors.py --no-cache` 通过。
* 返工验证：`$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m mypy src/hancode/models.py src/hancode/errors.py --cache-dir $env:TEMP\hancode-mypy-t1-review` 通过，no issues found in 2 source files。
* 返工验证：`$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest -p no:cacheprovider` 通过，27 passed。

### 非目标 / 边界

* 不实现 workspace。
* 不实现 config。
* 不实现 agent loop。

---

## T2：Workspace 初始化

| 元信息           | 值                       |
| ------------- | ----------------------- |
| 状态            | [x] 已完成                 |
| 依赖            | T1                      |
| 可并行           | 不并行；后续任务依赖 workspace 结构 |
| Worktree / PR | `feature/M1`              |
| 主贡献相关         | 否，支撑维度                  |
| Commit        | 已合并到 `main`              |

### 目标

实现 Project Workspace 与 Task Workspace 初始化，使 `.hancode/` 能稳定保存项目记忆、任务状态、trace、checkpoint 和阶段产物。

### 涉及文件

* `src/hancode/workspace.py`
* `tests/test_workspace.py`

### SPEC 依据

* Project Workspace 与 Task Workspace。
* 文件持久化映射。
* Workspace 与任务隔离验收。

### 接口契约

```python
from pathlib import Path

def init_project_workspace(project_root: Path, project_id: str, course_name: str, assignment_name: str) -> Path: ...
def init_task_workspace(project_root: Path, task_id: str) -> Path: ...
def task_path(project_root: Path, task_id: str) -> Path: ...
```

输入：课程项目根目录、project ID、course name、assignment name、task ID。
输出：`.hancode/` 与 `.hancode/tasks/<task_id>/` 的实际路径。
不变量：不同 task 的 `state.json`、`trace.jsonl`、`history.jsonl`、`checkpoints/` 不混用。
错误处理：路径不在 project root 内时返回结构化错误或抛出项目自定义异常。

### 预期失败测试

* `test_workspace_initializes_project_files`
* `test_task_workspace_initializes_required_artifacts`
* `test_workspace_has_separate_history`
* `test_workspace_rejects_path_outside_project_root`
* `test_project_workspace_init_preserves_existing_files`
* `test_task_workspace_init_preserves_existing_state_and_trace`
* `test_task_workspace_requires_initialized_project_workspace`

### 实现要点

* 使用 `Path.resolve()` 做 root 内路径约束。
* 初始化 Markdown 文件时写入最小标题，不写空白文件。
* 初始化 `trace.jsonl`、`history.jsonl` 为空文件。
* 初始化 `checkpoints/` 目录，但不创建真实 checkpoint。
* 冷启动验证发现直接重跑 init 会覆盖 `state.json`、`trace.jsonl`、`history.jsonl` 和 Markdown 产物；正式实现必须保持初始化幂等：只创建缺失文件，不覆盖已有 evidence。需要 reset 时必须另设显式 reset 语义，不放在 init 中。
* `init_task_workspace` 必须要求 Project Workspace 已初始化且包含有效 `project.json` 和项目级记忆文件；不得静默创建半完整 `.hancode/`。

### 验证步骤

```powershell
uv run pytest tests/test_workspace.py -v
uv run ruff check src/hancode/workspace.py tests/test_workspace.py
uv run mypy src/hancode/workspace.py
```

### 完成判定

* 能在 `tmp_path` 中生成完整 workspace。
* 不同 task 的状态、trace、history、checkpoint 互不混用。
* 重复初始化不会清空已有状态、trace、history、checkpoint 或阶段产物。
* 未初始化 Project Workspace 时，创建 Task Workspace 会明确失败。

### 非目标 / 边界

* 不实现 state 读写逻辑。
* 不实现 checkpoint 快照。
* 不实现 ContextBuilder。

### 实际验证

* Red-1：`test_task_workspace_state_json_contains_all_required_fields` 失败，缺失 8 个字段（`goal`、`checkpoint_seq`、`tests_run`、`test_status_consumed`、`phase_completed`、`source_edits_this_phase`、`rollback_required`、`rollback_done`）。
* Red-2：`test_task_workspace_init_preserves_existing_state_and_trace` 失败，`FileExistsError`——`init_task_workspace` 不幂等。
* Red-3：`test_workspace_rejects_tasks_directory_escape_via_link` 失败；`task_path()` 仅校验 `candidate` 位于已解析 `tasks_root` 下，未拒绝 `.hancode/tasks` 经 symlink / junction 逃逸到项目根外。
* Green-1：补齐 `state.json` 初始字段，对齐架构文档 §8.4 全部 18 个字段。
* Green-2：`init_task_workspace` 幂等化——`mkdir(exist_ok=True)` + `state.json`/`trace.jsonl`/`history.jsonl` 只在不存在时写入。
* Green-3：`task_path()` 同时要求已解析 `candidate` 保持在已解析 `tasks_root` 与 `.hancode` workspace root 内，阻止目录链接造成的路径逃逸。
* 旧测试 `test_task_workspace_initializes_required_artifacts` 的 state.json 精确等值断言已同步更新为完整字段集。
* 覆盖补强：`test_task_workspace_init_preserves_existing_checkpoints_and_artifacts` 首次运行即通过，确认 checkpoint 与阶段产物幂等性行为已存在，但此前缺少回归测试保护。
* 代码评审后补测：`test_task_workspace_rejects_incomplete_project_metadata`（4 个参数化场景：缺字段/空值/错误版本）、`test_task_workspace_rejects_missing_memory_files`（Markdown 记忆文件缺失）。
* 任务测试：`$env:PYTHONPATH='src'; uv run --no-sync pytest tests/test_workspace.py -v -p no:cacheprovider` 通过，20 passed。
* 全量测试：`$env:PYTHONPATH='src'; uv run --no-sync pytest -p no:cacheprovider` 在当前 worktree 状态通过，47 passed；其中包含用户已批准同步到该分支但尚未并入 T2 提交的 `tests/test_course_project_scaffold.py` 变更。
* Lint：`$env:PYTHONPATH='src'; uv run --no-sync ruff check src/hancode/workspace.py tests/test_workspace.py --no-cache` 通过。
* Type check：`$env:PYTHONPATH='src'; uv run --no-sync mypy src/hancode/workspace.py --cache-dir $env:TEMP\hancode-mypy-t2-fix` 通过，no issues found in 1 source file。
* Linux CI 回归修复：`make test` 在 Linux / Python 3.11.15 下失败，原因是 `Path("C:/outside").is_absolute()` 在 POSIX 语义下不识别 Windows 风格绝对路径，导致 `test_workspace_rejects_path_outside_project_root[C:/outside]` 收到 `invalid_task_id` 而不是 `workspace_path_outside_project_root`。
* Linux CI Green：`task_path()` 增加 `PureWindowsPath(task_id).is_absolute()` 判定后，Windows 本地验证通过：`$env:PYTHONPATH='src'; uv run --no-sync pytest tests/test_workspace.py -v -p no:cacheprovider` 20 passed；`$env:PYTHONPATH='src'; uv run --no-sync pytest -p no:cacheprovider` 47 passed；`ruff` 与 `mypy` 均通过。
* 评审遗留项（不阻塞 T2 合并）：(1) `workspace_version` 字段需同步到架构文档 §8.3；(2) init 错误的 `phase="spec"` 语义需 spec 决策（Phase 枚举是否加 INIT 或允许 None）。

---

## T3：ConfigLoader

| 元信息           | 值                     |
| ------------- | --------------------- |
| 状态            | [x] 已完成（返工后）       |
| 依赖            | T1, T2                |
| 可并行           | 可与 T4 并行              |
| Worktree / PR | `feature/M1`          |
| 主贡献相关         | 否，支撑维度                |
| Commit        | `e7fcee3` + `e3ddce9` — T3 初版与安全返工 |

### 目标

实现配置加载、默认值、非法配置拒绝，使 AgentLoop、ToolPolicy、ContextBuilder 共享同一配置对象。

### 涉及文件

* `src/hancode/config.py`
* `tests/test_config.py`

### SPEC 依据

* 配置加载与运行约束；T3 只加载共享配置输入，固定 phase 策略由 T5、工具权限决策由 T14 实现。
* 凭据不得明文写入配置。
* `max_steps`、`retry_budget`、测试命令、保护路径和可写根等当前配置字段必须显式校验；phase 规则由 T5、工具权限由 T14 负责。

### 接口契约

```python
from pathlib import Path

class HanCodeConfig: ...

def load_config(project_root: Path, task_id: str | None = None) -> HanCodeConfig: ...
```

输入：project root、可选 task ID、`.hancode/project.json`。
输出：`HanCodeConfig`。
不变量：配置不得包含明文真实凭据；凭据只保存来源类型或引用。
错误处理：`max_steps <= 0`、`retry_budget < 0`、未知 provider、非法路径配置必须拒绝启动。

### 预期失败测试

* `test_config_loads_defaults`
* `test_config_loads_project_json`
* `test_invalid_retry_budget_is_rejected`
* `test_invalid_max_steps_is_rejected`
* `test_config_does_not_accept_plaintext_secret`

### 实现要点

* 默认值：

  * `max_steps = 30`
  * `retry_budget = 2`
  * `max_checkpoints_per_task = 5`
  * `max_context_chars = 24000`
  * `max_trace_events = 40`
* 默认 protected patterns 是不可移除基线，包含作业说明、教师测试、评分脚本、样例数据、`.env`、凭据目录和常见密钥文件；项目配置只能追加规则。
* 不读取真实 secret，只读取 secret source 配置。

* `max_context_chars = 24000`、`max_trace_events = 40` 的权威来源是 2026-07-10 已批准的 T3 开发计划；本任务不再使用旧的 `12000/20` 草案值。

### 实现结果

* 新增冻结且使用 `slots` 的 `HanCodeConfig`；`load_config()` 从 `.hancode/project.json` 合并项目级覆盖与默认值，并可通过现有 `task_path()` 安全派生可选 `task_root`。
* 结构化拒绝未初始化 workspace、损坏或类型/范围非法配置、未知 provider、明文凭据字段和可写根路径逃逸；错误不回显明文值。
* 可写根仅接受 project root 内的相对目录，规范化 `src/**` 形式，并同时防御 POSIX/Windows 绝对路径、`..` 与符号链接逃逸。
* 明确不读取 task `state.json`、环境变量值、`.env` 或真实凭据，也不实现 CredentialProvider、路由或 ContextBuilder。
* `project.json` 仅接受 T2 元数据与当前 T3 活动字段；`stack`、`interactive`、`confirm_before_write`、`workspace_root` 等未来字段留给后续任务。
* 远程 provider 必须同时提供非空 `model_name` 与受支持的 `credential_source`；`mock`、`local` 可无凭据来源。
* `examples/.hancode-template/project.json` 与当前 schema 对齐；脚手架断言不再要求未来的 `stack` 字段。

### 验证步骤

```powershell
uv run --no-sync pytest tests/test_config.py -v -p no:cacheprovider
uv run --no-sync ruff check src/hancode/config.py tests/test_config.py --no-cache
uv run --no-sync mypy src/hancode/config.py --cache-dir "$env:TEMP\hancode-mypy-t3-review"
uv run --no-sync pytest -p no:cacheprovider
```

### 完成判定

* 配置错误会清晰失败。
* 默认配置足够驱动 MockLLM demo。
* 配置对象可被 ToolPolicy、ContextBuilder、AgentLoop 复用。
* 2026-07-10 初版实测：专项 25 passed；全量 72 passed。
* 2026-07-10 返工后实测：专项 42 passed；Ruff 通过；MyPy 通过；全量 89 passed。

### 非目标 / 边界

* 不实现 CredentialProvider。
* 不实现 CLI 配置命令。
* 不实现真实 provider 调用。

---

## T4：StateStore

| 元信息           | 值                   |
| ------------- | ------------------- |
| 状态            | [x] 已完成（专项、静态门禁与全量回归通过） |
| 依赖            | T1, T2              |
| 可并行           | 可与 T3 并行            |
| Worktree / PR | `feature/M1`        |
| 主贡献相关         | 否，控制流基础             |
| Commit        | `84ba160` — `feat: 完成 T4 StateStore` |

### 目标

实现 `state.json` 的机器状态读写和一致性检查，使状态机、PhaseGate、WorkspaceRouter 和 ToolPolicy 都只依赖机器状态源。

### 涉及文件

* `src/hancode/state.py`
* `tests/test_state.py`

### SPEC 依据

* `state.json` 是唯一机器状态源。
* Markdown 产物不作为状态机判断的唯一依据。
* 启动时发现 artifact drift 应进入 `inconsistent`，不得自动修复。

### 接口契约

```python
from pathlib import Path

class TaskState: ...

def load_state(task_root: Path) -> TaskState: ...
def save_state(task_root: Path, state: TaskState) -> None: ...
def reconcile_state(task_root: Path, state: TaskState) -> TaskState: ...
```

输入：task root、已有 `state.json`。
输出：`TaskState`。
不变量：`state.json` 是唯一机器状态源；发现 artifact 漂移时进入 `inconsistent`，不自动回写为 completed。
错误处理：JSON 损坏时返回 blocked / inconsistent 错误摘要或抛出结构化状态错误。

### 预期失败测试

* `test_state_json_is_single_machine_source`
* `test_state_parse_error_blocks_task`
* `test_reconcile_detects_artifact_drift_without_auto_fix`
* `test_state_save_preserves_allowed_status_values`
* `test_files_changed_updated_only_by_code_write`

### 实现要点

* `TaskState` 至少包含：

  * `task_id`
  * `status`
  * `current_phase`
  * `retry_budget_remaining`
  * `latest_checkpoint`
  * `latest_test_status`
  * `artifacts`
  * `files_changed`
  * `inconsistent`
* `reconcile_state` 只检测漂移，不自动把 Markdown 文件存在转换为 artifact completed。
* 损坏 JSON 不应导致高风险工具继续执行。

### 实现结果

* 新增冻结、slots 化的 `TaskState`，严格解析 schema v1 的 18 个字段，复用 `Phase`、`TaskStatus`，校验合法状态、阶段、测试状态、非负计数及固定 artifact / phase 键。
* `load_state()` 只读取 `state.json`，损坏 JSON、缺失字段、未知字段和非法枚举统一返回脱敏的结构化 `state_parse_error`。
* `save_state()` 使用临时文件 + 原子替换；写失败保留原文件并返回 `state_write_error`。校验 `task_id` 一致性，防止跨 task 串写；`files_changed` 仅允许持久化 code 且目标为 code/test 时更新。
* `reconcile_state()` 双向检测 artifact 与文件存在性漂移，返回 `inconsistent`，不回写 artifact 标志、不自动修复、也不自动清除既有 inconsistent 状态。
* `phase_completed` 与 `artifacts` 使用不可变映射，避免绕过运行时校验后写入非法状态。
* 不涉及 router、trace、Markdown artifact 生成或 T5 以后机制。

### 验证步骤

```powershell
uv run --no-sync pytest tests/test_state.py -v -p no:cacheprovider
uv run --no-sync ruff check src/hancode/state.py tests/test_state.py --no-cache
uv run --no-sync mypy src/hancode/state.py --no-incremental
```

### 完成判定

* `state.json` 读写稳定。
* artifact drift 被检测为 inconsistent。
* 不会从文件系统反向自动修复状态。
* 实际专项验证：23 passed；Ruff 与 MyPy 通过。
* 两阶段评审：首次评审发现 3 个 Important，修复后 Spec 合规与代码质量复评均 PASS。
* 全量回归复核已通过：`uv run --no-sync pytest -p no:cacheprovider` 为 112 passed；此前曾受 Windows pytest 临时目录 ACL 影响（27 passed、81 setup errors），该中间失败不代表当前代码失败。

### 非目标 / 边界

* 不实现 router。
* 不实现 trace。
* 不实现 Markdown artifact 内容生成。

---

## T5：Phase 枚举与 PhaseGate

| 元信息           | 值                  |
| ------------- | ------------------ |
| 状态            | [x] 已完成 |
| 依赖            | T1, T4             |
| 可并行           | 可与 T6 前置设计并行       |
| Worktree / PR | `feature/M1`        |
| 主贡献相关         | 否，控制流基础            |
| Commit        | `3c32408` — `feat: 完成 T5 PhaseGate` |

### 目标

实现六阶段定义和阶段写入权限判断，使非 code phase 不能修改业务代码，各 phase 只能写对应阶段产物。

### 涉及文件

* `src/hancode/phases.py`
* `tests/test_phase_gate.py`

### SPEC 依据

* 课程项目 Phase Gate。
* `spec -> plan -> code -> test -> review -> deliver` 六阶段流程。
* 只有 code phase 可以主动修改业务代码。

### 接口契约

```python
def can_write_artifact(phase: Phase, artifact_name: str) -> bool: ...
def can_write_source(phase: Phase, state: TaskState) -> bool: ...
```

输入：phase、artifact name、TaskState。
输出：无副作用的布尔判定；结构化拒绝由后续 T14 ToolPolicy 负责。
不变量：artifact 写入白名单固定；source write 只允许 code phase。
错误处理：未知 phase 返回拒绝。

### 预期失败测试

* `test_spec_phase_rejects_source_write`
* `test_plan_phase_rejects_source_write`
* `test_code_phase_allows_source_write_when_prerequisites_ready`
* `test_test_phase_only_writes_test_report`
* `test_review_phase_only_writes_review`
* `test_deliver_phase_rejects_source_write`

### 实现要点

* artifact 写入白名单：

  * spec -> `SPEC.md`
  * plan -> `PLAN.md`
  * test -> `TEST_REPORT.md`
  * review -> `REVIEW.md`
  * deliver -> `KNOWLEDGE.md`, `DELIVERABLES.md`
* 业务源代码写入必须处于 code phase。
* 若 state 为 inconsistent，拒绝 source write。

### 实现结果

* 新增 `hancode.phases`，复用既有 `Phase`、`TaskState`、`TaskStatus`，未重复定义枚举或修改 T4 StateStore。
* `can_write_artifact()` 以大小写敏感的固定白名单限制阶段产物：spec=`SPEC.md`、plan=`PLAN.md`、code=空集、test=`TEST_REPORT.md`、review=`REVIEW.md`、deliver=`KNOWLEDGE.md` 与 `DELIVERABLES.md`。
* `can_write_source()` 仅在参数 phase 与 `state.current_phase` 都为 code、SPEC/PLAN 均完成、`inconsistent=False` 且 status 非 `INCONSISTENT` 时返回 true；非法运行时 phase、未知 artifact、前置条件缺失与状态不一致均返回 false。
* 两个接口均为纯函数：不读取文件、不写入 state、不做持久化，不扩展到 router、ToolPolicy、路径分类、checkpoint、trace 或阶段完成门禁。

### 验证步骤

```powershell
$env:PYTHONPATH='src'; $env:UV_CACHE_DIR=Join-Path $env:TEMP 'hancode-uv-cache'; uv run --no-sync pytest tests/test_phase_gate.py -v -p no:cacheprovider
$env:PYTHONPATH='src'; $env:UV_CACHE_DIR=Join-Path $env:TEMP 'hancode-uv-cache'; uv run --no-sync ruff check src/hancode/phases.py tests/test_phase_gate.py --no-cache
$env:PYTHONPATH='src'; $env:UV_CACHE_DIR=Join-Path $env:TEMP 'hancode-uv-cache'; uv run --no-sync mypy src/hancode/phases.py
```

### 完成判定

* 每个 phase 能写哪些 artifact 有明确规则。
* 只有 code phase 允许业务代码修改。
* 实际专项验证：18 passed；Ruff 与 MyPy 通过；全量 pytest：130 passed。
* 两阶段任务评审和最终代码评审无 Critical/Important；普通未知 artifact 名称未显式断言为 Minor，不影响现有固定集合成员判断。
* 本次文档回写按用户要求暂不提交。

### 非目标 / 边界

* 不实现自动路由。
* 不实现 ToolPolicy 路径保护。
* 不执行文件写入。

---

## T6：WorkspaceRouter

| 元信息           | 值                        |
| ------------- | ------------------------ |
| 状态            | [x] 已完成（专项、静态门禁、全量回归与复审通过） |
| 依赖            | T4, T5                   |
| 可并行           | 完成后释放 T8-T10 与 T13-T15   |
| Worktree / PR | `feature/M1`              |
| 主贡献相关         | 否，控制流基础                  |
| Commit        | `2716b9a` — `feat: 完成 T6 WorkspaceRouter`；`2a495bc` — `test: 补充 T6 路由优先级覆盖` |

### 目标

实现无副作用的阶段路由决策，使缺少前置产物时不能进入 code phase，测试失败后进入 review，retry budget 耗尽时要求 rollback。

### 涉及文件

* `src/hancode/router.py`
* `tests/test_router.py`

### SPEC 依据

* WorkspaceRouter。
* Phase Gate。
* 失败恢复数据流。
* retry budget 超限强制 rollback。

### 接口契约

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class RoutingDecision:
    phase: Phase
    reason: str
    rollback_required: bool = False
    blocked: bool = False
    completed: bool = False

def select_next_phase(state: TaskState) -> RoutingDecision: ...
```

输入：`TaskState`。
输出：`RoutingDecision`。
不变量：router 是纯函数，不直接写 `state.json`、不创建文件、不执行 rollback。
错误处理：`inconsistent`、`blocked`、`failed` 状态返回保持当前 phase 的阻塞决策；retry 耗尽但没有 checkpoint 时进入 review 并标记阻塞。完成态保持六阶段 `Phase` 枚举，使用 `phase=deliver` 与 `completed=True` 表示。

### 预期失败测试

* `test_missing_spec_routes_to_spec`
* `test_missing_plan_routes_to_plan`
* `test_spec_and_plan_complete_routes_to_code`
* `test_failed_test_routes_to_review`
* `test_retry_budget_exhausted_requires_rollback`
* `test_router_is_pure_and_does_not_write_state`

### 实现要点

* router 只读 `TaskState.artifacts`、`latest_test_status`、`retry_budget_remaining`、`status`。
* 测试失败后路由到 review。
* retry budget 耗尽时 `rollback_required=True`。
* 不解析 Markdown 内容。

### 实现结果

* 新增冻结、slots 化的 `RoutingDecision` 与 `select_next_phase()`；函数只读取合法 `TaskState`，不接收路径、不读写 `state.json`、不执行工具、LLM 或 rollback。
* 路由优先级依次为不一致/终止状态、SPEC、PLAN、未消费测试失败及 retry/checkpoint、code、test、review、deliverable，最后返回 `Phase.DELIVER + completed=True` 的完成决策。
* retry 耗尽且有 checkpoint 时返回 `review/retry_budget_exhausted` 并要求 rollback；无 checkpoint 时返回 `review/retry_budget_exhausted_no_checkpoint` 且阻塞，避免虚构可恢复路径。
* 22 项测试覆盖任务卡的 6 个命名用例、终止状态、失败消费防死循环、无 checkpoint 阻塞、完整阶段推进、两个 deliverable、无副作用，以及 SPEC/PLAN/失败测试和两个 deliverable 同时缺失时的确定性优先级。

### 验证步骤

```powershell
$env:PYTHONPATH='src'; $env:UV_CACHE_DIR=Join-Path $env:TEMP 'hancode-uv-cache'; uv run --no-sync pytest tests/test_router.py -v -p no:cacheprovider
uv run --no-sync ruff check src/hancode/router.py tests/test_router.py --no-cache
uv run --no-sync mypy src/hancode/router.py --no-incremental
uv run --no-sync pytest -p no:cacheprovider
git diff --check
```

### 完成判定

* Router 只返回决策，不写文件、不改 state。
* 所有阶段推进依据 `TaskState`，不解析 Markdown 内容。
* 实际专项验证：22 passed；Ruff 与 MyPy 通过；补齐优先级碰撞测试后的全量回归 152 passed。
* 最终审查初次发现 Important：缺少多条件优先级碰撞回归测试；补测后复审无 Critical、Important 或 Minor。

### 非目标 / 边界

* 不执行 rollback。
* 不调用 LLM。
* 不执行工具。

---

## T7：Action Schema

| 元信息           | 值                     |
| ------------- | --------------------- |
| 状态            | [x] 已完成               |
| 依赖            | T1, T6                |
| 可并行           | 可与 T11 并行             |
| Worktree / PR | `feature/M1`           |
| 主贡献相关         | 是，主循环输入协议             |
| Commit        | `18ce975` — `feat: 完成 T7 Action Schema` |

### 目标

定义模型输出 action 的结构化数据协议，使 LLM / MockLLM 只能通过可解析、可校验的 action 与 Harness 交互。

### 涉及文件

* `src/hancode/actions.py`
* `tests/test_action_schema.py`

### SPEC 依据

* Action 解析与校验。
* 模型产生的 action 必须使用确定性 schema。
* malformed action、unknown tool、missing required fields 不得执行。

### 接口契约

```python
class Action: ...
class ActionType(str, Enum): ...
class ParseError: ...
```

Action 字段至少包含：

```text
tool_name
args
reason
phase
```

输入：模型产生的候选 action 数据。
输出：Action 或 ParseError。
不变量：action 不携带 `target_kind`；目标路径类型由 PathClassifier 推导。
错误处理：缺少 required field、unknown action type、unknown tool 返回结构化错误。

### 预期失败测试

* `test_action_requires_tool_name`
* `test_action_requires_phase`
* `test_write_action_requires_reason_field`
* `test_finish_action_has_no_tool_side_effect`
* `test_unknown_action_type_is_invalid`

### 实现要点

* `finish_phase` action 表示模型请求阶段结束，但是否 completed 由 ResultBuilder / AgentLoop 状态判定。
* write action 包括 `write_file`、`edit_file`。
* `run_tests` 不允许携带任意 shell command，实际命令来自 config。

### 实现结果

* 新增冻结、slots 化的 `Action`、`ActionType` 和 `ParseError`，并以 `Action.from_values()` 作为类型化候选 action 的确定性校验入口；原始 dict 的字段解析仍由 T8 实现。
* `ActionType` 固定为 `tool_call`、`finish_phase`、`ask_user`、`final`；action 不含 `target_kind`。
* 七个 MVP 工具使用固定参数 schema：`read_file(path)`、`list_files()` / `list_files(path)`、`search_text(query)`、`write_file(path, content)`、`edit_file(path, old_string, new_string)`、`run_tests()`、`rollback_last_checkpoint()`。
* `write_file` 和 `edit_file` 必须有非空 `reason`；`run_tests` 不接收 `command`；非法类型、phase、工具、参数和控制 action 工具名均返回不回显候选值的 `ParseError`。
* `run_tests` 与 `rollback_last_checkpoint` 是唯一的无参数工具；即使未来工具已注册但未声明 schema，也会 fail-closed 拒绝。
* `Action` 防御性复制并冻结 `args`，直接构造也会拒绝不合 schema 的对象。
* 实际验证：专项 31 passed；Ruff、MyPy 通过；审查修正后全量 183 passed；`git diff --check` 通过。

### 验证步骤

```powershell
$env:PYTHONPATH='src'; $env:UV_CACHE_DIR=Join-Path $env:TEMP 'hancode-uv-cache'; uv run --no-sync pytest tests/test_action_schema.py -v -p no:cacheprovider
uv run --no-sync ruff check src/hancode/actions.py tests/test_action_schema.py --no-cache
uv run --no-sync mypy src/hancode/actions.py --no-incremental
uv run --no-sync pytest -p no:cacheprovider
git diff --check
```

### 完成判定

* action schema 能表达所有 MVP 工具调用。
* 非法 action 无法进入 policy 和 tool。

### 非目标 / 边界

* 不实现 parser。
* 不实现 tool dispatch。
* 不判断 action 是否安全。

---

# M2：ActionParser 与 Loop 基础

---

## T8：ActionParser

| 元信息           | 值                     |
| ------------- | --------------------- |
| 状态            | [x] 已完成               |
| 依赖            | T7                    |
| 可并行           | 可与 T9 并行              |
| Worktree / PR | `feature/M2`          |
| 主贡献相关         | 是，主循环输入校验             |
| Commit        | `4afeef1`            |

### 目标

把 LLM / MockLLM 原始输出解析为合法 Action 或 ParseError，保证未通过 parser 的 action 不会进入 policy 和 tool。

### 涉及文件

* `src/hancode/actions.py`
* `tests/test_action_parser.py`

### SPEC 依据

* Action 解析与校验。
* malformed actions、unknown action types、missing required fields 必须被拒绝。
* 解析失败必须变成 observation 并写入 trace。

### 接口契约

```python
def parse_action(raw: dict[str, object], current_phase: Phase) -> Action | ParseError: ...
```

输入：LLM / MockLLM 原始输出及可信的当前 `Phase`。
输出：Action 或 ParseError。
不变量：顶层字段必须恰为 `type`、`phase`、`tool_name`、`args`、`reason`；parser 按 payload 类型、缺失字段、多余字段、`Action.from_values()`、action phase 与当前 phase 的顺序校验，不做安全策略判断。
错误处理：解析失败返回 ParseError，至少包含 `error_code`、`message`、`phase`、`denied_rule`、`suggested_fix`；其中 parse error 的 `denied_rule` 为 `null`。

### 预期失败测试

* `test_parse_valid_tool_actions`
* `test_parse_rejects_invalid_payload_boundary`
* `test_parse_preserves_action_schema_errors`
* `test_parse_rejects_valid_action_for_a_different_phase`
* `test_parse_does_not_mutate_input_or_return_mutable_arguments`

### 实现要点

* parser 支持 dict 输入，不依赖真实 LLM 字符串格式。
* 后续真实 LLM provider 可在 adapter 中把文本转成 dict。
* ParseError 应可被 FeedbackBuilder 转成 observation。
* 实现已新增 `parse_action()`：边界错误使用稳定的 `invalid_action_payload`、`missing_action_fields`、`unexpected_action_fields`、`phase_mismatch` 错误码，schema 错误原样返回 T7 的 `Action.from_values()` 结果。

### 验证步骤

```powershell
$env:PYTHONPATH='src'; $env:UV_CACHE_DIR=Join-Path $env:TEMP 'hancode-uv-cache'
uv run --no-sync pytest tests/test_action_parser.py -v -p no:cacheprovider
uv run --no-sync pytest tests/test_action_schema.py tests/test_action_parser.py -v -p no:cacheprovider
uv run --no-sync ruff check src/hancode/actions.py tests/test_action_parser.py --no-cache
uv run --no-sync mypy src/hancode/actions.py --no-incremental
uv run --no-sync pytest -p no:cacheprovider
git diff --check
```

### 完成判定

* 合法 action 可解析。
* 非法 action 不会进入 tool。
* 错误信息可诊断。
* 验证证据：parser 专项 12 passed；T7+T8 回归 43 passed；ruff 与 mypy 通过；控制代理在沙箱外全量验证 195 passed in 3.83s；`git diff --check` 通过。

### 非目标 / 边界

* 不执行 action。
* 不判断 policy。
* 不调用 LLM。

---

## T9：MockLLM

| 元信息           | 值                |
| ------------- | ---------------- |
| 状态            | [x] 已完成          |
| 依赖            | T7               |
| 可并行           | 可与 T8 并行         |
| Worktree / PR | `feature/M2`     |
| 主贡献相关         | 是，确定性测试基础        |
| Commit        | `a86fd44`（源码/初始测试）；`93ae774`（初始文档回填）；`3bba8cb`（malformed raw action 与深层返回值隔离审查补测）；`e9d14ae`（审查验证记录纠正）；`a397ccf`（提交记录修正）；`c9d0adc`（耗尽契约对齐）；后续跨文档契约同步（审查发现）：`54cc89b`（T9 审计回填）、`0410035`（T10 耗尽状态对齐）、`45b966e`（MockLLM 耗尽上位契约同步）、`8b87619`（MockLLM 隔离示例同步） |

### 目标

实现确定性的 MockLLM，用于离线测试和机制演示，使核心机制不依赖真实 LLM、网络或 API key。

### 涉及文件

* `src/hancode/llm.py`
* `tests/test_llm.py`

### SPEC 依据

* LLM 抽象与 MockLLM。
* 核心机制测试必须能替换真实 LLM。
* MockLLM 必须稳定复现指定 action 序列。

### 接口契约

```python
from typing import Protocol

class LLMClient(Protocol):
    def next_action(self, context: dict[str, object]) -> dict[str, object]: ...

class MockLLMExhausted(RuntimeError):
    error_code = "mock_llm_exhausted"
    suggested_fix = "Provide another mock action or stop the loop as blocked."

class MockLLM:
    def __init__(self, actions: list[dict[str, object]]) -> None: ...
    @property
    def contexts(self) -> tuple[dict[str, object], ...]: ...
    def next_action(self, context: dict[str, object]) -> dict[str, object]: ...
```

输入：结构化 context。
输出：预设 action。
不变量：MockLLM 不调用网络，不读取真实凭据。
错误处理：action 序列耗尽时先记录 context，再抛出可诊断的 `MockLLMExhausted`。T10 `AgentLoop` 捕获该异常后负责映射为 `blocked`；MockLLM 不返回 blocked dict。

### 预期失败测试

* `test_mock_llm_returns_actions_in_input_order`
* `test_mock_llm_records_deep_copied_contexts`
* `test_mock_llm_is_deterministic`
* `test_mock_llm_returns_raw_action_that_action_parser_can_parse`
* `test_mock_llm_returns_malformed_raw_actions_without_schema_validation`
* `test_mock_llm_exhaustion_has_stable_diagnostic_fields`（耗尽时抛出 `MockLLMExhausted`）
* `test_exhausted_mock_llm_call_still_records_context`
* `test_mock_llm_isolates_input_actions_and_returned_actions`
* `test_mock_llm_keeps_later_action_deeply_isolated_from_earlier_return`
* `test_mock_llm_isolates_input_context_and_public_history`

### 实现要点

* 每次调用记录 context，便于测试 ContextBuilder 是否生效。
* 不使用随机数。
* MockLLM 返回的数据应能被 ActionParser 解析。

### 验证步骤

```powershell
uv run pytest tests/test_llm.py -v
uv run ruff check src/hancode/llm.py tests/test_llm.py
uv run mypy src/hancode/llm.py
```

### 完成判定

* MockLLM 能稳定驱动 AgentLoop。
* 核心测试不依赖真实 LLM 和网络。

### 实际验证

* Red：先新增 `tests/test_llm.py`，执行 `$env:PYTHONPATH='src'; $env:UV_CACHE_DIR=Join-Path $env:TEMP 'hancode-uv-cache'; uv run --no-sync pytest tests/test_llm.py -v -p no:cacheprovider`；因 `hancode.llm` 不存在，收集阶段出现预期 `ModuleNotFoundError`。
* Green：新增仅使用标准库的 `src/hancode/llm.py` 后，以同一命令复跑，8 passed in 0.04s。覆盖 action 输入顺序、context 记录、等价实例确定性、parser-compatible 原始 action、耗尽异常诊断和耗尽调用记录，以及 action/context/history 的深拷贝隔离。
* T8+T9 回归：`$env:PYTHONPATH='src'; $env:UV_CACHE_DIR=Join-Path $env:TEMP 'hancode-uv-cache'; uv run --no-sync pytest tests/test_action_parser.py tests/test_llm.py -v -p no:cacheprovider`：20 passed in 0.05s。
* 静态检查：`uv run --no-sync ruff check src/hancode/llm.py tests/test_llm.py --no-cache` 通过；`uv run --no-sync mypy src/hancode/llm.py --no-incremental`：Success: no issues found in 1 source file。
* 全量：受限沙箱执行 `uv run --no-sync pytest -p no:cacheprovider` 时，pytest 的 `tmp_path` 在 `C:\\Users\\24125\\AppData\\Local\\Temp\\pytest-of-24125\\pytest-*\\.lock` 创建锁文件遭遇 `PermissionError`，结果为 106 passed、97 errors；控制端在沙箱外以同一命令复验：203 passed in 6.29s。
* `git diff --check` 通过。

### 耗尽职责边界

`MockLLM` 在耗尽时会先记录本次 context，再抛出 `MockLLMExhausted("MockLLM action sequence exhausted.")`，其固定 `error_code` 为 `mock_llm_exhausted` 并提供 suggested fix。T9 不将该异常转换为 blocked loop state；映射职责属于 T10 AgentLoop。

### 非目标 / 边界

* 不实现真实 ProviderAdapter。
* 不实现 prompt 模板优化。
* 不读取 credential。

---

## T10：AgentLoop 最小循环骨架

| 元信息           | 值                                                |
| ------------- | ------------------------------------------------ |
| 状态            | [x] 已完成（专项、静态门禁、回归、全量复验与审查通过）                 |
| 依赖            | T6, T8, T9                                       |
| 可并行           | 依赖注入 stub policy / stub tool，可先于真实 ToolPolicy 集成 |
| Worktree / PR | `feature/M2`                                    |
| 主贡献相关         | 是，主循环基础                                          |
| Commit        | `2f7dc5f` — `feat: 完成 T10 AgentLoop`             |

### 目标

实现最小 agent loop：build context -> call LLM -> parse action -> policy -> tool -> observation -> stop，并受 `max_steps` 限制。

### 涉及文件

* `src/hancode/agent_loop.py`
* `tests/test_agent_loop.py`

### SPEC 依据

* AgentLoop 主循环。
* LLM 不直接访问文件系统。
* action 必须经过 parser、policy、tool dispatch。
* max_steps 防止无限循环。

### 接口契约

```python
class AgentLoop:
    def run(self, task_id: str) -> AgentRunResult: ...
```

输入：task_id、LLM、ContextBuilder stub、Policy stub、ToolRegistry stub、FeedbackBuilder stub、StateStore。
输出：AgentRunResult，包含 status、steps、tool calls、risks、final observation。
不变量：所有工具执行前必须经过 parser 与 policy。
错误处理：T10 的 `AgentLoop` 捕获 `MockLLMExhausted` 后固定映射为 `blocked`，并构造完整结构化错误：`error_code`、`message`、当前 `phase`、`denied_rule=None` 和 `suggested_fix`；parse error、policy denial、超过 max_steps 与当前不支持的 `ask_user` 均固定返回 `blocked`，且不执行工具。

### 预期失败测试

* `test_agent_loop_calls_llm_with_context`
* `test_agent_loop_parses_action_before_policy`
* `test_agent_loop_calls_policy_before_tool`
* `test_policy_denial_does_not_execute_tool`
* `test_max_steps_prevents_infinite_loop`
* `test_finish_action_stops_loop`
* `test_final_action_stops_loop`
* `test_tool_observation_is_fed_into_next_context`
* `test_parse_error_blocks_without_policy_or_tool`
* `test_mock_llm_exhaustion_returns_structured_blocked_result`
* `test_terminal_routing_stops_before_llm`
* `test_ask_user_blocks_without_tool`
* `test_agent_loop_rejects_non_positive_max_steps`

### 实现要点

* 第一版 AgentLoop 使用依赖注入的 stub policy、stub tool registry、stub feedback builder。
* `finish` action 只停止循环，不直接判定 completed。
* 工具调用顺序应可通过 spy 对象测试。
* 捕获 `MockLLMExhausted` 时使用当前运行 phase 填充结构化错误的 `phase`，不把 T9 异常改造成策略拒绝；`denied_rule` 固定为 `None`。

### 实现结果

* 新增最小的依赖注入 Protocol：StateStore、ContextBuilder、Policy、ToolRegistry 与 FeedbackBuilder；它们只定义 T10 所需端口，不替代后续 T11/T14/T19/T20 的真实实现。
* 新增冻结、slots 化 `AgentRunResult`，返回 `status`、`steps`、已 dispatch 的工具名、预留 `risks`、最终 observation 与结构化 error。
* loop 先使用现有 `select_next_phase()` 取得 phase；每步复制 context、调用 LLM、解析 action、执行 policy，仅允许 `tool_call` 进入 `dispatch()`；工具 observation 回灌到下一次 LLM context。
* `finish_phase` 与 `final` 都在 policy allow 后停止并返回 `running`，不直接标记 completed；路由已完成时才以 0 步返回 `completed`。T10 不持久化 state、不解释 ToolResult、不处理 retry、rollback 或 trace。

### 实际验证

* Red：先新增 `tests/test_agent_loop.py`，执行 `$env:PYTHONPATH='src'; $env:UV_CACHE_DIR=Join-Path $env:TEMP 'hancode-uv-cache'; uv run --no-sync pytest tests/test_agent_loop.py -v -p no:cacheprovider`；因 `hancode.agent_loop` 不存在，收集阶段出现预期 `ModuleNotFoundError`。
* Green：新增最小实现后 T10 专项 12 passed；审查补充 `final` 的独立停止语义回归测试后，专项为 13 passed in 0.04s。
* T8+T9+T10 回归：`uv run --no-sync pytest tests/test_action_parser.py tests/test_llm.py tests/test_agent_loop.py -v -p no:cacheprovider`：35 passed in 0.09s。
* 静态检查：`uv run --no-sync ruff check src/hancode/agent_loop.py tests/test_agent_loop.py --no-cache` 通过；`uv run --no-sync mypy src/hancode/agent_loop.py --no-incremental`：Success: no issues found in 1 source file。
* 全量：受限沙箱以 `uv run --no-sync pytest -p no:cacheprovider` 执行时，pytest 在 `C:\\Users\\24125\\AppData\\Local\\Temp\\pytest-of-24125\\pytest-*\\.lock` 创建锁文件遭遇 `PermissionError`，结果为 120 passed、97 errors；控制端在沙箱外以同一命令复验：218 passed in 1.75s。
* 独立只读审查：无 Critical/Important；补充 `final` stop 回归测试后关闭 Minor。`git diff --check` 通过。

### 验证步骤

```powershell
uv run pytest tests/test_agent_loop.py -v
uv run ruff check src/hancode/agent_loop.py tests/test_agent_loop.py
uv run mypy src/hancode/agent_loop.py
```

### 完成判定

* MockLLM 可驱动最小 loop。
* parse error、policy denial、max_steps 均不会执行工具。
* 控制流顺序可被测试证明。

### 非目标 / 边界

* 不实现真实 FileTools。
* 不实现 retry budget。
* 不实现 rollback 集成。
* 不生成最终 Markdown 报告。

---

# M3：Tool 与 Governance

---

## T11：ToolResult 与 ToolRegistry

| 元信息           | 值                     |
| ------------- | --------------------- |
| 状态            | [x] 已完成（专项、静态门禁、回归、全量复验与审查通过） |
| 依赖            | T1, T7                |
| 可并行           | 可与 T8/T9 并行           |
| Worktree / PR | `feature/M3`          |
| 主贡献相关         | 是，工具调度基础              |
| Commit        | `a2309db` — `feat: 完成 T11 工具注册与分发` |

### 目标

实现工具注册、工具查找和结构化工具结果，保证工具异常不会静默失败。

### 涉及文件

* `src/hancode/tools.py`
* `tests/test_tool_registry.py`

### SPEC 依据

* ToolRegistry 与工具分发。
* 工具层必须返回结构化结果。
* 未注册工具不得执行。

### 接口契约

```python
class ToolResult: ...
class ToolRegistry:
    def register(self, name: str, tool: Callable[..., ToolResult]) -> None: ...
    def dispatch(self, action: Action) -> ToolResult: ...
```

输入：Action、已注册工具。
输出：ToolResult。
不变量：unknown tool 返回 failed result；工具异常转成结构化错误。
错误处理：不得让异常直接泄露 secret 或完整环境变量。

### 预期失败测试

* `test_register_and_dispatch_tool`
* `test_unknown_tool_returns_structured_error`
* `test_tool_exception_returns_failed_result`
* `test_tool_result_contains_action_name_success_and_error_summary`

### 实现要点

* ToolResult 至少包含：

  * `success`
  * `action_name`
  * `output`
  * `error_summary`
  * `exit_code`
  * `stdout`
  * `stderr`
* dispatch 不直接做 policy 判断，policy 在 AgentLoop 中先执行。

### 验证步骤

```powershell
uv run pytest tests/test_tool_registry.py -v
uv run ruff check src/hancode/tools.py tests/test_tool_registry.py
uv run mypy src/hancode/tools.py
```

### 完成判定

* 所有工具结果格式统一。
* 工具异常不会静默失败。

### 实际验证

* Red：新增 `tests/test_tool_registry.py` 后，执行 `$env:PYTHONPATH='src'; $env:UV_CACHE_DIR=Join-Path $env:TEMP 'hancode-uv-cache'; uv run --no-sync pytest tests/test_tool_registry.py -v -p no:cacheprovider`；因 `hancode.tools` 不存在，收集阶段出现预期 `ModuleNotFoundError`。
* Green：新增 `src/hancode/tools.py` 后，专项 8 passed；审查后补齐注册参数与未知工具无副作用覆盖，最终 T11+T10 专项 24 passed in 0.09s。
* 回归：T7-T11 的 Action/LLM/AgentLoop/ToolRegistry 测试 74 passed in 0.12s。
* 静态检查：`uv run --no-sync ruff check src tests --no-cache` 通过；`uv run --no-sync mypy src --no-incremental` 为 `Success: no issues found in 12 source files`。
* 全量：受限沙箱因 pytest 临时目录 `.lock` 的 `PermissionError` 得到 129 passed、97 errors；沙箱外复验 `uv run --no-sync pytest -p no:cacheprovider` 为 226 passed in 6.07s。
* `git diff --check` 通过。

### 审查与剩余风险

* 独立只读审查发现 AgentLoop 测试 spy 未随 `ToolRegistry.dispatch() -> ToolResult` 契约更新，已将其返回类型和 observation 断言对齐；同时补齐重复注册参数和 unknown-tool 无副作用测试。
* `mypy src tests --no-incremental` 仍有 6 项既有错误：`tests/test_llm.py` 的 5 项 `dict` 不变性问题和 `tests/test_agent_loop.py` 的 1 项 Policy Protocol 协变性问题；T11 引入的 ToolRegistry Protocol 错误已消除，剩余问题不在本任务范围。

### 非目标 / 边界

* 不实现具体文件工具。
* 不做路径安全策略。
* 不运行 shell 命令。

---

## T12：FileTools 最小读写

| 元信息           | 值                  |
| ------------- | ------------------ |
| 状态            | [x] 已完成（专项、静态门禁、全量复验与两阶段评审通过） |
| 依赖            | T2, T11            |
| 可并行           | 可与 T13 并行          |
| Worktree / PR | `feature/M3`       |
| 主贡献相关         | 是，工具能力基础           |
| Commit        | `0538bed` — `feat: 完成 T12 文件工具` |

### 目标

实现 workspace 内文件读取、写入、搜索的最小工具能力。

### 涉及文件

* `src/hancode/file_tools.py`
* `tests/test_file_tools.py`

### SPEC 依据

* File tools。
* 工具只能访问当前 workspace 允许路径。
* 所有工具返回 ToolResult。

### 接口契约

```python
def read_file(project_root: Path, path: str) -> ToolResult: ...
def write_file(project_root: Path, path: str, content: str) -> ToolResult: ...
def list_files(project_root: Path, path: str = ".") -> ToolResult: ...
def search_text(project_root: Path, query: str) -> ToolResult: ...
```

输入：project root、相对路径、内容或搜索词。
输出：ToolResult。
不变量：FileTools 做基础 root 检查；更完整的 protected policy 由 ToolPolicy 执行。
错误处理：文件不存在、路径非法、编码错误返回 failed ToolResult。

### 预期失败测试

* `test_read_file_inside_workspace`
* `test_write_file_inside_workspace`
* `test_list_files_inside_workspace`
* `test_search_text_inside_workspace`
* `test_file_tool_rejects_missing_file_with_structured_error`

### 实现要点

* MVP 中 `edit_file` 可暂时退化为整文件替换。
* 所有路径必须 resolve 到 project root 内。
* 输出中不得包含 secret-like 内容的完整展开。

### 验证步骤

```powershell
uv run pytest tests/test_file_tools.py -v
uv run ruff check src/hancode/file_tools.py tests/test_file_tools.py
uv run mypy src/hancode/file_tools.py
```

### 完成判定

* FileTools 返回 ToolResult。
* 文件读取、写入、列出、搜索在 tmp workspace 中可测试。

### 实际验证

* Red：先新增 `tests/test_file_tools.py`，执行 `$env:PYTHONPATH='src'; $env:UV_CACHE_DIR=Join-Path $env:TEMP 'hancode-uv-cache'; uv run --no-sync pytest tests/test_file_tools.py -v -p no:cacheprovider`；因 `hancode.file_tools` 不存在，收集阶段出现预期 `ModuleNotFoundError`。
* Green：新增 `src/hancode/file_tools.py` 后，沙箱外专项为 23 passed、1 skipped；评审新增的脱敏测试和安全边界测试均先观察到预期失败，再以最小修复转绿。
* T11+T12 回归：40 passed、2 skipped；skip 均因当前 Windows 环境不允许创建文件 symlink。
* 静态检查：`uv run --no-sync ruff check src tests --no-cache` 通过；`uv run --no-sync mypy src --no-incremental` 为 `Success: no issues found in 13 source files`。
* 全量：沙箱外 `uv run --no-sync pytest -q -p no:cacheprovider` 为 258 passed、2 skipped in 2.58s；受限沙箱的 tmp_path 测试仍会在 pytest 临时目录 `.lock` 处触发既有 `PermissionError`。
* `git diff --check` 通过。

### 两阶段评审与剩余风险

* 第一阶段契约审查发现带引号赋值、JSON password 和 search query 的脱敏缺口；补失败测试后统一使用 `[REDACTED]` 修复，且未越界实现 T13-T15/T17。
* 第二阶段质量审查发现 search 可经 symlink alias 读取 `.env`，并指出 resolve 异常、Windows 换行与 UTF-8 编码、空 query 边界；均补回归测试并修复。复审确认 T12 范围内无剩余 Critical/Important。
* 非阻断风险：通用 `.npmrc`/YAML/ghp/AKIA 脱敏、恶意并发替换 symlink/junction 的 TOCTOU，以及极端 symlink loop 的统一处理留给后续安全机制；T12 只承诺已批准的最小 secret fixture 与基础 root containment。

### 非目标 / 边界

* 不实现复杂 patch edit。
* 不处理 protected patterns。
* 不运行测试命令。

---

## T13：PathClassifier

| 元信息           | 值                       |
| ------------- | ----------------------- |
| 状态            | [x] 已完成（专项、静态门禁、全量复验与两阶段评审通过） |
| 依赖            | T2, T3                  |
| 可并行           | 可与 T12 并行               |
| Worktree / PR | `feature/M3`            |
| 主贡献相关         | 是，治理护栏基础                |
| Commit        | `6727894` — `feat: 完成 T13 路径分类器` |

### 目标

实现路径三区 / 四区分类，为 ToolPolicy 提供确定性的写入边界判断。

### 涉及文件

* `src/hancode/path_policy.py`
* `tests/test_path_classifier.py`

### SPEC 依据

* 可写 Action 的目标路径由 PathClassifier 推导。
* 课程文件保护。
* 路径逃逸必须被拒绝。

### 接口契约

```python
class PathZone(str, Enum):
    PROTECTED = "protected"
    ARTIFACT = "artifact"
    SOURCE = "source"
    OUT_OF_SCOPE = "out_of_scope"

class PathClassifier:
    def __init__(self, config: HanCodeConfig) -> None: ...
    def classify(self, target: str) -> PathZone: ...
```

输入：已验证的 `HanCodeConfig`、目标相对路径。
输出：PathZone。
不变量：不信任 LLM 自报路径类型；路径仅能归入 `protected`、`artifact`、`source` 或 `out_of_scope`；受保护规则优先于 artifact/source。
错误处理：空路径、绝对路径、`..`、无法 resolve 或 symlink 逃逸一律 `OUT_OF_SCOPE`；相对路径以词法和 canonical 两种 project-relative 表示匹配受保护模式。

### 预期失败测试

* `test_classifies_task_artifact`
* `test_classifies_source_file_under_configured_writable_root`
* `test_classifies_assignment_file_as_protected`
* `test_classifies_teacher_test_as_protected`
* `test_classifies_grading_script_as_protected`
* `test_rejects_path_escape_or_absolute_path`
* `test_rejects_symlink_escape`

### 实现要点

* task root 仅允许直系 `SPEC.md`、`PLAN.md`、`TEST_REPORT.md`、`REVIEW.md`、`KNOWLEDGE.md`、`DELIVERABLES.md` 归入 artifact；其他 task 文件默认 out of scope。
* `state.json`、`history.jsonl`、`trace.jsonl` 与 `checkpoints/**` 始终归入 protected。
* protected patterns 覆盖作业说明、教师测试、评分脚本、样例数据、`.env`、凭据文件，且优先于 artifact/source。
* Windows 路径使用 resolve、POSIX 分隔符和大小写归一化比较；source 只来自配置的 `writable_roots`。

### 验证步骤

```powershell
$env:PYTHONPATH='src'
$env:UV_CACHE_DIR=Join-Path $env:TEMP 'hancode-uv-cache'
uv run --no-sync pytest tests/test_path_classifier.py -v -p no:cacheprovider
uv run --no-sync pytest tests/test_config.py tests/test_path_classifier.py -v -p no:cacheprovider
uv run --no-sync ruff check src/hancode/path_policy.py tests/test_path_classifier.py --no-cache
uv run --no-sync mypy src/hancode/path_policy.py --no-incremental
```

### 完成判定

* 目标路径分类稳定。
* 路径逃逸和 protected 文件可被确定性识别。

### 实际验证

* Red：新增 `tests/test_path_classifier.py` 后，执行 `$env:PYTHONPATH='src'; $env:UV_CACHE_DIR=Join-Path $env:TEMP 'hancode-uv-cache'; uv run --no-sync pytest tests/test_path_classifier.py -v -p no:cacheprovider`；因 `hancode.path_policy` 不存在，收集阶段得到预期 `ModuleNotFoundError`。
* Green：新增 `src/hancode/path_policy.py` 后，同一专项为 29 passed、2 skipped；skip 均因当前 Windows 环境不允许创建文件 symlink。
* T3+T13 联合回归：68 passed、2 skipped；Ruff 通过；MyPy 为 `Success: no issues found in 1 source file`。
* 两阶段评审、全量回归、全量静态检查和 `git diff --check` 的最终记录见 `docs/AGENT_LOG.md`。

### 非目标 / 边界

* 不判断当前 phase。
* 不决定是否 checkpoint。
* 不执行文件写入。

---

## T14：ToolPolicy 基础规则

| 元信息           | 值                         |
| ------------- | ------------------------- |
| 状态            | [x] 已完成（专项、静态门禁、全量回归与两阶段评审通过） |
| 依赖            | T3, T5, T6, T7, T13       |
| 可并行           | 可与 T15 紧密衔接               |
| Worktree / PR | `feature/M3`               |
| 主贡献相关         | 是，治理护栏核心                  |
| Commit        | `0c898e8` — `feat: 完成 T14 基础工具策略` |

### 目标

实现工具执行前的确定性策略判定，拒绝越权工具、缺 reason 写入、非 code phase source write、缺 SPEC/PLAN source write。

### 涉及文件

* `src/hancode/tool_policy.py`
* `tests/test_tool_policy.py`
* `tests/test_agent_loop.py`

### SPEC 依据

* ToolPolicy 治理护栏。
* Phase Gate。
* 缺 SPEC / PLAN 时不得进入 code phase。
* `edit_file` / `write_file` 必须提供 reason。

### 接口契约

```python
@dataclass(frozen=True, slots=True)
class PolicyDecision:
    allowed: bool
    reason: str
    phase: Phase
    requires_checkpoint: bool = False
    denied_rule: str | None = None
    suggested_fix: str = ""

class ToolPolicy:
    def __init__(self, config: HanCodeConfig) -> None: ...
    def evaluate(
        self, *, action: Action, phase: Phase, state: TaskState
    ) -> PolicyDecision: ...
```

输入：构造时传入 `HanCodeConfig`；调用时传入 Action、phase、TaskState。
输出：PolicyDecision，包含 `allowed`、`reason`、`requires_checkpoint`、`denied_rule`、`suggested_fix`；`to_dict()` 使用 `error_code`、`message`、`phase`、`denied_rule`、`suggested_fix` 对齐结构化拒绝契约。
不变量：policy decision 必须由代码完成，不能依赖提示词。
错误处理：拒绝时不得执行工具，并把拒绝原因交给 FeedbackBuilder。

### 预期失败测试

* `test_denies_tool_not_allowed_in_phase`
* `test_defensively_denies_write_without_reason`
* `test_denies_protected_or_out_of_scope_write`
* `test_denies_source_write_when_prerequisite_is_missing`
* `test_edit_file_source_write_requires_checkpoint`
* `test_finish_phase_uses_deterministic_state_gate`
* `test_real_tool_policy_denial_does_not_execute_tool`

### 实现要点

* policy 先检查 Action phase、工具阶段权限和 reason，再检查 write path zone；未知/越界路径 fail-closed。
* 合法 source write 在 code phase 中返回 `requires_checkpoint=True`。
* denial 必须包含 `denied_rule` 和可执行的 `suggested_fix`。
* `finish_phase` 根据 TaskState 对 spec、plan、code、test、review、deliver 进行确定性完成门禁；不读取或写入状态文件。

### 验证步骤

```powershell
$env:PYTHONPATH='src'
$env:UV_CACHE_DIR=Join-Path $env:TEMP 'hancode-uv-cache'
uv run --no-sync pytest tests/test_tool_policy.py tests/test_agent_loop.py -v -p no:cacheprovider
uv run --no-sync pytest tests/test_phase_gate.py tests/test_path_classifier.py tests/test_tool_policy.py tests/test_agent_loop.py -v -p no:cacheprovider
uv run --no-sync ruff check src/hancode/tool_policy.py tests/test_tool_policy.py tests/test_agent_loop.py --no-cache
uv run --no-sync mypy src/hancode/tool_policy.py --no-incremental
uv run --no-sync pytest -p no:cacheprovider
uv run --no-sync ruff check src tests --no-cache
uv run --no-sync mypy src --no-incremental
git diff --check
```

### 完成判定

* policy 可以被 AgentLoop 在 tool 前调用。
* policy denial 可以转成 observation。
* source write 前能明确要求 checkpoint。
* `finish_phase` 不能绕过对应阶段的完成条件。

### 实际验证

* Red：新增 `tests/test_tool_policy.py` 后，专项在收集阶段因 `hancode.tool_policy` 不存在得到预期 `ModuleNotFoundError`。
* Green：最小实现后专项为 22 passed；审查补齐拒绝序列化、六阶段失败门禁、`edit_file` checkpoint 与真实 AgentLoop 拒绝回归后，T14 + AgentLoop 专项为 43 passed。
* 联合回归：T5、T10、T13、T14 为 82 passed、2 skipped；skip 均因当前 Windows 环境不允许创建文件 symlink。
* 全量：沙箱外 `uv run --no-sync pytest -p no:cacheprovider` 为 317 passed、4 skipped in 3.45s；Ruff 全量通过；MyPy `src` 为 `Success: no issues found in 15 source files`；`git diff --check` 通过。

### 非目标 / 边界

* 不实现具体课程文件保护扩展。
* 不执行 checkpoint。
* 不执行工具。

---

## T15：Course File Protection

| 元信息           | 值                              |
| ------------- | ------------------------------ |
| 状态            | [x] 已完成（TDD、聚焦回归、Ruff、MyPy 通过）      |
| 依赖            | T13, T14                       |
| 可并行           | 不并行；属于治理护栏加固                   |
| Worktree / PR | `feature/M3`                      |
| 主贡献相关         | 是，学生课程项目特定化治理                  |
| Commit        | `cfac049 feat: 完成 T15 课程文件保护` |

### 目标

把课程项目保护规则落到 ToolPolicy / PathClassifier 中，禁止 Agent 未经明确授权修改作业说明、教师测试、评分脚本、样例数据和凭据文件。

### 涉及文件

* `src/hancode/config.py`
* `src/hancode/tool_policy.py`
* `tests/test_config.py`
* `tests/test_tool_policy.py`
* `tests/test_agent_loop.py`
* `tests/test_course_file_protection.py`

### SPEC 依据

* 课程文件保护策略。
* 测试失败不得通过删除测试、绕过评分脚本、修改教师测试或忽略失败结果解决。
* 危险动作必须被 block 或 require approval。

### 接口契约

```text
输入：Action path、protected patterns、phase、state、config。
输出：PolicyDecision denied，`denied_rule` 指向 protected file rule，并提供 `suggested_fix`。
不变量：protected 文件默认不能被 Agent 修改或删除。
错误处理：受保护文件写入请求被拒绝，记录可回灌的原因和建议。
```

### 预期失败测试

* `test_policy_protects_assignment_files`
* `test_policy_protects_teacher_tests_or_grading_scripts`
* `test_policy_protects_sample_data`
* `test_policy_protects_env_file`
* `test_test_failure_cannot_be_fixed_by_deleting_teacher_test`

### 实现要点

* protected patterns 包含：

  * assignment、requirements、rubric、course_constraints 四类文件：精确基名、任意扩展名及对应目录；`requirements.*` 覆盖 `requirements.txt`，但不匹配 `requirements-lock.txt` 等前缀变体。
  * teacher tests。
  * grading scripts。
  * sample data。
  * `.env`、`.env.*`、secret、credential 文件。
* MVP 不实现 HITL 审批覆盖；全部 protected write 默认 denied。

### 验证步骤

```powershell
$env:PYTHONPATH='src'; $env:UV_CACHE_DIR=Join-Path $env:TEMP 'hancode-uv-cache'; uv run --no-sync pytest tests/test_config.py tests/test_path_classifier.py tests/test_tool_policy.py tests/test_agent_loop.py tests/test_course_file_protection.py -v -p no:cacheprovider
$env:PYTHONPATH='src'; $env:UV_CACHE_DIR=Join-Path $env:TEMP 'hancode-uv-cache'; uv run --no-sync ruff check src/hancode/config.py src/hancode/tool_policy.py tests/test_config.py tests/test_tool_policy.py tests/test_agent_loop.py tests/test_course_file_protection.py
$env:PYTHONPATH='src'; $env:UV_CACHE_DIR=Join-Path $env:TEMP 'hancode-uv-cache'; uv run --no-sync mypy src/hancode/config.py src/hancode/tool_policy.py tests/test_course_file_protection.py --cache-dir (Join-Path $env:TEMP 'hancode-mypy-cache-t15')
```

### 实际验证（2026-07-12）

* Red：新增/更新测试后，在沙箱外运行上述 pytest 聚焦命令，得到 `23 failed, 109 passed, 2 skipped in 5.76s`；失败为新增默认保护模式、嵌套模式和新的 protected-path 反馈尚未实现。
* Green：补充最小默认模式与固定反馈后，同一聚焦命令得到 `132 passed, 2 skipped in 1.25s`。
* 静态检查：Ruff 输出 `All checks passed!`；MyPy 输出 `Success: no issues found in 3 source files`；`git diff --check` 通过。
* 环境说明：首次在受限沙箱执行 pytest 时，`tmp_path` 创建受 `PermissionError` 阻断；使用同一命令在沙箱外复验后获得上述 Red/Green 证据。
* 范围扩展（2026-07-13）：第二阶段审查发现同名无扩展名或非 Markdown 课程文件在可写根下可归为 source；经人工确认后，将四类课程文件规则扩展为精确基名、`基名.*` 与目录模式。新增回归先得到 `10 failed, 6 passed`，最小规则扩展后 `tests/test_config.py tests/test_course_file_protection.py` 为 `69 passed`。
* 精确边界：`requirements.*` 不匹配 `requirements-lock.txt`。第二阶段复审补充该嵌套/非嵌套负向回归后，专项为 `2 passed`。
* 最终全量：`uv run --no-sync pytest -p no:cacheprovider` 为 `346 passed, 4 skipped`；Ruff 与 MyPy 全量通过，`git diff --cached --check` 通过。4 个 skip 均因当前 Windows 环境不允许创建文件 symlink。

### 完成判定

* 课程文件保护由代码策略完成。
* 测试失败不能通过改教师测试、删评分脚本、删样例数据解决。

### 非目标 / 边界

* 不实现人工审批覆盖。
* 不实现复杂权限系统。
* 不修改教师测试或评分脚本。

---

# M4：Trace 与可恢复状态

---

## T16：TraceLogger

| 元信息           | 值                    |
| ------------- | -------------------- |
| 状态            | [x] 已完成              |
| 依赖            | T1, T4               |
| 可并行           | 可与 T13/T14 并行        |
| Worktree / PR | `feature/M4`         |
| 主贡献相关         | 是，可观测性核心             |
| Commit        | `df39f8c` |

### 目标

实现 JSONL trace 追加、事件 ID、事件序号、脱敏和写失败处理。

### 涉及文件

* `src/hancode/trace.py`
* `tests/test_trace.py`

### SPEC 依据

* TraceLogger。
* trace 必须记录 phase 切换、LLM 决策、action 解析、policy 判定、工具调用、feedback、checkpoint、rollback 和最终状态。
* trace 不得泄露真实凭据。

### 接口契约

```python
class TraceEvent:
    event_id: str
    seq: int
    event_type: str
    task_id: str
    phase: Phase
    timestamp: datetime
    status: str
    action: Mapping[str, object] | None
    observation: Mapping[str, object] | None
    error_summary: str | None
    state_transition: Mapping[str, object] | None

def append_trace(
    task_root: Path,
    *,
    event_type: str,
    task_id: str,
    phase: Phase,
    status: str,
    action: Mapping[str, object] | None = None,
    observation: Mapping[str, object] | None = None,
    error_summary: str | None = None,
    state_transition: Mapping[str, object] | None = None,
    timestamp: datetime | None = None,
) -> TraceEvent: ...
```

输入：task root、事件字段；TraceLogger 生成 event ID 和序号。
输出：追加写入 `trace.jsonl` 后的 `TraceEvent`。
不变量：trace 只追加，不修改；`event_id=evt-{seq:06d}`，seq 在 task 内单调递增。
错误处理：trace 写入失败时阻止继续执行高风险工具。

### 预期失败测试

* `test_trace_appends_jsonl_event_with_event_id`
* `test_trace_event_has_monotonic_seq`
* `test_trace_redacts_nested_secret_like_values`
* `test_trace_truncates_large_content`
* `test_trace_rejects_malformed_existing_jsonl`
* `test_trace_rejects_invalid_existing_sequence`
* `test_trace_write_failure_blocks_high_risk_action`
* `test_trace_rejects_invalid_history_before_append`
* `test_trace_serialization_failure_returns_structured_error`
* `test_trace_redacts_secret_like_text_values`
* `test_trace_rejects_tool_event_without_auditable_action`
* `test_trace_rejects_failed_tool_event_without_error_summary`
* `test_trace_rejects_task_id_outside_task_root`
* `test_trace_redacts_cookie_aws_and_bearer_values`
* `test_trace_rejects_history_for_another_task`
* `test_trace_rejects_tool_event_without_complete_decision_or_status`
* `test_trace_normalizes_non_string_payload_keys`
* `test_trace_rejects_non_string_error_summary`
* `test_trace_rejects_task_root_outside_workspace_layout`
* `test_trace_rejects_task_root_without_valid_project_metadata`
* `test_trace_rejects_non_mapping_payloads`
* `test_trace_rejects_inconsistent_tool_event_details`
* `test_trace_omits_content_values_from_observations`
* `test_trace_omits_content_field_aliases_recursively`

### 实现要点

* `event_id` 使用 `evt-{seq:06d}` 格式，例如 `evt-000001`。
* 每行 JSONL 必须是合法 JSON。
* 脱敏字段包括 Authorization、api_key、token、secret、password。
* trace 不记录完整大文件内容。
* 规范化名称以 `content`、`output`、`stdout`、`stderr`、`body`、`text` 开头或结尾的字段只写入 `[CONTENT_OMITTED]` 摘要与字符串长度，不记录原文，覆盖 `file_content`、`tool_output`、`response_body` 等别名，避免受保护文件或工具输出进入 trace。
* 写入或既有 trace 解析失败时，返回不泄露底层异常的 `HanCodeError`；T16 不改 AgentLoop / ToolPolicy，后续调用方捕获此错误后阻断高风险动作。
* 追加前必须验证全量既有 JSONL：每行都是 JSON object，`seq` 从 1 连续递增，且 `event_id=evt-{seq:06d}`；中间损坏、重复或倒退编号拒绝追加。
* 文本内容也必须扫描并脱敏 `Authorization: ...`、`API_KEY=...` 等键值形式；JSON 编码失败同样转换为 `trace_write_error`。
* tool 事件要求 action 中包含 `tool_name`、`args`、`reason`、`policy_decision`；`tool_failed` 还要求错误摘要。传入 task ID 必须与 task root 目录名一致。
* task root 必须位于 `.hancode/tasks/<task_id>` 布局；历史事件的 task ID 必须与当前任务一致。工具 policy decision 至少记录 `allowed`、`message`、`phase`、`denied_rule` 和 `suggested_fix`，工具状态受限为 `running`、`succeeded`、`failed`、`blocked`。

### 验证步骤

```powershell
uv run pytest tests/test_trace.py -v
uv run ruff check src/hancode/trace.py tests/test_trace.py
uv run mypy src/hancode/trace.py
```

### 完成判定

* trace 可被测试读取和断言。
* secret fixture 不出现在 trace 中。
* trace 写失败有明确错误路径。

### 实际验证

* Red：新增基础测试后，`uv run --no-project --with pytest pytest tests/test_trace.py::test_trace_appends_jsonl_event_with_event_id -v -p no:cacheprovider --basetemp .pytest-tmp` 因 `ModuleNotFoundError: No module named 'hancode.trace'` 失败；编号、安全和错误路径测试均在对应最小实现前得到预期断言失败。
* Green：`$env:PYTHONPATH='src'; uv run --no-project --with pytest pytest tests/test_trace.py -v -p no:cacheprovider --basetemp .pytest-tmp` 通过，8 passed。
* 定向质量：`ruff check src/hancode/trace.py tests/test_trace.py --no-cache` 通过；`mypy src/hancode/trace.py` 通过，no issues found in 1 source file。
* 全量回归：`pytest -p no:cacheprovider --basetemp .pytest-tmp` 通过，354 passed、4 skipped；`ruff check src tests --no-cache` 通过；`mypy src` 通过，no issues found in 16 source files。
* 第一阶段评审修正：新增全量历史完整性、字符串凭据、JSON 编码失败、工具审计字段和 task ID 绑定测试后，专项通过，15 passed；全量回归通过，361 passed、4 skipped；ruff 与 mypy `src` 均通过。
* 第二阶段安全/质量审查修正：先补齐 cookie、AWS access key、裸 Bearer token、历史 task ID、完整 policy decision、状态、非字符串 payload key / error summary 和 task-root 布局；re-verdict 继续发现受保护短内容、伪造项目元数据、非 Mapping payload、工具事件状态一致性及内容字段别名缺口，已统一改为内容摘要并收紧项目 metadata / payload / policy 契约。最终专项通过，29 passed；全量回归通过，375 passed、4 skipped；ruff 与 mypy `src` 均通过。

### 非目标 / 边界

* 不实现 history summary。
* 不实现 demo 完整事件序列。
* 不实现 checkpoint。
* 不实现并发 writer lock、进程崩溃后的半行恢复或 `fsync` 耐久化保证；这些属于全局 post-MVP 单 task 单活跃 runner 与持久化增强，不得在 T16 提前扩展。

---

## T17：CheckpointManager

| 元信息           | 值                          |
| ------------- | -------------------------- |
| 状态            | [x] 已实现并完成动态回归验证         |
| 依赖            | T13, T15, T16              |
| 可并行           | 不并行；依赖路径和保护规则              |
| Worktree / PR | `feature/M4`                |
| 主贡献相关         | 是，可回退编码状态核心                |
| Commit        | `dcfd3fe feat: 完成 T17 CheckpointManager` |

### 目标

实现业务代码修改前的 checkpoint 创建和 manifest，使每轮代码尝试都能恢复到修改前状态。

### 涉及文件

* `src/hancode/checkpoints.py`
* `tests/test_checkpoints.py`

### SPEC 依据

* Checkpoint 与 Rollback。
* code phase 修改业务代码前创建 checkpoint。
* checkpoint 不保存凭据、受保护课程文件、教师测试、评分脚本或样例数据。

### 接口契约

```python
class CheckpointManifest: ...

def create_checkpoint(
    task_root: Path,
    files: list[Path],
    reason: str,
    *,
    created_at: datetime | None = None,
) -> CheckpointManifest: ...

def commit_checkpoint(task_root: Path, checkpoint_id: str) -> CheckpointManifest: ...
```

输入：task root、即将修改的 source files、reason；提交时传入 checkpoint ID。
输出：不可变 CheckpointManifest、文件快照。
不变量：`create_checkpoint()` 只创建 `pending` 的 before 快照；`commit_checkpoint()` 仅将同 task 的 pending manifest 原子转为 `committed` 并记录 after hash。缺失 SOURCE 目标表示新建文件，rollback 时应删除它。
错误处理：空文件集、空 reason、非 SOURCE、受保护文件、目录、损坏/篡改 manifest、快照/hash 不一致、路径或 symlink 越界均返回结构化错误；reason、trace 和 manifest 不记录 secret。

### 预期失败测试

* `test_edit_file_creates_checkpoint`（保留既有课程脚手架文档契约名称）
* `test_create_checkpoint_snapshots_existing_source_file`
* `test_create_checkpoint_supports_missing_source_target`
* `test_checkpoint_normalizes_deduplicates_and_sorts_paths`
* `test_create_checkpoint_updates_state_and_trace`
* `test_create_checkpoint_rejects_invalid_request`
* `test_create_checkpoint_removes_snapshot_when_state_update_fails`
* `test_create_checkpoint_compensates_state_when_trace_write_fails`
* `test_commit_checkpoint_records_after_hash_and_marks_committed`
* `test_commit_checkpoint_restores_pending_manifest_when_trace_write_fails`
* `test_commit_checkpoint_rejects_unrecoverable_before_snapshot`
* `test_commit_checkpoint_rejects_untrusted_manifest_data`
* `test_commit_checkpoint_rejects_checkpoint_directory_symlink_outside_task`
* `test_commit_checkpoint_rejects_external_checkpoint_contents_symlink`

### 实现要点

* manifest 记录：

  * `checkpoint_id`
  * `task_id`
  * `phase`
  * `reason`
  * `files`
  * `before_sha256`
  * `created_at`
  * `status`
* 快照与 initial manifest 先在 `.{checkpoint_id}.tmp` 写入，再 rename 为 `checkpoints/<checkpoint_id>/`；state 或 trace 失败时补偿删除并恢复 state，补偿失败显式报错。
* `checkpoint_id` 只由 `state.checkpoint_seq + 1` 分配，格式为 `ckpt-NNN`；manifest 记录 before/after hash、pending/committed 状态和 rollback 可用性。
* 创建和提交分别写 `checkpoint_created`、`checkpoint_committed` trace；trace 失败不得报告成功。
* manifest、`files/`、checkpoint 根和临时目录均需保持在 task workspace 内，拒绝 symlink/junction 外链；before snapshot 和 hash 必须可验证。

### 验证步骤

```powershell
uv run pytest tests/test_checkpoints.py -v
uv run ruff check src/hancode/checkpoints.py tests/test_checkpoints.py
uv run mypy src/hancode/checkpoints.py
```

### 实际验证（截至 2026-07-13）

* 专项：`\.venv\Scripts\python.exe -m pytest tests/test_checkpoints.py -q -p no:cacheprovider --basetemp <isolated-dir>` 为 `40 passed, 4 skipped in 1.93s`；4 个 skip 均因当前 Windows 环境不允许创建文件 symlink。
* 全量：`\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp <isolated-dir>` 为 `415 passed, 8 skipped in 5.10s`。
* 静态检查：Ruff 输出 `All checks passed!`；MyPy `src/hancode/checkpoints.py` 输出 `Success: no issues found in 1 source file`；`git diff --check` 通过。
* 两阶段新鲜子代理审查均无 Critical/Important；第二阶段静态安全复审结论为可合入。
* 文档契约修复：保留 `test_edit_file_creates_checkpoint` 这一既有脚手架断言名称，并在测试清单中同时列出 T17 当前实际测试。

### 完成判定

* source write 前可创建 checkpoint。
* checkpoint 不包含 `.env`、凭据、教师测试、评分脚本、样例数据。
* manifest 可被 rollback 使用。
* 最新 `tests/test_checkpoints.py`、全量 pytest、Ruff、MyPy 已取得新鲜通过证据；本卡可标记为 `[x]`。提交仍待用户决定。

### 非目标 / 边界

* 不实现 rollback。
* 不实现 checkpoint pruning。
* 不使用 git 作为 checkpoint 机制。
* 不实现跨进程锁、TOCTOU 消除或 pending crash reconcile；保留给后续并发/恢复增强。

---

## T18：RollbackManager

| 元信息           | 值                        |
| ------------- | ------------------------ |
| 状态            | [x] 已实现并完成全量验证              |
| 依赖            | T17                      |
| 可并行           | 不并行                      |
| Worktree / PR | `feature/M4`              |
| 主贡献相关         | 是，可回退编码状态核心              |
| Commit        | TODO（待用户决定）             |

### 目标

实现最近 checkpoint 的恢复流程，使测试失败、review 风险过高或 retry budget 耗尽时可以恢复业务文件。

### 涉及文件

* `src/hancode/checkpoints.py`
* `tests/test_rollback.py`
* `docs/PLAN.md`
* `docs/AGENT_LOG.md`
* `docs/系统架构.md`
* `src/hancode/README.md`

### SPEC 依据

* Checkpoint 与 Rollback。
* retry budget 超限必须强制 rollback。
* rollback 不得覆盖 protected files、`.env` 或凭据文件。

### 接口契约

```python
@dataclass(frozen=True, slots=True)
class RollbackResult:
    status: OperationStatus
    checkpoint_id: str | None
    restored_files: tuple[str, ...]
    failed_files: tuple[str, ...]
    error: StructuredError | None

    @property
    def error_summary(self) -> str | None: ...

    def to_dict(self) -> dict[str, object]: ...

def rollback_last_checkpoint(task_root: Path) -> RollbackResult: ...
```

输入：task root。
输出：结构化 `RollbackResult`，可由后续 FeedbackBuilder 直接序列化为 observation。
不变量：仅在 `review` phase 恢复 `state.latest_checkpoint` 指向的同 task、同 project、`code` phase、`committed` 且 `rollback_available=true` manifest；只恢复其中经 `PathClassifier` 重新确认的 SOURCE 文件。
冲突策略：当前业务文件的 SHA-256 必须等于 manifest 的 `after_sha256`；不一致时以 `rollback_conflict` 阻断，零文件写入，不提供 force / confirm。
状态机：checkpoint manifest 生命周期为 `pending -> committed -> rolled_back`；成功后 `rolled_back` 且 `rollback_available=false`，重复恢复返回 `rollback_not_available`。
错误处理：phase、state、manifest、快照、路径、symlink/junction、hash 或工作区身份任一校验失败均返回 `blocked`；恢复、manifest/state/trace 持久化失败返回 `failed`，不盲目恢复。

### 预期失败测试

* `test_rollback_last_checkpoint_restores_file`
* `test_rollback_removes_file_created_after_checkpoint`
* `test_rollback_records_restored_files_and_serializes_result`
* `test_rollback_resets_review_state_and_marks_manifest_rolled_back`
* `test_rollback_requires_review_phase_and_latest_checkpoint`
* `test_damaged_manifest_blocks_rollback`
* `test_rollback_does_not_restore_protected_files`
* `test_rollback_blocks_external_content_conflict_without_writes`
* `test_rollback_blocks_when_current_file_cannot_be_verified`
* `test_rollback_blocks_inconsistent_task_state`
* `test_rollback_blocks_repeated_restore`
* `test_rollback_blocks_snapshot_escape_before_writing_source`
* `test_rollback_blocks_external_source_symlink_before_writing`
* `test_rollback_does_not_reuse_preexisting_restore_temporary_path`
* `test_rollback_compensates_files_when_multi_file_restore_fails`
* `test_rollback_compensates_when_manifest_state_or_trace_write_fails`
* `test_rollback_marks_state_inconsistent_when_compensation_fails`
* `test_rollback_writes_trace_event`

### 实现要点

* 预检先完成所有读取与校验：task/project/manifest identity、`committed` 状态、before snapshots、SOURCE 分类、路径和链接边界、after hash；任一失败前不得写业务文件。
* `modify` 从 before snapshot 以同目录临时文件 + replace 恢复；`create` 删除当前目标。恢复前保留所有当前 bytes，用于补偿。
* 多文件恢复是全有或全无：任一恢复失败，或后续 manifest、state、trace 失败时，补偿全部已改业务文件、manifest 与 state；补偿无法完成时尽力标记 `TaskStatus.INCONSISTENT` / `inconsistent=true`，并返回 `rollback_compensation_failed`。
* 成功状态保留 `current_phase=review`、`latest_checkpoint`、checkpoint seq 和 retry budget；设置 `rollback_done=true`、`rollback_required=false`、`latest_test_status="none"`、`test_status_consumed=false`、`source_edits_this_phase=0`，并将 code/test/review 的 `phase_completed` 复位为 `false`。
* 记录 `rollback_started`（`running`）及最终 `rollback_performed`（`succeeded` / `blocked` / `failed`）trace；若 trace 无法持久化，不得报告恢复成功。
* 错误码至少包括：`rollback_requires_review_phase`、`rollback_checkpoint_required`、`rollback_inconsistent_state`、`rollback_not_available`、`rollback_conflict`、`rollback_restore_failed`、`rollback_manifest_update_failed`、`rollback_state_update_failed`、`rollback_trace_failed`、`rollback_compensation_failed`；沿用 checkpoint 身份、路径与 manifest 错误码。

### 验证步骤

```powershell
$env:PYTHONPATH='src'
uv run --no-sync pytest tests/test_rollback.py tests/test_checkpoints.py -v -p no:cacheprovider --basetemp .t18-pytest-tmp
uv run --no-sync pytest -q -p no:cacheprovider --basetemp .t18-pytest-tmp
uv run --no-sync ruff check src tests --no-cache
uv run --no-sync mypy src --no-incremental
git diff --check
```

### 实际验证（2026-07-13）

* TDD：从缺少 `rollback_last_checkpoint` 的导入 RED 开始；随后依次观察 manifest 生命周期、review state、trace、文件/manifest/state/trace 补偿、after-hash 预检读取、预置临时路径与 inconsistent 门禁的 RED，再以最小实现转绿。
* 最新联合回归：`tests/test_rollback.py tests/test_checkpoints.py` 为 `62 passed, 5 skipped`；5 个 skip 均为当前 Windows 环境不允许创建文件 symlink。
* 两阶段新鲜审查：第一阶段发现并修复 after-hash 预检读取错误应为 `blocked`；第二阶段发现并修复临时文件链接绕过、inconsistent 高风险门禁与补偿结果虚报。两阶段复核后均无 Critical/Important。
* 最终全量：`uv run --no-sync pytest -q -p no:cacheprovider --basetemp .t18-pytest-tmp` 为 `437 passed, 9 skipped in 8.33s`；9 个 skip 均为当前 Windows 环境不允许创建文件 symlink。
* 静态检查：Ruff 输出 `All checks passed!`；MyPy 输出 `Success: no issues found in 17 source files`；`git diff --check` 通过。

### 完成判定

* rollback 能将修改文件和新建文件恢复到 checkpoint 前状态。
* manifest、快照、路径或 hash 损坏时不发生业务文件写入。
* 任一文件或持久化阶段失败后不留下部分恢复；无法补偿显式进入 inconsistent。
* `RollbackResult` 结构化返回，state / manifest / trace 三者一致且可审计。

### 非目标 / 边界

* 不实现 git rollback。
* 不实现多 checkpoint pruning。
* 不恢复 protected files，也不提供 force / confirm 覆盖 hash 冲突。
* 不实现 pending crash reconcile、跨进程锁或 TOCTOU 消除。
* 不在本任务接入 AgentLoop / FileTools、不递减 retry budget、不写 REVIEW.md；这些由 T20-T22 消费恢复结果和 trace。

---

# M5：Context 与 Feedback

---

## T19：ContextBuilder

| 元信息           | 值                       |
| ------------- | ----------------------- |
| 状态            | [x] 已完成                 |
| 依赖            | T2, T3, T4, T5, T16     |
| 可并行           | 可与 T20 并行               |
| Worktree / PR | `feature/M5`             |
| 主贡献相关         | 否，支撑维度                  |
| Commit        | TODO                    |

### 目标

实现按 phase 选择最小必要上下文的 ContextBuilder，使课程规则、任务产物、测试结果、checkpoint 和 trace 摘要按需进入 LLM 上下文。

### 涉及文件

* `src/hancode/context.py`
* `src/hancode/tool_policy.py`
* `src/hancode/file_tools.py`
* `tests/test_context_builder.py`
* `tests/test_tool_policy.py`
* `docs/系统架构.md`
* `docs/AGENT_LOG.md`

### SPEC 依据

* ContextBuilder 与记忆选择。
* 课程项目上下文构造。
* 不得无条件加载全部历史。
* 不同 task 的 history、trace、checkpoint 不得混用。

### 接口契约

```python
def allowed_tools_for_phase(phase: Phase) -> tuple[str, ...]: ...

def build_context(
    project_root: Path,
    task_id: str,
    phase: Phase,
    config: HanCodeConfig,
    *,
    state: TaskState | None = None,
) -> dict[str, object]: ...

class ContextBuilder:
    def __init__(self, project_root: Path, config: HanCodeConfig) -> None: ...
    def build(self, *, task_id: str, phase: Phase, state: TaskState) -> dict[str, object]: ...
```

输入：project root、task ID、phase、config。
输出：结构化 context 字典。
不变量：不得无条件加载全部历史；不得混入其他 task 的 trace、history、checkpoint。
错误处理：必需产物、checkpoint、trace 或 task/config 身份不合法时抛出结构化
`HanCodeError`；可选上下文缺失时写入 `context_risks`；context 超预算时按规则省略或截断，
无法容纳必需骨架时返回 `context_budget_too_small`。

### 预期失败测试

* `test_context_builder_includes_course_context`
* `test_code_phase_context_requires_spec_and_plan`
* `test_review_phase_includes_test_report_changed_files_and_checkpoint`
* `test_deliver_phase_includes_required_artifacts`
* `test_context_builder_does_not_mix_other_task_trace`
* `test_context_builder_respects_max_context_chars`
* `test_required_artifact_link_is_rejected`

### 实现要点

* 优先加载课程要求和当前 phase 必需产物。
* 其次加载 project memory / experience；plan 只暴露配置的 writable roots，不扫描全仓库。
* trace 摘要最多取 `max_trace_events` 条。
* 截断时保留课程规则、当前 phase 必需产物和最近失败信息；project memory / experience /
  source snippets 等低优先级段先省略。
* 读取的文本沿用文件工具脱敏规则；不得跟随可选文档、必需产物、checkpoint 或 trace 的链接。

### 验证步骤

```powershell
uv run pytest tests/test_context_builder.py -v
uv run ruff check src/hancode/context.py tests/test_context_builder.py
uv run mypy src/hancode/context.py
```

### 完成判定

* 不同 phase 上下文内容不同。
* 不无条件加载全部历史。
* 不混入其他 task trace。

### 非目标 / 边界

* 不实现向量检索。
* 不使用 embedding。
* 不让 LLM 压缩上下文。

---

## T20：FeedbackBuilder 失败分类

| 元信息           | 值                        |
| ------------- | ------------------------ |
| 状态            | [x] 已完成                  |
| 依赖            | T8, T11, T14, T18        |
| 可并行           | 可与 T19 并行                |
| Worktree / PR | `feature/M5`              |
| 主贡献相关         | 是，反馈闭环核心                 |
| Commit        | TODO                     |

### 目标

实现确定性的测试失败分类和 observation 构造，将测试结果、policy denial、parse error、rollback result 转换为下一轮 AgentLoop 可用的反馈。

### 涉及文件

* `src/hancode/feedback.py`
* `src/hancode/tools.py`
* `src/hancode/agent_loop.py`
* `src/hancode/file_tools.py`
* `tests/test_feedback.py`
* `tests/test_tool_registry.py`
* `tests/test_agent_loop.py`
* `tests/test_file_tools.py`
* `docs/系统架构.md`
* `docs/AGENT_LOG.md`

### SPEC 依据

* 反馈回灌机制。
* 反馈必须来自确定性工具结果或系统判定，不能由 LLM 自行判断。
* 测试失败分类和纠正建议必须稳定可测试。

### 接口契约

```python
class FailureCategory(str, Enum):
    NONE = "none"
    SYNTAX_ERROR = "syntax_error"
    IMPORT_ERROR = "import_error"
    ASSERTION_FAILURE = "assertion_failure"
    ERROR_EXCEPTION = "error_exception"
    TIMEOUT_OR_CRASH = "timeout_or_crash"
    UNKNOWN = "unknown"

class ObservationKind(str, Enum): ...

@dataclass(frozen=True)
class Observation:
    kind: ObservationKind
    success: bool
    phase: Phase
    summary: str
    next_action_hint: str
    failure_category: FailureCategory | None
    details: Mapping[str, object]

def classify_test_output(
    output: str, exit_code: int, timed_out: bool = False, *, max_observation_bytes: int = 8192
) -> FeedbackReport: ...
def build_observation(
    result: ToolResult | PolicyDecision | CheckpointManifest | RollbackResult | ParseError,
    *, phase: Phase | None = None, max_observation_bytes: int = 8192
) -> Observation: ...
```

输入：测试输出、退出码、工具结果、策略拒绝、rollback 结果、parse error。
输出：FeedbackReport / Observation。
不变量：同一输入分类结果稳定；纠正建议由规则表生成。
错误处理：无法分类但 exit code 非零时返回 UNKNOWN，保留摘要并提示人工检查。

### 预期失败测试

* `test_feedback_classifies_syntax_error`
* `test_feedback_classifies_import_error`
* `test_feedback_classifies_assertion_failure`
* `test_feedback_classifies_error_exception`
* `test_feedback_classifies_timeout_or_crash`
* `test_feedback_classification_is_deterministic_on_fixture`
* `test_policy_denial_becomes_observation`
* `test_parse_error_becomes_observation`
* `test_rollback_result_becomes_observation`

### 实现要点

* 分类优先级：

  * syntax
  * import
  * assertion
  * timeout/crash
  * error exception
  * unknown
* 分类在完整输出上执行，摘要截断在分类之后执行。
* policy denial observation 包含 `denied_rule`、`reason`、`suggested_fix`；checkpoint 也必须可转为 observation。
* `ToolResult.timed_out` 是显式超时信号；AgentLoop 调用工具反馈时显式传入当前 phase。
* summary 在完整输出分类后统一脱敏和截断；整个 Observation 受 `max_observation_bytes` 约束。
* 不调用 LLM 判断失败原因。

### 实现结果

* 新增 `feedback.py`：固定优先级分类完整测试输出，并将测试、通用工具、policy、parse、checkpoint 与 rollback 的确定性结果构造成冻结 `Observation`。
* `ToolResult` 新增兼容默认值 `timed_out=False`；AgentLoop 仅在工具反馈构造时显式传递当前 `phase`，未进入 T21 的重试、回滚执行、状态或 trace 副作用。
* Observation 的摘要、建议与 details 在写入前脱敏，包含裸 `Bearer` token；总 canonical JSON UTF-8 字节数受预算限制，不足以容纳元数据时返回结构化 `feedback_budget_too_small`。
* 公开构造边界会将非法预算、phase 或非 JSON 工具输出转换为 `feedback_input_invalid`；分类优先级已与系统架构文档统一。

### 验证步骤

```powershell
uv run pytest tests/test_feedback.py -v
uv run ruff check src/hancode/feedback.py tests/test_feedback.py
uv run mypy src/hancode/feedback.py
```

实际验证：`pytest -q -p no:cacheprovider` 为 483 passed、9 skipped；`ruff check src tests` 与 `mypy src` 均通过。

### 完成判定

* 同一输入输出稳定。
* failure suggested_fix 由规则表生成。
* 反馈来自工具结果或系统判定。

### 非目标 / 边界

* 不实现 retry budget。
* 不执行 rollback。
* 不生成 TEST_REPORT。

---

## T21：AgentLoop 集成 feedback / retry / rollback

| 元信息           | 值                                 |
| ------------- | --------------------------------- |
| 状态            | [x] 已完成                              |
| 依赖            | T10, T14, T16, T18, T20           |
| 可并行           | 不并行；主贡献闭环任务                       |
| Worktree / PR | `feature/M5`                         |
| 主贡献相关         | 是，主贡献闭环核心                         |
| Commit        | `375f735b535c115b2d897adc52da9ae7371bf1c8` |

### 目标

把 AgentLoop 与 FeedbackBuilder、retry budget、review 路由、rollback 串起来，使“测试失败 -> feedback -> retry -> 强制 rollback”可在 MockLLM 下确定性复现。

### 涉及文件

* `src/hancode/agent_loop.py`
* `src/hancode/tool_policy.py`
* `src/hancode/router.py`
* `src/hancode/feedback.py`
* `src/hancode/file_tools.py`
* `src/hancode/state.py`
* `src/hancode/checkpoints.py`
* `src/hancode/trace.py`
* `src/hancode/workspace.py`
* `tests/test_agent_loop.py`
* `tests/test_agent_loop_adapters.py`
* `tests/test_feedback_loop.py`
* `tests/test_tool_policy.py`
* `tests/test_course_file_protection.py`
* `tests/test_router.py`
* `tests/test_workspace.py`

### SPEC 依据

* 反馈回灌机制。
* 测试失败时必须进入 review。
* retry budget 超限必须强制 rollback。
* rollback 结果必须作为 observation 回灌。

### 接口契约

```text
输入：MockLLM action 序列、TaskState、ToolResult、FeedbackBuilder、RollbackManager。
输出：AgentRunResult，包含最终状态、retry budget、trace、observation。
不变量：测试失败不得直接 completed；retry budget 耗尽必须 rollback。
错误处理：rollback 失败时返回 blocked / failed，并保留 error_summary。
```

### 预期失败测试

* `test_test_failure_generates_observation`
* `test_failed_test_decrements_retry_budget`
* `test_retry_budget_exhaustion_forces_rollback`
* `test_rollback_result_becomes_observation`
* `test_loop_does_not_return_completed_after_failed_test`
* `test_feedback_loop_trace_records_failure_retry_rollback`

### 实现要点

* AgentLoop 在测试失败后进入 review。
* retry budget 未耗尽时允许针对性回 code。
* retry budget 耗尽时调用 rollback。
* rollback 后保持 review / blocked，不直接 completed。
* 每个关键事件写 trace。
* blocked 状态默认 fail-closed，只有 `run(task_id, resume=True)` 才允许显式恢复；`failed` / `inconsistent` 不允许绕过修复门禁。
* adapter 返回值、checkpoint 指针、rollback 状态和 trace 事件均在边界处结构化校验；上下文构造失败保留原始结构化错误。
* source write 强制 checkpoint，artifact write 只更新 artifact 状态；测试执行追加 `tests_run` 审计记录。
* 文件系统适配层拒绝 workspace 链接，并使用独占临时文件完成 state/manifest 原子替换；错误、反馈和 trace 统一脱敏。
* 启动时通过文件系统适配层执行 artifact 漂移检查；不一致只在本次运行内 fail-closed，不自动回写 `state.json`。
* source write 后状态持久化异常保留 `rollback_required`，仅允许显式 `resume=True` 进入受限 rollback 恢复通道；真实文件系统 rollback 的生命周期 trace 由 AgentLoop 统一记录。

### 验证步骤

```powershell
uv run --no-sync pytest tests/test_agent_loop.py tests/test_feedback_loop.py tests/test_feedback.py tests/test_router.py -q -p no:cacheprovider
uv run --no-sync ruff check src tests --no-cache
uv run --no-sync mypy src
```

### 完成判定

* 主贡献闭环可在 MockLLM 下确定性复现。
* 测试失败不会直接 completed。
* retry 超限会强制 rollback。
* blocked 恢复必须显式传入 `resume=True`，完成态不会因状态漂移再次执行工具。
* persisted `completed` 状态仍需满足 `KNOWLEDGE.md` 与 `DELIVERABLES.md` 交付物完整性；缺失时 fail-closed 到 `deliver` blocked。
* 适配器边界的坏类型、非法 checkpoint ID、trace 参数和文件系统 workspace 越界均返回结构化拒绝。
* TraceAppender 返回的 tool event payload、artifact task 路径和 persisted completed 交付物完整性均在边界处再次校验。

### 非目标 / 边界

* 不生成最终 Markdown 报告。
* 不接真实 LLM。
* 不做 CLI demo。
* checkpoint 采用“单次 source write 前”粒度；一次 loop 内的多文件事务聚合、checkpoint pruning、跨进程锁和外部攻击者级 TOCTOU 防护留给后续任务。
* resume 不跨会话持久化上一次 observation，也不重放完整生命周期 trace；当前仅复用持久化 state、checkpoint 与已有 trace 序列。
* T21 补齐 feedback / retry / rollback 相关 trace 与边界事件；T21-R1 Task 2 追加 `phase_started` / `phase_completed` / `run_completed` 阶段生命周期事件。完整的 context / action 级生命周期事件矩阵仍不在本卡内重构。

---

## T21-R1：未覆盖缺陷安全、工具与恢复收尾

| 元信息           | 值                                 |
| ------------- | --------------------------------- |
| 状态            | [~] 进行中（Task 1-6 已实现；Task 7 门禁、两阶段评审与最终收口中） |
| 依赖            | T21                              |
| 可并行           | 分组串行；先安全边界，再工具与恢复          |
| Worktree / PR | `feature/M7`                       |
| 主贡献相关         | 是，T21 收尾修复                     |
| Commit        | Task 1 `b91ed75`；Task 2 `78acbe7`；T21-R1 收口待提交 |

### 目标

在 `feature/M7` 完成 T21-R1 剩余机制：凭据路径保护一致性、精确文件编辑、受限测试执行、默认工具装配，以及 pending checkpoint 的可审计 abort / 恢复。保持 Mock/stub 可替换、禁止通用 shell，并通过 TDD、结构化错误和证据化验证收口。

### 修复边界

* checkpoint / trace 达到上限时 fail-closed 拒绝新增，不自动 pruning。（Task 1 已实现）
* policy denial 保留为主错误；trace 写失败作为审计风险，不得导致工具执行。（Task 2 已实现：`policy_denied` 主错误保留、trace 失败降级为 `Risk`）
* 纯审计标记点（phase_started / phase_completed / run_completed / policy_denied）trace 写失败降级为 risk 不掩盖主错误；变更与工具执行点（tool_called / source_write_authorized / checkpoint）保持 fail-closed。（Task 2 已实现）
* `edit_file` 使用恰好一次匹配规则和原子写入；失败在可证明未写入时返回 `mutation_applied=False`，原子替换阶段不确定时返回 `None`。
* `run_tests` 只执行配置提供的命令：用 `shlex.split` 固定拆分 argv，固定 `cwd=project_root`、`shell=False`、`capture_output=True`、`check=False`，默认超时 120 秒；命令和输出先脱敏再进入结果、state 和 trace。
* 凭据路径由 `src/hancode/path_security.py` 统一判定，覆盖 `.env*`、credentials/secrets/certificates/keys 目录、`id_rsa` 等精确文件名及 `.key/.pem/.token/.crt/.cer/.der/.p12/.pfx` 后缀；后缀本身作为隐藏文件名（如 `.pem`、`.key`、`.crt`）时同样拒绝；FileTools、PathClassifier 和 CheckpointManager 共用该边界。
* `redact_text()` 在通用规则前完整替换 PEM 私钥块（包括 `PRIVATE KEY`、`RSA PRIVATE KEY`、`OPENSSH PRIVATE KEY` 和 `ENCRYPTED PRIVATE KEY`），不将私钥正文、BEGIN/END 标记写入工具结果、state 或 trace。
* pending checkpoint 状态只允许 `pending | committed | rolled_back | aborted`。普通启动对未修改 pending 自动 abort；发现源文件变化时保存 `inconsistent + rollback_required` 并 fail-closed；只有 `resume=True` 才恢复已校验的 before snapshot。恢复成功后状态为 `blocked`，由显式 resume 转为 running；manifest、快照、hash、symlink/junction 无法验证时不写业务文件。
* 不接真实 LLM、真实凭据或网络 provider；不提前实现 T22-T27 的交付任务。

### 涉及文件

* `src/hancode/file_tools.py`
* `src/hancode/workspace.py`
* `src/hancode/checkpoints.py`
* `src/hancode/trace.py`
* `src/hancode/tools.py`
* `src/hancode/agent_loop.py`
* `src/hancode/path_security.py`
* `src/hancode/test_tools.py`
* `src/hancode/tool_factory.py`
* 对应 `tests/` 回归测试与本文件、`docs/AGENT_LOG.md`

### 验证要求

* 每组先新增失败测试，再实现最小修复。
* 通过专项 pytest、全量 pytest、Ruff、MyPy、源码编译和 `git diff --check`。
* 覆盖凭据路径、原子写入、junction、精确编辑、受限测试执行、默认工具装配、trace 生命周期/并发、错误优先级和 pending checkpoint 恢复。

### 实现与评审前验证

* 变更专项：`uv run --no-sync pytest tests/test_checkpoints.py tests/test_file_tools.py tests/test_feedback_loop.py -q -p no:cacheprovider` → `138 passed, 7 skipped`。
* 全量回归：`uv run --no-sync pytest -q -p no:cacheprovider` → `711 passed, 13 skipped`。
* 质量门禁：`uv run --no-sync ruff check src tests`、`uv run --no-sync mypy src`、`uv run --no-sync python -m compileall -q src tests` 和 `git diff --check` 均通过。
* 当前仅完成评审前验证；两阶段新鲜评审、评审返工后的最终门禁、临时文件清理和提交号待回填。
* 评审返工安全回归：隐藏凭据后缀与 PEM 私钥脱敏测试 `7 passed`；首次受宿主 Windows Temp ACL 阻断，已改用可写临时目录重新取得完整门禁。
* 修复后全量验证（开发者本地 PowerShell）：`uv run --no-sync pytest -q -p no:cacheprovider --basetemp C:\Temp\HanCode-t21r1\pytest` → `724 passed, 13 skipped in 30.69s`；Ruff、MyPy（27 个源文件）、compileall 和 `git diff --check` 均通过。

### 接口与状态契约

```python
@dataclass(frozen=True, slots=True)
class ToolResult:
    command: str | None = None
    mutation_applied: bool | None = None

def edit_file(
    project_root: Path,
    path: str,
    old_string: str,
    new_string: str,
) -> ToolResult: ...

def run_tests(
    project_root: Path,
    command: str | None,
    *,
    runner: Callable[..., CompletedProcess[str]] | None = None,
    timeout_seconds: float = 120.0,
) -> ToolResult: ...

def build_default_tool_registry(
    config: HanCodeConfig,
    *,
    run_tests_tool: Callable[[], ToolResult] | None = None,
) -> ToolRegistry: ...

def abort_pending_checkpoint(
    task_root: Path,
    checkpoint_id: str,
    *,
    restore_files: bool,
) -> CheckpointManifest: ...

def reconcile_pending_checkpoint(
    task_root: Path,
    state: TaskState,
    *,
    recover: bool,
) -> TaskState: ...
```

`CheckpointManifest.status` 的生命周期为 `pending | committed | rolled_back | aborted`。`FilesystemStateStore.reconcile()` 接收 `recover_pending`，AgentLoop 只在调用方显式传入 `resume=True` 时授权 pending 恢复；不接受 LLM 提供的任意测试命令，也不提供通用 shell 或多文件 patch。

---

# M6：Delivery 与 Demo

---

## T22：Delivery Artifacts 生成

| 元信息           | 值                          |
| ------------- | -------------------------- |
| 状态            | [x] 已完成（两阶段评审 + 返工修复 + 全量回归通过） |
| 依赖            | T19, T20, T21              |
| 可并行           | 不并行；交付产物依赖反馈与上下文           |
| Worktree / PR | `feature/M6`                |
| 主贡献相关         | 是，知识沉淀交付                   |
| Commit        | TODO（等待开发者授权提交）           |

### 目标

生成课程项目交付产物：`TEST_REPORT.md`、`REVIEW.md`、`KNOWLEDGE.md`、`DELIVERABLES.md`。

### 涉及文件

* `src/hancode/delivery.py`
* `src/hancode/state.py`
* `tests/test_delivery.py`

### SPEC 依据

* 测试报告与审查记录。
* Knowledge Delivery。
* deliver phase 不应修改业务代码。
* 缺 KNOWLEDGE 或 DELIVERABLES 不得 completed。

### 接口契约

```python
def write_test_report(task_root: Path, report: FeedbackReport, command: str) -> Path: ...
def write_review(task_root: Path, coverage: list[RequirementCoverage], risks: list[str]) -> Path: ...
def write_knowledge(task_root: Path, items: list[KnowledgeItem]) -> Path: ...
def write_deliverables(
    task_root: Path,
    result: AgentRunResult,
    coverage: Sequence[RequirementCoverage] = (),
) -> Path: ...

class ResultBuilder:
    def build(
        self,
        task_root: Path,
        run_result: AgentRunResult,
        coverage: Sequence[RequirementCoverage] = (),
        knowledge_items: Sequence[KnowledgeItem] = (),
    ) -> DeliveryResult: ...

@dataclass(frozen=True, slots=True)
class DeliveryResult:
    def to_dict(self) -> dict[str, object]: ...
```

`DeliveryResult.to_dict()` 输出键：`status`、`task_id`、`course_project_summary`、`requirements_covered`、`files_changed`、`tests_run`、`test_status`、`checkpoints`、`rollback_performed`、`deliverables`、`knowledge_items`、`trace_event_ids`、`risks`、`next_steps`。

输入：task root、测试反馈、需求覆盖、风险、trace 摘要、最终结果；`coverage` 为可选参数。写入 `DELIVERABLES.md` 时会将 coverage 的确定性摘要和最终状态持久化至 `state.json`；后续 `ResultBuilder` 必须提供相同 coverage，并只以持久化状态给出 completed。
输出：四个 Markdown 产物。
不变量：deliver phase 不修改业务代码。
错误处理：缺少测试或 review 时在 `risks[]` 中说明；核心需求未覆盖、测试未通过或 coverage 与已持久化交付回执不一致时 blocked / failed。

### 预期失败测试

* `test_write_test_report_contains_command_status_summary`
* `test_code_change_requires_test_or_risk_note`
* `test_review_contains_requirement_coverage_table`
* `test_knowledge_contains_decisions_failures_and_reusable_lessons`
* `test_deliver_requires_knowledge_file`
* `test_deliver_requires_deliverables_file`
* `test_deliver_with_failed_tests_returns_blocked`
* `test_delivery_result_to_dict_redacts_directly_constructed_values`
* `test_result_builder_blocks_when_delivery_coverage_differs_from_receipt`
* `test_delivery_status_is_persisted_and_not_overridden_by_stale_run_result`

### 实现要点

* Markdown 标题和表格结构稳定，便于课程评估和测试断言。
* REVIEW 至少包含需求、证据、状态、风险列。
* KNOWLEDGE 至少包含课程知识点、设计决策、测试失败、错误修复、可复用模式。
* DELIVERABLES 至少包含交付物清单、测试状态、风险、最终状态。
* `state.json` 持久化 coverage 摘要与最终状态；Markdown 只作可读交付物，不能反向成为机器状态来源，`AgentRunResult.status` 也不能覆盖持久化状态。

### 验证步骤

```powershell
uv run pytest tests/test_delivery.py -v
uv run ruff check src/hancode/delivery.py src/hancode/state.py tests/test_delivery.py
uv run mypy src/hancode/delivery.py src/hancode/state.py
```

### 完成判定

* Markdown 产物标题和结构稳定，可被测试断言。
* deliver phase 不修改业务代码。
* 缺测试 / 缺 review 时写入 risks。

### 实际验证

* 专项测试：`$env:PYTHONPATH='src'; uv run --no-sync pytest tests/test_delivery.py tests/test_state.py tests/test_workspace.py -q -p no:cacheprovider` 通过，75 passed。
* Lint：`uv run --no-sync ruff check src/hancode/delivery.py src/hancode/state.py src/hancode/workspace.py tests/test_delivery.py tests/test_state.py tests/test_workspace.py` 通过。
* Type check：`uv run --no-sync mypy src/hancode/delivery.py src/hancode/state.py src/hancode/workspace.py` 通过，no issues found in 3 source files。
* 全量回归：`uv run --no-sync pytest -q -p no:cacheprovider` 通过，577 passed，9 skipped，0 failed。
* 两阶段评审：第一阶段检查接口、状态一致性、SPEC/PLAN 同步和结构化错误；第二阶段检查链接 fail-closed、溯源、脱敏与全量验证证据；两阶段均无阻塞项。
* 返工修复（`docs/superpowers/plans/2026-07-17-t22-review-remediation.md`）：
  * SPEC §7.4 同步 `delivery_coverage_digest` 字段与约束；PLAN T22 补充 `ResultBuilder.build` / `DeliveryResult` 契约与 `to_dict()` 14 个输出键。
  * `delivery.py` / `state.py` 的 `_is_link` 异常子句统一为 `(AttributeError, OSError, RuntimeError)`，与 `workspace.py` 一致。
  * `write_knowledge` 新增 `source_trace_id` 非空守卫（`delivery_knowledge_provenance_required`）。
  * `write_deliverables` 新增 `AgentRunResult` 类型守卫（`delivery_result_invalid`）；blocker / next_steps 文案统一中文；`_cell` 删除冗余换行替换。
  * #6 双重 state 加载保留为写入前重校验；#9 三处 `_is_link` 共享 helper 抽取列为后续技术债。

### 非目标 / 边界

* 不让真实 LLM 写总结。
* 不做漂亮模板渲染。
* 不运行完整 demo。

---

## T23：MockLLM 机制 Demo

| 元信息           | 值                 |
| ------------- | ----------------- |
| 状态            | [x] 已完成（待开发者授权提交） |
| 依赖            | T21, T22          |
| 可并行           | 不并行；集成演示任务        |
| Worktree / PR | `feature/M6`      |
| 主贡献相关         | 是，主贡献演示           |
| Commit        | TODO              |

### 目标

实现可重复运行的 MockLLM demo，证明 policy denial、checkpoint、测试失败反馈、retry、rollback、delivery artifacts 真实发生。

### 涉及文件

* `examples/broken_project/`
* `scripts/demo_mock_loop.py`
* `tests/test_mock_demo.py`

### SPEC 依据

* MockLLM 机制演示。
* 主贡献机制必须在无网络、无真实 LLM、无真实凭据下可复现。
* trace 必须证明控制流真实发生。

### 接口契约

```python
def run_mock_demo(project_root: Path) -> AgentRunResult: ...
```

输入：demo project root。
输出：AgentRunResult、trace、TEST_REPORT、REVIEW、KNOWLEDGE、DELIVERABLES。
不变量：demo 不依赖真实 LLM、网络或 API key。
错误处理：demo 任一步失败时返回 blocked / failed，并保留 trace。

### 预期失败测试

* `test_mock_demo_runs_without_real_credentials`
* `test_mock_demo_trace_contains_policy_denial`
* `test_mock_demo_trace_contains_feedback_generated`
* `test_mock_demo_trace_contains_checkpoint_created`
* `test_mock_demo_trace_contains_rollback_performed`
* `test_mock_demo_generates_knowledge_and_deliverables`

### 实现要点

* demo 使用固定 MockLLM action 序列。
* demo 至少包含：

  * 一次 protected file write 被拒绝。
  * 一次合法 code write 前 checkpoint。
  * 一次测试失败。
  * 一次反馈分类。
  * retry budget 消耗。
  * rollback。
  * deliver artifacts 生成。
* `examples/broken_project/` 只作为 fixture，不作为 HanCode 自身实现。
* fixture 中使用标准库 `unittest`；测试器以固定 argv、`shell=False` 和有限超时执行，不调用网络或 provider。
* 测试报告必须直接使用该次 `ToolResult` 的确定性失败分类和原始（已脱敏）输出，不能从 trace 状态反向推断摘要。
* 每次 `AgentLoop` 子运行使用局部 trace 序号适配器；持久 trace 仍由文件系统适配器统一写入，最终结果只读取持久 trace。
* retry 预算耗尽后的 rollback 保留在 review；恢复后的正确实现通过测试后才切换到 deliver 并调用 T22 交付写入器。

### 实施记录（待评审）

* 新增受保护的课程要求、初始缺陷加法实现与 `unittest` fixture；运行时仅接受该 fixture 的干净副本，其他目录返回结构化 `mock_demo_fixture_required`。
* 固定 MockLLM action 序列依次证明：protected write 拒绝、source write 前 checkpoint、两次失败测试与确定性 `assertion_failure` 分类、retry budget 耗尽、rollback、正确修复后的通过测试，以及 6 个交付物写入。
* demo 对未预期的运行时异常收口为结构化 `mock_demo_internal_error`，并保留 trace 与 blocked state；预期的 HanCode 错误保留原错误码。
* TDD：先验证 fixture 与脚本缺失导致 Red；随后新增“测试报告包含真实 unittest 输出”的断言，初始报告仅含合成 `OK` 而失败，改为直接传递 `ToolResult` 分类报告后 Green。
* 两阶段评审后验证：`uv run --no-sync pytest tests/test_mock_demo.py -q -p no:cacheprovider --basetemp '.test-tmp-t23-r2-green'` 为 8 passed；脚本原命令 `uv run --no-sync python scripts/demo_mock_loop.py` 返回 `completed`；专项 ruff 与 mypy 通过。全量回归为 585 passed、10 skipped。

### 验证步骤

```powershell
uv run pytest tests/test_mock_demo.py -v
uv run python scripts/demo_mock_loop.py
uv run ruff check scripts/demo_mock_loop.py tests/test_mock_demo.py
uv run mypy src
```

### 完成判定

* `uv run python scripts/demo_mock_loop.py` 可重复运行。
* demo 不依赖真实 LLM、网络或 API key。
* trace 能证明 policy、feedback、checkpoint、rollback、deliver 发生过。

### 非目标 / 边界

* 不做真实学生项目完整实现。
* 不做 Docker demo image。
* 不接真实 provider。

---

# M7：CLI / 凭据 / CI

---

## T24：CLI 最小入口

| 元信息           | 值                                 |
| ------------- | --------------------------------- |
| 状态            | [x] 已完成（TDD、两阶段新鲜评审、静态门禁、全量回归与 wheel 验证通过） |
| 依赖            | T2, T23                           |
| 可并行           | 可先实现 help / init，demo 命令等 T23 后接入 |
| Worktree / PR | `feature/M7`                      |
| 主贡献相关         | 否，交付入口                            |
| Commit        | `e272991` — `feat: 完成 T24 CLI 最小入口` |

### 目标

实现 Typer CLI 的最小命令结构，使用户可以初始化 workspace、运行 mock demo、查看帮助和导出产物。

### 涉及文件

* `src/hancode/cli.py`
* `src/hancode/demo.py`
* `src/hancode/export.py`
* `src/hancode/_demo_fixture/`
* `scripts/demo_mock_loop.py`
* `tests/test_cli.py`
* `tests/test_export.py`
* `tests/test_mock_demo.py`
* `pyproject.toml`

### SPEC 依据

* CLI entry point。
* Headless CLI 是 Demo、测试和课程评估入口。
* CLI 不应绕过 Harness Core。

### CLI 命令契约

```text
hancode --help
hancode init [PROJECT_ROOT]
hancode demo --provider mock
hancode export --task task-001 --out deliverables/
```

输入：CLI 参数、workspace 路径、provider 参数。
输出：稳定 exit code、结构化文本输出、必要产物。
本任务实际实现：`help`、`init`、`demo --provider mock`、`export`；`auth` 留给 T25，通用 `run` 等待 TaskController 对应任务卡。
不变量：CLI 只调用 core，不绕过 policy、workspace、state 或 demo runner；demo runner 与 fixture 同时包含在源码和 package data 中。
错误处理：provider 未知 exit code 1；配置错误 exit code 2；trace/checkpoint 不可恢复错误 exit code 3。

### 接口契约

```python
def run_packaged_mock_demo() -> DeliveryResult: ...

def export_task_artifacts(
    project_root: Path,
    task_id: str,
    output_dir: Path,
) -> ExportResult: ...
```

`ExportResult.to_dict()` 输出 `task_id`、`output_dir` 和按稳定顺序排列的 `artifacts`。
export 只复制 state 声明存在的 `SPEC.md`、`PLAN.md`、`TEST_REPORT.md`、`REVIEW.md`、`KNOWLEDGE.md`、`DELIVERABLES.md`，不覆盖已有目录，不导出 state、trace、checkpoint 或凭据。

### 预期失败测试

* `test_cli_help_displays_supported_commands`
* `test_cli_init_creates_workspace_with_deterministic_defaults`
* `test_cli_init_accepts_explicit_project_metadata`
* `test_cli_demo_runs_with_mock_provider_without_credentials`
* `test_cli_unknown_provider_returns_clear_error`
* `test_cli_config_error_uses_stable_exit_code`
* `test_cli_trace_error_uses_unrecoverable_exit_code`
* `test_cli_export_copies_declared_artifacts`
* `test_export_copies_only_declared_delivery_artifacts`
* `test_export_rejects_inconsistent_task_state`
* `test_export_rejects_existing_output_without_overwriting`
* `test_export_rejects_task_path_escape`
* `test_export_rejects_linked_output_parent`
* `test_packaged_mock_demo_runs_without_repository_fixture`

### 实现要点

* 使用 Typer。
* `demo --provider mock` 不要求真实凭据。
* CLI 输出状态必须明确：completed / blocked / failed。
* 不在命令行参数中接收明文 key。
* demo runner 从 `scripts/` 迁入 `src/hancode/`，脚本仅保留薄入口；固定 fixture 作为 package data，确保 wheel 安装后仍可运行。
* init 默认当前目录、目录名项目 ID、稳定非空课程/作业占位值；显式参数可以覆盖默认值。
* export 通过 `task_path`、`load_state` 和 `reconcile_state` 使用权威 task state；目标目录使用临时目录完成后再重命名。

### 验证步骤

```powershell
uv run pytest tests/test_mock_demo.py tests/test_cli.py tests/test_export.py -v
uv run ruff check src/hancode/demo.py src/hancode/cli.py src/hancode/export.py scripts/demo_mock_loop.py tests/test_mock_demo.py tests/test_cli.py tests/test_export.py
uv run mypy src/hancode/demo.py src/hancode/cli.py src/hancode/export.py scripts/demo_mock_loop.py
uv run hancode --help
uv run hancode demo --provider mock
```

### 实际验证

* Red：迁移测试首次导入 `hancode.demo` 时因模块不存在得到预期 `ImportError`；CLI 测试首次导入 `hancode.cli` 时得到预期 `ImportError`；export 测试首次调用 `hancode.export` 时得到预期 `ModuleNotFoundError`。
* Green：T23 demo 专项迁移后 `9 passed`；CLI 专项 `9 passed`；CLI + export 联合专项 `13 passed`；T24 三模块专项合计 `23 passed`。
* 分发：`uv build --wheel` 成功，wheel 包含 `hancode/cli.py`、`hancode/demo.py`、`hancode/export.py` 和三份 `_demo_fixture` 文件。
* 全量：`uv run --no-sync pytest -q -p no:cacheprovider` 为 `600 passed、11 skipped`；Ruff 全量通过；Mypy `src scripts/demo_mock_loop.py` 为 `Success: no issues found in 24 source files`。
* 入口：`uv run --no-sync hancode --help` 显示 `init`、`demo`、`export`；`uv run --no-sync python scripts/demo_mock_loop.py` 返回码 0。
* 两阶段新鲜评审：第一阶段确认 CLI 退出码、demo 包资源和 export 白名单方向正确，并要求确认 wheel package data；`uv build --wheel` 已证明资源进入 wheel。第二阶段发现 export 未检查父目录 symlink/junction；新增回归测试先 Red、补充逐级链路检查后 Green，专项 `13 passed`。随后补充 JSON 键顺序和 Typer 缺参 exit code 回归；无 Critical/Important 未解决项。最终将 package-data 从宽泛 glob 收窄为三类明确文件模式，避免 pytest `__pycache__` 进入 wheel。

### 完成判定

* CLI help 可用。
* init 能创建 workspace。
* mock demo 可通过 CLI 运行。
* export 只导出允许的 delivery artifacts，并对不一致 state、链接和已存在目标 fail-closed。
* T23 回归、专项 lint/type check、全量门禁和两阶段新鲜评审通过。

### 非目标 / 边界

* 不实现复杂 TUI。
* 不实现真实 provider smoke test。
* 不实现 Docker。

---

## T25：CredentialProvider

| 元信息           | 值                   |
| ------------- | ------------------- |
| 状态            | [x] 已完成             |
| 依赖            | T3, T24             |
| 可并行           | 可与 T26 部分并行         |
| Worktree / PR | `feature/M7`        |
| 主贡献相关         | 否，安全边界              |
| Commit        | `07f67af`           |

### 目标

实现凭据状态、录入、清除的安全边界，保证 CLI、trace、日志、测试快照不打印真实 secret。

### 涉及文件

* `src/hancode/credentials.py`
* `tests/test_credentials.py`
* `src/hancode/cli.py`
* `tests/test_cli.py`

### SPEC 依据

* 凭据与分发设计。
* 凭据状态检查只能显示是否存在，不得回显明文。
* 优先使用 keyring，`.env` 仅作为本地开发 fallback。

### 接口契约

```python
CredentialSource = Literal["keyring", "env", "dotenv", "missing"]

@dataclass(frozen=True, slots=True)
class CredentialStatus:
    configured: bool
    provider: str
    source: CredentialSource
    masked_id: str | None = None

class CredentialProvider:
    def status(self, provider: str) -> CredentialStatus: ...
    def get_secret(self, provider: str) -> str: ...
    def set_secret(self, provider: str, value: str) -> None: ...
    def clear_secret(self, provider: str) -> None: ...

def credentials_status(provider: str) -> CredentialStatus: ...
def credentials_set(provider: str, secret: str) -> None: ...
def credentials_clear(provider: str) -> None: ...
```

输入：provider、隐藏输入 secret。
输出：CredentialStatus 或操作结果。
不变量：CLI 只接受显式 `--provider`，不通过命令行参数接收明文 key；status 只显示 configured/source/masked_id。
来源优先级：`keyring → env → dotenv → missing`；环境变量固定映射为 `openai_compatible → OPENAI_API_KEY`、`anthropic → ANTHROPIC_API_KEY`，`.env` 默认读取当前目录且只读。
写入边界：`set_secret` / login / update 只写 OS keyring（service=`hancode`、account=`provider`），keyring 不可用时结构化失败，不静默写 `.env`。
清除边界：clear 需要确认；仅清除 keyring。若有效来源是 env 或 dotenv，直接返回 `credential_external_source_requires_manual_clear`，不虚报成功；mock/local 不需要 secret，status 为 `configured=true/source=missing`。
错误处理：unknown provider、空 secret、keyring/dotenv 失败和外部来源清除均返回 `StructuredError`，错误文本不包含 secret。

### 预期失败测试

* `test_auth_status_does_not_print_secret`
* `test_credential_status_reports_configured_without_value`
* `test_credentials_clear_removes_secret`
* `test_auth_login_does_not_accept_key_argument`
* `test_fake_credential_provider_for_tests`
* `test_credential_status_falls_back_to_environment`
* `test_credential_status_falls_back_to_dotenv`
* `test_keyring_unavailable_fails_closed_without_writing_dotenv`
* `test_dotenv_symlink_is_structured`
* `test_cli_auth_login_uses_hidden_input`
* `test_cli_auth_update_overwrites_fake_keyring_secret`
* `test_cli_auth_clear_does_not_claim_to_clear_external_source`
* `test_cli_auth_login_keeps_json_on_stdout_with_real_hidden_prompt`

### 实现要点

* 使用 fake credential provider 完成单元测试。
* 使用可注入的 fake keyring backend；真实 OS keyring 不进入 CI 测试路径。
* `.env` fallback 明确标注为本地开发后备。
* dotenv 路径拒绝 symlink / 非普通文件，读取、解析和 loader 异常统一 fail-closed。
* 所有错误、CLI stdout/stderr 和 status 输出脱敏；mask 覆盖 Unicode 控制字符与行分隔符。
* auth 子命令为 `status/login/update/clear --provider <provider>`；login/update 使用隐藏输入，clear 使用 stderr 确认提示。

### 验证步骤

```powershell
uv run pytest tests/test_credentials.py -v
uv run pytest tests/test_credentials.py tests/test_cli.py -q
uv run ruff check src/hancode/credentials.py src/hancode/cli.py tests/test_credentials.py tests/test_cli.py
uv run mypy src/hancode/credentials.py src/hancode/cli.py
```

### 实际验证记录（2026-07-18）

* TDD Red：核心测试首次导入不存在的 `hancode.credentials`；CLI 先验证 auth help、凭据状态、隐藏输入和 keyring failure，得到 8 项预期失败；评审返工的 keyring 读故障、未知 provider、clear 确认/外部来源、删除异常、dotenv 异常、Unicode mask 和 stdout JSON 回归均先 Red 后 Green。
* Green：CredentialProvider + CLI 专项最终 `41 passed, 1 skipped`；跳过项为当前 Windows 权限不允许创建 symlink 的真实 symlink fixture。
* 质量门禁：Ruff `src/hancode/credentials.py src/hancode/cli.py tests/test_credentials.py tests/test_cli.py` 通过；MyPy 对两个源文件无错误；串行全量 pytest `632 passed, 12 skipped`；`uv build`、CLI help/auth help 和 `git diff --check` 通过。`hancode demo --provider mock` 在将 `TEMP/TMP` 指向 M7 可写临时目录后返回 `completed`；默认宿主 Temp 的 ACL 失败已记录为环境风险并清理临时目录。

### 评审与返工记录（2026-07-18）

* 第一阶段新鲜评审：发现 keyring 读取故障静默降级、未知 provider 先 prompt、clear 缺确认/外部来源误报成功、dotenv 真实边界测试不足；均以 Red → Green 修复。
* 第二阶段新鲜对抗评审：发现 `PasswordDeleteError` 被误判成功、交互提示污染 stdout、dotenv 任意异常穿透、clear 公共入口可绕过外部来源、Unicode mask 不完整、mock/local 先 prompt；均以 Red → Green 修复。
* 第二阶段修复后新鲜复核：Critical / Important / Minor 均 0，结论 clean；专项复核 `41 passed, 1 skipped`。

### 完成判定

* CLI 不输出 secret 明文。
* 测试只用 fake secret。
* 凭据状态可以显示来源和是否配置；login/update/clear 的 stdout 保持机器可读 JSON。
* keyring、env、dotenv 和 clear 的失败边界均返回结构化错误。

### 非目标 / 边界

* 不在 CI 中调用真实 provider。
* 不把 key 写入 config、trace、checkpoint。
* 不实现企业级 secret manager。

---

## T26：Package Build 与 CI

| 元信息           | 值                  |
| ------------- | ------------------ |
| 状态            | [x] 已完成            |
| 依赖            | T24, T25           |
| 可并行           | 不并行；交付验证任务         |
| Worktree / PR | `feature/M7`       |
| 主贡献相关         | 否，交付质量保障           |
| Commit        | `e18c71f`          |

### 目标

完成 Python package build、测试命令和 CI job，使项目可在干净环境中安装、测试和运行 MockLLM demo。

### 涉及文件

* `pyproject.toml`
* `uv.lock`
* `Makefile`
* `.github/workflows/ci.yml`
* `.gitlab-ci.yml`
* `tests/test_package_metadata.py`
* `tests/test_ci_config.py`

### SPEC 依据

* 分发设计。
* CI 应运行测试、lint、type check。
* CI 不依赖真实 LLM、网络或 secret。

### 接口契约

```text
uv sync --extra dev
uv run pytest
uv run ruff check src tests scripts
uv run mypy src
uv build
uv run hancode --help
uv run hancode demo --provider mock
```

输入：干净 checkout、已安装 uv。
输出：测试、lint、type check、package build 通过。
不变量：CI 不要求真实 API key。
错误处理：CI 失败必须记录原因，不得绕过。

### 预期失败测试

* `test_python_package_metadata_has_console_script`
* `test_make_check_contains_lint_typecheck_test`
* `test_github_ci_uses_uv_for_pytest_ruff_mypy`
* `test_gitlab_ci_contains_unit_test_job`
* `test_ci_does_not_require_real_secret`

### 实现要点

* `pyproject.toml` 保留 console script：

  * `hancode = "hancode.cli:app"`
* `pyproject.toml` 必须与项目约定保持一致：`requires-python >= 3.11`，ruff / mypy 目标版本也使用 Python 3.11。
* `uv.lock` 必须纳入版本控制，确保本地与 CI 使用一致的依赖解析结果。
* GitHub Actions 可作为仓库 CI，并通过 uv 安装依赖和运行质量门禁。
* 若课程要求 GitLab CI，补 `.gitlab-ci.yml` 的 `unit-test` job。
* 使用 `uv build` 生成 wheel / sdist。

### 验证步骤

```powershell
uv sync --extra dev
uv run pytest
uv run ruff check src tests scripts
uv run mypy src
uv build
uv run hancode --help
uv run hancode demo --provider mock
```

### 实施与评审记录

* TDD Red：新增 package / CI 配置契约后，初始专项为 6 failed、2 passed；失败准确指向缺失 `uv.lock`、Makefile 未使用 uv、GitHub CI 未运行 uv 门禁与缺失 GitLab `unit-test` job。
* Green：生成 `uv.lock`，将 Makefile 收敛为 `uv run` 门禁；GitHub Actions 与 GitLab CI 均固定 Python 3.11、`uv==0.11.8`、`uv sync --locked --extra dev`，并执行测试、lint、type check、build、源码 CLI 与 Mock Demo。
* 第一阶段新鲜评审发现：仅 `uv build` 后运行 editable CLI 不能证明 wheel 可安装。新增 CI 契约测试先 Red，再让两个 CI 都在独立 Python 3.11 venv 安装 `dist/*.whl` 后运行 `hancode --help` 与 `hancode demo --provider mock`。
* 第二阶段新鲜评审发现两个 Minor：wheel venv 位于工作区、配置测试未锁定命令顺序。修复后 wheel venv 分别位于 `$RUNNER_TEMP` / `$CI_BUILDS_DIR`，测试断言 `uv sync` 先于质量门禁、`uv build` 先于 wheel 安装。
* 最终验证：配置专项 11 passed；全量 `pytest` 为 643 passed、12 skipped；Ruff 通过；MyPy 为 24 个 source files 无问题；`uv lock --check`、`uv sync --locked --extra dev`、`uv build`、源码 CLI / Mock Demo 以及独立 Python 3.11 wheel CLI / Mock Demo 全部通过。
* 本机普通沙箱会拒绝 setuptools / pytest 临时目录写入；在受控临时目录以非沙箱方式复验成功。该限制未写入产品配置，也不影响 Linux CI。

### 完成判定

* 测试、lint、type check、package build 全绿。
* CI 文件包含 unit-test job。
* CI 不依赖真实 secret。

### 非目标 / 边界

* Docker image 属 post-MVP。
* 不做真实 LLM smoke test。
* 不部署线上服务。

---

## T27：README 运行与分发文档

| 元信息           | 值                            |
| ------------- | ---------------------------- |
| 状态            | [x] 已完成                      |
| 依赖            | T23, T24, T25, T26           |
| 可并行           | 最终文档任务                       |
| Worktree / PR | `feature/M7`                   |
| 主贡献相关         | 否，最终交付文档                     |
| Commit        | `81151dc`（实现与评审修正）       |

### 目标

更新 README，使新用户能在干净环境中安装、运行 mock demo、理解凭据安全和已知限制。

### 涉及文件

* `README.md`
* `tests/test_readme.py`
* `docs/AGENT_LOG.md`
* `docs/SPEC_PROCESS.md`
* `docs/PLAN.md`

### SPEC 依据

* 最终 README 必须包含安装、运行、凭据设置、分发方式、已知限制。
* 最终交付需要过程证据和验证命令。
* 不得承诺未实现能力。

### 文档内容要求

README 至少包含：

* 项目定位。
* Harness 核心机制。
* 安装方式。
* `hancode --help`。
* `hancode demo --provider mock`。
* 凭据设置方式。
* `.env` 明文风险。
* MockLLM 与真实 provider 区别。
* 已知限制。
* 验证命令。
* 不包含真实 key。

### 预期检查

* `test_readme_contains_mock_demo_command`
* `test_readme_mentions_no_real_credentials`
* `test_readme_documents_known_limitations`
* `test_readme_documents_verification_commands`
* `test_readme_documents_source_and_wheel_installation`
* `test_readme_documents_auth_commands_and_hidden_input`
* `test_readme_scopes_available_and_installed_commands`
* `test_readme_contains_no_secret_like_literals`
* `test_readme_documents_runtime_temp_boundary`
* `test_readme_documents_init_and_export_boundaries`

### 实现要点

* README 不写“未来会支持”式不确定承诺。
* 所有命令必须与 CLI 实际命令一致。
* AGENT_LOG 记录实现过程、验证命令和人工干预。
* SPEC_PROCESS 记录冷启动验证结果和修订。

### 当前实现记录

* TDD Red：收紧 README 契约测试后，专项结果为 `4 failed、1 passed`；失败原因是 README 缺少无真实凭据说明、真实 key 禁止提交、完整限制表述、Python 3.11+ 与 wheel 安装方式及 `.env` 明文风险。
* TDD Green：补充 README 的 headless CLI、Harness 机制、源码/wheel 安装、MockLLM、凭据安全、已知限制和验证命令后，README 专项为 `6 passed`。
* README 明确当前未提供 `hancode run`、REPL/TUI/WebUI、真实 Provider 执行和 Docker 必需分发路径；这些内容不作为当前功能承诺。
* 第一阶段新鲜评审确认 README 与 CLI、凭据边界和范围要求一致，但指出测试存在性断言偏弱；新增分区正反断言和 secret-like 文本扫描后，先得到 `1 failed、7 passed`，补充 wheel 安装命令分区标题后 Green 为 `8 passed`。
* 第二阶段冷启动复核确认受限沙箱的系统 Temp ACL 会导致 Demo 返回 `cli_internal_error`；同一命令在受控可写环境中返回 `status=completed`，因此将 `TEMP/TMP` 可写前提和该环境风险写入 README，不修改生产 Demo。
* 第二阶段建议已转为测试和文档修正：补充 Anthropic secret-like 前缀、非空环境变量赋值扫描、init/export 行为边界；README 专项最终为 `10 passed`。
* 全量回归、静态检查、wheel 独立环境 smoke 和第二阶段复审均已完成；最终清理后由文档追踪提交回填本任务证据。

### 最终验证记录

* `uv lock --check`：通过，解析 39 个锁定依赖。
* README 专项：`10 passed`。
* 全量 pytest：`653 passed、12 skipped`。
* Ruff：`All checks passed!`；MyPy：`Success: no issues found in 24 source files`。
* `uv build`：成功生成 `dist/hancode-0.1.0.tar.gz` 和 `dist/hancode-0.1.0-py3-none-any.whl`。
* 源码环境 `hancode --help` 和 `hancode demo --provider mock` 均返回 0，Demo `status=completed`。
* 独立 Python 3.11.15 wheel 环境安装 wheel 后，裸 `hancode --help` 和 `hancode demo --provider mock` 均返回 0，Demo `status=completed`。
* 两阶段新鲜评审：第一阶段初评 Important 已修复并复审通过；第二阶段初评的 Temp ACL 环境阻塞、状态同步和测试/文档问题已修复，复审 Critical/Important/Minor 均为 0。
* `git diff --check`：通过；验证生成的 build、dist、wheel venv、uv cache、pytest 临时目录和 `.superpowers` 过程文件已清理。

### 验证步骤

```powershell
Get-Content -Raw -Encoding UTF8 README.md
Select-String -Path README.md -Pattern 'hancode demo --provider mock','凭据','已知限制','uv run pytest'
uv run pytest
git status --short
```

### 完成判定

* README 能让陌生用户运行 mock demo。
* README 不包含真实 key。
* 文档与当前 CLI 命令一致。
* AGENT_LOG / SPEC_PROCESS 已补充最终过程证据。

### 非目标 / 边界

* 不写 REFLECTION 正文。
* 不承诺未实现能力。
* 不补 Docker。

---

## T28：P0 分层结构重组与装配层抽取

| 元信息           | 值                                      |
| ------------- | -------------------------------------- |
| 状态            | [x] 已完成                              |
| 依赖            | T1-T27                                |
| 可并行           | 不并行；先迁移模块，再抽取 provider / engine / CLI |
| Worktree / PR | 当前结构调整会话                         |
| 主贡献相关         | 否；结构与装配支撑                         |
| Commit        | 未提交（用户未要求提交）                  |

### 目标

在不改变 AgentLoop、ToolPolicy、Checkpoint、Trace、State 业务逻辑、trace 格式、state schema 和 checkpoint manifest schema 的前提下，将 P0 模块迁移到分层包，并保留旧 import 的兼容代理。通用 AgentLoop 装配统一进入 `runtime/engine.py`，CLI 实现迁移到 `interfaces/cli.py`，Provider 仅实现现有 MockLLM 能力，不引入真实网络调用。

### 本轮边界

* 实际目录使用 `storage/`、`tooling/`，避开既有 `workspace.py`、`tools.py` 与 Python 包同名冲突。
* P0 包为 `core/`、`runtime/`、`policy/`、`storage/`、`tooling/`、`providers/`、`interfaces/`。
* `delivery.py`、`credentials.py`、`path_security.py` 保持平铺；`app/`、`demo_support/`、`delivery_support/` 延后到后续任务。
* 旧路径通过模块别名兼容代理保留，以维持现有测试中的 monkeypatch 和外部 import 行为。
* `providers/factory.py` 只支持 `mock`；`prompt_builder.py` 与 `action_schema.py` 只提供确定性边界适配，不调用真实 Provider。
* Demo 本轮不大拆文件，只改为通过 `runtime.engine.create_agent_loop()` 复用通用装配，并继续注入 MockLLM、测试工具和 demo trace 适配器。

### 涉及文件

* `src/hancode/core/`
* `src/hancode/runtime/`
* `src/hancode/policy/`
* `src/hancode/storage/`
* `src/hancode/tooling/`
* `src/hancode/providers/`
* `src/hancode/interfaces/`
* `src/hancode/actions.py`、`models.py`、`errors.py`、`phases.py`、`state.py`、`router.py`、`config.py`
* 其他平铺兼容代理：`agent_loop.py`、`context.py`、`feedback.py`、`tool_policy.py`、`path_policy.py`、`workspace.py`、`checkpoints.py`、`trace.py`、`export.py`、`tools.py`、`file_tools.py`、`test_tools.py`、`tool_factory.py`、`llm.py`、`cli.py`
* `src/hancode/demo.py`、`tests/test_structure_layers.py`、对应回归测试、`docs/AGENT_LOG.md`

### 接口契约

```python
def create_provider_adapter(config: HanCodeConfig) -> LLMClient: ...

def create_agent_loop(
    project_root: Path,
    task_id: str,
    *,
    provider: LLMClient | None = None,
) -> AgentLoop: ...

def run_task(
    project_root: Path,
    task_id: str,
    *,
    resume: bool = False,
    provider: LLMClient | None = None,
) -> AgentRunResult: ...
```

输入：既有 Project / Task Workspace、可选 MockLLM provider。
输出：新路径与旧路径均可导入的同一实现对象；engine 返回现有 AgentLoop 结果。
不变量：兼容代理不复制核心类；新旧导入的类身份一致；默认 provider 只产生空 action 序列；所有现有持久化格式和 public behavior 不变。
错误处理：未知 provider 返回现有 `NotImplementedError` 边界；核心业务错误继续使用现有结构化错误。

### 预期失败测试

* `test_layered_modules_are_importable`
* `test_legacy_imports_alias_layered_implementations`
* `test_provider_factory_supports_only_mock`
* `test_engine_accepts_injected_provider`
* `test_cli_entry_proxy_exports_app`
* `test_demo_uses_engine_factory`

### 实现要点

* 先新增层结构与兼容 / engine 测试并确认 Red，再迁移文件和修正新目录内部 import。
* 旧模块使用模块别名代理，而不是复制定义，确保现有测试对旧路径模块级依赖和 monkeypatch 继续有效。
* `runtime/engine.py` 复用 `FilesystemAgentLoopPorts`、`ContextBuilder`、`ToolPolicy`、默认工具注册、`FeedbackBuilder` 和 `load_config`。
* Demo 的自定义 registry、trace adapter 与 max step 仍通过 engine 的可选装配参数注入，不在 demo 中重新构造 AgentLoop。
* `providers/base.py`、`providers/mock.py` 从旧 `llm.py` 拆出；旧 `llm.py` 同时代理两者。

### 验证步骤

```powershell
$env:PYTHONPATH='src'; uv run --no-sync pytest tests/test_structure_layers.py -v -p no:cacheprovider
$env:PYTHONPATH='src'; uv run --no-sync pytest -p no:cacheprovider
$env:PYTHONPATH='src'; uv run --no-sync ruff check src tests --no-cache
$env:PYTHONPATH='src'; uv run --no-sync mypy src --cache-dir (Join-Path $env:TEMP 'hancode-mypy-t28')
$env:PYTHONPATH='src'; uv run --no-sync python -m compileall -q src tests
git diff --check
```

### 完成判定

* P0 新路径全部可导入，旧路径仍可用且与新实现保持身份一致。
* demo、init、auth、export 的现有测试通过；MockLLM 不依赖网络或真实凭据。
* engine 负责通用 AgentLoop 装配，demo 不再手写 AgentLoop 构造。
* pytest、Ruff、MyPy、compileall 和 `git diff --check` 有本轮新鲜输出。
* 本卡状态、验证证据和剩余风险同步到本文件与 `docs/AGENT_LOG.md`。

### 实际验证记录

* TDD Red：新增 `tests/test_structure_layers.py` 后运行专项，6 项均按预期失败：缺少 `core/`、`providers/`、`runtime/`、`interfaces/` 和 engine factory。
* Green：完成分层迁移、兼容代理、Provider、engine、CLI 和 Demo 装配抽取后，专项 `tests/test_structure_layers.py` 为 `6 passed`。
* 全量 pytest：`$env:PYTHONPATH='src'; uv run --no-sync pytest -p no:cacheprovider` 为 `730 passed, 13 skipped`。
* Ruff：`$env:PYTHONPATH='src'; uv run --no-sync ruff check src tests --no-cache` 输出 `All checks passed!`。
* MyPy：`$env:PYTHONPATH='src'; uv run --no-sync mypy src --cache-dir (Join-Path $env:TEMP 'hancode-mypy-t28')` 输出 `Success: no issues found in 61 source files`。
* Compile：`$env:PYTHONPATH='src'; uv run --no-sync python -m compileall -q src tests` 通过。
* Package build：`uv build` 成功，构建日志确认新 `core`、`interfaces`、`policy`、`providers`、`runtime`、`storage`、`tooling` 包均进入 sdist / wheel；随后已清理 `dist/`、`build/` 和 `src/hancode.egg-info/`。
* CLI smoke：`uv run --no-sync hancode --help`、`uv run --no-sync hancode demo --provider mock`、`uv run --no-sync hancode auth status --provider mock` 和临时目录 `hancode init` 均返回成功。
* `git diff --check` 通过；本轮未创建或保留临时缓存、`.pyc`、pytest cache 或 `.superpowers` 文件。

### 实现结果与剩余风险

* `core/`、`runtime/`、`policy/`、`storage/`、`tooling/`、`providers/`、`interfaces/` 均可直接导入；旧平铺模块通过模块别名保持类和函数身份一致。
* `providers/factory.py` 只装配 `MockLLM([])`；未实现真实 OpenAI / Anthropic provider，符合本卡非目标。
* P1 `app/`、P2 `demo_support/` 和 `delivery_support/` 已由 T29/T30 完成；`credentials.py`、`path_security.py` 仍按既有边界保留平铺。

### 非目标 / 边界

* 不重写 AgentLoop、ToolPolicy、Checkpoint、Trace、State 业务逻辑。
* 不拆分 delivery、demo、app，不新增真实 OpenAI / Anthropic 调用。
* 不改变 trace JSONL、state JSON、checkpoint manifest 或 CLI 命令语义。
* 不顺手修复与结构迁移无关的既有安全或行为问题。

---

## T29：P1 应用服务层拆分

| 元信息           | 值                                      |
| ------------- | -------------------------------------- |
| 状态            | [x] 已完成                              |
| 依赖            | T28                                    |
| 可并行           | 不并行；先稳定应用门面，再拆分交付与 Demo     |
| Worktree / PR | 当前结构调整会话                         |
| 主贡献相关         | 否；应用装配与入口隔离                       |
| Commit        | 待回填                                  |

### 目标

新增 `app/` 应用服务层，把项目初始化、任务运行、凭据访问和交付导出从 CLI 入口中抽出。服务只调用已有确定性 core/runtime/storage/provider 机制，不改变 CLI 命令、JSON 输出、凭据边界或 export 行为。

### 涉及文件

* `src/hancode/app/__init__.py`
* `src/hancode/app/project_service.py`
* `src/hancode/app/task_service.py`
* `src/hancode/app/auth_service.py`
* `src/hancode/app/delivery_service.py`
* `src/hancode/interfaces/cli.py`
* `tests/test_app_layers.py`

### 接口契约

```python
class ProjectService:
    def initialize(self, project_root: Path, project_id: str, course_name: str, assignment_name: str) -> Path: ...

class TaskService:
    def initialize(self, project_root: Path, task_id: str) -> Path: ...
    def run(self, project_root: Path, task_id: str, *, resume: bool = False, provider: LLMClient | None = None) -> AgentRunResult: ...

class AuthService:
    def status(self, provider: str) -> CredentialStatus: ...
    def set_secret(self, provider: str, secret: str) -> None: ...
    def clear_secret(self, provider: str) -> None: ...

class DeliveryService:
    def export(self, project_root: Path, task_id: str, output_dir: Path) -> ExportResult: ...
```

### 预期失败测试

* `test_app_service_modules_are_importable`
* `test_project_service_delegates_workspace_initialization`
* `test_task_service_delegates_engine_run`
* `test_auth_service_uses_injected_credential_provider`
* `test_delivery_service_delegates_export`
* `test_cli_uses_application_services_without_changing_output`

### 非目标 / 边界

* 不重写 `CredentialProvider`、`AgentLoop`、`Delivery` 或 `Export` 业务逻辑。
* 不新增 CLI 命令，不改变现有 exit code、stdout JSON 或 secret 处理。
* 不把服务层变成全局状态容器；凭据服务支持显式 provider 注入。

### 实际验证记录

* TDD Red：新增 app 层契约测试后，收集阶段因 `hancode.app` 不存在得到预期 `ModuleNotFoundError`。
* Green：新增 `ProjectService`、`TaskService`、`AuthService`、`DeliveryService`，并让 `interfaces/cli.py` 通过服务调用；`tests/test_app_layers.py` 的 P1 用例通过。
* 回归：`tests/test_app_layers.py tests/test_cli.py` 通过，CLI 现有 JSON、exit code、凭据注入行为不变。
* 全量与静态门禁记录统一回填在 T30 的最终验证中。

### 完成判定

* 应用服务模块可独立导入并可注入 fake / provider。
* CLI 不再直接编排 workspace、credential 和 export 机制。
* 现有 CLI public behavior 保持不变。

---

## T30：P2 Demo 与 Delivery 支持包拆分

| 元信息           | 值                                      |
| ------------- | -------------------------------------- |
| 状态            | [x] 已完成                              |
| 依赖            | T29                                    |
| 可并行           | 不并行；Delivery 兼容层先于 Demo 入口迁移    |
| Worktree / PR | 当前结构调整会话                         |
| 主贡献相关         | 否；交付与演示结构整理                       |
| Commit        | 待回填                                  |

### 目标

将交付产物能力拆到 `delivery_support/`，将离线 Demo 拆到 `demo_support/`，旧 `delivery.py` 与 `demo.py` 保留兼容模块别名。拆分只改变代码位置和 import，不改变产物内容、trace、state、checkpoint、Demo 结果或 package data。

### 涉及文件

* `src/hancode/delivery_support/__init__.py`
* `src/hancode/delivery_support/result.py`
* `src/hancode/delivery_support/reports.py`
* `src/hancode/delivery_support/review.py`
* `src/hancode/delivery_support/knowledge.py`
* `src/hancode/delivery_support/deliverables.py`
* `src/hancode/demo_support/__init__.py`
* `src/hancode/demo_support/runner.py`
* `src/hancode/demo_support/actions.py`
* `src/hancode/demo_support/fixture.py`
* `src/hancode/delivery.py`、`src/hancode/demo.py`
* `tests/test_app_layers.py`、`tests/test_delivery.py`、`tests/test_mock_demo.py`

### 接口契约

```python
from hancode.delivery_support.result import DeliveryResult, ResultBuilder
from hancode.delivery_support.reports import write_test_report
from hancode.delivery_support.review import write_review
from hancode.delivery_support.knowledge import write_knowledge
from hancode.delivery_support.deliverables import write_deliverables

from hancode.demo_support.runner import run_mock_demo, run_packaged_mock_demo
```

不变量：旧路径导入的类、函数与新路径保持身份一致；旧模块级 monkeypatch 仍作用于实际实现；Demo fixture 仍作为 package data 分发；Delivery 专项测试的 Markdown、状态和脱敏断言不变。

### 预期失败测试

* `test_delivery_support_modules_are_importable`
* `test_delivery_legacy_imports_alias_support_modules`
* `test_demo_support_modules_are_importable`
* `test_demo_legacy_imports_alias_runner`
* `test_demo_action_sequences_remain_deterministic`

### 非目标 / 边界

* 不修改交付 Markdown schema、DeliveryResult schema、Demo action 序列或 fixture digest。
* 不新增真实 LLM、网络调用、Docker 或新的 Demo 场景。
* 不删除旧入口文件；兼容层继续服务现有 CLI、测试和外部 import。

### 实际验证记录

* TDD Red：新路径契约测试初次运行时，`delivery_support` / `demo_support` 导入均因包不存在而失败。
* Green：Delivery 实现迁入 `delivery_support/result.py`，报告、审查、知识、交付由责任模块包装导出；Demo runner、action sequence、fixture 校验分别迁入 `demo_support/`。
* 兼容回归：旧 `hancode.delivery` / `hancode.demo` 指向新实现；现有 Delivery 的模块级 `save_state`、`_is_link` monkeypatch 和 Demo 的 registry / knowledge monkeypatch 均保持有效。
* 全量 pytest：`$env:PYTHONPATH='src'; uv run --no-sync pytest -p no:cacheprovider` 为 `741 passed, 13 skipped`。
* Ruff：`$env:PYTHONPATH='src'; uv run --no-sync ruff check src tests --no-cache` 通过。
* MyPy：`$env:PYTHONPATH='src'; uv run --no-sync mypy src --cache-dir (Join-Path $env:TEMP 'hancode-mypy-t29-t30-full')` 输出 `Success: no issues found in 76 source files`。
* Compile 与 package：`python -m compileall -q src tests`、`uv build` 通过；构建日志确认 `app`、`delivery_support`、`demo_support` 进入 sdist / wheel。
* CLI smoke：`hancode --help`、`hancode demo --provider mock`、`hancode auth status --provider mock` 均返回成功；`git diff --check` 通过。

### 完成判定

* P1/P2 新路径可导入，旧路径兼容代理可用。
* Delivery 产物、Demo trace/state/checkpoint 和 CLI 行为保持现有测试契约。
* 全量测试、静态检查、编译和 package build 均有本轮新鲜证据。

---

## S1：Headless 任务生命周期与 CLI 入口

| 元信息           | 值                                      |
| ------------- | -------------------------------------- |
| 状态            | [x] 已完成                              |
| 依赖            | T1-T30                                |
| 可并行           | 不并行；应用层入口任务                          |
| Worktree / PR | 当前结构调整会话                         |
| 主贡献相关         | 否；应用入口与任务生命周期                       |
| Commit        | `a337ea3`                  |

### 目标

扩展现有 TaskService 为任务生命周期应用服务，新增 CLI task 命令组和根级 run 命令，使用户可以创建带 goal 的任务、运行任务、恢复任务和查看任务状态。不新增 TaskController，不修改 AgentLoop 内核。

### 涉及文件

* `src/hancode/app/task_models.py`（新增）
* `src/hancode/app/task_service.py`（修改）
* `src/hancode/storage/workspace.py`（修改）
* `src/hancode/interfaces/cli.py`（修改）
* `src/hancode/providers/factory.py`（修改）
* `tests/test_task_service.py`（新增）
* `tests/test_cli_tasks.py`（新增）
* `tests/test_provider_factory.py`（新增）
* `tests/test_workspace.py`（修改）
* `tests/test_structure_layers.py`（修改）

### 接口契约

```python
class TaskService:
    def create(self, project_root: Path, goal: str, *, task_id: str | None = None) -> TaskSummary: ...
    def get(self, project_root: Path, task_id: str) -> TaskSummary: ...
    def list_tasks(self, project_root: Path) -> tuple[TaskSummary, ...]: ...
    def run(self, project_root: Path, task_id: str, *, resume: bool = False, provider: LLMClient | None = None) -> AgentRunResult: ...
    def resume(self, project_root: Path, task_id: str, *, provider: LLMClient | None = None) -> AgentRunResult: ...
```

### 实际验证

* 全量 pytest：796 passed, 13 skipped in 38.17s
* Ruff：All checks passed!
* MyPy：Success: no issues found in 54 source files
* CLI smoke：hancode task create/status/list/run/resume 和 hancode run 全部返回结构化 JSON

### 非目标 / 边界

* 不实现真实 Provider。
* 不实现 ASK_USER。
* 不实现实时事件流。
* 不实现 TUI。
* 不修改 AgentLoop 内核。
* 不修改 state.json schema version。

---

## S2：真实 OpenAI-Compatible ProviderAdapter

| 元信息           | 值                                      |
| --------------- | -------------------------------------- |
| 状态            | [x] 已完成                              |
| 依赖            | S1 (Headless 任务生命周期)               |
| 基线            | `154a7ec`                              |
| 主贡献相关         | 否；Provider 适配层                       |

### 阶段目标

实现真实 OpenAI-Compatible ProviderAdapter，使 HanCode 能由真实模型驱动，同时仍受自研 phase、policy、checkpoint、feedback 和 rollback 内核约束。完成后 `openai_compatible` 不再返回 `provider_not_implemented`。

### 阶段边界

**实现**：OpenAI-Compatible ProviderAdapter、真实 HTTP 请求、Context 转消息、System Prompt、Action JSON Schema、凭据读取、timeout、429/5xx/网络失败重试、401/403 结构化错误、无效响应解析、Provider 错误进入 blocked、Provider 错误 trace、FakeTransport 离线测试、可选真实模型 smoke test。

**不实现**：Anthropic Provider、本地模型 Provider、Streaming、原生 Function Calling、ASK_USER、TUI、Token 成本统计、多轮聊天历史恢复、自动模型发现、任意 HTTP Header 配置、自动 fallback。

### 核心架构约束

* AgentLoop 不知道 HTTP / OpenAI / API key，只知道 `next_action(context)`。
* ProviderAdapter 只能生成 Action，不能直接执行工具/访问 workspace/修改 state/创建 checkpoint/运行测试。
* Provider 重试与任务 retry_budget 是两种独立机制，Provider 重试不消耗 retry_budget。
* API key 不进入 stdout / state / trace / error message。

### 新增文件

| 文件 | 职责 |
| --- | --- |
| `src/hancode/providers/openai_compatible.py` | OpenAI-Compatible ProviderAdapter |
| `src/hancode/providers/transport.py` | HTTP Transport 抽象与默认实现 |
| `src/hancode/providers/errors.py` | ProviderError 和错误映射 |
| `tests/providers/test_openai_compatible.py` | Adapter 单元测试 |
| `tests/providers/test_transport.py` | Transport 和 timeout 测试 |
| `tests/providers/test_provider_integration.py` | FakeTransport → AgentLoop 集成测试 |

### 修改文件

`providers/base.py`、`providers/factory.py`、`providers/prompt_builder.py`、`providers/action_schema.py`、`core/config.py`、`app/task_service.py`、`runtime/agent_loop.py`、`runtime/engine.py`、`interfaces/cli.py`、`pyproject.toml`、`uv.lock`、`README.md`、`docs/PLAN.md`、`docs/AGENT_LOG.md`。

### TDD 实现顺序

#### S2-0：阶段一最后收尾

| 元信息           | 值                                      |
| --------------- | -------------------------------------- |
| 状态            | [x] 已完成                              |
| 涉及文件        | `src/hancode/interfaces/cli.py`, `tests/test_cli_tasks.py` |
| 目标            | `task list` 的 OSError 结构化边界       |
| 验证            | `test_cli_task_list_filesystem_failure_returns_json` 通过；全量 801 passed, 13 skipped |

#### S2-1：Provider 配置

| 元信息           | 值                                      |
| --------------- | -------------------------------------- |
| 状态            | [x] 已完成                              |
| 依赖            | S2-0                                   |
| 涉及文件        | `src/hancode/core/config.py`, `tests/test_config.py` |
| 目标            | 在 HanCodeConfig 增加 provider 连接字段并增加 URL/数值校验，保证 plaintext secret 规则不退化 |

新增配置字段：`provider_base_url`、`provider_timeout_seconds`、`provider_max_retries`、`provider_max_output_tokens`、`provider_max_response_bytes`。

校验规则：远程地址必须 HTTPS（localhost 允许 HTTP）；URL 禁止 username/password/query；timeout 正整数；retries 非负整数；output_tokens 正整数；response_bytes 正整数。

完成条件：配置失败测试通过；URL scheme/credential/query 校验生效；数值边界校验生效；plaintext secret 规则不退化。

实际验证：
- 全量 pytest：821 passed, 13 skipped（基线 801，新增 20 个 config 测试）
- Ruff：All checks passed!
- MyPy：Success: no issues found in 54 source files

#### S2-2：Prompt 与 Action Schema

| 元信息           | 值                                      |
| --------------- | -------------------------------------- |
| 状态            | [x] 已完成                              |
| 依赖            | S2-1                                   |
| 涉及文件        | `src/hancode/providers/prompt_builder.py`, `src/hancode/providers/action_schema.py`, `src/hancode/providers/base.py`, `src/hancode/tooling/factory.py`, `tests/providers/test_prompt_builder.py`, `tests/providers/test_action_schema.py` |
| 目标            | 实现 system prompt、phase 指令、user message 和动态 Action JSON Schema |
| 完成条件        | 给定相同 context 输出完全确定；Schema 示例能通过现有 parse_action；ASK_USER 不对模型开放 |

实际验证：
- 全量 pytest：850 passed, 13 skipped（基线 821，新增 29 个测试）
- Ruff：All checks passed!
- MyPy：Success: no issues found in 54 source files

#### S2-3：Transport 与 Decoder

| 元信息           | 值                                      |
| --------------- | -------------------------------------- |
| 状态            | [x] 已完成                              |
| 依赖            | S2-2                                   |
| 涉及文件        | `src/hancode/providers/transport.py`, `src/hancode/providers/errors.py`, `src/hancode/providers/openai_compatible.py`, `pyproject.toml`, `tests/providers/test_transport.py`, `tests/providers/test_response_decoder.py` |
| 目标            | 实现 ProviderTransport 抽象、HttpxProviderTransport、FakeTransport 和 ResponseDecoder |
| 完成条件        | FakeTransport 可完全替代真实 HTTP；Decoder 可以得到 Action dict；响应体和 header 不泄漏 |

实际验证：
- 全量 pytest：866 passed, 13 skipped（基线 850，新增 16 个测试）
- Ruff：All checks passed!
- MyPy：Success: no issues found in 57 source files

#### S2-4：Adapter、错误和重试

| 元信息           | 值                                      |
| --------------- | -------------------------------------- |
| 状态            | [x] 已完成                              |
| 依赖            | S2-3                                   |
| 涉及文件        | `src/hancode/providers/openai_compatible.py`, `tests/providers/test_openai_compatible.py` |
| 目标            | 实现 ProviderError、错误映射和 RetryPolicy |
| 完成条件        | 429/timeout/5xx 重试；401/400 不重试；达到上限后返回 ProviderError；使用注入 Sleeper |

实际验证：
- 全量 pytest：881 passed, 13 skipped（基线 866，新增 15 个测试）
- Ruff：All checks passed!
- MyPy：Success: no issues found in 57 source files

#### S2-5：Factory 与 Credential 装配

| 元信息           | 值                                      |
| --------------- | -------------------------------------- |
| 状态            | [x] 已完成                              |
| 依赖            | S2-4                                   |
| 涉及文件        | `src/hancode/providers/factory.py`, `src/hancode/app/task_service.py`, `tests/test_provider_factory.py`, `tests/test_task_service.py`, `tests/test_structure_layers.py` |
| 目标            | 修改 ProviderFactory 接口接收 credential/transport/sleeper；TaskService 解析凭据并装配真实 Provider |
| 完成条件        | mock 继续离线；openai_compatible 能创建真实 Adapter；secret 通过内存注入；显式 provider 注入仍然有效 |

实际验证：
- 全量 pytest：886 passed, 13 skipped（基线 881，新增 5 个测试）
- Ruff：All checks passed!
- MyPy：Success: no issues found in 57 source files

#### S2-6：AgentLoop ProviderError 语义

| 元信息           | 值                                      |
| --------------- | -------------------------------------- |
| 状态            | [x] 已完成                              |
| 依赖            | S2-5                                   |
| 涉及文件        | `src/hancode/runtime/agent_loop.py`, `tests/test_provider_failure_loop.py` |
| 目标            | AgentLoop 捕获 ProviderError，进入 blocked 而非 inconsistent |
| 完成条件        | Provider 失败 → blocked；不进入 inconsistent；不消耗 retry budget；不触发 rollback；可 resume；trace 脱敏 |

实际验证：
- 全量 pytest：895 passed, 13 skipped（基线 886，新增 9 个测试）
- Ruff：All checks passed!
- MyPy：Success: no issues found in 57 source files

#### S2-7：CLI 和 FakeTransport 集成

| 元信息           | 值                                      |
| --------------- | -------------------------------------- |
| 状态            | [x] 已完成                              |
| 依赖            | S2-6                                   |
| 涉及文件        | `src/hancode/interfaces/cli.py`, `tests/providers/test_provider_integration.py` |
| 目标            | 根级 run 预检 Provider；FakeTransport 端到端跑通 Provider → AgentLoop → Tool |
| 完成条件        | hancode run 预检 provider；FakeTransport 能跑通 Provider → AgentLoop；所有输出仍为结构化 JSON |

实际验证：
- 全量 pytest：898 passed, 13 skipped（基线 895，新增 3 个集成测试）
- Ruff：All checks passed!
- MyPy：Success: no issues found in 57 source files

#### S2-8：文档和真实 Smoke

| 元信息           | 值                                      |
| --------------- | -------------------------------------- |
| 状态            | [x] 已完成                              |
| 依赖            | S2-7                                   |
| 涉及文件        | `README.md`, `tests/integration/test_real_provider_smoke.py`, `tests/test_readme.py` |
| 目标            | README 准确区分 Mock 和真实 Provider；真实 smoke 默认跳过 |
| 完成条件        | 文档只描述已实现能力；真实 smoke 默认跳过；不提交真实凭据 |

实际验证：
- 全量 pytest：898 passed, 14 skipped（smoke test 默认跳过）
- Ruff：All checks passed!
- MyPy：Success: no issues found in 57 source files

#### S2.1：审核修复与真实工具链路补强

| 元信息           | 值                                      |
| --------------- | -------------------------------------- |
| 状态            | [x] 已完成                              |
| 依赖            | S2-0~S2-8                              |
| 目标            | 修复端到端工具链路、Prompt 契约、Transport 限制、错误分类和凭据来源装配 |

实现内容：

* FakeTransport 集成测试真实执行 `write_file`，写入 `.hancode/tasks/task-001/SPEC.md`，断言 `tool_calls`、artifact state 和 `tool_called` trace。
* Prompt 发送 `args_schema`，按当前 phase 过滤工具；Action Schema 暴露工具参数；Context 增加 `task_workspace` 和 `artifact_targets`，小预算时确定性省略并记录 truncation。
* HttpxProviderTransport 使用 streaming 和 `Content-Length`/累计字节双重限制；超限在 JSON 解析前失败。
* Transport 只定义并捕获 timeout/network/response-too-large 异常；编程异常不再伪装成网络错误；ProviderError 使用当前 phase。
* `credential_source` 支持定向 keyring/env/dotenv 读取，dotenv 运行时使用 project root 下的 `.env`。

实际验证：

* 全量 pytest：`912 passed, 14 skipped`
* Ruff：`All checks passed!`
* MyPy：`Success: no issues found in 57 source files`
* Package build：`uv build` 成功生成 sdist/wheel

### 阶段验收标准

1. `openai_compatible` 不再返回 `provider_not_implemented`。
2. MockLLM 路径保持完全离线。
3. ProviderAdapter 实现 `LLMClient.next_action(context)`。
4. Context 能转换为稳定的 system/user messages。
5. Action Schema 与现有 ActionParser 契约一致。
6. 模型响应能转换为 Action dict。
7. Provider 不直接执行工具。
8. 401、403 返回结构化认证错误。
9. timeout、429、5xx 按配置重试。
10. Provider 重试不消耗任务 retry budget。
11. Provider 最终失败后任务进入 blocked。
12. Provider 失败后可以 `task resume`。
13. Provider 错误不会触发 rollback。
14. Provider 错误不会把状态标记为 inconsistent。
15. API key 不进入 stdout。
16. API key 不进入 state。
17. API key 不进入 trace。
18. API key 不进入错误 message。
19. 所有核心测试不依赖网络。
20. FakeTransport 能跑通 Provider → AgentLoop → Tool 的完整链路。
21. 真实网络 smoke 默认跳过。
22. `hancode run` 能使用真实 Provider 产生至少一个合法 Action。
23. 现有 Demo、MockLLM 和阶段一任务生命周期测试全部通过。
24. Ruff、MyPy、package build 全部通过。
25. README 准确区分 Mock 模式和真实 Provider 模式。

---

## S3：Human-in-the-Loop——ASK_USER 暂停、回答持久化与跨进程恢复

| 元信息   | 值                                                    |
| ----- | ---------------------------------------------------- |
| 状态    | [x] 已完成（S3-0 至 S3-9 TDD、静态门禁、全量回归与构建通过） |
| 依赖    | S2（真实 OpenAI-Compatible ProviderAdapter）             |
| 主贡献相关 | 是；Human-in-the-Loop 状态机                              |
| Commit | 未提交（按用户要求保留在当前工作区）                    |

### S3.1 阶段定位

阶段二完成后，HanCode 已经能够：

```text
ContextBuilder
→ OpenAI-Compatible Provider
→ Action
→ AgentLoop
→ ToolPolicy
→ ToolRegistry
→ State / Trace
```

但当前真实模型只能：

* 调用工具；
* 完成阶段；
* 返回 Final。

当课程要求不明确、项目存在多种方案、用户偏好缺失时，模型无法暂停并询问用户。

虽然 `ActionType.ASK_USER` 已经存在，ActionParser 也要求其包含非空 `question`，但它目前只是一个未接入运行时的预留 Action。

Provider 当前仍然固定：

```python
interaction_enabled=False
```

因此真实模型看不到 `ask_user` Schema。

AgentLoop 也没有 ASK_USER 分支，最终会把它作为：

```text
unsupported_control_action
```

处理。

S3 的核心目标是：

> 让模型可以发出 ASK_USER，HanCode 将问题持久化并安全退出；用户之后通过 CLI 提交回答，再从相同 phase、相同 task 和相同上下文恢复 AgentLoop。

它不做 TUI，而是先把交互能力落实到 Harness 内核和 Headless CLI，为后续 TUI 提供稳定接口。

### S3.2 S3 进入门禁

在开始 S3 前，应先完成 S2.2 的两个收尾问题：

1. Action JSON Schema 必须将每个 `tool_name` 与对应 `args_schema` 绑定。
2. Transport 必须将非法 UTF-8 响应转换为 `provider_invalid_response`，不能让任务进入 `inconsistent`。

这两项属于 Provider 契约基础。ASK_USER 同样依赖 Action Schema，因此不应在错误 Schema 上继续扩展。

### S3.3 阶段范围

#### 3.1 本阶段实现

| 能力 | 是否实现 |
|---|---:|
| `ask_user` Provider Schema | 是 |
| ASK_USER Prompt 约束 | 是 |
| AgentLoop 暂停 | 是 |
| Pending Interaction 持久化 | 是 |
| `waiting_input` 任务状态 | 是 |
| 用户回答持久化 | 是 |
| 跨 CLI 进程恢复 | 是 |
| 同一 phase 多轮问答 | 是 |
| 用户回答进入下一轮 Context | 是 |
| Task status 展示待回答问题 | 是 |
| CLI `task answer` | 是 |
| 回答幂等性 | 是 |
| 并发回答和 AgentLoop 锁 | 是 |
| Interaction Trace | 是 |
| 回答脱敏和长度限制 | 是 |
| FakeProvider 端到端测试 | 是 |

#### 3.2 本阶段不实现

| 能力 | 原因 |
|---|---|
| TUI | 后续阶段只消费 S3 接口 |
| Streaming | 与 ASK_USER 状态机无直接依赖 |
| 自动终端聊天循环 | S3 保持 Headless CLI |
| `confirm_before_write` | 属于另一类人工审批 |
| 人工批准 Tool Call | 后续单独设计 |
| 多用户协作回答 | 当前 task 只有一个本地用户 |
| WebSocket / Server | 当前是本地 CLI 产品 |
| 远程通知 | 非课程项目 MVP |
| 长期聊天历史 | 只保留当前 phase 的结构化问答 |
| 用户通过回答提供 API key | 凭据必须继续走 `hancode auth` |

当前 PLAN 已将 `confirm_before_write`、复杂 TUI 和 WebUI 列为 post-MVP，因此 S3 不应把这些能力混入 ASK_USER。

### S3.4 用户使用流程

#### 4.1 模型提出问题

用户运行：

```bash
hancode task run task-001 --project-root .
```

模型返回：

```json
{
  "type": "ask_user",
  "phase": "spec",
  "tool_name": null,
  "args": {
    "question": "这个项目要求使用 FastAPI，还是允许自行选择 Web 框架？"
  },
  "reason": "The framework constraint is required before producing SPEC.md."
}
```

HanCode：

1. 不调用工具；
2. 不创建 checkpoint；
3. 不消耗 retry budget；
4. 保持当前 phase；
5. 持久化问题；
6. 将任务状态设置为 `waiting_input`；
7. 退出 AgentLoop。

CLI 输出：

```json
{
  "command": "task run",
  "status": "waiting_input",
  "task": {
    "task_id": "task-001",
    "current_phase": "spec",
    "requires_input": true,
    "resumable": false,
    "pending_interaction": {
      "interaction_id": "ask-000001",
      "phase": "spec",
      "question": "这个项目要求使用 FastAPI，还是允许自行选择 Web 框架？",
      "answer_received": false
    }
  }
}
```

建议退出码：

```text
4 = waiting_input
```

#### 4.2 用户提交回答

```bash
hancode task answer task-001 --project-root .
```

CLI 从终端读取：

```text
Answer: 课程没有限制框架，优先使用 FastAPI。
```

输出不能回显回答全文：

```json
{
  "command": "task answer",
  "status": "completed",
  "interaction": {
    "interaction_id": "ask-000001",
    "answer_received": true
  },
  "task": {
    "task_id": "task-001",
    "status": "waiting_input",
    "resumable": true,
    "requires_input": false
  }
}
```

然后用户执行：

```bash
hancode task resume task-001 --project-root .
```

恢复后的 Provider Context 包含：

```json
{
  "interaction_history": [
    {
      "interaction_id": "ask-000001",
      "phase": "spec",
      "question": "这个项目要求使用 FastAPI，还是允许自行选择 Web 框架？",
      "answer": "课程没有限制框架，优先使用 FastAPI。"
    }
  ]
}
```

### S3.5 为什么需要新的任务状态

当前 `TaskStatus` 只有：

```text
created
running
blocked
failed
completed
inconsistent
```

不能继续复用 `blocked` 表示 ASK_USER，原因是：

```text
blocked
= Provider 失败、Context 缺失、路由阻塞或运行边界错误

waiting_input
= 系统运行正常，只是在等待用户提供信息
```

两者恢复条件不同：

| 状态 | 恢复条件 |
|---|---|
| `blocked` | 修复 Provider、配置或 Workspace |
| `waiting_input` | 提交对应问题的用户回答 |
| `inconsistent` | 状态修复或 rollback |
| `failed` | 通常不可直接恢复 |

因此增加：

```python
class TaskStatus(str, Enum):
    ...
    WAITING_INPUT = "waiting_input"
```

### S3.6 Interaction 数据模型

新增：

```python
class InteractionStatus(str, Enum):
    WAITING = "waiting"
    ANSWERED = "answered"
```

```python
@dataclass(frozen=True, slots=True)
class InteractionRecord:
    interaction_id: str
    phase: Phase
    question: str
    answer: str | None
    status: InteractionStatus
```

TaskState 增加：

```python
@dataclass(frozen=True, slots=True)
class TaskState:
    ...
    interaction_seq: int = 0
    interactions: tuple[InteractionRecord, ...] = ()
    pending_interaction_id: str | None = None
```

#### 6.1 字段语义

##### interaction_seq

单调递增，用于生成：

```text
ask-000001
ask-000002
ask-000003
```

禁止根据列表长度生成，避免清理旧记录后 ID 重复。

##### interactions

只保存当前 phase 内已经发生的结构化问答。

模型每次构造 Context 时都能看到当前阶段已回答的问题，避免下一轮 Provider 调用遗忘用户回答。

##### pending_interaction_id

指向当前需要回答或刚收到回答、等待恢复的 Interaction。

### S3.7 状态不变量

TaskState 必须验证：

1. `interaction_seq` 是非负整数。
2. `interaction_id` 必须满足：

```text
ask-\d{6}
```

3. 所有 Interaction 的 phase 必须等于 `current_phase`。
4. 同一个 task 中 Interaction ID 不得重复。
5. 最多只能有一个 `WAITING` Interaction。
6. `pending_interaction_id` 必须指向现有 Interaction。
7. `WAITING` 状态必须满足：

```text
answer is None
```

8. `ANSWERED` 状态必须满足：

```text
answer 是非空字符串
```

9. `TaskStatus.WAITING_INPUT` 时必须存在 `pending_interaction_id`。
10. 非 `WAITING_INPUT` 状态不得存在未回答 Interaction。
11. 单 phase Interaction 数不得超过配置上限。
12. phase 完成时必须清空该 phase 的 Interaction History。

### S3.8 State Schema 兼容设计

当前 TaskState 没有 Interaction 字段。

为了兼容现有任务，不需要立即将 `schema_version` 从 1 升到 2，可以把三个新字段作为可选字段：

```python
interaction_seq = 0
interactions = ()
pending_interaction_id = None
```

但当前 `_ACCEPTED_STATE_FIELD_SETS` 通过枚举可选字段组合实现。继续增加字段会产生组合爆炸。

应重构为：

```python
required_fields = _STATE_FIELDS - _OPTIONAL_STATE_FIELDS
actual_fields = frozenset(data)

if not (
    required_fields <= actual_fields
    and actual_fields <= _STATE_FIELDS
):
    raise ValueError(...)
```

保存时始终写出新字段，旧 state 第一次保存后自动升级为完整格式。

### S3.9 Interaction 生命周期

#### 9.1 ASK_USER

```text
RUNNING
→ Provider 返回 ASK_USER
→ Parser 校验
→ Policy 校验
→ 创建 InteractionRecord(WAITING)
→ 保存 state
→ Trace interaction_requested
→ WAITING_INPUT
```

状态变化：

```python
new_interaction = InteractionRecord(
    interaction_id=f"ask-{state.interaction_seq + 1:06d}",
    phase=current_phase,
    question=sanitized_question,
    answer=None,
    status=InteractionStatus.WAITING,
)

state = replace(
    state,
    status=TaskStatus.WAITING_INPUT,
    interaction_seq=state.interaction_seq + 1,
    interactions=(*state.interactions, new_interaction),
    pending_interaction_id=new_interaction.interaction_id,
)
```

#### 9.2 用户回答

```text
WAITING_INPUT + WAITING
→ task answer
→ 验证 Interaction ID
→ 回答脱敏
→ 保存 ANSWERED
→ 状态仍为 WAITING_INPUT
→ resumable = true
```

回答后不立即改成 `RUNNING`，因为：

* `task answer` 和 `task resume` 是两个不同操作；
* 回答已经安全持久化；
* 即使进程退出，之后仍可恢复；
* 状态不会谎称 Agent 正在运行。

#### 9.3 恢复

```text
WAITING_INPUT + ANSWERED
→ task resume
→ RUNNING
→ ContextBuilder 注入 interaction_history
→ Provider 继续选择 Action
```

如果没有回答就执行 `task resume`：

```text
interaction_answer_required
```

不得调用 Provider。

#### 9.4 回答何时被消费

不能在第一次 Provider 调用后立刻删除问答记录。

HanCode 的 Provider 每轮都会重新构造 Context，不保存厂商聊天历史。若回答在第一次 Tool Call 后被删除，模型下一轮就会遗忘用户信息。

因此设计为：

* `pending_interaction_id`：在模型成功返回一个合法的非 ASK_USER Action 后清除；
* `interactions`：当前 phase 完成前一直保留；
* phase 完成后统一清空。

这样：

```text
answer
→ read_file
→ list_files
→ write_file
→ finish_phase
```

每一轮都能看到该回答。

### S3.10 多轮问题

同一个 phase 可以多次 ASK_USER：

```text
ask-000001 → answered
ask-000002 → answered
ask-000003 → answered
```

Context：

```json
{
  "interaction_history": [
    {
      "interaction_id": "ask-000001",
      "question": "...",
      "answer": "..."
    },
    {
      "interaction_id": "ask-000002",
      "question": "...",
      "answer": "..."
    }
  ]
}
```

增加配置：

```json
{
  "interaction_mode": "ask_user",
  "max_interactions_per_phase": 8,
  "max_interaction_question_chars": 2048,
  "max_interaction_answer_chars": 8192
}
```

达到上限后：

```text
interaction_limit_exceeded
```

任务进入 `blocked`，防止模型无限追问。

### S3.11 Provider 与 Prompt 修改

#### 11.1 配置

新增：

```python
interaction_mode: Literal[
    "disabled",
    "ask_user",
] = "disabled"
```

默认关闭，保证旧项目行为不变。

用户显式配置：

```json
{
  "interaction_mode": "ask_user"
}
```

#### 11.2 ProviderFactory

```python
OpenAICompatibleProvider(
    ...
    interaction_enabled=(
        config.interaction_mode == "ask_user"
    ),
)
```

#### 11.3 OpenAICompatibleProvider

当前代码固定传入：

```python
interaction_enabled=False
```

修改为实例字段：

```python
self._interaction_enabled = interaction_enabled
```

```python
prompt = self._prompt_builder.build(
    context=context,
    tool_catalog=self._tool_catalog,
    interaction_enabled=self._interaction_enabled,
)
```

#### 11.4 ASK_USER Schema

现有 Action Schema Builder 已经具有 `_ask_user_branch()`，只是没有对真实 Provider 开放。

S3 开启后输出：

```json
{
  "type": "object",
  "required": [
    "type",
    "phase",
    "reason",
    "tool_name",
    "args"
  ],
  "properties": {
    "type": {
      "const": "ask_user"
    },
    "phase": {
      "const": "spec"
    },
    "reason": {
      "type": "string",
      "minLength": 1
    },
    "tool_name": {
      "type": "null"
    },
    "args": {
      "type": "object",
      "required": [
        "question"
      ],
      "properties": {
        "question": {
          "type": "string",
          "minLength": 1,
          "maxLength": 2048
        }
      },
      "additionalProperties": false
    }
  },
  "additionalProperties": false
}
```

#### 11.5 Prompt 约束

System Prompt 增加：

```text
Use ask_user only when information is genuinely required
and cannot be inferred from the provided context.

Ask one precise question at a time.

Do not ask for API keys, passwords, tokens, credentials,
private keys, or other secrets.

Do not use ask_user merely to ask for permission to continue.

Do not ask questions whose answers are already available
in SPEC.md, PLAN.md, course context, project files, or prior
interaction history.
```

避免模型：

```text
"我可以继续吗？"
"需要我读取文件吗？"
"请提供 API key。"
```

### S3.12 Interaction Policy

当前 ToolPolicy 对 `ASK_USER` 和 `FINAL` 直接允许。

S3 应拆开：

```python
if action.type is ActionType.ASK_USER:
    return self._evaluate_ask_user(
        action,
        phase,
        state,
    )

if action.type is ActionType.FINAL:
    return _allowed(phase)
```

ASK_USER Policy 检查：

1. `interaction_mode == "ask_user"`。
2. question 非空。
3. question 长度不超限。
4. 当前不存在未处理 pending Interaction。
5. 当前 phase 问答次数未超限。
6. question 不包含明显的凭据请求。
7. TaskState 一致。
8. ASK_USER 不需要 checkpoint。
9. ASK_USER 不消耗 retry budget。
10. ASK_USER 不触发 rollback。

错误：

```text
interaction_disabled
interaction_question_required
interaction_question_too_long
interaction_already_pending
interaction_limit_exceeded
interaction_secret_request_denied
```

### S3.13 AgentLoop 修改

新增 ASK_USER 分支，位置应在 Tool Call 和 Finish Phase 之间：

```python
if action.type is ActionType.ASK_USER:
    state, interaction = self._request_user_input(
        task_id,
        state,
        action,
        routing.phase,
    )

    trace_error = self._append_trace(
        task_id,
        trace_events,
        event_type="interaction_requested",
        phase=routing.phase,
        status="waiting",
        observation={
            "interaction_id": interaction.interaction_id,
            "question_length": len(
                interaction.question
            ),
        },
    )

    if trace_error is not None:
        ...

    return _result(
        TaskStatus.WAITING_INPUT,
        step,
        tuple(tool_calls),
        {
            "interaction_id":
                interaction.interaction_id,
            "question":
                interaction.question,
        },
        None,
        state,
    )
```

禁止把完整用户回答写入 Trace。

### S3.14 Router 修改

当前 Router 只显式阻止：

```text
BLOCKED
FAILED
INCONSISTENT
```

增加：

```python
if state.status is TaskStatus.WAITING_INPUT:
    return RoutingDecision(
        state.current_phase,
        "interaction_answer_required",
        blocked=True,
    )
```

但 `resume=True` 且 pending Interaction 已回答时，AgentLoop 应在调用 Router 前把状态转换为：

```text
WAITING_INPUT
→ RUNNING
```

### S3.15 ContextBuilder 修改

ContextBuilder 接收 TaskState，因此可以直接加入：

```python
if state.interactions:
    context["interaction_history"] = [
        {
            "interaction_id":
                record.interaction_id,
            "phase":
                record.phase.value,
            "question":
                record.question,
            "answer":
                record.answer,
        }
        for record in state.interactions
        if record.status
            is InteractionStatus.ANSWERED
    ]
```

未回答的问题不能送回 Provider，因为 AgentLoop 在等待用户期间根本不应再次调用模型。

#### 15.1 Context Budget

Interaction History 比：

```text
project_memory
experience
project_structure
```

更重要。

上下文裁剪顺序建议：

```text
project_memory
→ experience
→ source_snippets
→ 非当前阶段 artifact targets
→ interaction_history 中最旧记录
→ required artifacts
```

当前代码在预算不足时会先删除 `artifact_targets` 和 `task_workspace`，这不适合作为 S3 最终顺序。

建议至少保留：

```json
{
  "current_artifact_target":
    ".hancode/tasks/task-001/SPEC.md"
}
```

以及最新 Interaction。

### S3.16 Application Service 设计

新增：

```python
class InteractionService:
    def get_pending(
        self,
        project_root: Path,
        task_id: str,
    ) -> InteractionRecord | None:
        ...

    def answer(
        self,
        project_root: Path,
        task_id: str,
        answer: str,
        *,
        interaction_id: str | None = None,
    ) -> TaskSummary:
        ...
```

#### 16.1 answer 行为

```text
load state
→ reconcile
→ 获取 pending Interaction
→ 校验可回答
→ 校验 interaction_id
→ 脱敏
→ 长度限制
→ 幂等检查
→ 保存 ANSWERED
→ 返回 TaskSummary
```

### S3.17 回答幂等性

重复执行：

```bash
hancode task answer task-001
```

可能发生在：

* CLI 输出丢失；
* 用户不确定第一次是否成功；
* 脚本自动重试；
* 进程在保存后崩溃。

规则：

| 情况 | 结果 |
|---|---|
| 同一个 Interaction、同一个回答 | 幂等成功 |
| 同一个 Interaction、不同回答 | `interaction_answer_conflict` |
| Interaction 已被消费 | `interaction_not_pending` |
| ID 不匹配 | `interaction_id_mismatch` |
| 没有 pending Interaction | `interaction_not_pending` |

不能静默覆盖旧回答，否则恢复上下文不可审计。

### S3.18 并发与锁

当前任务级 mutation lock 实现在 AgentLoop 内部，并只包围 `run()`。

但 `task answer` 同样会修改 state.json。

如果不使用同一把锁，可能发生：

```text
AgentLoop 正在保存 WAITING_INPUT
同时 task answer 修改 state
→ 后写入者覆盖前写入者
```

因此 S3 应将锁抽取到：

```text
src/hancode/storage/task_lock.py
```

提供：

```python
class TaskMutationGuard(Protocol):
    def acquire(
        self,
        task_id: str,
        phase: Phase,
    ) -> AbstractContextManager[None]:
        ...
```

由以下组件共同使用：

```text
AgentLoop
InteractionService.answer
未来 confirm_before_write
未来 TUI session
```

锁冲突返回：

```text
mutation_lock_busy
```

用户稍后重试，不得覆盖 state。

### S3.19 CLI 设计

新增：

```bash
hancode task answer TASK_ID
```

参数：

```text
TASK_ID
--project-root PATH
--interaction-id ID
--answer-file PATH
```

默认行为：

* 未提供 `--answer-file` 时，从 stdin 读取；
* 不允许通过 `--answer "..."` 直接传入，避免回答进入 shell history；
* 支持多行 answer file；
* 不输出回答全文。

示例：

```bash
hancode task answer task-001
```

或：

```bash
hancode task answer \
  task-001 \
  --interaction-id ask-000001 \
  --answer-file answer.txt
```

Task CLI 当前只有 create、run、resume、status、list，因此 S3 只需在现有 `task_app` 下增加 answer。

### S3.20 TaskSummary 修改

当前 `resumable` 只考虑：

* blocked 且一致；
* inconsistent 且可以 rollback。

增加：

```python
pending = state.pending_interaction

requires_input = (
    state.status is TaskStatus.WAITING_INPUT
    and pending is not None
    and pending.status
        is InteractionStatus.WAITING
)

resumable = existing_resumable or (
    state.status is TaskStatus.WAITING_INPUT
    and pending is not None
    and pending.status
        is InteractionStatus.ANSWERED
)
```

TaskSummary 增加：

```python
requires_input: bool
pending_interaction: InteractionSummary | None
```

InteractionSummary 不包含 answer：

```python
{
    "interaction_id": "...",
    "phase": "spec",
    "question": "...",
    "answer_received": true
}
```

### S3.21 Exit Code

建议扩展：

| Exit Code | 含义 |
|---:|---|
| 0 | completed |
| 1 | blocked / failed |
| 2 | CLI、配置或输入错误 |
| 3 | inconsistent |
| 4 | waiting_input |

`waiting_input` 不是失败，也不是完成，需要独立代码方便外部脚本和未来 TUI 判断。

### S3.22 Trace 设计

新增事件：

```text
interaction_requested
interaction_answered
interaction_resumed
interaction_pending_cleared
interaction_history_cleared
```

#### 22.1 interaction_requested

允许记录：

```json
{
  "interaction_id": "ask-000001",
  "question_length": 36
}
```

可以记录脱敏后的问题摘要，但不建议记录完整问题。

#### 22.2 interaction_answered

只记录：

```json
{
  "interaction_id": "ask-000001",
  "answer_length": 22,
  "redacted": false
}
```

禁止记录 answer。

#### 22.3 interaction_resumed

```json
{
  "interaction_id": "ask-000001"
}
```

### S3.23 安全边界

用户回答进入 State 和 Provider Context 前必须：

1. 去除首尾空白；
2. 校验非空；
3. 校验 UTF-8 长度；
4. 调用 `redact_text()`；
5. 禁止把回答写入 Trace；
6. 禁止把回答写入普通 CLI 输出；
7. 禁止把回答加入错误 message；
8. 禁止用 ASK_USER 获取凭据。

如果用户输入只有：

```text
sk-xxxxxxxx
```

脱敏后只剩 `[REDACTED]`，应返回：

```text
interaction_answer_contains_only_sensitive_content
```

提示：

```text
Do not provide credentials through ASK_USER.
Use hancode auth login instead.
```

### S3.24 文件变更设计

#### 24.1 新增文件

| 文件 | 职责 |
|---|---|
| `src/hancode/core/interactions.py` | Interaction 模型和校验 |
| `src/hancode/app/interaction_service.py` | 查询和提交回答 |
| `src/hancode/storage/task_lock.py` | 共享 task mutation lock |
| `tests/test_interactions.py` | Interaction 模型测试 |
| `tests/test_interaction_service.py` | Answer 服务测试 |
| `tests/test_interaction_loop.py` | AgentLoop 暂停恢复测试 |
| `tests/providers/test_interaction_integration.py` | Provider 端到端问答测试 |

#### 24.2 修改文件

| 文件 | 修改 |
|---|---|
| `src/hancode/core/models.py` | 增加 WAITING_INPUT |
| `src/hancode/core/state.py` | Interaction 状态持久化 |
| `src/hancode/core/router.py` | waiting_input 路由 |
| `src/hancode/core/actions.py` | ASK_USER 长度与安全契约 |
| `src/hancode/core/config.py` | interaction 配置 |
| `src/hancode/policy/tool_policy.py` | ASK_USER Policy |
| `src/hancode/runtime/context.py` | interaction_history |
| `src/hancode/runtime/agent_loop.py` | ASK_USER 暂停和 resume |
| `src/hancode/providers/factory.py` | interaction_enabled 装配 |
| `src/hancode/providers/openai_compatible.py` | 不再固定关闭交互 |
| `src/hancode/providers/prompt_builder.py` | ASK_USER Prompt |
| `src/hancode/app/task_models.py` | pending interaction 展示 |
| `src/hancode/interfaces/cli.py` | task answer 和 exit code 4 |
| `README.md` | 人机交互使用说明 |
| `docs/PLAN.md` | S3 任务卡 |
| `docs/AGENT_LOG.md` | 实现证据 |

### S3.25 TDD 实现顺序

#### S3-0：S2.2 收尾

完成：

```text
tool_name 与 args schema 绑定
非法 UTF-8 → provider_invalid_response
```

#### S3-1：Interaction 领域模型

涉及：

```text
core/interactions.py
core/models.py
```

测试：

```text
test_interaction_waiting_requires_no_answer
test_interaction_answered_requires_answer
test_interaction_id_format
test_waiting_input_status_exists
```

#### S3-2：TaskState 持久化

涉及：

```text
core/state.py
```

测试：

```text
test_old_state_loads_with_empty_interactions
test_state_roundtrips_interactions
test_state_rejects_dangling_pending_id
test_state_rejects_multiple_waiting_questions
test_state_rejects_cross_phase_interaction
```

#### S3-3：Config、Prompt 和 Schema

涉及：

```text
core/config.py
providers/prompt_builder.py
providers/factory.py
providers/openai_compatible.py
```

测试：

```text
test_interaction_disabled_by_default
test_prompt_exposes_ask_user_when_enabled
test_prompt_excludes_ask_user_when_disabled
test_prompt_forbids_secret_requests
```

#### S3-4：ASK_USER Policy

涉及：

```text
policy/tool_policy.py
```

测试：

```text
test_ask_user_allowed_when_enabled
test_ask_user_denied_when_disabled
test_ask_user_requires_question
test_ask_user_does_not_require_checkpoint
test_ask_user_does_not_consume_retry_budget
test_ask_user_limit
```

#### S3-5：AgentLoop 暂停

涉及：

```text
runtime/agent_loop.py
core/router.py
```

测试：

```text
test_ask_user_sets_waiting_input
test_ask_user_keeps_phase
test_ask_user_persists_question
test_ask_user_does_not_dispatch_tool
test_ask_user_does_not_checkpoint
test_ask_user_does_not_rollback
test_ask_user_appends_safe_trace
```

#### S3-6：InteractionService 与锁

涉及：

```text
app/interaction_service.py
storage/task_lock.py
```

测试：

```text
test_answer_updates_pending_interaction
test_same_answer_is_idempotent
test_different_answer_conflicts
test_answer_requires_pending_question
test_answer_uses_task_lock
test_answer_does_not_echo_secret
```

#### S3-7：Context 和 Resume

涉及：

```text
runtime/context.py
runtime/agent_loop.py
app/task_service.py
```

测试：

```text
test_resume_requires_answer
test_resume_with_answer_sets_running
test_answer_enters_provider_context
test_interaction_history_survives_multiple_steps
test_interaction_history_clears_after_phase
test_provider_failure_keeps_answer
```

#### S3-8：CLI

涉及：

```text
interfaces/cli.py
app/task_models.py
```

测试：

```text
test_cli_run_returns_waiting_input
test_cli_waiting_input_exit_code_is_4
test_cli_status_shows_question
test_cli_answer_reads_stdin
test_cli_answer_reads_file
test_cli_answer_does_not_echo_answer
test_cli_resume_after_answer
```

#### S3-9：端到端交互测试

FakeTransport 序列：

```text
1. ask_user
2. write_file SPEC.md
3. finish_phase spec
4. HTTP 400 结束测试脚本
```

验证第二次 Provider 请求包含用户回答：

```text
ASK_USER
→ WAITING_INPUT
→ task answer
→ task resume
→ Context 包含 answer
→ write_file
→ SPEC.md 存在
→ state.artifacts["SPEC.md"] == true
```

### S3.26 核心端到端测试示例

```python
def test_provider_ask_user_answer_resume(
    tmp_path: Path,
) -> None:
    service.create(
        tmp_path,
        "Generate SPEC.md",
    )

    first_provider = provider_with_actions([
        ask_user(
            phase="spec",
            question="Which framework should be used?",
        ),
    ])

    first = service.run(
        tmp_path,
        "task-001",
        provider=first_provider,
    )

    assert first.status is TaskStatus.WAITING_INPUT
    assert first.final_state.current_phase is Phase.SPEC

    interaction_service.answer(
        tmp_path,
        "task-001",
        "Use FastAPI.",
    )

    second_transport = InspectingFakeTransport([
        write_spec_action(),
        finish_spec_action(),
        stop_response(),
    ])

    second = service.resume(
        tmp_path,
        "task-001",
        provider=provider(second_transport),
    )

    assert second.tool_calls == ("write_file",)
    assert "Use FastAPI." in (
        second_transport.requests[0]
        .json_body["messages"][1]["content"]
    )

    assert (
        tmp_path
        / ".hancode"
        / "tasks"
        / "task-001"
        / "SPEC.md"
    ).is_file()
```

### S3.27 S3 验收标准

S3 只有同时满足以下条件才能标记完成：

1. `ask_user` 在 interaction enabled 时进入 Provider Schema。
2. interaction disabled 时 ASK_USER 不对模型开放。
3. ASK_USER 能通过 ActionParser。
4. ASK_USER 不调用 ToolRegistry。
5. ASK_USER 不创建 checkpoint。
6. ASK_USER 不消耗 retry budget。
7. ASK_USER 不触发 rollback。
8. ASK_USER 保持当前 phase。
9. ASK_USER 将任务设为 `waiting_input`。
10. Pending question 持久化到 state。
11. 进程结束后 `task status` 仍能展示问题。
12. `task answer` 能提交回答。
13. 回答不会出现在 CLI 输出。
14. 回答不会出现在 Trace。
15. 回答不会出现在错误 message。
16. 同一回答重复提交是幂等的。
17. 不同回答覆盖已提交回答会被拒绝。
18. 未回答时不能 resume。
19. 已回答时可以 resume。
20. 恢复后 Provider Context 包含回答。
21. 回答在当前 phase 的后续多轮中保持可见。
22. phase 完成后 Interaction History 被清理。
23. Provider 失败不会丢失已提交回答。
24. 回答和 AgentLoop 使用同一 task lock。
25. waiting_input 有独立 CLI exit code。
26. TaskSummary 正确区分 requires_input 和 resumable。
27. FakeTransport 能跑通 ask → answer → resume → tool。
28. 旧 state.json 能正常加载。
29. MockLLM 路径保持确定性离线。
30. pytest、Ruff、MyPy、package build 全部通过。

### S3.28 最终架构

S3 完成后的链路：

```text
User
 │
 ▼
hancode task run
 │
 ▼
AgentLoop
 │
 ▼
ProviderAdapter
 │
 ▼
ASK_USER
 │
 ▼
Interaction State
 │
 ├─ status = waiting_input
 ├─ question persisted
 └─ AgentLoop exits
        │
        ▼
hancode task answer
        │
        ├─ sanitize
        ├─ lock
        └─ persist answer
               │
               ▼
hancode task resume
               │
               ▼
ContextBuilder
               │
               ├─ phase context
               ├─ artifacts
               └─ interaction_history
                      │
                      ▼
               ProviderAdapter
                      │
                      ▼
                 next Action
```

S3 的核心不是增加一个 CLI 提示，而是建立：

> **模型提问、任务暂停、问题持久化、回答持久化、跨进程恢复、上下文重放和并发保护的完整 Human-in-the-Loop 状态机。**

完成 S3 后，HanCode 才真正具备后续 TUI 所需的交互内核；TUI 只需要展示 `pending_interaction`、读取回答并调用 `InteractionService`，不需要重新实现 Agent 状态逻辑。

`TaskState` 不变量、共享 task lock 和端到端恢复测试是 S3 最关键的三部分，应按 `S3-0 → S3-9` 顺序逐项 TDD 推进。

### S3.29 实施记录

- S3-0：完成 `tool_name` 与工具参数 Schema 绑定，并将非法 UTF-8 响应映射为 `provider_invalid_response`。
- S3-1/S3-2：新增 `InteractionRecord`、`WAITING_INPUT`、state 交互字段、旧 state 兼容加载和状态不变量校验。
- S3-3/S3-4：新增默认关闭的交互配置、Provider/Prompt 装配、问题长度限制、秘密请求拒绝和 phase 交互次数限制。
- S3-5/S3-7：AgentLoop 可安全暂停、持久化问题、等待回答、恢复已回答交互，并把已回答历史加入 Provider Context。
- S3-6：新增 `InteractionService` 和共享 task mutation lock，支持回答幂等、冲突拒绝、长度限制和脱敏。
- S3-8：新增 `task answer`、pending 问题状态展示和 waiting_input 独立退出码 4；回答不进入普通 CLI 输出或 trace 内容。
- S3-9：FakeTransport 完成 `ask_user → answer → resume → write_file → finish_phase → provider failure` 链路测试。
- 新鲜验证：`968 passed, 14 skipped`；Ruff、MyPy 和 `uv build` 全部通过。
- 剩余风险：TUI/REPL/WebUI 仍是后续范围；Windows symlink/junction 相关测试在无权限环境可能继续 skip；当前工作区未提交。

---

# 8. 需求→任务追溯

| SPEC 锚点                                  | 对应任务                         | 状态  |
| ---------------------------------------- | ---------------------------- | --- |
| FR-1 AgentLoop 主循环                       | T10, T21                     | [x] |
| FR-2 LLM 抽象与 MockLLM                     | T9, T23                      | [x] |
| FR-3 Action 解析与校验                        | T7, T8                       | [x] |
| FR-4 ToolRegistry 与工具分发                  | T11, T12                     | [x] |
| FR-5 ToolPolicy 治理护栏                     | T13, T14, T15                | [x] |
| FR-6 ContextBuilder 与记忆选择                | T19                          | [x] |
| FR-7 反馈回灌机制                              | T20, T21                     | [x] |
| FR-8 TraceLogger                         | T16                          | [x] |
| FR-9 配置加载与运行约束                           | T3, T26                      | [x] |
| FR-10 Project Workspace 与 Task Workspace | T2                           | [x] |
| FR-11 课程项目 Phase Gate                    | T5, T6                       | [x] |
| FR-12 课程项目上下文构造                          | T19                          | [x] |
| FR-13 课程文件保护策略                           | T13, T14, T15                | [x] |
| FR-14 Checkpoint 与 Rollback              | T17, T18, T21                | [x] |
| FR-15 测试报告与审查记录                          | T20, T22                     | [x] |
| FR-16 Knowledge Delivery                 | T22, T23                     | [x] |
| 凭据与分发设计                                  | T25, T26, T27                | [ ] |
| 可测试性约定                                   | T1-T30                       | [ ] |
| 测试失败分类                                   | T20                          | [ ] |
| 危险动作与治理护栏                                | T13, T14, T15                | [ ] |
| 记忆与上下文机制                                 | T2, T19                      | [ ] |
| 主贡献维度                                    | T16, T17, T18, T20, T21, T23 | [ ] |
| MockLLM 机制演示                             | T9, T21, T23                 | [ ] |
| P0 分层结构与装配抽取                         | T28                         | [x] |
| P1 应用服务层拆分                             | T29                         | [x] |
| P2 Demo 与 Delivery 支持包拆分                 | T30                         | [x] |

### 里程碑分支与 PR 一览

所有里程碑均使用统一分支开发、单次 PR 合并：

| 里程碑 | 分支            | 覆盖任务       | PR |
| ---- | ------------- | ----------- | -- |
| M1   | `feature/M1` | T1-T7       | 单 PR |
| M2   | `feature/M2` | T8-T10      | 单 PR |
| M3   | `feature/M3` | T11-T15     | 单 PR |
| M4   | `feature/M4` | T16-T18     | 单 PR |
| M5   | `feature/M5` | T19-T21     | 单 PR |
| M6   | `feature/M6` | T22-T23     | 单 PR |
| M7   | `feature/M7` | T24-T27     | 单 PR |

#### M1 覆盖详情

| 子任务 | 模块                | 文件                            |
| ---- | ----------------- | ----------------------------- |
| T1   | 共享模型与错误类型        | `models.py`, `errors.py`      |
| T2   | Workspace 初始化    | `workspace.py`                |
| T3   | ConfigLoader      | `config.py`                   |
| T4   | StateStore        | `state.py`                    |
| T5   | Phase 枚举与 PhaseGate | `phases.py`                   |
| T6   | WorkspaceRouter   | `router.py`                   |
| T7   | Action Schema     | `actions.py`                  |

#### M2 覆盖详情

| 子任务 | 模块            | 文件                   |
| ---- | ------------- | -------------------- |
| T8   | ActionParser  | `actions.py`         |
| T9   | MockLLM       | `llm.py`             |
| T10  | AgentLoop 最小骨架 | `agent_loop.py`      |

#### M3 覆盖详情

| 子任务 | 模块                  | 文件                            |
| ---- | ------------------- | ----------------------------- |
| T11  | ToolResult 与 ToolRegistry | `tools.py`                    |
| T12  | FileTools 最小读写       | `file_tools.py`               |
| T13  | PathClassifier      | `path_policy.py`              |
| T14  | ToolPolicy 基础规则     | `tool_policy.py`              |
| T15  | Course File Protection | `tool_policy.py`, `path_policy.py` |

#### M4 覆盖详情

| 子任务 | 模块                | 文件                |
| ---- | ----------------- | ----------------- |
| T16  | TraceLogger       | `trace.py`        |
| T17  | CheckpointManager | `checkpoints.py`  |
| T18  | RollbackManager   | `checkpoints.py`  |

#### M5 覆盖详情

| 子任务 | 模块                        | 文件              |
| ---- | ------------------------- | --------------- |
| T19  | ContextBuilder            | `context.py`    |
| T20  | FeedbackBuilder 失败分类      | `feedback.py`   |
| T21  | AgentLoop 集成 feedback/retry/rollback | `agent_loop.py` |

#### M6 覆盖详情

| 子任务 | 模块                    | 文件              |
| ---- | --------------------- | --------------- |
| T22  | Delivery Artifacts 生成 | `delivery.py`   |
| T23  | MockLLM 机制 Demo      | `scripts/demo_mock_loop.py` |

#### M7 覆盖详情

| 子任务 | 模块                      | 文件                     |
| ---- | ----------------------- | ---------------------- |
| T24  | CLI 最小入口               | `cli.py`               |
| T25  | CredentialProvider      | `credentials.py`       |
| T26  | Package Build 与 CI     | `pyproject.toml`, CI 配置 |
| T27  | README 运行与分发文档        | `README.md`            |

---

# 9. 冷启动验证结果

冷启动验证已在实现前完成并记录到 `docs/SPEC_PROCESS.md`。

## 9.1 已执行验证

1. 第二个 agent：OpenCode + GLM-5.2。
2. 验证目录：`D:\agent-leanring\demo`。
3. 提供上下文：

   * `SPEC.md`
   * `PLAN.md`
   * `系统架构.md`
4. 未提供：

   * 之前聊天记录。
   * 隐藏上下文。
   * 口头解释。
   * 主 agent 的记忆。
5. 尝试任务：

   * T1 共享模型与错误类型。
   * T2 Workspace 初始化。
6. 复核结果：

   * pytest：19 passed。
   * ruff：passed。
   * mypy：passed。
   * secret 模式扫描：无命中。

说明：本次额外提供了 `系统架构.md`，因此属于扩展上下文冷启动验证；它证明 T1 / T2 可由陌生 agent 启动并产出可运行代码，但不能抹去正式实现时的 TDD / 日志 / 评审要求。

## 9.2 已回写的发现

冷启动复核发现以下问题，并已回写到 T1 / T2 任务卡：

* `OperationResult.status` 不得使用任意字符串。
* Workspace 初始化必须幂等，不得覆盖已有 state、trace、history、checkpoint 或阶段产物。
* Task Workspace 初始化必须依赖有效 Project Workspace。
* Python 版本目标必须与项目约定保持一致。
* 冷启动 demo 的 TDD 红阶段和过程日志不足，不能作为正式任务完成证据。

## 9.3 正式实现入口

正式开发从 T1 开始。每个任务必须满足：

* 先写失败测试并记录红阶段输出。
* 只实现当前任务卡范围内的代码。
* 运行任务卡列出的 pytest / ruff / mypy 验证。
* 更新本文件对应任务状态、验证结果和 commit hash。
* 在 `docs/AGENT_LOG.md` 记录 agent、上下文、红绿重构证据、人工干预和经验教训。
* 进入下一任务前完成代码审查。

---

# 10. 执行与提交规则

每个实现任务完成时，必须更新本文件对应任务卡：

```text
状态：从 [ ] 改为 [x]
Commit：填写实际 commit hash
验证：填写实际运行过的命令和结果
备注：记录未完成风险或后续任务
```

每个任务的提交说明建议格式：

```text
T<编号>: <任务名称>

- Added failing tests for ...
- Implemented ...
- Verified with ...
```

每个任务完成后必须在 `docs/AGENT_LOG.md` 记录：

* 时间戳。
* 任务 ID。
* 使用的 agent / subagent。
* 使用的工作流或 skill。
* 关键提示词 / 上下文。
* 测试红阶段证据。
* 绿阶段实现摘要。
* 验证命令。
* 提交 hash。
* 人工干预。
* 经验教训。

---

# 11. 总体验证命令

MVP 完成后，至少运行：

```powershell
uv run pytest
uv run ruff check src tests scripts
uv run mypy src
uv build
uv run hancode --help
uv run hancode demo --provider mock
```

若存在 Makefile：

```powershell
make check
```

若 CI 已配置：

```text
推送后检查 GitHub Actions / GitLab CI unit-test job 是否通过。
```

---

# 12. 当前风险与控制措施

| 风险                               | 影响                    | 控制措施                                 |
| -------------------------------- | --------------------- | ------------------------------------ |
| 任务粒度再次膨胀                         | 子 agent 一次修改太多模块，难以审查 | 保持每个任务只做一个机制                         |
| AgentLoop 过早变复杂                  | 主循环难以测试和定位问题          | 先做 T10 最小 loop，再由 T21 集成反馈和 rollback |
| ToolPolicy 与 PathClassifier 边界混乱 | 安全策略重复或遗漏             | T13 只分类路径，T14/T15 才做策略判定             |
| Checkpoint 与 Rollback 混在一起       | 恢复机制难测试               | T17 创建 checkpoint，T18 单独 rollback    |
| Delivery 与 Demo 混在一起             | 交付产物结构不稳定             | T22 先做产物生成，T23 再集成 demo              |
| CLI / 凭据 / CI 变成大杂烩              | 最终交付任务失控              | T24、T25、T26、T27 分开                   |
| 使用真实 LLM 证明机制                    | 不满足 Harness 可测试性      | 全部核心测试使用 MockLLM / stub              |
| 凭据泄露                             | 安全事故和评分风险             | T25 专门验证不打印 secret                   |
| 文档承诺超过实现                         | 交付不一致                 | README 只写已实现能力和明确限制                  |

---

# 13. 实现顺序建议

推荐按以下顺序执行（每个里程碑在对应 `feature/Mx` 分支开发，单 PR 合并）：

```text
T0
M1: T1 -> T2 -> T3 -> T4 -> T5 -> T6 -> T7  (feature/M1, 单 PR)
M2: T8 -> T9 -> T10                          (feature/M2, 单 PR)
M3: T11 -> T12 -> T13 -> T14 -> T15          (feature/M3, 单 PR)
M4: T16 -> T17 -> T18                        (feature/M4, 单 PR)
M5: T19 -> T20 -> T21                        (feature/M5, 单 PR)
M6: T22 -> T23                               (feature/M6, 单 PR)
M7: T24 -> T25 -> T26 -> T27                 (feature/M7, 单 PR)
```

最小可运行骨架优先顺序（M1 统一在 `feature/M1` 分支完成）：

```text
T1 models/errors
T2 workspace
T3 config
T4 state
T5 phase gate
T6 router
T7 action schema
```

主贡献闭环优先顺序：

```text
T16 trace
T17 checkpoint
T18 rollback
T20 feedback
T21 feedback loop integration
T23 mock demo
```

最终交付优先顺序：

```text
T22 delivery artifacts
T24 CLI
T25 credentials
T26 package / CI
T27 README
```

---

# 14. 完成定义

HanCode MVP 完成必须同时满足：

* 所有 T1-T27 状态为 [x]。
* 所有任务都有 commit hash 和验证记录。
* `uv run pytest` 通过。
* `uv run ruff check src tests scripts` 通过。
* `uv run mypy src` 通过。
* `uv build` 通过。
* `uv run hancode --help` 可运行。
* `uv run hancode demo --provider mock` 可运行。
* MockLLM demo trace 能证明：

  * policy denial。
  * feedback generated。
  * checkpoint created。
  * retry budget consumed。
  * rollback completed。
  * delivery artifacts generated。
* README 说明安装、运行、凭据设置、MockLLM demo 和已知限制。
* AGENT_LOG 记录主要 agentic development 过程。
* SPEC_PROCESS 记录冷启动验证和修订。
* 仓库中不包含真实凭据。
