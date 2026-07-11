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
* blocked 后的 resume 断点续跑语义。
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
| 状态            | [ ] 未开始               |
| 依赖            | T7                    |
| 可并行           | 可与 T9 并行              |
| Worktree / PR | `feature/M2`          |
| 主贡献相关         | 是，主循环输入校验             |
| Commit        | TODO                  |

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
def parse_action(raw: dict[str, object]) -> Action | ParseError: ...
```

输入：LLM / MockLLM 原始输出。
输出：Action 或 ParseError。
不变量：parser 只做格式和 schema 校验，不做安全策略判断。
错误处理：解析失败返回 ParseError，至少包含 `error_code`、`message`、`phase`、`denied_rule`、`suggested_fix`；其中 parse error 的 `denied_rule` 为 `null`。

### 预期失败测试

* `test_parse_valid_read_file_action`
* `test_parse_valid_edit_file_action`
* `test_parse_valid_run_tests_action`
* `test_parse_rejects_malformed_payload`
* `test_parse_rejects_unknown_tool`
* `test_parse_error_becomes_structured_error`

### 实现要点

* parser 支持 dict 输入，不依赖真实 LLM 字符串格式。
* 后续真实 LLM provider 可在 adapter 中把文本转成 dict。
* ParseError 应可被 FeedbackBuilder 转成 observation。

### 验证步骤

```powershell
uv run pytest tests/test_action_parser.py -v
uv run ruff check src/hancode/actions.py tests/test_action_parser.py
uv run mypy src/hancode/actions.py
```

### 完成判定

* 合法 action 可解析。
* 非法 action 不会进入 tool。
* 错误信息可诊断。

### 非目标 / 边界

* 不执行 action。
* 不判断 policy。
* 不调用 LLM。

---

## T9：MockLLM

| 元信息           | 值                |
| ------------- | ---------------- |
| 状态            | [ ] 未开始          |
| 依赖            | T7               |
| 可并行           | 可与 T8 并行         |
| Worktree / PR | `feature/M2`     |
| 主贡献相关         | 是，确定性测试基础        |
| Commit        | TODO             |

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
from typing import Protocol, Any

class LLMClient(Protocol):
    def next_action(self, context: dict[str, Any]) -> dict[str, Any]: ...

class MockLLM:
    def __init__(self, actions: list[dict[str, Any]]) -> None: ...
    def next_action(self, context: dict[str, Any]) -> dict[str, Any]: ...
```

输入：结构化 context。
输出：预设 action。
不变量：MockLLM 不调用网络，不读取真实凭据。
错误处理：action 序列耗尽时返回 blocked signal 或抛出可诊断 MockLLMExhausted。

### 预期失败测试

* `test_mock_llm_returns_actions_in_order`
* `test_mock_llm_records_contexts`
* `test_mock_llm_exhaustion_returns_blocked_signal`
* `test_mock_llm_is_deterministic`

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

### 非目标 / 边界

* 不实现真实 ProviderAdapter。
* 不实现 prompt 模板优化。
* 不读取 credential。

---

## T10：AgentLoop 最小循环骨架

| 元信息           | 值                                                |
| ------------- | ------------------------------------------------ |
| 状态            | [ ] 未开始                                          |
| 依赖            | T6, T8, T9                                       |
| 可并行           | 依赖注入 stub policy / stub tool，可先于真实 ToolPolicy 集成 |
| Worktree / PR | `feature/M2`                                    |
| 主贡献相关         | 是，主循环基础                                          |
| Commit        | TODO                                             |

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
错误处理：parse error、policy denial、MockLLM 耗尽、超过 max_steps 均返回 blocked 或 failed，不执行高风险工具。

### 预期失败测试

* `test_agent_loop_calls_llm_with_context`
* `test_agent_loop_parses_action_before_policy`
* `test_agent_loop_calls_policy_before_tool`
* `test_policy_denial_does_not_execute_tool`
* `test_max_steps_prevents_infinite_loop`
* `test_finish_action_stops_loop`

### 实现要点

* 第一版 AgentLoop 使用依赖注入的 stub policy、stub tool registry、stub feedback builder。
* `finish` action 只停止循环，不直接判定 completed。
* 工具调用顺序应可通过 spy 对象测试。

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
| 状态            | [ ] 未开始               |
| 依赖            | T1, T7                |
| 可并行           | 可与 T8/T9 并行           |
| Worktree / PR | `feature/M3`          |
| 主贡献相关         | 是，工具调度基础              |
| Commit        | TODO                  |

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

### 非目标 / 边界

* 不实现具体文件工具。
* 不做路径安全策略。
* 不运行 shell 命令。

---

## T12：FileTools 最小读写

| 元信息           | 值                  |
| ------------- | ------------------ |
| 状态            | [ ] 未开始            |
| 依赖            | T2, T11            |
| 可并行           | 可与 T13 并行          |
| Worktree / PR | `feature/M3`       |
| 主贡献相关         | 是，工具能力基础           |
| Commit        | TODO               |

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

### 非目标 / 边界

* 不实现复杂 patch edit。
* 不处理 protected patterns。
* 不运行测试命令。

---

## T13：PathClassifier

| 元信息           | 值                       |
| ------------- | ----------------------- |
| 状态            | [ ] 未开始                 |
| 依赖            | T2, T3                  |
| 可并行           | 可与 T12 并行               |
| Worktree / PR | `feature/M3`            |
| 主贡献相关         | 是，治理护栏基础                |
| Commit        | TODO                    |

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
    ARTIFACT = "artifact"
    SOURCE = "source"
    PROTECTED = "protected"
    OUTSIDE = "outside"

def classify_path(project_root: Path, target: str, protected_patterns: list[str]) -> PathZone: ...
```

输入：project root、目标相对路径、protected patterns。
输出：PathZone。
不变量：不信任 LLM 自报路径类型。
错误处理：无法 resolve、路径逃逸、symlink 逃逸返回 OUTSIDE 或 PROTECTED。

### 预期失败测试

* `test_classifies_task_artifact`
* `test_classifies_source_file`
* `test_classifies_assignment_file_as_protected`
* `test_classifies_teacher_test_as_protected`
* `test_classifies_grading_script_as_protected`
* `test_rejects_dotdot_path_escape`
* `test_rejects_symlink_escape`

### 实现要点

* allow-list 优先识别 artifact zone。
* protected patterns 保护作业说明、教师测试、评分脚本、样例数据、`.env`、凭据文件。
* Windows 路径使用 resolve 和大小写归一化比较。

### 验证步骤

```powershell
uv run pytest tests/test_path_classifier.py -v
uv run ruff check src/hancode/path_policy.py tests/test_path_classifier.py
uv run mypy src/hancode/path_policy.py
```

### 完成判定

* 目标路径分类稳定。
* 路径逃逸和 protected 文件可被确定性识别。

### 非目标 / 边界

* 不判断当前 phase。
* 不决定是否 checkpoint。
* 不执行文件写入。

---

## T14：ToolPolicy 基础规则

| 元信息           | 值                         |
| ------------- | ------------------------- |
| 状态            | [ ] 未开始                   |
| 依赖            | T3, T5, T6, T7, T13       |
| 可并行           | 可与 T15 紧密衔接               |
| Worktree / PR | `feature/M3`               |
| 主贡献相关         | 是，治理护栏核心                  |
| Commit        | TODO                      |

### 目标

实现工具执行前的确定性策略判定，拒绝越权工具、缺 reason 写入、非 code phase source write、缺 SPEC/PLAN source write。

### 涉及文件

* `src/hancode/tool_policy.py`
* `tests/test_tool_policy.py`

### SPEC 依据

* ToolPolicy 治理护栏。
* Phase Gate。
* 缺 SPEC / PLAN 时不得进入 code phase。
* `edit_file` / `write_file` 必须提供 reason。

### 接口契约

```python
class PolicyDecision: ...

def evaluate_policy(action: Action, phase: Phase, state: TaskState, config: HanCodeConfig) -> PolicyDecision: ...
```

输入：Action、phase、TaskState、HanCodeConfig。
输出：PolicyDecision，包含 `allowed`、`reason`、`requires_checkpoint`、`denied_rule`、`suggested_fix`。
不变量：policy decision 必须由代码完成，不能依赖提示词。
错误处理：拒绝时不得执行工具，并把拒绝原因交给 FeedbackBuilder。

### 预期失败测试

* `test_disabled_tool_is_denied`
* `test_edit_file_requires_reason`
* `test_non_code_phase_source_write_is_denied`
* `test_spec_and_plan_required_before_source_write`
* `test_code_phase_source_write_requires_checkpoint`
* `test_policy_denial_contains_denied_rule_and_suggested_fix`

### 实现要点

* policy 先检查工具是否允许，再检查 phase，再检查 path zone，再检查 checkpoint requirement。
* 合法 source write 在 code phase 中返回 `requires_checkpoint=True`。
* denial 必须包含 `denied_rule` 和可执行的 `suggested_fix`。

### 验证步骤

```powershell
uv run pytest tests/test_tool_policy.py -v
uv run ruff check src/hancode/tool_policy.py tests/test_tool_policy.py
uv run mypy src/hancode/tool_policy.py
```

### 完成判定

* policy 可以被 AgentLoop 在 tool 前调用。
* policy denial 可以转成 observation。
* source write 前能明确要求 checkpoint。

### 非目标 / 边界

* 不实现具体课程文件保护扩展。
* 不执行 checkpoint。
* 不执行工具。

---

## T15：Course File Protection

| 元信息           | 值                              |
| ------------- | ------------------------------ |
| 状态            | [ ] 未开始                        |
| 依赖            | T13, T14                       |
| 可并行           | 不并行；属于治理护栏加固                   |
| Worktree / PR | `feature/M3`                      |
| 主贡献相关         | 是，学生课程项目特定化治理                  |
| Commit        | TODO                           |

### 目标

把课程项目保护规则落到 ToolPolicy / PathClassifier 中，禁止 Agent 未经明确授权修改作业说明、教师测试、评分脚本、样例数据和凭据文件。

### 涉及文件

* `src/hancode/tool_policy.py`
* `src/hancode/path_policy.py`
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

  * assignment / requirements / rubric 类文件。
  * teacher tests。
  * grading scripts。
  * sample data。
  * `.env`、`.env.*`、secret、credential 文件。
* MVP 不实现 HITL 审批覆盖；全部 protected write 默认 denied。

### 验证步骤

```powershell
uv run pytest tests/test_course_file_protection.py -v
uv run ruff check src/hancode/tool_policy.py src/hancode/path_policy.py tests/test_course_file_protection.py
uv run mypy src/hancode/tool_policy.py src/hancode/path_policy.py
```

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
| 状态            | [ ] 未开始              |
| 依赖            | T1, T4               |
| 可并行           | 可与 T13/T14 并行        |
| Worktree / PR | `feature/M4`         |
| 主贡献相关         | 是，可观测性核心             |
| Commit        | TODO                 |

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
class TraceEvent: ...

def append_trace(task_root: Path, event: TraceEvent) -> None: ...
```

输入：task root、TraceEvent。
输出：追加写入 `trace.jsonl`。
不变量：trace 只追加，不修改；event_id / seq 在 task 内可排序。
错误处理：trace 写入失败时阻止继续执行高风险工具。

### 预期失败测试

* `test_trace_appends_jsonl_event_with_event_id`
* `test_trace_event_has_monotonic_seq`
* `test_trace_redacts_secret_like_values`
* `test_trace_does_not_store_large_file_content`
* `test_trace_write_failure_blocks_high_risk_action`

### 实现要点

* `event_id` 格式可采用 `evt-000001`。
* 每行 JSONL 必须是合法 JSON。
* 脱敏字段包括 Authorization、api_key、token、secret、password。
* trace 不记录完整大文件内容。

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

### 非目标 / 边界

* 不实现 history summary。
* 不实现 demo 完整事件序列。
* 不实现 checkpoint。

---

## T17：CheckpointManager

| 元信息           | 值                          |
| ------------- | -------------------------- |
| 状态            | [ ] 未开始                    |
| 依赖            | T13, T15, T16              |
| 可并行           | 不并行；依赖路径和保护规则              |
| Worktree / PR | `feature/M4`                |
| 主贡献相关         | 是，可回退编码状态核心                |
| Commit        | TODO                       |

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

def create_checkpoint(task_root: Path, files: list[Path], reason: str) -> CheckpointManifest: ...
```

输入：task root、即将修改的 source files、reason。
输出：CheckpointManifest、文件快照。
不变量：checkpoint 只保存业务代码修改前的必要快照。
错误处理：空文件集、文件不存在、protected 文件进入快照请求时返回结构化错误。

### 预期失败测试

* `test_edit_file_creates_checkpoint`
* `test_checkpoint_manifest_contains_before_hash`
* `test_checkpoint_excludes_env_and_protected_files`
* `test_checkpoint_rejects_empty_file_set`
* `test_checkpoint_id_is_stable_format`

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
* 快照文件保存在 `checkpoints/<checkpoint_id>/files/`。
* 创建 checkpoint 后写 trace event。

### 验证步骤

```powershell
uv run pytest tests/test_checkpoints.py -v
uv run ruff check src/hancode/checkpoints.py tests/test_checkpoints.py
uv run mypy src/hancode/checkpoints.py
```

### 完成判定

* source write 前可创建 checkpoint。
* checkpoint 不包含 `.env`、凭据、教师测试、评分脚本、样例数据。
* manifest 可被 rollback 使用。

### 非目标 / 边界

* 不实现 rollback。
* 不实现 checkpoint pruning。
* 不使用 git 作为 checkpoint 机制。

---

## T18：RollbackManager

| 元信息           | 值                        |
| ------------- | ------------------------ |
| 状态            | [ ] 未开始                  |
| 依赖            | T17                      |
| 可并行           | 不并行                      |
| Worktree / PR | `feature/M4`              |
| 主贡献相关         | 是，可回退编码状态核心              |
| Commit        | TODO                     |

### 目标

实现最近 checkpoint 的恢复流程，使测试失败、review 风险过高或 retry budget 耗尽时可以恢复业务文件。

### 涉及文件

* `src/hancode/checkpoints.py`
* `tests/test_rollback.py`

### SPEC 依据

* Checkpoint 与 Rollback。
* retry budget 超限必须强制 rollback。
* rollback 不得覆盖 protected files、`.env` 或凭据文件。

### 接口契约

```python
class RollbackResult: ...

def rollback_last_checkpoint(task_root: Path) -> RollbackResult: ...
```

输入：task root。
输出：RollbackResult，包含 restored files、failed files、error summary。
不变量：只恢复 manifest 中允许恢复的业务文件。
错误处理：manifest 损坏、快照缺失、恢复失败时返回 failed / blocked，不盲目恢复。

### 预期失败测试

* `test_rollback_last_checkpoint_restores_file`
* `test_rollback_records_restored_files`
* `test_damaged_manifest_blocks_rollback`
* `test_rollback_does_not_restore_protected_files`
* `test_rollback_writes_trace_event`

### 实现要点

* rollback 成功后写 trace。
* rollback 结果应可被 FeedbackBuilder 转成 observation。
* 恢复后更新 state 中 latest checkpoint / rollback 信息。

### 验证步骤

```powershell
uv run pytest tests/test_rollback.py -v
uv run ruff check src/hancode/checkpoints.py tests/test_rollback.py
uv run mypy src/hancode/checkpoints.py
```

### 完成判定

* rollback 能恢复业务文件到 checkpoint 状态。
* manifest 损坏时不盲目恢复。
* rollback 结果结构化返回。

### 非目标 / 边界

* 不实现 git rollback。
* 不实现多 checkpoint pruning。
* 不恢复 protected files。

---

# M5：Context 与 Feedback

---

## T19：ContextBuilder

| 元信息           | 值                       |
| ------------- | ----------------------- |
| 状态            | [ ] 未开始                 |
| 依赖            | T2, T3, T4, T5, T16     |
| 可并行           | 可与 T20 并行               |
| Worktree / PR | `feature/M5`             |
| 主贡献相关         | 否，支撑维度                  |
| Commit        | TODO                    |

### 目标

实现按 phase 选择最小必要上下文的 ContextBuilder，使课程规则、任务产物、测试结果、checkpoint 和 trace 摘要按需进入 LLM 上下文。

### 涉及文件

* `src/hancode/context.py`
* `tests/test_context_builder.py`

### SPEC 依据

* ContextBuilder 与记忆选择。
* 课程项目上下文构造。
* 不得无条件加载全部历史。
* 不同 task 的 history、trace、checkpoint 不得混用。

### 接口契约

```python
def build_context(project_root: Path, task_id: str, phase: Phase, config: HanCodeConfig) -> dict[str, str]: ...
```

输入：project root、task ID、phase、config。
输出：结构化 context 字典。
不变量：不得无条件加载全部历史；不得混入其他 task 的 trace、history、checkpoint。
错误处理：code phase 缺 SPEC/PLAN 时返回 blocked context 或明确风险；context 超预算时按规则截断。

### 预期失败测试

* `test_context_builder_includes_course_context`
* `test_code_phase_context_requires_spec_and_plan`
* `test_review_phase_includes_test_report_changed_files_and_checkpoint`
* `test_deliver_phase_includes_required_artifacts`
* `test_context_builder_does_not_mix_other_task_trace`
* `test_context_builder_respects_max_context_chars`

### 实现要点

* 优先加载课程要求和当前 phase 必需产物。
* 其次加载 project memory / experience。
* trace 摘要最多取 `max_trace_events` 条。
* 截断时保留课程规则、当前 phase 必需产物和最近失败信息。

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
| 状态            | [ ] 未开始                  |
| 依赖            | T8, T11, T14, T18        |
| 可并行           | 可与 T19 并行                |
| Worktree / PR | `feature/M5`              |
| 主贡献相关         | 是，反馈闭环核心                 |
| Commit        | TODO                     |

### 目标

实现确定性的测试失败分类和 observation 构造，将测试结果、policy denial、parse error、rollback result 转换为下一轮 AgentLoop 可用的反馈。

### 涉及文件

* `src/hancode/feedback.py`
* `tests/test_feedback.py`

### SPEC 依据

* 反馈回灌机制。
* 反馈必须来自确定性工具结果或系统判定，不能由 LLM 自行判断。
* 测试失败分类和纠正建议必须稳定可测试。

### 接口契约

```python
class FailureCategory(str, Enum):
    SYNTAX_ERROR = "syntax_error"
    IMPORT_ERROR = "import_error"
    ASSERTION_FAILURE = "assertion_failure"
    ERROR_EXCEPTION = "error_exception"
    TIMEOUT_OR_CRASH = "timeout_or_crash"
    UNKNOWN = "unknown"

def classify_test_output(output: str, exit_code: int, timed_out: bool = False) -> FeedbackReport: ...
def build_observation(result: ToolResult | PolicyDecision | RollbackResult | ParseError) -> Observation: ...
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
* policy denial observation 包含 `denied_rule`、`reason`、`suggested_fix`。
* 不调用 LLM 判断失败原因。

### 验证步骤

```powershell
uv run pytest tests/test_feedback.py -v
uv run ruff check src/hancode/feedback.py tests/test_feedback.py
uv run mypy src/hancode/feedback.py
```

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
| 状态            | [ ] 未开始                           |
| 依赖            | T10, T14, T16, T18, T20           |
| 可并行           | 不并行；主贡献闭环任务                       |
| Worktree / PR | `feature/M5`                         |
| 主贡献相关         | 是，主贡献闭环核心                         |
| Commit        | TODO                              |

### 目标

把 AgentLoop 与 FeedbackBuilder、retry budget、review 路由、rollback 串起来，使“测试失败 -> feedback -> retry -> 强制 rollback”可在 MockLLM 下确定性复现。

### 涉及文件

* `src/hancode/agent_loop.py`
* `tests/test_feedback_loop.py`

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

### 验证步骤

```powershell
uv run pytest tests/test_feedback_loop.py -v
uv run ruff check src/hancode/agent_loop.py tests/test_feedback_loop.py
uv run mypy src/hancode/agent_loop.py
```

### 完成判定

* 主贡献闭环可在 MockLLM 下确定性复现。
* 测试失败不会直接 completed。
* retry 超限会强制 rollback。

### 非目标 / 边界

* 不生成最终 Markdown 报告。
* 不接真实 LLM。
* 不做 CLI demo。

---

# M6：Delivery 与 Demo

---

## T22：Delivery Artifacts 生成

| 元信息           | 值                          |
| ------------- | -------------------------- |
| 状态            | [ ] 未开始                    |
| 依赖            | T19, T20, T21              |
| 可并行           | 不并行；交付产物依赖反馈与上下文           |
| Worktree / PR | `feature/M6`                |
| 主贡献相关         | 是，知识沉淀交付                   |
| Commit        | TODO                       |

### 目标

生成课程项目交付产物：`TEST_REPORT.md`、`REVIEW.md`、`KNOWLEDGE.md`、`DELIVERABLES.md`。

### 涉及文件

* `src/hancode/delivery.py`
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
def write_deliverables(task_root: Path, result: AgentRunResult) -> Path: ...
```

输入：task root、测试反馈、需求覆盖、风险、trace 摘要、最终结果。
输出：四个 Markdown 产物。
不变量：deliver phase 不修改业务代码。
错误处理：缺少测试或 review 时在 `risks[]` 中说明；核心需求未覆盖或测试未通过时 blocked / failed。

### 预期失败测试

* `test_write_test_report_contains_command_status_summary`
* `test_code_change_requires_test_or_risk_note`
* `test_review_contains_requirement_coverage_table`
* `test_knowledge_contains_decisions_failures_and_reusable_lessons`
* `test_deliver_requires_knowledge_file`
* `test_deliver_requires_deliverables_file`
* `test_deliver_with_failed_tests_returns_blocked`

### 实现要点

* Markdown 标题和表格结构稳定，便于课程评估和测试断言。
* REVIEW 至少包含需求、证据、状态、风险列。
* KNOWLEDGE 至少包含课程知识点、设计决策、测试失败、错误修复、可复用模式。
* DELIVERABLES 至少包含交付物清单、测试状态、风险、最终状态。

### 验证步骤

```powershell
uv run pytest tests/test_delivery.py -v
uv run ruff check src/hancode/delivery.py tests/test_delivery.py
uv run mypy src/hancode/delivery.py
```

### 完成判定

* Markdown 产物标题和结构稳定，可被测试断言。
* deliver phase 不修改业务代码。
* 缺测试 / 缺 review 时写入 risks。

### 非目标 / 边界

* 不让真实 LLM 写总结。
* 不做漂亮模板渲染。
* 不运行完整 demo。

---

## T23：MockLLM 机制 Demo

| 元信息           | 值                 |
| ------------- | ----------------- |
| 状态            | [ ] 未开始           |
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
* `test_mock_demo_trace_contains_rollback_completed`
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
| 状态            | [ ] 未开始                           |
| 依赖            | T2, T23                           |
| 可并行           | 可先实现 help / init，demo 命令等 T23 后接入 |
| Worktree / PR | `feature/M7`                      |
| 主贡献相关         | 否，交付入口                            |
| Commit        | TODO                              |

### 目标

实现 Typer CLI 的最小命令结构，使用户可以初始化 workspace、运行 mock demo、查看帮助和导出产物。

### 涉及文件

* `src/hancode/cli.py`
* `tests/test_cli.py`

### SPEC 依据

* CLI entry point。
* Headless CLI 是 Demo、测试和课程评估入口。
* CLI 不应绕过 Harness Core。

### CLI 命令契约

```text
hancode --help
hancode init
hancode demo --provider mock
hancode run "<goal>" --provider mock
hancode auth status --provider openai
hancode export --task task-001 --out deliverables/
```

输入：CLI 参数、workspace 路径、provider 参数。
输出：稳定 exit code、结构化文本输出、必要产物。
不变量：CLI 只调用 core，不绕过 policy、workspace、demo runner。
错误处理：provider 未知 exit code 1；配置错误 exit code 2；trace/checkpoint 不可恢复错误 exit code 3。

### 预期失败测试

* `test_cli_help_displays_commands`
* `test_cli_init_creates_workspace`
* `test_cli_demo_runs_with_mock_provider_without_credentials`
* `test_cli_unknown_provider_returns_clear_error`
* `test_cli_exit_code_for_config_error_is_stable`

### 实现要点

* 使用 Typer。
* `demo --provider mock` 不要求真实凭据。
* CLI 输出状态必须明确：completed / blocked / failed。
* 不在命令行参数中接收明文 key。

### 验证步骤

```powershell
uv run pytest tests/test_cli.py -v
uv run ruff check src/hancode/cli.py tests/test_cli.py
uv run mypy src/hancode/cli.py
uv run hancode --help
```

### 完成判定

* CLI help 可用。
* init 能创建 workspace。
* mock demo 可通过 CLI 运行。

### 非目标 / 边界

* 不实现复杂 TUI。
* 不实现真实 provider smoke test。
* 不实现 Docker。

---

## T25：CredentialProvider

| 元信息           | 值                   |
| ------------- | ------------------- |
| 状态            | [ ] 未开始             |
| 依赖            | T3, T24             |
| 可并行           | 可与 T26 部分并行         |
| Worktree / PR | `feature/M7`        |
| 主贡献相关         | 否，安全边界              |
| Commit        | TODO                |

### 目标

实现凭据状态、录入、清除的安全边界，保证 CLI、trace、日志、测试快照不打印真实 secret。

### 涉及文件

* `src/hancode/credentials.py`
* `tests/test_credentials.py`

### SPEC 依据

* 凭据与分发设计。
* 凭据状态检查只能显示是否存在，不得回显明文。
* 优先使用 keyring，`.env` 仅作为本地开发 fallback。

### 接口契约

```python
class CredentialStatus: ...

def credentials_status(provider: str) -> CredentialStatus: ...
def credentials_set(provider: str, secret: str) -> None: ...
def credentials_clear(provider: str) -> None: ...
```

输入：provider、隐藏输入 secret。
输出：CredentialStatus 或操作结果。
不变量：CLI 不通过命令行参数接收明文 key；status 只显示 configured/source/masked_id。
错误处理：unknown provider 返回结构化错误。

### 预期失败测试

* `test_auth_status_does_not_print_secret`
* `test_credential_status_reports_configured_without_value`
* `test_credentials_clear_removes_secret`
* `test_auth_login_does_not_accept_key_argument`
* `test_fake_credential_provider_for_tests`

### 实现要点

* 使用 fake credential provider 完成单元测试。
* keyring 集成可做最小封装。
* `.env` fallback 明确标注为本地开发后备。
* 所有错误输出脱敏。

### 验证步骤

```powershell
uv run pytest tests/test_credentials.py -v
uv run ruff check src/hancode/credentials.py tests/test_credentials.py
uv run mypy src/hancode/credentials.py
```

### 完成判定

* CLI 不输出 secret 明文。
* 测试只用 fake secret。
* 凭据状态可以显示来源和是否配置。

### 非目标 / 边界

* 不在 CI 中调用真实 provider。
* 不把 key 写入 config、trace、checkpoint。
* 不实现企业级 secret manager。

---

## T26：Package Build 与 CI

| 元信息           | 值                  |
| ------------- | ------------------ |
| 状态            | [ ] 未开始            |
| 依赖            | T24, T25           |
| 可并行           | 不并行；交付验证任务         |
| Worktree / PR | `feature/M7`       |
| 主贡献相关         | 否，交付质量保障           |
| Commit        | TODO               |

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
| 状态            | [ ] 未开始                      |
| 依赖            | T23, T24, T25, T26           |
| 可并行           | 最终文档任务                       |
| Worktree / PR | `feature/M7`                   |
| 主贡献相关         | 否，最终交付文档                     |
| Commit        | TODO                         |

### 目标

更新 README，使新用户能在干净环境中安装、运行 mock demo、理解凭据安全和已知限制。

### 涉及文件

* `README.md`
* `docs/AGENT_LOG.md`
* `docs/SPEC_PROCESS.md`

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

### 实现要点

* README 不写“未来会支持”式不确定承诺。
* 所有命令必须与 CLI 实际命令一致。
* AGENT_LOG 记录实现过程、验证命令和人工干预。
* SPEC_PROCESS 记录冷启动验证结果和修订。

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

# 8. 需求→任务追溯

| SPEC 锚点                                  | 对应任务                         | 状态  |
| ---------------------------------------- | ---------------------------- | --- |
| FR-1 AgentLoop 主循环                       | T10, T21                     | [ ] |
| FR-2 LLM 抽象与 MockLLM                     | T9, T23                      | [ ] |
| FR-3 Action 解析与校验                        | T7, T8                       | [ ] |
| FR-4 ToolRegistry 与工具分发                  | T11, T12                     | [ ] |
| FR-5 ToolPolicy 治理护栏                     | T13, T14, T15                | [ ] |
| FR-6 ContextBuilder 与记忆选择                | T19                          | [ ] |
| FR-7 反馈回灌机制                              | T20, T21                     | [ ] |
| FR-8 TraceLogger                         | T16                          | [ ] |
| FR-9 配置加载与运行约束                           | T3, T26                      | [ ] |
| FR-10 Project Workspace 与 Task Workspace | T2                           | [ ] |
| FR-11 课程项目 Phase Gate                    | T5, T6                       | [ ] |
| FR-12 课程项目上下文构造                          | T19                          | [ ] |
| FR-13 课程文件保护策略                           | T13, T14, T15                | [ ] |
| FR-14 Checkpoint 与 Rollback              | T17, T18, T21                | [ ] |
| FR-15 测试报告与审查记录                          | T20, T22                     | [ ] |
| FR-16 Knowledge Delivery                 | T22, T23                     | [ ] |
| 凭据与分发设计                                  | T25, T26, T27                | [ ] |
| 可测试性约定                                   | T1-T27                       | [ ] |
| 测试失败分类                                   | T20                          | [ ] |
| 危险动作与治理护栏                                | T13, T14, T15                | [ ] |
| 记忆与上下文机制                                 | T2, T19                      | [ ] |
| 主贡献维度                                    | T16, T17, T18, T20, T21, T23 | [ ] |
| MockLLM 机制演示                             | T9, T21, T23                 | [ ] |

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
