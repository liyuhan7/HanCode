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
* `confirm_before_write` 写前人工确认（→ 已由 S3-R 审批协议覆盖）。
* Docker demo image。
* 复杂 TUI（→ S3-R5 审批面板已实现）。
* WebUI。
* 多语言测试命令扩展。
* 完整 Git 分支管理。
* 真实 LLM provider smoke test 作为 CI 必需项。

### 3.3 S3 阶段：交互暂停、恢复与事件流

S3 阶段在 M1-M7 里程碑完成后追加，包含：
* **S3-R**: 人工审批协议（Approval Protocol）
* **S3-A**: ASK_USER 交互（已完成于 TUI 开发中）
* **S3-T**: TaskList 刷新与面板残留修复（已完成于基线 b76c65c）

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

M8 Task Runtime Memory
  S13-R0 文档契约
    -> S13-R1 模型 / Store / 配置
    -> S13-R2 Recorder / 失效
    -> S13-R3 Context / 统一预算
    -> S13-R4 Memory Tools
    -> S13-R5 Demo / 全量门禁
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
| M4 反馈与回退闭环成立 | 测试失败 -> feedback -> retry -> rollback 可在 MockLLM 下确定性复现                 | T19-T21 |
| M5 Demo 可证明机制 | MockLLM demo 生成 trace、TEST_REPORT、REVIEW、KNOWLEDGE、DELIVERABLES         | T22-T23 |
| M6 可交付        | CLI、凭据边界、package build、CI、README 完成                                     | T24-T27 |
| M8 Runtime Memory 成立 | 工具摘要与文件快照可跨进程恢复，stale 不自动注入，Context 总预算、Memory Tool 和有效只读动作复用约束可确定性验证 | S13-R0-R5 |

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
| 主贡献相关         | 是，S13 Project/Task workspace 基础 |
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
| 主贡献相关         | 是，S13 Memory 配额配置基础 |
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
* `run_tests` 可携带一个显式测试 `command`；省略时使用 config fallback，显式命令必须经过人工审批，且不支持 shell 组合语义。

### 实现结果

* 新增冻结、slots 化的 `Action`、`ActionType` 和 `ParseError`，并以 `Action.from_values()` 作为类型化候选 action 的确定性校验入口；原始 dict 的字段解析仍由 T8 实现。
* `ActionType` 固定为 `tool_call`、`finish_phase`、`ask_user`、`final`；action 不含 `target_kind`。
* 七个 MVP 工具使用固定参数 schema：`read_file(path)`、`list_files()` / `list_files(path)`、`search_text(query)`、`write_file(path, content)`、`edit_file(path, old_string, new_string)`、`run_tests()` / `run_tests(command)`、`rollback_last_checkpoint()`。
* `write_file` 和 `edit_file` 必须有非空 `reason`；`run_tests.command` 为可选非空字符串，显式命令需审批且拒绝 shell 语法；非法类型、phase、工具、参数和控制 action 工具名均返回不回显候选值的 `ParseError`。
* `rollback_last_checkpoint` 是无参数工具；`run_tests` 仅允许可选 `command` 参数；即使未来工具已注册但未声明 schema，也会 fail-closed 拒绝。
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
| 主贡献相关         | 是，S13 统一 Context 预算基础 |
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
| 可并行           | 不并行；反馈与回退闭环任务                     |
| Worktree / PR | `feature/M5`                         |
| 主贡献相关         | 是，三项主贡献中的反馈与回退闭环核心               |
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

* 反馈与回退闭环可在 MockLLM 下确定性复现。
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
* T21 当时的边界是不跨会话持久化上一次 observation，也不重放完整生命周期 trace，仅复用 state、checkpoint 与已有 trace；该缺口由后续 S13-R2/R3 的 task runtime memory 和统一 Context 预算显式补齐。
* T21 补齐 feedback / retry / rollback 相关 trace 与边界事件；T21-R1 Task 2 追加 `phase_started` / `phase_completed` / `run_completed` 阶段生命周期事件。完整的 context / action 级生命周期事件矩阵仍不在本卡内重构。

---

## T21-R1：未覆盖缺陷安全、工具与恢复收尾

| 元信息           | 值                                 |
| ------------- | --------------------------------- |
| 状态            | [x] 已完成（Task 1-9、两阶段评审与全量验证通过） |
| 依赖            | T21                              |
| 可并行           | 分组串行；先安全边界，再工具与恢复          |
| Worktree / PR | `main`（已合并 `feature/M7`）       |
| 主贡献相关         | 是，T21 收尾修复                     |
| Commit        | Task 1 `b91ed75`；Task 2 `78acbe7`；收尾 `5d9c4ad`；审批/测试闭环 `088739f`、`c0c0906` |

### 目标

在 `feature/M7` 完成 T21-R1 剩余机制：凭据路径保护一致性、精确文件编辑、受限测试执行、默认工具装配，以及 pending checkpoint 的可审计 abort / 恢复。保持 Mock/stub 可替换、禁止通用 shell，并通过结构化错误和证据化验证收口。

### 修复边界

* checkpoint / trace 达到上限时 fail-closed 拒绝新增，不自动 pruning。（Task 1 已实现）
* policy denial 保留为主错误；trace 写失败作为审计风险，不得导致工具执行。（Task 2 已实现：`policy_denied` 主错误保留、trace 失败降级为 `Risk`）
* 纯审计标记点（phase_started / phase_completed / run_completed / policy_denied）trace 写失败降级为 risk 不掩盖主错误；变更与工具执行点（tool_called / source_write_authorized / checkpoint）保持 fail-closed。（Task 2 已实现）
* `edit_file` 使用恰好一次匹配规则和原子写入；失败在可证明未写入时返回 `mutation_applied=False`，原子替换阶段不确定时返回 `None`。
* `run_tests` 未提供 `command` 时执行配置命令；显式 `command` 必须经过人工审批。两种路径都用 `shlex.split` 固定拆分为单条 argv，固定 `cwd=project_root`、`shell=False`、`capture_output=True`、`check=False`，默认超时 120 秒；`&&`、`||`、管道、重定向、分号等 shell 操作符直接拒绝，命令和输出先脱敏再进入结果、state、trace 和报告。
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
* `src/hancode/core/tool_specs.py`
* `src/hancode/core/actions.py`
* `src/hancode/tooling/test_tools.py`
* `src/hancode/tooling/factory.py`
* `src/hancode/demo_support/runner.py`
* `src/hancode/policy/approval_policy.py`
* `src/hancode/runtime/approval_request.py`
* `src/hancode/runtime/agent_loop.py`
* 对应 `tests/` 回归测试、`docs/SPEC.md`、本文件和 `docs/AGENT_LOG.md`

### 验证要求

* 直接实现最小修复，并用专项测试、全量测试和静态检查验证；本轮按用户要求不采用 TDD Red/Green 流程。
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
    run_tests_tool: Callable[[str | None], ToolResult] | None = None,
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

`CheckpointManifest.status` 的生命周期为 `pending | committed | rolled_back | aborted`。`FilesystemStateStore.reconcile()` 接收 `recover_pending`，AgentLoop 只在调用方显式传入 `resume=True` 时授权 pending 恢复；`run_tests` 可接收一个显式 `command`，但该命令必须先获人工批准，只能作为单条 argv 执行；不提供通用 shell 或多文件 patch。

### T21-R1 Task 8：动态测试命令审批与执行安全化

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已实现，专项与全量验证通过 |
| 目标 | 保留 LLM 传入单条测试命令的能力，同时强制动态命令人工确认并形成可审计脱敏链路。 |
| 允许修改 | `src/hancode/core/tool_specs.py`、`src/hancode/core/actions.py`、`src/hancode/tooling/test_tools.py`、`src/hancode/tooling/factory.py`、`src/hancode/demo_support/runner.py`、`src/hancode/policy/approval_policy.py`、`src/hancode/runtime/approval_request.py`、`src/hancode/runtime/agent_loop.py`、对应测试、`docs/SPEC.md`、`docs/PLAN.md`、`docs/AGENT_LOG.md`。 |

#### 行为契约

* Action 的 `run_tests.args` 可省略 `command`；省略时使用 `config.test_command`，不额外触发审批。
* 显式提供 `command` 时，无论 `approval_mode` 是否为 `disabled`，都必须返回 `ApprovalCategory.RUN_TESTS` 要求；审批拒绝或未批准时不得调用 ToolRegistry。
* 批准记录的 digest 绑定完整 Action（含完整 args），resume 只能执行原批准命令；恢复时命令被替换必须 fail-closed。
* 执行统一采用 `shlex.split`、固定 `cwd=project_root`、`shell=False`、`capture_output=True`、`check=False`，拒绝 `&&`、`||`、管道、重定向、分号等 shell 语法。
* 命令、审批预览/记录、ToolResult、state、trace 和 `TEST_REPORT.md` 的用户可见字段必须脱敏；敏感命令不得进入持久化审批记录。

#### 验收标准

* schema 接受可选字符串 `command`，拒绝非字符串和额外参数；fallback、显式命令、注入 callback 均有专项回归。
* shell 操作符在 runner 启动前被拒绝；自定义 `run_tests_tool` 接收最终命令，不再因零参数签名产生 TypeError。
* 显式命令覆盖 disabled 模式的审批门；拒绝不启动 runner，批准后执行原命令，digest 或恢复篡改会被拒绝。
* 审批预览、tool/test trace、state 和测试报告不出现敏感值；`SPEC`、`PLAN`、`AGENT_LOG` 与实现和实际验证结果一致。

#### 非目标

* 不引入通用 `run_shell`，不启用 shell，不支持 pipeline、重定向或多命令组合。
* 不修改无关 TUI 文件，不增加配置字段，不接真实 LLM、网络或依赖自动安装。

### T21-R1 Task 9：Agent 自生成测试命令与审批后续闭环

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已实现，专项与全量验证通过 |
| 依赖 | T21-R1 Task 8、现有 Router / Approval / DeliveryPipeline |
| 分支 | `main`（按用户要求直接开发） |
| 范围 | TEST 阶段探索、显式命令审批、审批后 AgentLoop 续跑、Provider 空响应有限重试 |
| 非目标 | 不重写 `test_tools.py`、`factory.py`、`approval_policy.py`、`delivery_pipeline.py` 或 `core/router.py` |

#### 行为契约

* TEST 阶段不再要求 `config.test_command`；若配置存在，只作为可选候选注入上下文。
* `run_tests` 仅允许在 TEST 阶段；`list_files`、`read_file`、`search_text` 可在 TEST 阶段用于项目结构探索，`list_files` 的 `path` 参数在 ToolSpec 中显式声明。
* Provider-facing schema 在 TEST 的 `run_tests` 分支强制 `args.command`，Prompt 要求单条、非编译-only 的行为测试命令，并由运行时自动请求审批。
* 批准的 `run_tests` 执行后回灌结构化测试反馈；同一次 `resume` 继续调用 Provider，成功完成 TEST，失败按现有 Router 进入 REVIEW，不改变 `latest_test_status`、`test_status_consumed` 与 retry/rollback 语义。
* `provider_invalid_response` 与 `provider_empty_response` 只做有限两次连续重试；审批 manifest/state 同步失败返回结构化 `approval_state_sync_failed`，不静默吞错。

#### 验收证据

* TDD Red：新增阶段、Schema、审批续跑和 Provider 重试测试在实现前复现原有失败行为。
* 全量 pytest：`1336 passed, 17 skipped`。
* Ruff：`uv run --no-sync ruff check src tests` → `All checks passed!`。
* MyPy：`uv run --no-sync mypy src/hancode` → `Success: no issues found in 98 source files`。
* 构建：`uv build` → 成功生成 `dist/hancode-0.1.0.tar.gz` 与 `dist/hancode-0.1.0-py3-none-any.whl`；首次无提升权限运行仅受 Windows `WinError 5` 临时目录权限阻断，提升权限后复验通过。

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

## S4：REPL/TUI 终端交互层与实时运行事件桥接

| 元信息   | 值                                                    |
| ----- | ---------------------------------------------------- |
| 状态    | [x] 已完成（S4-T1 至 S4-T8 TDD、静态门禁、全量回归与构建通过）        |
| 依赖    | S3（Human-in-the-Loop ASK_USER 状态机）                   |
| 主贡献相关 | 是；终端交互产品形态                                            |
| Commit | 未提交（按用户要求保留在当前工作区）                    |

### S4.1 阶段定位

S3 完成后，HanCode 的交互内核已经可通过 Headless CLI 驱动：

```text
自然语言目标
→ hancode task create / run
→ AgentLoop（真实 Provider 或 MockLLM）
→ ASK_USER 暂停 → hancode task answer → hancode task resume
→ 六阶段产物与最终状态
```

S4 在此之上封装类似 Claude Code 的简化终端 Coding Agent 产品：

```text
hancode tui
→ 输入课程项目目标
→ 实时展示 phase / tool / test / checkpoint / risk
→ Agent 请求澄清时暂停并聚焦输入框
→ 用户直接回答，自动 resume
→ 查看 SPEC / PLAN / TEST_REPORT / REVIEW / KNOWLEDGE
→ 查看最终状态和风险
```

S4 只新增 Presentation Layer，不重新实现 AgentLoop、ProviderAdapter、ToolPolicy、CheckpointManager、RollbackManager、ContextBuilder、Interaction 状态机、Trace 协议或六阶段 Router。

### S4.2 与现有代码的接口对齐（实现前已核验）

下列内核接口在实现 S4 前已对照源码确认存在，S4 直接复用，不得旁路：

* `TaskService.create / get / list_tasks / run / resume`（`app/task_service.py`），`run` / `resume` 返回 `AgentRunResult`。
* `InteractionService.answer(project_root, task_id, answer, *, interaction_id=None)`（`app/interaction_service.py`），内部已做 mutation lock、脱敏、幂等、`interaction_answered` trace 与补偿回滚。TUI 不得自行修改 `state.json`。
* `TaskSummary`（`app/task_models.py`）已含 `status / current_phase / retry_budget_remaining / latest_test_status / files_changed / tests_run / latest_checkpoint / rollback_required / inconsistent / artifacts / resumable / requires_input / pending_interaction`。
* `AgentRunResult`（`runtime/agent_loop.py`）已含 `status / steps / tool_calls / risks / final_observation / error / final_state / retry_budget_remaining / trace_events`。
* `TraceEvent`（`storage/trace.py`）已含 `event_id / seq / event_type / task_id / phase / timestamp / status / action / observation / error_summary / state_transition`，写入前已结构化脱敏，S4 不再定义重复事件 Schema。
* `TraceAppender`（`runtime/agent_loop.py`）是 `Protocol`，签名为 `append(self, task_id, *, event_type, phase, status, action=None, observation=None, error_summary=None, state_transition=None) -> TraceEvent`。
* `create_agent_loop`（`runtime/engine.py`）已支持注入 `trace_appender`，`trace_observer` 为纯增量参数。

### S4.3 阶段范围

#### 3.1 本阶段实现

| 能力 | 是否实现 |
|---|---:|
| `hancode tui` 显式入口 | 是 |
| `ObservedTraceAppender` 持久化后实时通知 UI | 是 |
| `runtime.engine` / `TaskService.run/resume` 透传 `trace_observer` | 是 |
| 后台 Worker 执行 AgentLoop，主线程只渲染 | 是 |
| 单 TUI Session 单活跃 Task Worker | 是 |
| `TuiViewState` 不可变状态 + reducer | 是 |
| CommandParser（slash command + 普通文本语义） | 是 |
| TaskList / PhaseBar / ActivityLog / DetailPanel / Composer | 是 |
| WAITING_INPUT 显示问题、回答后自动 resume | 是 |
| `InspectionService` 恢复历史 Trace 与安全 Artifact 预览 | 是 |
| `RecoveryService` 受控 rollback（显式确认） | 是 |
| 重启 TUI 后恢复 Task 列表与历史 Trace | 是 |
| Answer 正文不回显、credential 不进入界面 | 是 |

#### 3.2 本阶段不实现

| 能力 | 原因 |
|---|---|
| 多 Task 并行运行 / 多 Agent 协作 | 单 Session 单 Worker |
| 流式 LLM Token 展示 | 展示单位是可审计 Action / TraceEvent，非 Token 流 |
| 自由聊天上下文 / 追加 Prompt | 避免变成无边界 Agent |
| 任意 Shell passthrough / `!command` | 安全边界 |
| 完整代码编辑器 / Diff 编辑 / 源码浏览 | 超出 MVP |
| 裸 `hancode` 自动进入 TUI | 延后到 `hancode tui` 稳定后 |
| 强制 Cancel 正在运行的 Worker | 需 AgentLoop 支持 CancellationToken |
| WebUI / 远程执行 / MCP / 语音输入 | 非当前产品形态 |

### S4.4 目标架构与边界

```text
Textual TUI App (TaskList / PhaseBar / ActivityLog / DetailPanel / Composer)
        │ command / text
        ▼
TuiSessionController (CommandParser / ViewStateReducer / Worker)
        │
        ├── TaskService / InteractionService / InspectionService / RecoveryService
        ▼
runtime.engine → AgentLoop → ObservedTraceAppender
                                   ├─ trace.jsonl（先持久化）
                                   └─ TraceObserver → Textual Message Queue（后通知）
```

必须保持 `TUI → Application Service → Engine → AgentLoop`。禁止：`TUI → AgentLoop private method`、`TUI → ToolRegistry.dispatch()`、`TUI → write state.json`、`TUI → append trace.jsonl`、`TUI → rollback_last_checkpoint()`、`TUI → ProviderAdapter.next_action()`。

### S4.5 核心机制约束

* **Trace 先落盘再通知**：`ObservedTraceAppender.append()` 先调用内层 `TraceAppender.append()` 完成持久化，成功后再 `observer.on_trace(event)`；Observer 抛异常必须被吞掉，不改变 AgentLoop 运行结果、不产生 `INCONSISTENT`。
* **签名一致性（MyPy strict）**：`ObservedTraceAppender.append` 必须完整复刻 `TraceAppender` Protocol 的关键字签名（`task_id` 位置参数、其余 keyword-only），不使用 `**kwargs`，以保持内层调用的类型安全。
* **可选透传**：`create_agent_loop` / `run_task` / `TaskService.run` / `TaskService.resume` 增加的 `trace_observer: TraceObserver | None = None` 必须是可选关键字参数，Headless CLI 与现有测试行为不变。
* **后台 Worker**：Provider 请求、AgentLoop、文件工具、测试、checkpoint、rollback、Trace / Artifact 加载均在 Worker 中运行；Observer 不得直接操作 Widget，只能 `post_message`。
* **单运行约束**：`ViewState.busy=True` 时禁止再次 `/run`、切换 active task、`/rollback`、提交新 goal；文件系统 mutation lock 仍是最终并发保护。
* **UI 事件缓存上限**：界面最多缓存最近 500 个 `TraceEvent`；删除最旧 UI Event 不影响 `trace.jsonl` 完整审计。
* **纯文本渲染**：所有用户文本与 Trace 文本按纯文本处理，禁用用户输入的 Rich markup / ANSI 注入。

### S4.6 新增与修改文件

新增：`runtime/observation.py`（`TraceObserver`、`ObservedTraceAppender`）、`app/inspection_service.py`、`app/recovery_service.py`、`interfaces/tui/`（`app.py` / `controller.py` / `commands.py` / `messages.py` / `view_state.py` / `formatters.py` / `screens/main.py` / `widgets/*`）。

修改：`runtime/engine.py`、`app/task_service.py`、`interfaces/cli.py`、`pyproject.toml`（锁定 Textual 版本）、`uv.lock`、`README.md`、`docs/PLAN.md`、`docs/AGENT_LOG.md`。

### S4.7 TDD 实现顺序

#### S4-T1：TUI 依赖与空壳入口

| 元信息 | 值 |
|---|---|
| 状态 | [x] 已完成 |
| 依赖 | S3 |
| 涉及文件 | `pyproject.toml`, `uv.lock`, `interfaces/cli.py`, `interfaces/tui/__init__.py`, `interfaces/tui/app.py`, `interfaces/tui/screens/main.py`, `tests/test_tui_app.py` |
| 目标 | 锁定 Textual 版本，新增显式 `hancode tui` 子命令并挂载基础主屏 |

* 先写测试：`test_tui_command_is_registered`、`test_tui_app_mounts_main_screen`、`test_headless_cli_output_remains_json`、`test_existing_cli_help_is_unchanged`。
* 完成判定：TUI 可启动；现有 CLI JSON 输出与 `--help` 不变；无 Provider / Workspace 时给出结构化提示而非崩溃。
* 边界：本任务只加显式 `hancode tui`，不改 `no_args_is_help`，不实现裸 `hancode` 进入 TUI；不得引入 Textual 私有 API。

实际验证（2026-07-21）：

* 依赖：`pyproject.toml` 增加 `textual>=0.60`，`uv lock` 解析到 `textual v8.2.8`，`uv sync --extra dev` 完成安装。
* Red：新增 `tests/test_tui_app.py` 后，`test_tui_command_is_registered`（`--help` 无 `tui`）与 `test_tui_app_mounts_main_screen`（`ModuleNotFoundError: hancode.interfaces.tui`）如期失败，2 passed / 2 failed。
* Green：新增 `interfaces/tui/{__init__,app}.py` 与 `screens/main.py`（Header/Static/Footer 空壳），CLI 增加 `@app.command("tui")` 惰性导入并 `HanCodeTuiApp(project_root=...).run()`；Textual `run_test()` 通过 `asyncio.run` 驱动，未引入 pytest-asyncio。专项 `4 passed`。
* 门禁：`ruff check`（新增 TUI 代码 + 测试 + cli）通过；`mypy src` 为 64 源文件无问题；全量 `pytest` 为 `978 passed, 14 skipped`；`uv build` 成功生成 sdist/wheel（已清理 dist/build/egg-info）。
* 入口：`hancode --help` 显示 `tui  Launch the interactive terminal session (REPL/TUI).`。
* 剩余：`mypy tests/test_tui_app.py` 单独检查时报 Textual `import-untyped`，属第三方库无 `py.typed`；项目标准门禁为 `mypy src`，不受影响。Commit 待用户决定。

#### S4-T2：ObservedTraceAppender 与 Engine 透传

| 元信息 | 值 |
|---|---|
| 状态 | [x] 已完成 |
| 依赖 | S4-T1 |
| 涉及文件 | `runtime/observation.py`, `runtime/engine.py`, `app/task_service.py`, `tests/test_observed_trace.py`, `tests/test_app_layers.py`, `tests/test_task_service.py` |
| 目标 | 持久化 Trace 成功后实时通知 UI，且不改变 Harness 运行结果 |

* 先写测试：`test_observer_receives_event_after_trace_persistence`、`test_observer_failure_does_not_change_agent_result`、`test_observer_never_receives_unpersisted_event`、`test_task_service_forwards_trace_observer`、`test_observer_receives_events_in_seq_order_during_mock_run`（另含 engine 装配透传的两条）。
* 完成判定：MockLLM 运行过程中 Observer 按 `seq` 接收事件；Observer 异常被吞、不影响 `AgentRunResult`、不产生 `INCONSISTENT`；无 observer 时行为与现状一致。

实际验证（2026-07-21）：

* Red：新增 `tests/test_observed_trace.py` 后收集期 `ModuleNotFoundError: hancode.runtime.observation`。
* Green：新增 `runtime/observation.py`（`TraceObserver` Protocol + `ObservedTraceAppender`，完整复刻 `TraceAppender` 关键字签名、不使用 `**kwargs`，先持久化再通知、Observer 异常吞掉）；`create_agent_loop` / `run_task` / `TaskService.run` / `resume` 增加可选 `trace_observer` 关键字透传。专项 `7 passed`（含 MockLLM 端到端按 seq 接收事件）。
* 回归修复：`test_app_layers.py`、`test_task_service.py` 中三个 monkeypatch 的 fake `run_task` 增补可选 `trace_observer` 形参（`run` 现始终转发该 kwarg）。
* 门禁：`ruff check`（src + 相关测试）通过；`mypy src` 为 65 源文件无问题；全量 `pytest` 为 `985 passed, 14 skipped`。Commit 待用户决定。

#### S4-T3：InspectionService

| 元信息 | 值 |
|---|---|
| 状态 | [x] 已完成 |
| 依赖 | S4-T2 |
| 涉及文件 | `app/inspection_service.py`, `tests/test_inspection_service.py` |
| 目标 | 分页恢复历史 Trace 与 allow-list Artifact 安全预览 |

* 接口：`read_trace(project_root, task_id, *, after_seq=0, limit=200) -> TracePage`；`read_artifact(project_root, task_id, artifact_name, *, max_chars=50_000) -> ArtifactPreview`。
* 先写测试：`test_read_trace_returns_events_in_seq_order`、`test_read_trace_rejects_gapped_sequence`、`test_read_trace_rejects_symlink`、`test_read_trace_rejects_wrong_task_id`、`test_read_artifact_allows_declared_artifact`、`test_read_artifact_rejects_source_file`、`test_read_artifact_rejects_credentials`、`test_read_artifact_truncates_large_preview`（另含 after_seq/limit 分页与 undeclared 拒绝）。
* Artifact allow-list 仅：`SPEC.md`、`PLAN.md`、`TEST_REPORT.md`、`REVIEW.md`、`KNOWLEDGE.md`、`DELIVERABLES.md`，且要求 `state.artifacts[name] == True`；拒绝 `.env` / 凭据 / 任意源码 / 教师测试 / 评分脚本 / 任务目录外 / symlink。
* 完成判定：重启 TUI 后可恢复 Task 列表、当前状态与历史 Trace。

实际验证（2026-07-21）：

* Red：新增 `tests/test_inspection_service.py` 后收集期 `ModuleNotFoundError: hancode.app.inspection_service`。
* Green：新增 `app/inspection_service.py`（`TracePage` / `ArtifactPreview` / `InspectionService`）。`read_trace` 复用与 `storage/trace.py` 一致的完整性校验（逐行 JSON object、`seq` 从 1 连续、`event_id=evt-NNNNNN`、`task_id` 绑定），拒绝 symlink trace，按 `after_seq`/`limit` 分页。`read_artifact` 走固定 allow-list + `state.artifacts[name] == True` + 非 symlink + `redact_text` 脱敏 + `max_chars` 截断。专项 `9 passed, 1 skipped`（symlink 用例在无权限 Windows 环境 skip）。
* 门禁：`ruff` 通过；`mypy src` 66 源文件无问题（修正一处 `error_summary` 的 `object` 收窄）；全量 `pytest` 为 `994 passed, 15 skipped`。Commit 待用户决定。

#### S4-T4：CommandParser 与 TuiViewState

| 元信息 | 值 |
|---|---|
| 状态 | [x] 已完成 |
| 依赖 | S4-T1 |
| 涉及文件 | `interfaces/tui/commands.py`, `interfaces/tui/view_state.py`, `tests/test_tui_commands.py`, `tests/test_tui_view_state.py` |
| 目标 | 建立与 Textual 无关的命令解析与不可变状态转换 |

* 先写测试：`test_parse_task_command_with_goal`、`test_parse_use_command`、`test_unknown_command_returns_structured_error`、`test_plain_text_creates_task_when_no_active_task`、`test_plain_text_answers_when_waiting_input`、`test_plain_text_is_rejected_during_normal_idle`、`test_view_state_reducer_preserves_event_order`、`test_view_state_caps_event_buffer`。
* Slash 命令 MVP：`/help /task /tasks /use /run /resume /status /trace /artifacts /open /rollback /clear /quit`。
* 普通文本语义：无 active task → 创建并运行；WAITING_INPUT → answer + resume；其他 idle → 结构化拒绝，不作为追加 Prompt。
* 完成判定：命令语义可完全用普通单元测试验证；事件缓存上限（500）生效。

实际验证（2026-07-21）：

* Red：新增两个测试模块后收集期 `ModuleNotFoundError: hancode.interfaces.tui.commands / view_state`。
* Green：新增 `commands.py`（`parse_command` 返回 `TuiCommand | TuiCommandError`，`shlex` 拆分、空/未知/缺参/多参/引号包裹/长度上限校验；`classify_plain_text` → `CREATE_TASK / ANSWER / REJECT`）与 `view_state.py`（冻结 `TuiViewState` + 纯 reducer，事件缓存上限 500、丢最旧不动 trace 文件）。专项 `16 passed`。
* 门禁：`ruff` 通过；`mypy src` 68 源文件无问题。CommandParser 不执行任何业务操作。Commit 待用户决定。

#### S4-T5：主界面与实时运行

| 元信息 | 值 |
|---|---|
| 状态 | [x] 已完成 |
| 依赖 | S4-T2, S4-T3, S4-T4 |
| 涉及文件 | `interfaces/tui/controller.py`, `interfaces/tui/messages.py`, `interfaces/tui/app.py`, `interfaces/tui/widgets/{phase_bar,activity_log}.py`, `interfaces/tui/screens/main.py`, `tests/test_tui_controller.py` |
| 目标 | TaskList / PhaseBar / ActivityLog / DetailPanel / Composer 与后台 Worker |

* Textual Message：`TraceArrived / RunFinished / RunFailed / TaskSummaryChanged`。
* 先写测试：`test_selecting_task_refreshes_summary`、`test_run_disables_mutating_commands`、`test_trace_message_updates_activity_log`、`test_run_finished_refreshes_task_state`、`test_phase_bar_follows_task_summary`、`test_small_terminal_uses_compact_layout`（另含未知事件渲染、waiting/inconsistent 相位、app 端到端流式事件）。
* PhaseBar 只从 `TaskSummary`（`current_phase` + `status`）派生，不自行推进 phase；ActivityLog 每个 TraceEvent 独立成行，未知事件显示 `[phase] event_type status` 而非丢弃。
* 完成判定：运行 MockLLM Demo 时事件在运行结束前逐条出现。

实际验证（2026-07-21）：

* Red：新增 `tests/test_tui_controller.py` 后收集期 `ModuleNotFoundError: hancode.interfaces.tui.controller`。
* Green：新增 Textual 无关的 `TuiSessionController`（持有 `TuiViewState`，`can_mutate()` 单运行约束，`select_task`/`mark_running`/`on_trace`/`on_run_finished`）、纯派生的 `phase_bar.phase_cells` / `activity_log.format_event`、`messages.py`（4 个 Message），主屏加 `is_compact_width` 与真实 widget 布局，`app.py` 用后台线程 Worker + `_WorkerTraceObserver`（`call_from_thread` post message，绝不直接操作 widget）串起 composer→service→run。
* 专项 `TUI 全套 29 passed`，含一条 app 级端到端：`submit_input("Write the spec.")` → 后台 MockLLM run → 事件经 observer/message 流入 activity log、结束后 `busy=False`。
* 门禁：`ruff` 通过；`mypy src` 73 源文件无问题；全量 `pytest` 为 `1019 passed, 15 skipped`。Commit 待用户决定。

#### S4-T6：HITL 自动回答与恢复

| 元信息 | 值 |
|---|---|
| 状态 | [x] 已完成 |
| 依赖 | S4-T5 |
| 涉及文件 | `interfaces/tui/app.py`（`submit_answer` 编排）, `tests/test_tui_hitl.py` |
| 目标 | 完成 ask → pause → display → answer → resume 表现层编排 |

* 编排：`InteractionService.answer(...)` 成功后调用 `TaskService.run(..., resume=True, trace_observer=observer)`；不修改 S3 状态机；Headless CLI 仍保持 answer / resume 两步。
* 先写测试：`test_answer_uses_pending_interaction_id`、`test_answer_success_automatically_resumes_task`、`test_answer_failure_does_not_resume`、`test_secret_only_answer_is_rejected_without_echo`、`test_answer_confirmation_reports_length_not_content`、`test_answer_without_pending_interaction_is_noop`、`test_end_to_end_ask_answer_resume_writes_spec`。
* 完成判定：同一 TUI 会话内完成一次 ASK_USER 后继续写入 SPEC；提交后仅显示 `Answer submitted · N chars`，不回显正文。

实际验证（2026-07-21）：

* Red/Green：`submit_answer` 在 S4-T5 已随 app 落地；本任务补齐 7 条 HITL 断言。`answer` 成功→自动 `run(resume=True)`；`answer` 失败（含 stale id / secret-only）→不 resume；确认提示只显示 `Answer submitted · N chars`，通知与错误均不含 answer 正文；无 pending 时 no-op。
* 真实端到端：MockLLM 序列 `ask_user`（`interaction_mode=ask_user`）→ WAITING_INPUT → `submit_answer("Use FastAPI.")` → 自动 resume → `write_file` → `finish_phase`，最终 `SPEC.md` 落盘且含回答内容。
* 门禁：`ruff` 通过；`mypy src` 73 源文件无问题；HITL 专项 `7 passed`。Commit 待用户决定。

#### S4-T7：Artifact 与 Rollback 操作

| 元信息 | 值 |
|---|---|
| 状态 | [x] 已完成 |
| 依赖 | S4-T3, S4-T5 |
| 涉及文件 | `app/recovery_service.py`, `interfaces/tui/app.py`（rollback/artifact 编排）, `tests/test_recovery_service.py` |
| 目标 | `/artifacts`、`/open <name>`、`/rollback`（显式确认） |

* `RecoveryService.rollback_last(project_root, task_id) -> RecoverySummary`：reconcile → 校验 latest checkpoint → 取 mutation lock → 调用 `rollback_last_checkpoint` → 返回摘要；`preview_last` 从 checkpoint manifest 读取受影响文件。TUI 只调用该服务，确认信息只来源于 manifest。
* 先写测试：`test_rollback_requires_confirmation`、`test_cancelled_rollback_does_not_mutate_state`、`test_confirmed_rollback_executes`、`test_rollback_last_uses_rollback_manager`、`test_preview_last_reports_no_checkpoint`、`test_rollback_last_without_checkpoint_is_structured_error`。
* 完成判定：TUI 不直接调用 storage 模块；rollback 必须经用户确认。

实际验证（2026-07-21）：

* Red：新增 `tests/test_recovery_service.py` 后收集期 `ModuleNotFoundError: hancode.app.recovery_service`。
* Green：新增 `app/recovery_service.py`（`RecoveryService` + `RollbackPreview` + `RecoverySummary`）。`preview_last` 只从 manifest 读取 `files`/`rollback_available`；`rollback_last` 在共享 `FilesystemTaskMutationGuard` 下委托 `rollback_last_checkpoint`，非成功抛结构化错误。app 增加 `request_rollback`（预览+待确认）/`confirm_rollback`（执行+刷新 summary）/`cancel_rollback`，以及 `/rollback`、`/artifacts`、`/open <name>`（走 InspectionService）命令。
* 专项 `6 passed`；确认前不执行、取消不改状态、确认才委托 RollbackManager 均验证。
* 门禁：`ruff` 通过；`mypy src` 74 源文件无问题；全量 `pytest` 为 `1032 passed, 15 skipped`。Commit 待用户决定。

#### S4-T8：端到端测试与交付

| 元信息 | 值 |
|---|---|
| 状态 | [x] 已完成 |
| 依赖 | S4-T1~S4-T7 |
| 涉及文件 | `tests/test_tui_e2e.py`（另含 `tests/test_observed_trace.py` 已在 S4-T2 建立） |
| 目标 | 建立完整 MockLLM TUI 演示并完成全量门禁 |

* 场景：启动 TUI → 输入目标 → 创建 task → spec phase 请求澄清 → 用户回答 → 自动 resume → 写 SPEC → 完成 spec；随后以全新会话经 InspectionService 恢复完整 trace 并按 allow-list 预览产物。
* 验证：`pytest`、`ruff`、`mypy` strict、`uv build`、CLI smoke、TUI smoke、MockLLM TUI E2E。

实际验证（2026-07-21）：

* 新增 `tests/test_tui_e2e.py` 两条端到端：
  * `test_tui_full_ask_answer_resume_and_inspection`：`submit_input(目标)` → 创建并运行 → WAITING_INPUT（trace 已实时流入）→ `submit_answer` → 自动 resume → `SPEC.md` 落盘含 "FastAPI"；再用 `InspectionService.read_trace` 以全新会话恢复，`seq` 有序、含 `interaction_requested`/`interaction_answered`，且 answer 正文不出现在任何持久化 trace。
  * `test_tui_artifact_preview_after_completion`：完成后 `read_artifact("SPEC.md")` 经 allow-list 成功预览。
* 全量门禁：`ruff check src tests` 通过；`mypy src` 74 源文件无问题；全量 `pytest` 为 `1034 passed, 15 skipped`；`uv build` 成功且 wheel 含完整 `interfaces/tui/` 包；`hancode --help` 显示 `tui`；`hancode demo --provider mock` 返回 `completed`。构建产物已清理。
* 文档：`README.md` 新增「终端交互（TUI）」章节（`hancode tui` 用法、slash 命令、展示层边界、回答不回显），并把 TUI 从「已知限制」移出、仅保留 WebUI/Streaming 未实现；`tests/test_readme.py` 先补 `test_readme_documents_tui` 与 available-commands 断言（先红后绿）。全量回归 `1035 passed, 15 skipped`。Commit 待用户决定。

#### S4-R1：评审发现的产品交互收尾修复

| 元信息 | 值 |
|---|---|
| 状态 | [x] 已完成 |
| 依赖 | S4-T8 |
| 涉及文件 | `interfaces/tui/app.py`, `interfaces/tui/controller.py`, `interfaces/tui/commands.py`, `interfaces/tui/screens/main.py`, `tests/test_tui_command_exec.py`, `tests/test_tui_task_list.py`, `tests/test_tui_trace_restore.py`, `tests/test_tui_waiting_input.py`, `tests/test_recovery_service.py`, `tests/test_tui_controller.py`, `tests/test_tui_hitl.py` |
| 目标 | 修复独立评审发现的 6 项产品交互缺陷（原测试直接调 App 方法、绕过真实命令/输入路径导致漏网） |

评审背景：一份独立评审指出 S4 多处"用户可见能力只实现了服务或解析器，未真正接入 TUI"，且测试盲区（直调 App 方法而非走命令/Pilot 输入）掩盖了两个真实功能错误。本卡按评审优先级 1–6 逐项 TDD 修复。

* **R1-1 `/rollback confirm|cancel` 断链**：parser `"rollback"` 由 `(0,0)` 改为 `(0,1)`；`_handle_rollback` 分派 `confirm`/`cancel`/无参预览/未知子命令拒绝。补 4 条走 `submit_input("/rollback ...")` 真实路径的测试。
* **R1-2 空操作命令**：实现 `/help /tasks /status /trace /clear /quit`（原仅解析不执行）；`/clear` 清屏不动 trace 文件。
* **R1-3 TaskList 未接入**：`on_mount` 挂载回调 `_on_ready` 启动即 `refresh_tasks` 并填充 ListView；`on_list_view_selected` 绑定选择。**并修复关键缺陷**：app 内部 `self.query_one` 查不到 pushed screen 上的 widget（NoMatches 被吞），全部改为 `self.screen.query_one`，此前 activity/phase/detail/tasklist 更新其实从未真正到达 DOM。
* **R1-4 Trace 恢复/切换**：`TuiSessionController` 注入 `InspectionService`，`select_task` 先清空旧事件再 `read_trace` 恢复目标任务 trace（不同任务事件不再混流；也是"重启恢复历史"的真实路径）。
* **R1-5 WAITING_INPUT 展示**：run 结束进入 WAITING_INPUT 时把问题渲染到 DetailPanel、Composer placeholder 改为提示回答并聚焦；非等待态复位 placeholder。
* **R1-6 Worker 终态兜底**：`_body` 增补 `except Exception` → post 脱敏的 `tui_internal_error` `RunFailed`，保证 `busy` 一定被清除、原始异常不泄漏；此前非 HanCodeError 会让 Worker 崩溃并永久卡 busy。

实际验证（2026-07-21）：

* 每项先补"走真实命令/Pilot 输入"的红测试再实现；新增 18 个测试（command_exec 5、task_list 3、trace_restore 3、waiting_input 2、rollback 命令链 4、worker 兜底 1）。
* HITL fake 因新增启动加载补 `list_tasks`；task_list 测试查询改用 `app.screen.query_one`。
* 门禁：`ruff` 通过；`mypy src` 74 源文件无问题；全量 `pytest` 为 `1053 passed, 15 skipped`。
* 剩余（评审 7–9，非阻塞，未纳入本卡）：`AgentRunResult.error/risks` 展示、阻塞型 FS 操作移入 Worker、rollback preview→confirm 竞态（`expected_checkpoint_id`）、compact layout 实际切换、真实 Pilot 键盘输入端到端、textual 主版本上界锁定。Commit 待用户决定。

#### S4-R1.1：评审发现的状态刷新与恢复边界补完

| 元信息 | 值 |
|---|---|
| 状态 | [x] 已完成 |
| 依赖 | S4-R1 |
| 涉及文件 | `interfaces/tui/app.py`, `interfaces/tui/controller.py` |
| 目标 | 补完评审中判定为"部分完成"的 4 项交互闭环 |

评审回顾：`S4-R1` 完成后独立评审判定 6 项中 `#1 /rollback` 和 `#6 Worker 清理` 通过，其余 4 项存在残留缺口。本卡补完：

* **R1.1-1 `/status` 刷新**：`_show_status` 不再读缓存 `active_task`，改为通过 `TaskService.get()` 获取最新状态，更新 Controller 状态、刷新 PhaseBar 并调用 `_reflect_waiting_input()`。
* **R1.1-2 TaskList 生命周期同步**：统一方法 `_refresh_task_list_data()`（数据 + 组件）在 `_create_and_run`（新建）和 `confirm_rollback`（回退后）调用；`_refresh_task_list_data_only()`（仅数据，避免 Textual `pilot.pause` 超时）在 `on_run_finished` 和 `on_run_failed` 调用。
* **R1.1-3 选择 WAITING_INPUT Task 触发响应**：`_select()` 调用 `_reflect_waiting_input()`，使跨 Task 切换至已有 `WAITING_INPUT` 状态的任务时正确展示问题、设置 placeholder 和焦点。
* **R1.1-4 Trace 分页恢复**：`TuiSessionController._restore_trace()` 从单次 `read_trace(limit=200)` 改为分页循环（每页 500），收集全部事件后截取最新 `MAX_EVENT_BUFFER`（500）条，避免重启后只恢复前 200 条的问题。

实际验证（2026-07-21）：

* 不新增测试（已有覆盖足够验证 4 项行为）；全量回归无新增失败。
* 门禁：全量 `pytest` 为 `1053 passed, 15 skipped`。

### S4.8 S4 验收标准

**功能**：`hancode tui` 可启动；可创建/选择/运行/恢复 Task；实时展示 TraceEvent 与六阶段状态；展示 tool/test/checkpoint/rollback/risk；WAITING_INPUT 显示问题并可自动 resume；可查看允许的产物；可执行受控 rollback；重启后可恢复 Task 与历史 Trace。

**边界**：TUI 不直接调用 LLM / 执行工具 / 读写 State / 修改 Trace / 调用 RollbackManager；Headless CLI 的 JSON 输出与行为兼容；MockLLM 仍可离线运行；ProviderAdapter 不依赖 Textual。

**安全**：Trace 持久化成功后才进入 UI；answer 正文不回显；credential 不进入界面；Artifact Preview 固定 allow-list；用户文本不能注入终端 markup；Observer 失败不影响 AgentLoop；无 shell passthrough；运行中不强杀 Worker。

**测试**：CommandParser、ViewState reducer、Observer 顺序与容错、InspectionService 安全、HITL TUI 端到端测试全部通过；全量现有测试无回归；Ruff、MyPy strict、package build 通过。

### S4.9 非目标 / 边界

* 不修改 AgentLoop / ProviderAdapter / ToolPolicy / Checkpoint / Trace / State 业务逻辑。
* 不改变 trace JSONL、state JSON schema version、checkpoint manifest schema 或现有 CLI 命令语义。
* 不实现多 Task 并行、流式 Token、自由聊天、任意 Shell、代码编辑器、WebUI、远程执行、强制取消。
* 不引入外部 Agent Framework（OpenCode Loop / Aider / LangChain AgentExecutor / AutoGen / CrewAI）充当交付内核；仅复用 Textual 的布局、键盘事件、后台任务与渲染能力。

---

# 8. 需求→任务追溯

| SPEC 锚点                                  | 对应任务                         | 状态  |
| ---------------------------------------- | ---------------------------- | --- |
| FR-1 AgentLoop 主循环                       | T10, T21                     | [x] |
| FR-2 LLM 抽象与 MockLLM                     | T9, T23                      | [x] |
| FR-3 Action 解析与校验                        | T7, T8                       | [x] |
| FR-4 ToolRegistry 与工具分发                  | T11, T12                     | [x] |
| FR-5 ToolPolicy 治理护栏                     | T13, T14, T15                | [x] |
| FR-6 ContextBuilder 与记忆选择                | T19, S13-R3                  | [~] |
| FR-7 反馈回灌机制                              | T20, T21                     | [x] |
| FR-8 TraceLogger                         | T16                          | [x] |
| FR-9 配置加载与运行约束                           | T3, T26, S13-R1              | [~] |
| FR-10 Project Workspace 与 Task Workspace | T2, S13-R1                   | [~] |
| FR-11 课程项目 Phase Gate                    | T5, T6                       | [x] |
| FR-12 课程项目上下文构造                          | T19                          | [x] |
| FR-13 课程文件保护策略                           | T13, T14, T15                | [x] |
| FR-14 Checkpoint 与 Rollback              | T17, T18, T21                | [x] |
| FR-15 测试报告与审查记录                          | T20, T22                     | [x] |
| FR-16 Knowledge Delivery                 | T22, T23                     | [x] |
| FR-21 Task-scoped Persistent Runtime Memory | S13-R1-R5                 | [~] |
| 凭据与分发设计                                  | T25, T26, T27                | [x] |
| 可测试性约定                                   | T1-T30, S13-R1-R5            | [~] |
| 测试失败分类                                   | T20                          | [x] |
| 危险动作与治理护栏                                | T13, T14, T15                | [x] |
| 记忆与上下文机制                                 | T2, T19, S13-R1-R5           | [~] |
| 主贡献维度                                    | T16-T21, T23, S13-R1-R5      | [~] |
| MockLLM 机制演示                             | T9, T21, T23, S13-R5         | [~] |
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

反馈与回退闭环优先顺序（S13 前基线）：

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

---

## S3-R：人工审批协议

| 元信息           | 值                                      |
| ------------- | -------------------------------------- |
| 状态            | [x] 已完成 (S3-R1~S3-R4)              |
| 依赖            | ASK_USER、Task 持久化、AgentLoop、ToolPolicy、Checkpoint、Trace |
| 分支           | 当前基线上直接实现                     |
| 主贡献相关         | 是；审批安全机制                        |

### S3-R1：Approval 模型、状态与配置

状态：`[x]`

涉及文件：
- `core/approvals.py`（新增）—— ApprovalStatus, ApprovalCategory, ApprovalTarget, ApprovalActionSnapshot, ApprovalPreview, ApprovalRecord
- `core/models.py` —— 新增 TaskStatus.WAITING_APPROVAL
- `core/state.py` —— 新增 approval_seq / pending_approval_id
- `core/config.py` —— 新增 approval_mode / confirm_agent_rollback / max_approvals_per_phase 等
- `core/router.py` —— WAITING_APPROVAL 阻塞路由
- `app/task_models.py` —— TaskSummary 新增 requires_approval / pending_approval

测试：`tests/test_approval_model.py` —— 24 passed

### S3-R2：ApprovalPolicy、Preview 与 Store

状态：`[x]`

涉及文件：
- `policy/approval_policy.py`（新增）—— ApprovalPolicy 与 ApprovalRequirement
- `runtime/approval_request.py`（新增）—— ApprovalRequestBuilder（Diff Preview + 敏感检测）
- `storage/approvals.py`（新增）—— ApprovalStore（原子持久化 + 生命周期）

测试：`tests/test_approval_policy.py` —— 20 passed

### S3-R3：AgentLoop 审批门控与恢复

状态：`[x]`

涉及文件：
- `runtime/agent_loop.py` —— 插入 Approval Gate（Policy 后、Checkpoint 前）；WAITING_APPROVAL resume；批准后直接执行原 Action 不调用 Provider

### S3-R4：ApprovalService 与 Headless CLI

状态：`[x]`

涉及文件：
- `app/approval_service.py`（新增）—— approve / reject / get_pending（幂等 + 冲突检测 + Task Guard）
- `interfaces/cli.py` —— `task approval` / `task approve` / `task reject` 命令；`task status` 输出审批信息

### S3-R5：TUI Approval UX

状态：`[x]`

涉及文件：
- `interfaces/tui/commands.py` —— `/approve`、`/reject` 命令；等待批准时明文输入判定为 `APPROVAL_REQUIRES_COMMAND`
- `interfaces/tui/view_state.py` —— 新增 `pending_approval_id` / `pending_approval_summary` 与 reducer
- `interfaces/tui/app.py` —— `submit_approval` / `submit_rejection`（决策后自动 resume）、`_reflect_waiting_approval` 面板

测试：`tests/test_tui_approval.py`（7）+ `tests/test_tui_commands.py` 新增（5）

### S3-R6：E2E / Recovery / Security 验收

状态：`[x]`

涉及文件（缺陷修复）：
- `runtime/agent_loop.py` —— `_inconsistent()` helper 统一清 pending 双指针；`_mark_inconsistent` 补清 `pending_approval_id`；持久化的 EXECUTING manifest 恢复时失败关闭并落盘
- `app/approval_service.py` —— 幂等短路（重复同向决策返回成功）

测试：`tests/test_approval_security.py`（4）、`tests/test_approval_recovery.py` 新增（2）、`tests/test_approval_service.py`（7）、`tests/test_cli_approval.py`（5）；E2E 见 `tests/test_approval_e2e.py`

### 核心安全约束（已保证）

- ToolPolicy deny 不能被人工批准绕过
- 审批发生在任何副作用（checkpoint、文件写入）之前
- 批准绑定精确 Action（sha256 digest）
- 批准后不重新调用 Provider，直接执行原 Action
- 默认 approval_mode=disabled，不破坏现有 MockLLM 测试行为
- approval 与 ASK_USER 不共享状态模型

### 验证

- 全量 pytest: 1141 passed, 15 skipped（R1–R6 全部接线后）
- 新增测试: R1 model(24) + R2 policy/store(20) + R3 E2E/resume-guards/recovery + R4 service(7)/CLI(5) + R5 TUI(7)/commands(5) + R6 security(4)/recovery(2)
- Ruff `All checks passed!`；MyPy `Success: no issues found in 79 source files`
- 现有 ASK_USER、rollback、TUI 测试无回归

---

# S4：统一交付流程与受控开发工具

| 元信息           | 值                                      |
| ------------- | -------------------------------------- |
| 状态            | [x] 已完成（正式运行链路、安全边界、离线 E2E 与质量门禁通过） |
| 依赖            | AgentLoop、ToolPolicy、Checkpoint、Trace、Feedback、S3-R Approval |
| 分支           | 当前分支                                   |
| 主贡献相关         | 是；统一交付流程                               |

S4 阶段目标是把 HanCode 当前分散的测试执行、测试反馈、Checkpoint、Rollback、交付物生成、DeliveryResult 和 Artifact Export 收敛为一条统一、确定性、可观察的正式运行路径。

核心原则：
- Diff 不依赖 Git；
- Build 不能执行模型提供的任意命令；
- 测试和 Build 结果必须来自真实 ToolResult；
- 交付状态不能由 DemoRunner 或 TUI 手工推进；
- 所有入口共用相同的 Application Service 和 DeliveryPipeline。

---

## S4-R0：需求与架构契约

| 元信息           | 值          |
| ------------- | ---------- |
| 状态            | [x] 已完成    |
| 依赖            | S3-R 全部完成  |
| 可并行           | 不并行；文档前置任务 |
| Worktree / PR | 当前分支       |

### 目标

在 SPEC.md / PLAN.md / 系统架构.md 中建立 S4 阶段的需求基线和实现契约。

### 涉及文件

- `docs/SPEC.md` —— 新增 UR-8、FR-18、FR-19、FR-20
- `docs/PLAN.md` —— 新增 S4 里程碑与 S4-R0~R6 任务卡
- `docs/系统架构.md` —— 更新架构分层与组件图
- `docs/SPEC_PROCESS.md` —— 记录 S4 设计决策

### 完成标准

- Diff 明确不依赖 Git
- Build 明确只能来自配置
- Demo 和正式任务共用 DeliveryService
- 确定性 Artifact 与模型 Artifact 边界明确

---

## S4-R1：Checkpoint Query 与 `get_diff`

| 元信息           | 值          |
| ------------- | ---------- |
| 状态            | [x] 已完成    |
| 依赖            | S4-R0      |
| 可并行           | 可与 R2、R3 并行 |
| Worktree / PR | 当前分支       |

### 目标

建立统一的 Checkpoint Query Repository，使 RecoveryService、ChangeInspectionService、list_checkpoints tool 和 TUI 共用同一套校验逻辑。实现基于 checkpoint 快照的 `get_diff`，不依赖 Git。

### 涉及文件

- `core/change_models.py`（新增）—— ChangeType, DiffScope, FileDiff, TaskDiff
- `storage/checkpoint_queries.py`（新增）—— CheckpointQueryRepository
- `tooling/diff_tools.py`（新增）—— get_diff 工具实现
- `app/change_inspection_service.py`（新增）—— ChangeInspectionService

### 预期测试

- `test_checkpoint_query_sorts_manifests`
- `test_checkpoint_query_rejects_wrong_task`
- `test_checkpoint_query_rejects_symlink`
- `test_diff_modified_file`
- `test_diff_created_file`
- `test_diff_deleted_file`
- `test_task_diff_uses_earliest_baseline`
- `test_latest_diff_uses_latest_checkpoint`
- `test_diff_marks_workspace_drift`
- `test_diff_redacts_secrets`
- `test_diff_skips_binary_content`
- `test_diff_is_bounded`
- `test_diff_does_not_require_git`

---

## S4-R2：`run_build`

| 元信息           | 值          |
| ------------- | ---------- |
| 状态            | [x] 已完成    |
| 依赖            | S4-R0      |
| 可并行           | 可与 R1、R3 并行 |
| Worktree / PR | 当前分支       |

### 目标

实现 `run_build` 工具，命令只能来自 `config.build_command`，模型不得传入任意命令。抽取 `command_runner.py` 供 `run_tests` 和 `run_build` 共用。

### 涉及文件

- `tooling/command_runner.py`（新增）—— run_configured_command
- `tooling/build_tools.py`（新增）—— run_build 工具
- `app/build_service.py`（新增）—— BuildService
- `core/config.py` —— 新增 max_diff_* 配置（已在 R1 使用）
- `core/state.py` —— 新增 builds_run / latest_build_status 字段

### 预期测试

- `test_build_uses_configured_command`
- `test_build_rejects_missing_command`
- `test_build_uses_shell_false`
- `test_build_uses_project_root`
- `test_build_times_out`
- `test_build_redacts_output`
- `test_build_truncates_output`
- `test_agent_build_requires_approval`
- `test_build_does_not_change_test_status`
- `test_configured_build_is_delivery_gate`

---

## S4-R3：`read_test_report`

| 元信息           | 值          |
| ------------- | ---------- |
| 状态            | [x] 已完成    |
| 依赖            | S4-R0, 现有 InspectionService |
| 可并行           | 可与 R1、R2 并行 |
| Worktree / PR | 当前分支       |

### 目标

实现 `read_test_report` 工具，提供受控、脱敏、有限长度的测试摘要。`run_tests` 完成后自动生成 `TEST_REPORT.md`。

### 涉及文件

- `app/delivery_inspection_service.py`（新增）—— 结构化解析 TEST_REPORT
- `tooling/delivery_tools.py`（新增）—— read_test_report 工具
- `runtime/agent_loop.py` —— run_tests 后自动触发 DeliveryPipeline.record_test

### 预期测试

- `test_run_tests_generates_test_report`
- `test_read_test_report_requires_declared_artifact`
- `test_read_test_report_rejects_link`
- `test_read_test_report_is_redacted`
- `test_read_test_report_is_bounded`
- `test_read_test_report_returns_structured_counts`

---

## S4-R4：`list_checkpoints`

| 元信息           | 值          |
| ------------- | ---------- |
| 状态            | [x] 已完成    |
| 依赖            | S4-R1 Checkpoint Query |
| 可并行           | 可与 R2、R3 并行 |
| Worktree / PR | 当前分支       |

### 目标

实现 `list_checkpoints` 工具和 `CheckpointInspectionService`。让 RecoveryService 复用 Checkpoint Query Repository 而非自行解析 manifest。

### 涉及文件

- `app/checkpoint_inspection_service.py`（新增）
- `tooling/checkpoint_tools.py`（新增）
- `app/recovery_service.py` —— 改用 CheckpointQueryRepository

### 预期测试

- `test_list_checkpoints_returns_validated_summaries`
- `test_list_checkpoints_hides_snapshot_paths`
- `test_list_checkpoints_rejects_corrupt_manifest`
- `test_list_checkpoints_is_task_scoped`
- `test_recovery_preview_uses_checkpoint_query`

---

## S4-R5：DeliveryPipeline 与 DeliveryService

| 元信息           | 值          |
| ------------- | ---------- |
| 状态            | [x] 已完成    |
| 依赖            | S4-R1~R4   |
| 可并行           | 不并行       |
| Worktree / PR | 当前分支       |

### 目标

实现统一 `DeliveryPipeline`，使 `TEST_REPORT.md`（自动）、`REVIEW.md`（结构化工具）、`KNOWLEDGE.md`（结构化工具）和 `DELIVERABLES.md`（finalize 自动）均由权威路径生成。扩展 `DeliveryService` 为完整交付入口。

### 涉及文件

- `core/delivery_evidence.py`（新增）—— DeliveryEvidence 模型
- `storage/delivery_evidence.py`（新增）—— DeliveryEvidenceStore
- `runtime/delivery_pipeline.py`（新增）—— DeliveryPipeline
- `tooling/delivery_tools.py` —— record_review / record_knowledge
- `app/delivery_service.py` —— 扩展为完整服务
- `core/phases.py` —— Deliver phase 完成条件调整
- `policy/tool_policy.py` —— 新工具的阶段权限

### 预期测试

- `test_test_report_is_generated_from_real_tool_result`
- `test_raw_write_cannot_forge_test_report`
- `test_record_review_requires_core_coverage`
- `test_record_review_writes_review_and_evidence`
- `test_record_knowledge_requires_all_categories`
- `test_record_knowledge_requires_trace_provenance`
- `test_finalize_generates_deliverables`
- `test_finalize_requires_passing_tests`
- `test_finalize_requires_build_when_configured`
- `test_finalize_requires_non_drifted_diff`
- `test_finalize_is_idempotent`
- `test_delivery_failure_marks_inconsistent_when_compensation_fails`

### 回归修复验证（2026-07-22）

- 根因：S4-R5 管线仍接收旧 `delivery_support` 模型，但旧模型缺少 S4 使用的 `NOT_COVERED`、扩展知识分类和可选溯源字段；管线转换知识分类时又将枚举错误降为字符串，且 `finalize` 未经受控写入路径生成 `DELIVERABLES.md`。
- 修复：补齐兼容模型边界；在 `DeliveryPipeline.finalize()` 中将知识分类转换为 `core` 枚举并通过 `_write_artifact()` 生成/登记 `DELIVERABLES.md`。
- 验证：`python -m pytest tests/test_s4_delivery_e2e.py -q -p no:cacheprovider` 为 `15 passed`；交付/Demo/App/E2E 回归为 `52 passed`；全量 pytest 为 `1213 passed, 17 skipped`；全量 MyPy 为 `94 source files` 无错误；本次修改文件的 Ruff 检查通过。全仓 Ruff 仍受其他未提交 S4 测试文件中的 12 个未使用导入/变量告警阻塞，未在本修复中扩大范围处理。

---

## S4-R6：ToolSpec、CLI、Demo 与 E2E

| 元信息           | 值          |
| ------------- | ---------- |
| 状态            | [x] 已完成    |
| 依赖            | S4-R1~R5   |
| 可并行           | 不并行       |
| Worktree / PR | 当前分支       |

### 目标

建立 ToolSpec 单一真源；接入 Headless CLI 查询入口；收敛 DemoRunner 到统一交付路径；完成 MockLLM E2E 验收。

### 涉及文件

- `core/tool_specs.py`（新增）—— ToolSpec 定义
- `core/actions.py` —— 使用 ToolSpec
- `tooling/factory.py` —— 注册新工具
- `interfaces/cli.py` —— 新增 diff/checkpoints/test-report/build/delivery 命令
- `demo_support/runner.py` —— 收敛到 DeliveryPipeline
- `README.md` —— 更新工具列表

### 预期测试

- `test_action_schema_matches_provider_catalog`
- `test_new_tools_are_registered`
- `test_new_tools_have_correct_phase_policy`
- `test_cli_diff_uses_change_service`
- `test_cli_build_uses_build_service`
- `test_cli_checkpoints_uses_inspection_service`
- `test_demo_does_not_call_delivery_writers_directly`
- `test_demo_uses_task_service`
- `test_mock_e2e_generates_delivery_result`

---

## S4 依赖关系

```
S4-R0 文档契约
      |
      v
Checkpoint Query Core
      |
      +---------------+
      v               v
S4-R1 Diff        S4-R4 Checkpoints

S4-R2 Build       S4-R3 Test Report
      \               /
       \             /
        v           v
        S4-R5 DeliveryPipeline
                 |
                 v
        S4-R6 CLI / Demo / E2E
```

可并行：R1、R2、R3；R4 依赖 R1；R5 依赖 R1~R4；R6 最后进行。

---

## S4 完成标准

- [x] `get_diff` 不依赖 Git
- [x] Task Diff 使用最早 checkpoint baseline
- [x] Diff 检测 workspace drift
- [x] Diff 内容不进入 Trace
- [x] `run_build` 只能执行配置命令
- [x] `run_build` 使用 shell=False
- [x] Agent Build 默认需要审批
- [x] 测试完成后自动生成 TEST_REPORT
- [x] `list_checkpoints` 使用统一校验层
- [x] RecoveryService 不再自行解析 manifest
- [x] REVIEW 通过结构化 evidence 生成
- [x] KNOWLEDGE 通过结构化 evidence 生成
- [x] DELIVERABLES 自动生成
- [x] DeliveryResult 来自权威 state/trace/evidence
- [x] DemoRunner 不直接调用交付 writer
- [x] CLI、TUI、Demo 共用 Application Service
- [x] MockLLM E2E 完全离线通过
- [x] 原有 Approval、ASK_USER、Rollback 无回归
- [x] Pytest、Ruff、MyPy、Build 全部通过
- [x] SPEC、PLAN、架构和 SPEC_PROCESS 已同步

---

## S4-R7：评审阻断修复与正式运行闭环

| 元信息           | 值 |
| ------------- | --- |
| 状态            | [x] 已完成（评审阻断修复、正式 AgentLoop 闭环与最终门禁通过） |
| 依赖            | S4-R1~R6 |
| 可并行           | 分批串行；每批先补回归测试 |
| Worktree / PR | 当前分支 |
| 边界            | 只修复 S4-R 评审列出的工具接线、AgentLoop 交付闭环、交付物真实性、证据持久化和 checkpoint/diff/report/CLI 安全边界 |

### 目标

将 S4 新工具从 Provider Catalog 真实接入 `ActionParser -> ToolPolicy -> ApprovalPolicy -> ToolRegistry -> AgentLoop`；使 `run_tests`、`run_build`、review/knowledge evidence 和 finalize 由正式任务路径驱动；同时阻止通用写工具伪造确定性交付物，并对 checkpoint、diff、test report、evidence 的读取与持久化执行 fail-closed 校验。

### 涉及文件

- `src/hancode/core/actions.py`
- `src/hancode/core/tool_specs.py`
- `src/hancode/policy/tool_policy.py`
- `src/hancode/policy/approval_policy.py`
- `src/hancode/tooling/factory.py`
- `src/hancode/runtime/agent_loop.py`
- `src/hancode/runtime/delivery_pipeline.py`
- `src/hancode/app/build_service.py`
- `src/hancode/core/router.py`
- `src/hancode/storage/delivery_evidence.py`
- `src/hancode/storage/checkpoint_queries.py`
- `src/hancode/tooling/diff_tools.py`
- `src/hancode/tooling/delivery_tools.py`
- `src/hancode/demo_support/runner.py`
- `src/hancode/interfaces/cli.py`
- `tests/test_s4_review_remediation.py`

### 预期失败测试

- S4 工具在 Parser、ToolSpec、Policy、Registry、Provider Catalog 间保持一致。
- AgentLoop 执行 `run_tests` 自动写入 `TEST_REPORT.md`。
- AgentLoop 执行 `run_build` 持久化 Build 状态并遵守审批。
- `record_review` / `record_knowledge` 跨 Pipeline 实例和跨 Task 隔离。
- finalize 对 test/build/diff/review/knowledge 执行交付门并返回正式交付结果。
- 通用 `write_file` / `edit_file` 拒绝四类确定性交付物。
- checkpoint snapshot 越界、损坏 evidence、report 脱敏/超限均 fail-closed。
- Demo 通过正式 AgentLoop/DeliveryService 路径完成离线交付。

### 完成标准

- 新工具不存在 Catalog、Parser、Policy、Registry 任一断线。
- `run_tests -> TEST_REPORT` 和 `run_build -> state/trace/evidence` 在正式 AgentLoop 中可重复验证。
- DeliveryPipeline 不依赖进程内 accumulator；finalize 不绕过交付门，不以失败测试伪造 completed。
- 四类确定性交付物不能由通用文件工具写入。
- checkpoint、diff、report、evidence 对路径、身份、大小、敏感内容和损坏输入 fail-closed。
- Provider -> AgentLoop -> Delivery 的离线 E2E、Pytest、Ruff、MyPy、Build 均通过。

### 实现与验证记录（2026-07-22）

- 正式 AgentLoop 在真实 `run_tests` 后生成 `TEST_REPORT.md`，在真实 `get_diff` 后持久化 Diff digest，并在 `record_review`、`record_knowledge`、finalize 后写入交付 trace 事件。
- Demo action 序列改为通过 MockLLM 驱动 `record_review`、`get_diff`、`record_knowledge` 和 `finish_phase`，移除 Runner 手工推进 Deliver phase、手工写交付证据和手工 finalize。
- 补齐 `DeliveryPipelinePort.record_diff`、BuildService policy decision、Diff drift fail-closed、snapshot 大小上限前置检查，以及对应回归测试。
- 专项 `tests/test_s4_delivery_e2e.py tests/test_mock_demo.py tests/test_s4_review_remediation.py`：基线为 `40 passed`；审批/恢复、CLI Build、Evidence 安全和二进制 drift follow-up 后历史记录为 `64 passed`；本轮包含 Diff 回归的实际专项命令为 `56 passed`。
- 全量 `pytest -q -p no:cacheprovider`：`1236 passed, 17 skipped`。
- `ruff check src tests --no-cache`：`All checks passed!`；`mypy src`：`94 source files` 无错误；`uv build` 成功生成 sdist 与 wheel。
- 审批后的 `run_build` / source write 统一执行 state 后处理；CLI Build 通过 `DeliveryService.record_build()` 写入 Evidence；Demo 最终返回持久化 core `DeliveryResult`。
- Structured Evidence 统一执行敏感内容脱敏、字段截断、条目数量限制和 `source_trace_id` 边界校验；二进制 Diff 使用 bounded bytes 计算 drift hash。
- 普通 source write 不再重复注入 checkpoint 管理器已写入的 trace 事件，避免 Demo 分 stage 逻辑序号与持久化 trace 序列冲突；审批恢复仍保留必要的外部 trace 同步。
- 未使用真实网络、凭据或第三方 Agent 框架；基线提交为 `f0f8989`，本轮 follow-up 改动尚未提交。
- GitHub Actions 尚无本轮独立 run 证据；本地质量门与 Windows 平台既有 skip 需与远端 CI 分开记录。

### 缺陷修复记录（2026-08-03）— 交付阻塞后 blocked 分支复写旧状态

- 现象：交付阶段任务被门禁判定 BLOCKED 后，磁盘存在 `DELIVERABLES.md`，但 `state.json` 的 `artifacts["DELIVERABLES.md"]` 仍为 `false`、`delivery_coverage_digest` 为 `null`，随后 trace 记录 `state_inconsistent`。
- 直接阻塞原因：存在 Checkpoint 但缺少最新 Diff 证据（`delivery/evidence.json` 的 `latest_diff_sha256` 为 `null`），交付门禁返回 BLOCKED。
- 代码缺陷根因：`AgentLoop` 的 DELIVER `FINISH_PHASE` blocked 分支用旧的 in-memory `state` 调用 `_block()`，把 `DeliveryPipeline.finalize()` 经 `_write_artifact` 已持久化的交付状态复写回旧值，造成文件与 `state.json` 漂移。
- 修复：两个 blocked 分支（异常分支与 `delivery_status is not COMPLETED` 分支）在 `_block()` 前先 `state = self._state_store.load(task_id)` 重新加载权威状态，与成功分支已有行为对齐。
- 回归测试：`test_deliver_finalize_blocked_preserves_persisted_delivery_state`（单元级）与 `test_deliver_finalize_blocked_no_diff_keeps_state_consistent`（集成级，真实 Pipeline + 真实已提交 checkpoint）均先红后绿。
- 验证：相关套件 `141 passed, 5 skipped`；全量 pytest `1467 passed, 17 skipped`；Ruff `All checks passed!`；`mypy src` `130 source files` 无错误。
- 未改变 `_delivery_blockers` 门禁判定；解除直接阻塞仍需模型在交付前成功执行 `get_diff`。

### 缺陷修复记录（2026-08-04）— remediation planned_paths 跨文件修复死锁

- 现象：task-003 测试失败进入 REVIEW，模型 `record_remediation(kind=modify_test, planned_paths=[.hancode/tests/interaction.test.js])` 后回 CODE 修复；模型发现真实 `index.html` 缺少 `#back-to-top` 按钮需补充，但每次 `edit_file index.html` 均被策略 `remediation_planned_path_required` 拒绝（"写目标不在 remediation planned_paths"），且 `record_remediation` 仅在 REVIEW 阶段可用，模型在 CODE 阶段无法扩展修复范围，陷入死循环。
- 代码缺陷根因：`record_remediation` 的 `allowed_phases=frozenset({Phase.REVIEW})`，导致 CODE 阶段无法重新声明 remediation 范围；`remediation_planned_path_required` 策略又严格锁定写操作于已声明 `planned_paths`，跨文件修复被永久阻断。
- 修复：`src/hancode/core/tool_specs.py` 中 `record_remediation` 的 `allowed_phases` 扩展为 `{Phase.REVIEW, Phase.CODE}`。`AgentLoop` 的 record_remediation 处理本身阶段无关（更新 `latest_remediation_digest`、重置 CODE 完成标记），`tool_policy` 的 `active_test_failure_required` 检查（必须有 failed 测试）防止滥用。模型在 CODE 阶段可用 `modify_source` 重新声明含源文件的 `planned_paths` 自救。
- 回归测试：`test_record_remediation_allowed_in_code_phase_when_test_failed`（CODE 阶段 record_remediation 通过 policy）；更新 `test_allowed_tools_for_phase_returns_sorted_policy_matrix` 的 CODE 允许工具断言。
- 验证：`test_tool_policy.py` 61 passed；action_schema/prompt/tool_factory/remediation 相关套件 178 passed；全量 pytest `1588 passed, 17 skipped`；Ruff `All checks passed!`；`mypy src` `135 source files` 无错误。
- 注意：`modify_test` 只接受 test 路径；要改 `index.html` 需用 `modify_source`（允许任意 SOURCE 路径）。该修复仅提供"自救能力"，task-003 当前仍卡在 CODE，需 resume 后由模型实际重新声明 remediation 才能继续。
- 契约引导增强（同日实施）：`src/hancode/providers/prompt_contract.py` 的 REVIEW 契约提示模型在 `record_remediation` 时一次性声明 `planned_paths` 覆盖所有将修改的文件（源码/测试/标记语言），因同一阶段内无法再扩展；CODE 契约提示修复时只写 `planned_paths` 内文件，若需跨文件可重新 `record_remediation` 扩展。验证：providers/tool_policy/phases/context_builder/tool_factory/action_schema 相关套件 258 passed。

### 非目标 / 边界

- 不引入真实网络 LLM、真实凭据或新的第三方 Agent 框架。
- 不重写既有 Checkpoint/Rollback 生命周期，只补 S4 查询和交付边界。
- 不修改与本评审无关的历史兼容入口或 UI 视觉行为。
---
## S5 总体状态

| 状态 | `[x]` 核心 TUI 产品能力、Approval 查询竞态、Delivery Gate 展示、Rollback 确认绑定与最终集成验证已完成；无独立远端 CI run 证据 |

本轮审查发现的三个 P0 已分别由 Query 顺序、只读 `DeliverySummary` 和 `expected_checkpoint_id` 绑定修复；P1 的 Mutation Worker 全面化、Detail 滚动、Recent Trace 查询和 App 进一步拆分不纳入本轮修复范围。

---

## S5-R0：TUI Intent/Operation 契约与 App 瘦身

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已完成（返工后） |
| 依赖 | S4-R7 |
| Worktree / 分支 | `main`（按用户要求不在阶段中提交） |
| 边界 | 收口 Intent/Operation、Controller/Executor 和 Worker 结果协议；S5-R1~R6 的产品化视图与端到端功能另行推进 |

### 交付内容

- 新增 `src/hancode/interfaces/tui/operations.py`，冻结 `TuiIntent`、`TuiOperation`、`TuiOperationResult`、`TuiOperationError` 和 `TuiOperationExecutor`。
- `TuiSessionController` 负责 Intent 校验、request ID、busy guard、结果应用和过期结果丢弃；Application Service 由 Executor 注入和调用。
- `HanCodeTuiApp` 的创建、运行、交互、审批、回退、状态和 Artifact 操作均通过 Controller/Executor 边界；Worker 只执行 Operation，并发布带完整 request context 的 `OperationFinished` / `OperationFailed`。
- `Controller.execute_sync()` 是同步生命周期的唯一入口；`TuiIntent` / `TuiOperation` 传递 `diff_scope`、`diff_path`、`export_output_dir`，`TuiOperationValue` 覆盖当前及已预留 S4 操作的公开返回对象。
- 保留 S4 的命令、Message、Widget 行为和兼容构造参数；新增 App 边界、Executor 路由和 Controller 生命周期测试。

### Red → Green

- Red：评审复现了 RUN_TASK 丢失 request context、App 重复同步生命周期和预留操作参数缺失；返工测试又准确复现了非运行态 `OperationFailed` 处理启动 Worker 时的 `RuntimeError: no running event loop`，以及契约字段尚未传递时的 `TypeError`。
- Green：Worker 成功/失败均发布完整 `TuiOperationResult` / `TuiOperationError`；结果统一经 `Controller.apply_result()` / `apply_error()`；删除 App 的 `_execute_sync()`，同步入口集中到 `Controller.execute_sync()`；新增字段和结果联合类型测试通过。R0 聚焦测试：`15 passed`。
- TUI 与 TaskService 回归：`113 passed`；全仓 Pytest：`1261 passed, 17 skipped`。
- 全仓 Ruff：`All checks passed!`；全仓 MyPy：`Success: no issues found in 96 source files`；`git diff --check`：通过。
- 最新合并后没有独立 GitHub Actions run/combined status 证据；本卡只记录本地 Windows 验证结果，不将本地结果冒充远程 CI。

### 未纳入边界

- 更完整的 Query Worker 取消策略、Inspection Views、Export 视图、响应式布局和完整端到端质量门留给 S5-R2~R6；R0 只冻结并闭环操作结果协议。
- 不引入真实网络 LLM、凭据或第三方 Agent 框架；不在本阶段提交 Git commit。

---

## S5-R1：ViewState、Presenter 与事件展示契约

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已完成 |
| 依赖 | S5-R0 |
| 分支 | `main`（按用户要求不在阶段中提交） |
| 边界 | 只补齐 ViewModel、Presenter、Build 展示信息和 TraceEvent 映射；完整 Query Worker 取消策略与 Inspection Views 留给 S5-R2/R3 |

### 交付内容

- 新增 `interfaces/tui/presenters.py`，提供 `DetailKind`、Task/Activity/Event/Interaction/Approval/Artifact ViewModel 和纯 Presenter。
- Presenter 对用户文本执行脱敏、控制字符清理、长度上限和条目上限；绝对路径显示为 `<absolute-path-hidden>`。
- `TaskSummary` 暴露 `latest_build_status` 与 `builds_run`，并由 `TaskState` 统一传递到 TUI Task Overview。
- ViewState 保存当前 Detail 类型与纯 Task ViewModel；ActivityLog 使用 Presenter 的事件标签映射，未知事件仍保留原始类型。
- App 的活动记录和 Task Overview 渲染改为消费 Presenter 结果，并保留既有 TraceEvent 兼容入口。

### Red → Green 与验证

- Red：新 Presenter 测试首先因 `interfaces.tui.presenters` 缺失而无法导入；Build 传递测试的第一次失败来自不完整的 `TaskState.artifacts` 夹具，修正夹具后进入 Green。
- `tests/test_tui_presenters.py tests/test_tui_view_state.py tests/test_tui_controller.py tests/test_tui_app.py tests/test_tui_operations.py tests/test_tui_app_s5.py tests/test_tui_controller_s5.py tests/test_task_service.py`：`54 passed`。
- R1 专项 Presenter：`8 passed`。
- Ruff：变更文件 `All checks passed!`；MyPy：5 个 TUI/TaskSummary 源文件无错误；`git diff --check` 通过。

### 未纳入边界

- 更完整的 Query Worker 取消策略、过期 Query 体验和 Inspection Views 留给 S5-R2/R3；R0 已提供基础的 request-scoped Operation 消息。
- Diff、Test、Checkpoint、Delivery、Export 视图和完整 HITL Modal 留给 S5-R3~R6。

---

## S5-R2：通用异步 Operation

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已完成 |
| 依赖 | S5-R0、S5-R1 |
| 分支 | `main`（按用户要求不在阶段中提交） |
| 边界 | 统一 Mutation/Query Worker 生命周期、request-scoped 结果和过期查询丢弃；不实现 Inspection 视图 |

### 任务拆分与验收

1. **统一 Worker 执行器**：在 `app.py` 中收敛成功、结构化错误和未知异常的发布逻辑；Mutation 使用 `task-mutation` 组，Query 使用 `task-query` 组；Worker 不触碰 Widget。
2. **补齐 Query 路由**：`TuiOperationExecutor` 为 Diff、Test Report、Checkpoint、Delivery、Trace 和 Artifact 提供只读服务路由；每个请求通过 `dispatch → begin_operation → Worker → OperationFinished/Failed`。
3. **过期与失败回归**：补充 request ID、task ID、旧 Query 不污染新 Detail、异常清除 loading 状态和取消 Worker 不泄漏原始异常的测试。

### 完成标准

- Diff/Test/Checkpoint/Delivery/Artifact 查询不在 Textual 主线程执行。
- 旧 task 或旧 request 的结果不会覆盖当前 Detail。
- Worker 异常始终通过 `OperationFailed` 清理当前请求状态。
- R2 聚焦测试、现有 TUI 回归和 Ruff/MyPy 通过。

### 实现与验证

- `TuiOperationExecutor` 已路由 Diff、Test Report、Checkpoint、Delivery evidence、Artifact 和 Trace 查询；Delivery 查询只调用 `get_evidence()`，不触发 `finalize()`。
- `/trace` 与 `/artifacts` 已切换到 `task-query` Worker；Trace 结果通过 `TracePage` 有界写入 ViewState。
- Controller 对 request ID、operation task ID 和当前 active task 做联合校验；旧请求、旧任务结果或错误不会清理/覆盖当前请求。
- Worker 统一使用 `task-mutation` / `task-query` 分组和 `OperationFinished` / `OperationFailed` 消息，取消 Worker 不发布结果。
- R2 聚焦测试：`20 passed`；TUI/TaskService 回归：`118 passed`；全量 Pytest：`1266 passed, 17 skipped`。
- Ruff：`All checks passed!`；MyPy：`Success: no issues found in 96 source files`；`git diff --check`：通过。
- 未提交 commit；R3 继续负责 Inspection View、命令参数和 Detail 路由。

## S5-R3：Inspection Views

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已完成 |
| 依赖 | S5-R2 |
| 分支 | `main`（按用户要求不在阶段中提交） |
| 边界 | 接入 Diff/Test/Checkpoint/Delivery/Artifact 只读视图和命令，不改变 S4 服务算法 |

### 任务拆分与验收

1. **命令契约**：扩展 `commands.py` 支持 `/diff [task|latest] [path]`、`/test`、`/checkpoints`、`/delivery`、`/artifacts`、`/open <artifact>` 和 `/trace [event-id]`，所有非法参数返回结构化 `TuiCommandError`。
2. **安全 ViewModel/Presenter**：在 `presenters.py` 增加 Diff、Test Report、Checkpoint、Delivery、Export 视图模型；继续执行脱敏、Plain Text、长度/条目上限和路径隐藏。
3. **Detail 路由**：根据 `DetailKind` 更新 Detail Panel 和 ViewState；Trace 事件可选中并展示安全摘要，完整 Diff/Provider 原始响应不进入 UI。

### 完成标准

- Diff 只调用 `ChangeInspectionService`，不调用 Git 或直接读取 checkpoint。
- Test Report 只调用 `DeliveryInspectionService`，不直接读取文件。
- Checkpoint 只调用 `CheckpointInspectionService`，Artifact 只调用 `InspectionService`。
- Delivery 查询不调用 `DeliveryService.finalize()`。
- R3 命令、Presenter、Executor 和 Textual 集成测试通过。

### 实现与验证

- `commands.py` 支持 `/diff [task|latest] [path]`、`/test`、`/checkpoints`、`/delivery`、`/artifacts`、`/open <artifact>` 和 `/trace [event-id]`，非法 Diff scope 与非 allow-list Artifact 返回结构化命令错误。
- `presenters.py` 增加 Diff、Test Report、Checkpoint、Delivery、Export ViewModel；所有内容继续执行脱敏、截断、数量上限和路径隐藏。
- Controller 根据 `DetailKind` 保存 Diff/Test/Checkpoint/Delivery/Artifact/Event ViewModel；App 使用 Plain Text Detail Panel 渲染，未知 TraceEvent 仍保留。
- Inspection 数据仍只来自既有 Application Service；Delivery evidence 缺失时显示只读 blocked 状态，不执行 finalize。
- R3 专项新增测试：`50 passed`；TUI/TaskService 回归：`124 passed`；全量 Pytest：`1272 passed, 17 skipped`。
- Ruff：`All checks passed!`；MyPy：`Success: no issues found in 96 source files`。
- 未提交 commit；R4 继续负责 ASK_USER、Approval Modal 和 Rollback Modal。

## S5-R4：Human-in-the-Loop 产品界面

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已完成 |
| 依赖 | S5-R3 |
| 分支 | `main`（按用户要求不在阶段中提交） |
| 边界 | 将 ASK_USER、Approval、Rollback 的现有安全流程产品化；不修改 S3 状态机和 Recovery 算法 |

### 任务拆分与验收

1. **ASK_USER Panel**：使用 Presenter 显示有界问题文本、interaction ID 和输入提示；回答仍经 `InteractionService.answer()` 后自动 resume。
2. **Approval Modal**：显示工具、风险、原因、目标和有界 diff preview；只在 Modal 获得焦点时接受 Y/N/Esc，普通文本不得触发 Approval。
3. **Rollback Modal**：显示 `RecoveryService.preview_last()` 的 checkpoint 和文件列表；只有显式确认才调用 rollback，取消和关闭不产生写操作。
4. **过期/失败反馈**：过期 Approval、服务错误和自动 resume 失败通过结构化错误和安全 Notice 展示。

### 完成标准

- 普通文本不能批准或拒绝 Approval。
- Approval approve/reject 后只执行一次对应决策并自动 resume。
- Rollback 必须二次确认，Modal 取消不修改状态。
- Approval preview、ASK_USER 文本和错误 Notice 均有界且脱敏。
- R4 Textual 集成和现有 HITL E2E 通过。

### 实现与验证

- 新增 `ApprovalDialog` 和 `RollbackDialog`；Approval 只在 Modal 焦点内接受 Y/N/Esc，Rollback 只在显式确认后调用已有 RecoveryService。
- ASK_USER 面板改用 `InteractionView`，问题和 interaction ID 经过 Presenter 有界脱敏；Approval 结果校验 approval ID，过期 Modal 不执行决策。
- 保留 `/approve`、`/reject`、`/rollback confirm` 显式命令和自动 resume；Modal 取消、服务错误和 stale Approval 只生成安全 Notice。
- R4 Modal/HITL 专项：`18 passed`；TUI/TaskService 回归：`128 passed`；全量 Pytest：`1277 passed, 17 skipped`。
- Ruff：`All checks passed!`；MyPy：`Success: no issues found in 97 source files`。
- 当前进入 R5：Export、启动恢复和响应式布局；未提交 commit。

## S5-R5：Export、恢复与响应式布局

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已完成 |
| 依赖 | S5-R4 |
| 分支 | `main`（按用户要求不在阶段中提交） |
| 边界 | 接入 Export、启动恢复和宽中窄布局；不扩展为 IDE、Shell 或多项目工作区 |

### 任务拆分与验收

1. **Export Operation**：`/export <directory>` 通过 `DeliveryService.export()` 在 Mutation Worker 中执行，展示导出目录和实际 artifact 列表，不覆盖已有目录。
2. **启动恢复**：启动时刷新任务列表；选择或恢复任务时通过 `InspectionService` 恢复当前 Task 的有界 Trace，退出不写入额外业务状态。
3. **响应式布局**：让 `COMPACT_WIDTH_THRESHOLD` 真正控制宽、中、窄三种布局，并确保窄布局仍能访问 Task、Activity、Detail、Composer 核心操作。
4. **恢复/导出回归**：补充退出后重新进入 WAITING_INPUT/WAITING_APPROVAL、Export 只导出 state 声明 Artifact 和窄终端命令测试。

### 完成标准

- TUI 退出不破坏 Task state/trace，重新进入能恢复未完成任务。
- Export 只经 `DeliveryService`，不直接读写 artifact，也不覆盖已有输出目录。
- 宽、中、窄布局均可挂载并执行核心命令。
- R5 专项测试和静态检查通过。

### 实现与验证

- `/export <directory>` 已路由到 `DeliveryService.export()` 的 `task-mutation` Worker，使用 `ExportResultView` 显示有界目录和 Artifact 列表；覆盖行为继续由 DeliveryService 拒绝。
- 启动时保留无残留 Worker 的同步任务列表初始化；Task 选择通过 Query Worker 恢复有界 Trace 和 WAITING 状态，退出不写入业务状态。
- `MainScreen` 增加 `wide`、`medium`、`narrow` 三档布局模式，窄终端切换为纵向核心区域，宽/中终端保留任务、Activity、Detail 三栏。
- R5 Export/布局/恢复回归已纳入 TUI/TaskService 测试；全量 Pytest：`1279 passed, 17 skipped`。
- Ruff：`All checks passed!`；MyPy：`Success: no issues found in 97 source files`。
- 未提交 commit；R6 继续负责完整 Textual E2E、Build、Demo 和最终质量门。

## S5-R6：端到端验收

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已完成（E2E、全量质量门与 Mock Demo 验证通过；无独立远端 CI run 证据） |
| 依赖 | S5-R2~R5 |
| 分支 | `main`（按用户要求不在阶段中提交） |
| 边界 | 用 MockLLM 和 Textual `run_test` 验证完整产品路径，不使用真实网络或凭据 |

### 任务拆分与验收

1. 补充基本任务 E2E：create → run → completed。
2. 补充 ASK_USER E2E：waiting input → answer → auto resume。
3. 补充 Approval E2E：waiting approval → explicit approve/reject → exact action → auto resume。
4. 补充 Delivery E2E：diff → test report → checkpoints → delivery → export，并断言 Delivery 查询不触发 finalize。
5. 运行全量 `pytest`、`ruff`、`mypy`、`uv build` 和 packaged Mock Demo；同步 PLAN、AGENT_LOG、README/架构文档中的 S5 状态。

### 完成标准

- S5 完成清单的每一项都有源码和测试证据。
- 全量质量门通过，且本地验证与远程 CI 状态分开记录。
- 未提交 commit，等待用户在 R2-R6 全部完成后统一提交。

### 实现与验证

- 新增 `/build` Mutation Operation，使用注入的 BuildService，在后台 Worker 执行配置 Build 并展示安全摘要；`/export`、Inspection 和 HITL 路径均有统一 TUI 边界。
- 新增 S5 Textual E2E：基本任务 create/run/completed 和 Delivery diff/test/checkpoints/delivery/export；ASK_USER、Approval 路径复用既有 MockLLM E2E，并断言 Delivery 查询不触发 finalize。
- 全量 Pytest：`1283 passed, 17 skipped`；Ruff：`All checks passed!`；MyPy：`Success: no issues found in 97 source files`；`git diff --check`：通过。
- `uv build --offline` 成功生成 `dist/hancode-0.1.0.tar.gz` 与 `dist/hancode-0.1.0-py3-none-any.whl`；首次联网 `uv build` 因环境 TLS 握手失败，离线缓存构建作为本地证据。
- `uv run hancode demo --provider mock` 成功返回 completed DeliveryResult；未使用真实网络、凭据或真实 LLM。
- S5-R0~R6 未提交 commit；当前工作区保留既有用户改动和本阶段实现，等待用户统一审阅/提交。

### P0 审查修复

- Approval 查询竞态：`RUN_TASK`/`GET_STATUS` 先刷新 Task List，`LIST_TASKS` 完成后才反映 WAITING_APPROVAL 并启动 `GET_APPROVAL`。
- Delivery Gate：新增 `DeliveryInspectionService.read_delivery_summary()`，复用 DeliveryPipeline blocker/status 计算；Presenter 只展示服务结果，不自行推测 ready。
- Rollback 绑定：Rollback preview 的 checkpoint ID 随 Operation 传递，在 Task Lock 内复核最新 checkpoint，不一致返回 `rollback_preview_stale`。
- P0 回归专项：`19 passed`；修复后全量 Pytest：`1300 passed, 17 skipped`。

---

## S5-TUI-R7：实时 TaskSummary 状态投影

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已完成 |
| 依赖 | S5-R2（异步 Mutation Worker 与 request-scoped Controller） |
| 分支 | `codex/tui-live-status` |
| 提交 | 不提交、不推送（除非用户另行要求） |

### 范围与边界

- 每条 Trace 成功持久化后，由同一 Mutation Worker 读取最新 `TaskSummary` 并向 Textual 主线程投递快照；ActivityLog 仍逐事件追加。
- 只更新既有 TaskList、PhaseBar、Task Overview；不新增运行面板、不轮询，且 TUI 不根据 TraceEvent 推演业务状态。
- Controller 仅接受当前 Mutation request、当前 `running_task_id` 和当前 active task 的实时摘要；旧 request、错误 task 和 Worker 结束后的迟到消息必须丢弃。
- ViewState reducer 同步 status、phase、test/build、checkpoint、artifact、retry 和 HITL 摘要；用户正在查看 Diff/Event/Artifact 等 Inspection Detail 时不得抢占该面板。
- 保留 `OperationFinished` 的终态刷新与 WAITING_INPUT/WAITING_APPROVAL 聚焦流程，实时快照失败只能漏过单次刷新，不能影响 Trace 展示或 AgentLoop 结果。
- 允许修改：`src/hancode/interfaces/tui/` 的 operation、message、controller、view-state、app 接线及对应 TUI 测试，`docs/PLAN.md`、`docs/SPEC.md`、`docs/AGENT_LOG.md`。
- 不修改：AgentLoop 状态机、`TraceObserver` 核心协议、TaskState/state.json schema、路由和 Delivery 算法。

### 验收与验证

1. 使用真实 App、TaskService 和阻塞式 Fake Provider，在 Worker 未结束时断言 `created` 已投影为 `running`，TaskList、PhaseBar 和 ActivityLog 均已更新。
2. 下一 phase 开始后、Worker 结束前，PhaseBar 与完整 TaskSummary 字段（test/build/checkpoint/artifact/retry/HITL）同步到 ViewState 与 Task Detail。
3. 旧 request、错误 task、Worker 结束后的摘要以及 Inspection Detail 抢占均由公开 App/Controller 行为回归覆盖。
4. 摘要读取或 UI observer 失败时，Trace 仍实时显示，AgentLoop 不转为失败或 inconsistent；`OperationFinished` 仍能纠正遗漏刷新。
5. 覆盖 WAITING_INPUT、WAITING_APPROVAL、completed、blocked、unexpected Worker error；运行聚焦 TUI 测试及全量 pytest、Ruff、MyPy、`uv build --offline`、Mock Demo、`git diff --check`，并清理缓存/构建产物。

### 实施记录

- Red：新增 reducer/Controller 测试后执行 `uv run --no-sync pytest tests/test_tui_controller.py -q -p no:cacheprovider`，收集期因缺少 `reduce_task_summary_changed` 失败，确认实时摘要投影尚未实现。
- Green：新增 `TuiRunObserver` 与运行期摘要转发器；每条已持久化 Trace 后在同一 Mutation Worker 调用 `TaskService.get()`，把 `request_id + TaskSummary` 投递为 `TaskSummaryChanged`。Controller 以 active mutation、`running_task_id`、active task 三重门控；ViewState 纯 reducer 仅在 TASK Detail 刷新 Overview，Inspection Detail 保持原样。
- 回归：真实 `HanCodeTuiApp + TaskService +` 阻塞 Fake Provider 在 Worker 仍运行、已进入 PLAN 时断言 `running` 摘要、TaskList、PhaseBar 与 ActivityLog 已更新；另覆盖完整摘要/HITL、旧 request、错误 task、Worker 结束后迟到消息、摘要读取失败与 UI observer 失败。最终聚焦新增测试为 `21 passed`，TUI 范围回归为 `44 passed`。
- 完整门禁（2026-07-28）：全量 pytest `1340 passed, 17 skipped`；Ruff `All checks passed!`；MyPy `Success: no issues found in 98 source files`；`uv build --offline` 成功；`uv run --no-sync hancode demo --provider mock` 返回 `status=completed`；`git diff --check` 通过。首次使用空隔离 uv cache 的离线 build 因缺少缓存内 `setuptools>=68` 未进入构建，改用既有用户级缓存后成功。
- 清理：删除本轮 `dist/`、`src/hancode.egg-info/`、`.pytest_cache/`、`.mypy_cache/`、`.ruff_cache/`；不提交、不推送。

---

## S5-R1：统一阶段完成门禁

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已完成 |
| 依赖 | S5 |
| 可并行 | 不并行 |
| 主贡献相关 | 是 |
| Commit | 未提交 |

### 范围

- `src/hancode/core/phases.py`
- `src/hancode/providers/action_schema.py`
- `src/hancode/policy/tool_policy.py`
- `src/hancode/runtime/agent_loop.py`

### 验收

- Context 和 Policy 消费同一个 PhaseGate。
- LLM 可看到 `phase_gate.can_finish`。
- 不存在重复的阶段完成判断逻辑。
- 模型 Schema 中没有 `final`。
- 写工具必须提供 `reason`。
- Router 仍是唯一全局完成控制者。

---

## S5-R2：规范 Provider Prompt Contract

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已完成 |
| 依赖 | S5-R1 |
| 可并行 | 不并行 |
| 主贡献相关 | 是 |
| Commit | 未提交 |

### 范围

- `src/hancode/providers/prompt_contract.py`
- `src/hancode/providers/prompt_builder.py`
- `src/hancode/runtime/context.py`
- `src/hancode/core/tool_specs.py`

### 验收

- Prompt 明确 Workspace 内容为不可信证据。
- Provider Schema 不暴露 `final`。
- 写操作 Schema 必须包含非空 `reason`。
- Prompt 带版本号。
- Context 含 `runtime_state` 和 `phase_gate`。
- 不再重复注入 `allowed_tools`。
- 不再双重 JSON 编码。

---

## S5-R3：严格结构化 Provider 输出

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已完成 |
| 依赖 | S5-R2 |
| 可并行 | 不并行 |
| 主贡献相关 | 是 |
| Commit | 未提交 |

### 范围

- `src/hancode/core/config.py`
- `src/hancode/providers/base.py`
- `src/hancode/providers/openai_compatible.py`
- `src/hancode/providers/factory.py`

### 验收

- 支持 `json_object` 和 `json_schema` 两种模式。
- 严格模式实际把 Action Schema 放入 API `response_format`。
- 兼容模式仍嵌入 Schema。

---

## S5-R4：完善工具语义

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已完成 |
| 依赖 | S5-R2 |
| 可并行 | 不并行 |
| 主贡献相关 | 是 |
| Commit | 未提交 |

### 范围

- `src/hancode/core/tool_specs.py`

### 验收

- 所有工具参数禁止额外字段。
- 写工具说明何时使用、何时避免。
- 结构化数组定义 `items`。

---

## S6：多模式 Structured Action Provider

### 目标

在不改变 AgentLoop、ActionParser、ToolRegistry 与 ToolPolicy 既有语义的前提下，扩展 OpenAI-compatible Provider 的输出协议：支持文本 JSON、JSON Schema 与原生 tool calling；严格模式必须由纯投影器将现有 Action Schema 转为 provider 可接受的子集；自动降级必须由可审计的确定性规则控制。

### 全局约束

- `ProviderError.protocol_retryable` 只描述协议层重试资格；HTTP/网络重试使用 provider 内部异常模型，二者不得混用。
- AgentLoop 仅在 `parse_action()` 成功后清零连续协议失败计数；任何 provider 返回但未被解析为 Action 的响应仍计入协议失败。
- `ToolSpec` 是 Action、JSON Schema 与原生工具定义的唯一业务真源；所有 schema 校验使用同一 Draft 2020-12 语义。
- Strict projection 是无副作用的纯函数；只允许删除投影器新增的可空 `null`，不得删除模型原始提交的 `null`。
- R0--R4 的默认模式保持 `json_object`；R5 完成后默认切换为 `auto`。
- 不记录模型原文、API key、Authorization header 或 tool arguments 的敏感内容到 trace。

### 依赖图

`S6-R0 -> S6-R1 -> S6-R2 -> S6-R3 -> S6-R4 -> S6-R5`

### S6-R0：任务契约与基线

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已完成 |
| 依赖 | S5-R4 |
| 可并行 | 不并行 |
| 提交 | 不提交，等待用户统一审阅 |

#### 范围

- `docs/PLAN.md`
- `docs/AGENT_LOG.md`

#### 验收

1. 为 R1--R5 写明依赖顺序、修改边界、行为验收与验证矩阵。
2. 在未改代码的 `main@9be2e78470d74de00fbacb45f0af266f70daa549` 上取得可复核全量基线。
3. 记录 S6 不改变的核心边界与风险分类。

### S6-R1：统一 Action Schema 校验与 ToolSpec 审计

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已完成 |
| 依赖 | S6-R0 |
| 可并行 | 不并行 |

#### 范围

- `pyproject.toml`、锁文件
- `src/hancode/core/actions.py`
- `src/hancode/core/tool_specs.py`
- `tests/test_actions.py`、`tests/test_tool_specs.py`（及新增专属测试）

#### 验收

1. 运行时 `ActionParser` 与 provider 入口使用同一 Draft 2020-12 validator，支持嵌套 object、array `items`、`enum`、`oneOf`、`additionalProperties` 与 nullable union。
2. 非 provider schema 违规保持现有 `action_*` 错误语义；provider 响应 schema 违规统一映射为 `provider_invalid_response`。
3. 审计并补齐 ToolSpec 中会阻碍统一校验的约束；不得放宽既有工具策略或把 prompt 当作校验。

#### 实施记录

- Red：新增 `record_review.requirements[].status="unknown-status"` 的公开 Action 测试，旧顶层校验错误接受该 Action。
- Green：加入 `jsonschema` 运行时依赖，以 `Draft202012Validator` 统一校验工具与控制 Action 参数；删除旧的浅层手写匹配逻辑。
- 审计：将原先隐含于手写代码的非空白约束显式写入 `path`、`query`、`run_tests.command`、`run_build.command` 与 `edit_file.old_string` 的 ToolSpec schema，避免统一校验放宽既有行为。
- 验证（2026-07-29）：`tests/test_action_schema.py tests/test_action_parser.py tests/providers/test_action_schema.py tests/test_s4_review_remediation.py` 为 `87 passed`；目标 Ruff 通过；目标 MyPy 为 `Success: no issues found in 2 source files`；`git diff --check` 通过。

### S6-R2：文本响应解析、协议重试与计数

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已完成 |
| 依赖 | S6-R1 |
| 可并行 | 不并行 |

#### 范围

- `src/hancode/providers/errors.py`
- `src/hancode/providers/openai_compatible.py`
- `src/hancode/runtime/agent_loop.py`
- `tests/providers/test_openai_compatible.py`、`tests/test_provider_failure_loop.py`

#### 验收

1. `ProviderError` 显式提供默认 `False` 的 `protocol_retryable`；transport retry 由私有 transport 异常决定，不暴露为协议重试。
2. 空内容、非法 JSON、非 object 与 Action schema 失败均为 `provider_invalid_response` 或 `provider_empty_response`，且可按协议预算回灌重试。
3. 成功取得 provider 响应不清零计数；仅 `parse_action()` 成功清零。transport exhausted、refusal、content filter、length 等终态错误不重试。

#### 实施记录

- Red：`ProviderError(..., protocol_retryable=True)` 在旧模型中不被支持；旧 AgentLoop 在 `next_action()` 返回后即清零连续协议失败计数。
- Green：`ProviderError` 改为默认关闭的 `protocol_retryable`；OpenAI-compatible adapter 用私有 `_TransportFailure` 管理 HTTP/网络的指数重试，耗尽后转换为不可协议重试的边界错误。
- 解析：空 content 现在为 `provider_empty_response` 且可协议重试；非法 JSON、非 object 及其他不合规响应为可协议重试的 `provider_invalid_response`；响应大小限制与 transport 终态保持不可协议重试。
- 计数：AgentLoop 改为只在 `parse_action()` 成功后清零，并直接消费 `ProviderError.protocol_retryable`，不再维护硬编码错误码白名单。
- 验证（2026-07-29）：Provider failure loop 与 OpenAI-compatible adapter 测试 `38 passed`；目标 Ruff 通过；目标 MyPy 为 `Success: no issues found in 3 source files`；`git diff --check` 通过。

### S6-R3：Strict JSON Schema 投影与配置迁移

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已完成 |
| 依赖 | S6-R2 |
| 可并行 | 不并行 |

#### 范围

- `src/hancode/core/config.py`
- `src/hancode/providers/action_schema.py`
- `src/hancode/providers/prompt_builder.py`
- `src/hancode/providers/openai_compatible.py`
- `tests/test_config.py`、`tests/providers/test_prompt_builder.py`、`tests/providers/test_openai_compatible.py`

#### 验收

1. 新配置 `provider_action_mode` 支持 `auto`、`native_tools_strict`、`native_tools`、`json_schema`、`json_object`；旧 `provider_response_mode` 仅作读取兼容别名，两者并存时 fail-closed。
2. `StrictSchemaProjection` 对每个 object 设置 `additionalProperties: false` 与完整 required；原 optional 字段用可空 union 表达，并精确记录 `promoted_optional_paths` 与 `synthetic_nullable_paths`。
3. 从 strict 响应恢复 canonical Action 时只删除“投影新增且值为 null”的字段，保留原生 null；无参工具在 reason 注入后不与 `maxProperties: 0` 冲突。
4. 投影前后分别校验 canonical / strict schema，且 projection-normalization round trip 可复现。

#### 实施记录

- Red：`provider_action_mode` 被旧配置白名单拒绝。
- Green：新增纯 `StrictSchemaProjection`，递归投影 object、array 和组合分支；投影前后执行 Draft 2020-12 schema 检查。归一化仅删除路径元数据标记为“投影新增可空”的 `null`，原 schema 自身允许的 `null` 保留。
- 配置：新增 `provider_action_mode`（五种模式）；旧 `provider_response_mode` 仅单键读取兼容，双键并存返回 `config_invalid`；R3 默认仍为 `json_object`。
- 集成：`json_schema` 请求发送 strict projection，响应先按 strict schema 校验、归一化，再验证 canonical schema；失败映射为可协议重试的 `provider_invalid_response`。
- 验证（2026-07-29）：配置、Factory、Prompt、Action Schema、Provider 与 projection 回归 `152 passed`；目标 Ruff 通过；目标 MyPy 为 `Success: no issues found in 5 source files`；`git diff --check` 通过。

### S6-R4：原生 Tool Calling 执行路径

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已完成 |
| 依赖 | S6-R3 |
| 可并行 | 不并行 |

#### 范围

- `src/hancode/providers/base.py`
- `src/hancode/providers/openai_compatible.py`
- `src/hancode/providers/factory.py`
- `tests/providers/test_openai_compatible.py`、`tests/test_provider_factory.py`

#### 验收

1. Provider 接收由 ToolSpec 生成的 `ProviderToolDefinition`；原生 strict 请求发 `tools`、`tool_choice=required`、`parallel_tool_calls=false` 与 `strict=true`。
2. non-strict 模式省略 `strict` 字段，不能发送 `false`；原生路径忽略 message content，只接受恰好一个 function tool call。
3. refusal、`content_filter`、`length`、零或多个 tool calls、未知工具、非法 JSON arguments 均返回结构化且不可协议重试的 provider 错误。

#### 实施记录

- Red：`native_tools_strict` 仍走文本 content 解析，无法读取 `message.tool_calls`。
- Green：从 ToolSpec-derived catalog 构造 `ProviderToolDefinition`；将 `reason` 注入 function parameters 并在 response 中拆回 Action 字段，无参数工具同步移除旧 `maxProperties: 0` 限制。
- 请求：strict native 发送 `tools`、`tool_choice="required"`、`parallel_tool_calls=false` 和 `function.strict=true`；non-strict 显式省略 `strict` 与 `response_format`。
- 响应：忽略 message content，严格接受一个 function call；refusal、content filter、length、零/多个调用、未知工具、非法 JSON 与参数校验失败都映射为不可协议重试的 ProviderError。
- 验证（2026-07-29）：OpenAI-compatible Provider 回归 `33 passed`；目标 Ruff 通过；目标 MyPy 为 `Success: no issues found in 2 source files`；`git diff --check` 通过。

### S6-R5：Auto 降级与 Provider Trace 事件

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已完成 |
| 依赖 | S6-R4 |
| 可并行 | 不并行 |

#### 范围

- `src/hancode/providers/base.py`
- `src/hancode/providers/openai_compatible.py`
- `src/hancode/runtime/engine.py`
- `src/hancode/core/config.py`
- `tests/providers/test_openai_compatible.py`、`tests/test_provider_factory.py`（及新增 trace 测试）

#### 验收

1. `auto` 只依据精确的 `unsupported_parameter` / `unsupported_value` 及参数名执行一次同请求降级：strict → native、tools/tool_choice/parallel → json_schema、`response_format.type=json_schema` → json_object；未知响应 fail-closed。
2. 自动降级不消耗 AgentLoop 协议预算或步骤预算；非能力错误不触发降级。
3. Provider 层通过 `ProviderEventSink` 发出无敏感参数的 `provider_mode_selected`、`provider_mode_downgraded`、`provider_request_failed`；Engine 在构造 Provider 前完成 trace bridge 组装。
4. R5 完成后把默认 `provider_action_mode` 切换到 `auto`，并覆盖从 strict 到 json_object 的完整降级链。

#### 实现与验证（2026-07-29）

- `auto` 从 `native_tools_strict` 开始，仅对精确的 capability 400 错误在一次 `next_action()` 内依次降级；未识别的参数、非 400 响应和 transport/protocol 错误均保持 fail-closed。
- 新增 `ProviderEvent` / `ProviderEventSink`；Provider 只发出模式和错误码，Engine 在构造 adapter 前装配 best-effort trace bridge，不传递请求体、arguments 或凭据。
- 默认 `provider_action_mode` 已切换到 `auto`；覆盖 strict→native、native→json_schema、json_schema→json_object、未知错误拒绝及 trace 安全字段。
- 验证：相邻模块与 Trace 回归 `181 passed`；目标 Ruff `All checks passed!`；目标 MyPy `Success: no issues found in 13 source files`；最终全量 pytest `1364 passed, 17 skipped`；全仓 Ruff 通过、MyPy `99 source files` 无错误；`uv build --offline` 和 `hancode demo --provider mock` 成功；`git diff --check` 通过。验证后的 build、cache、临时目录与仓库内字节码已清理。

### S6 验证矩阵

- 每个 R 先新增一个公开行为测试并确认 RED，再做最小 GREEN；相邻 R 的回归测试必须保留。
- R1--R5 分别运行相关 provider、Action、config、AgentLoop 测试；R5 运行全量 `uv run --no-sync pytest -q -p no:cacheprovider`、Ruff、MyPy、`uv build --offline`、Mock Demo 与 `git diff --check`。
- 每个 R 完成后更新本计划和 `docs/AGENT_LOG.md`，清理 `.pytest_cache`、`.mypy_cache`、`.ruff_cache`、构建产物和临时目录。

### S6 正式计划整改（2026-07-29，已完成）

本段以《HanCode S6 结构化 Action 与原生 Tool Calling 正式实施计划》为验收优先级，覆盖上文 S6-R1--R5 中与正式契约冲突的叙述。当前工作直接在恢复后的未提交 `main` 工作区进行；用户已明确批准“不创建分支/worktree、不提交”的 Git 流程豁免，因此不生成提交 hash，且该豁免不降低技术验收要求。

- R1/R2：新增 `provider_protocol_retries: int = 2`，只接受非负整数并由 Engine 注入 AgentLoop；decode、normalize、Schema 及 `parse_action()` 失败使用同一连续协议计数，只有完整合法 Action 才清零，transport 重试耗尽保持不可协议重试。
- R1/R3：统一 Draft 2020-12 validator 输出稳定、脱敏的 `SchemaViolation(path, validator, message)`；文本模式 Schema 失败固定为 `provider_action_schema_invalid`，不得进入 Policy 或 Registry。
- R3/R4：`StrictSchemaProjection` 的公开 provider schema 为 `provider_schema`，保留 optional promotion 与 synthetic-null 路径；`ProviderToolDefinition` 同时保留 `request_schema`、`original_args_schema` 与 projection。原生 Prompt 为 `hancode-tool-v1`，用户 payload 只含版本、request 与 task context；文本 Prompt 保持 `hancode-action-v2`。
- R4：原生 Decoder 依序校验响应外壳、终止原因、refusal、tool-call 数量/type/name/arguments/schema，使用 `provider_tool_call_missing`、`provider_tool_call_count_invalid`、`provider_tool_name_invalid`、`provider_tool_arguments_invalid`、`provider_tool_schema_invalid`、`provider_refusal`、`provider_content_filtered`、`provider_output_truncated`；畸形或缺失调用可协议重试，未知工具/拒绝/过滤/截断终止且零 dispatch。
- R5：Provider 缓存 effective mode，只向更宽松模式移动；fallback 仅依据精确 code/parameter，并在成功 emit `ProviderEvent(kind="mode_fallback", phase, from_mode, to_mode, reason_code)` 后缓存。Engine 写入无敏感值的 `provider_mode_fallback` Trace；sink 失败不吞掉，由 AgentLoop 既有运行边界转为 `inconsistent`。
- 非目标不变：Responses API、其他 Provider、Streaming、parallel/multi tool call 均不在 S6 范围；原 ToolSpec 保持不可变。

完成状态：S6 MVP 与 Enhanced 的正式计划验收项均已实现；Git 仅保留用户批准的“不提交”豁免。最终门禁：全量 pytest `1376 passed, 17 skipped`；Ruff `All checks passed!`；MyPy `Success: no issues found in 102 source files`；`uv build --offline` 与 `uv run --no-sync hancode demo --provider mock` 均成功。首次隔离 uv cache 的离线构建因缺少 `setuptools>=68` 失败，随后使用已有用户级离线 cache 成功，未访问网络。

### S6-R6：审查整改与可复现交付

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已完成 |
| 依据 | `main@2bd110e` 的 S6 评审结论 |
| 依赖 | S6-R5 |
| 分支 | `codex/s6-review-remediation` |

#### 范围

- `pyproject.toml`、`uv.lock`：锁定 `jsonschema>=4.23` 并验证 locked 同步。
- `core/schema_validator.py`、`core/actions.py`、Provider 相关模块：消除 Core 对 Provider 的反向依赖。
- 原生 Decoder：所有 native mode 校验 Function request schema；只接受一个 choice；超限统一为不可协议重试的 `provider_response_too_large`。
- Prompt：修正 `private_key` 规范化匹配并递归处理 tuple。
- Normalizer：让 `action_normalizer.py` 承担 native arguments 的 schema/投影归一化职责，避免无职责薄封装。

#### 非目标

- 不新增或配置 GitHub CI；该项需单独的仓库自动化与远端授权。
- 不修改 Responses API、其他 Provider、Streaming、多 tool call 语义或业务 ToolSpec。

#### 验收

1. `uv.lock` 的根项目依赖与 `pyproject.toml` 同时声明 `jsonschema>=4.23`，`uv sync --locked --extra dev` 成功。
2. strict 与 non-strict native 均在提取 `reason` 前校验对应 request schema；额外字段、缺失 reason 和嵌套非法参数返回 `provider_tool_schema_invalid` 且零 dispatch。
3. native 响应严格要求一个 choice、一个 function tool call；响应超限为不可重试 `provider_response_too_large`。
4. `Action`、strict projection 与 Provider 共同依赖 core validator；`private_key` 和 tuple 内敏感字段不会进入任意 Prompt。
5. 每个子项先有 RED 测试，再最小 GREEN；最终执行 pytest、Ruff、MyPy、locked sync、offline build、Mock Demo 与 `git diff --check`。

#### 实施与验证

- Red：non-strict native 缺失 `reason`、控制工具额外字段、多个 choice、native 超限和 tuple 内 `private_key` 均先由新增测试暴露。
- Green：Function request schema 在所有 native mode 下先校验；native 强制单 choice；超限映射为不可重试 `provider_response_too_large`。Schema validator 迁入 Core，Normalizer 承担 strict/non-strict 参数归一化，Prompt 规范化敏感 marker 并递归处理 tuple。
- 锁定交付：`uv lock` 新增 `jsonschema` 及其解析依赖；`uv sync --locked --extra dev` 成功。
- 最终验证：pytest `1381 passed, 17 skipped`；Ruff `All checks passed!`；MyPy `Success: no issues found in 102 source files`。

## 直接修复测试命令审批与状态 Trace（2026-07-27）

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已完成 |
| 分支 | main |
| 提交 | 未提交 |

### 范围

- run_tests 仅允许 TEST 阶段且必须携带显式 command。
- 所有 Agent run_tests 强制进入审批；非 Agent 内部的 Factory 配置 fallback 保留。
- TEST Prompt 要求执行测试 runner/测试二进制，编译-only 命令改用 run_build。
- 测试状态、TEST_REPORT.md 和 test_result_recorded trace 在普通执行与审批恢复路径保持一致；trace 写入失败 fail-closed 为 INCONSISTENT。
- Mock Demo 在离线驱动层自动批准显式测试命令，仍通过真实审批持久化与恢复路径。

### 边界

- 不修改 Router、DeliveryPipeline 和底层测试命令执行安全机制。
- 本轮不增加编译器命令黑名单或运行时语义分析。
- 不新增测试；仅更新既有测试中的旧 run_tests action 契约和审批恢复调用。

---

## S7：TUI 中文开发者工作台

| 元信息 | 值 |
| --- | --- |
| 状态 | [~] 实施中，等待三轮人工页面评审 |
| 分支 | `codex/tui-ux` |
| 范围 | Textual 表现层与只读展示模型；不修改 Harness Core、持久化或 Headless CLI |
| 开发方式 | 用户明确不采用 TDD；每轮先实现页面，再运行自动回归并进行人工评审 |

### 交互契约

- 默认中文、技术标识保留原文；深浅双主题，默认石墨深色，`Ctrl+T` 或 `/theme dark|light` 仅改变当前会话。
- `F2` 或 `/view focus|inspect` 只切换中栏语义活动流与 Raw Trace，不能抢占当前 Inspector Detail。
- Wide `>=100` 三栏；Medium `70-99` 隐藏任务栏；Narrow `<70` 使用进展、改动、状态、任务四个 Tab。
- 普通输入永远不能批准 Approval；所有操作仍通过既有 Application Service、Approval、Checkpoint 与 Policy。
- 测试页面只展示已持久化的 TEST_REPORT 字段；不伪造 stdout/stderr 或未记录的失败用例名。

### R0–R8 任务卡

1. **R0 文档契约**：同步 PLAN、架构、README 与 AGENT_LOG，冻结安全、响应式、主题和评审边界。
2. **R1 中文文案与主题**：集中阶段、状态、工具和事件文案；注册 `hancode-dark`/`hancode-light`。
3. **R2 工作台与活动流**：任务导航、语义 ActivityFeed、Raw Trace 和 Focus/Inspect 切换。
4. **R3 Inspector**：将纯文本 DetailPanel 升级为任务、Diff、测试、审批、检查点、交付、产物和错误的结构化展示。
5. **R4 决策界面**：源码 Diff 使用全屏决策页，test、build 和 rollback 保留紧凑弹窗；均显示后果、证据和显式操作，拒绝可附原因。
6. **R5 测试与 Diff**：安全的专用检查页面、文件标记、截断/脱敏和结构化 TEST_REPORT 摘要。
7. **R6 操作菜单**：`Ctrl+K` 的状态感知 Palette 与现有 Slash Command 共用操作描述。
8. **R7 响应式与可访问性**：三档布局、键盘操作、颜色外的文字/符号状态和双主题。
9. **R8 文档与 Demo**：批准截图、README、TUI UX 指南、Mock Demo 与最终质量门。

### 人工评审门禁

- 第一轮：R0–R3，评审中文术语、主题、宽中屏信息层级、活动流和 Inspector。
- 第二轮：R4–R6，评审审批、Rollback、测试、Diff 与 Palette 的决策清晰度。
- 第三轮：R7–R8，评审 `120×36`、`90×32`、`60×28` 三种终端尺寸、文档与 Demo。

### R4 人工评审整改：源码 Diff 全屏审批

- 用户冻结“源码 Diff 使用全屏审批页；测试、构建等短内容继续使用紧凑弹窗”。
- Source write、overwrite 和 multi-file write 路由到全屏 Modal Screen；标题、目的、影响范围、风险、可恢复性和操作区固定，Diff 使用独立滚动区，技术标识默认折叠。
- `Y/N/Esc`、J/K、PageUp/PageDown 和按钮均只在决策页生效；批准、拒绝和稍后处理仍返回既有 TUI Intent，不直接修改 Approval 状态。
- `120×36`、`90×32` 和 `60×28` 必须保持三枚操作按钮完整可见；Narrow 隐藏重复 Footer 并使用全宽纵向按钮。
- 测试、构建及其他短审批继续使用原 `ApprovalDialog`；Rollback 继续使用独立紧凑确认弹窗。

---

## S8：完整项目配置模板与全屏配置中心

| 元信息 | 值 |
| --- | --- |
| 状态 | [~] API 凭据配置扩展与自动验证完成，等待配置页面人工评审 |
| 分支 | `codex/tui-ux` |
| 范围 | 项目配置默认模板、Application Service、CLI 与 Textual 配置表现层 |
| 开发方式 | 用户明确不采用 TDD；先实现，再补自动回归与人工评审 |

### 任务边界

- 新项目的 `.hancode/project.json` 展开当前全部配置键；旧最小配置继续兼容，重复 init 不覆盖已有文件。
- 新增 `hancode config setup`、`hancode init --configure`、主 TUI `/config` 和 Command Palette 入口。
- 配置写入只能经过统一校验与同目录原子替换；取消、失败和链接目标不得改变原文件。
- 配置中心通过既有 `AuthService` 收集远程 Provider API Key；隐藏输入只写入 OS Keyring，绝不写入 `project.json`、trace、日志或截图。
- Keyring 凭据可在配置中心更新和清除；环境变量与 `.env` 来源只显示状态，必须由用户在来源处手动修改。
- 保存 Key 后只在内存草稿中将 `credential_source` 设为 `keyring`；仍需用户确认保存项目配置，两个写入动作互不冒充成功。
- 不修改 AgentLoop、ToolPolicy、Approval 状态机、任务持久化格式或 Provider 协议语义。

### 验收

- 默认模板、ConfigLoader 与配置中心共享一份字段顺序和默认值真源。
- Wide、Medium、Narrow、深浅主题、分组编辑、恢复默认、变更确认和放弃修改均可演示。
- 普通 init 输出保持兼容；配置 TUI 退出后 stdout 只输出一条结构化结果。
- 自动回归覆盖模板、旧配置迁移、原子保存、CLI、Textual 键盘路径和主工作台状态保持。
- Provider 页显示“未配置 / 已配置（末四位）/ 环境变量 / `.env`”状态；Key 输入使用密码模式，更新和清除均需显式确认。
- Keyring 不可用、空 Key、外部来源清除等失败不得泄露输入值，也不得改变 `project.json`。

---

## S9：Approval 消费后连续运行 AgentLoop

| 元信息 | 值 |
| --- | --- |
| 状态 | [~] 实施中 |
| 分支 | `codex/tui-ux` |
| 范围 | AgentLoop 审批恢复控制流与回归测试；不修改 Approval/Checkpoint 持久化格式 |
| 开发方式 | Core 行为修复，遵循 RED → GREEN → 回归验证 |

### 行为契约

- Approval 是 AgentLoop 的暂停点，不是一次 run 的结束点。
- 用户批准后，`resume=True` 复核原 Action、Policy、digest 与 Checkpoint，执行并消费 Approval；成功且状态仍为 `RUNNING` 时，将 ToolResult observation 回灌并在同一次调用中继续 Provider 循环。
- 只有再次进入 `WAITING_APPROVAL`、`WAITING_INPUT`，达到资源限制，或进入 `BLOCKED`、`FAILED`、`INCONSISTENT`、`COMPLETED` 时才能返回。
- 已消费或执行中的 Approval 不得重复 dispatch；审批执行失败、状态同步失败和 Checkpoint 失败继续 fail-closed。
- `run_tests` 已有连续恢复语义推广到所有批准动作；TUI、CLI 和 Headless 共用同一 AgentLoop 行为，不在 TUI 层串联第二次 resume。
- 拒绝后的结构化反馈与继续运行语义保持兼容。

### 文件边界

- `src/hancode/runtime/agent_loop.py`
- `tests/test_approval_e2e.py` 及必要的既有审批恢复测试
- `docs/PLAN.md`、`docs/AGENT_LOG.md`

### 验收

- 批准源码/Artifact 写入后，同一次 `run_task(..., resume=True)` 必须再次调用 Provider，并继续到下一暂停点或终态。
- 连续运行时保留 approved ToolResult observation、step/tool-call/risk 统计和现有 Trace 顺序。
- 下一动作再次需要审批时创建新的 Approval ID 并返回 `WAITING_APPROVAL`，不绕过 Policy。
- 错误或非 `RUNNING` 结果不得继续 Provider；CONSUMED/EXECUTING 恢复不得重复执行工具。
- 审批 E2E、恢复、AgentLoop、TUI 自动恢复回归、Ruff、MyPy 与 `git diff --check` 通过。

---

## S10：Agent 自主测试策略

| 元信息 | 值 |
| --- | --- |
| 状态 | [~] 实现完成；全量门禁有 1 个既有基线失败，离线构建缺少本地 `setuptools` 缓存 |
| 分支 | `codex/agent-test-strategy` |
| 依赖 | S9 |
| 范围 | CODE→TEST 测试策略登记、自动补建测试、执行绑定与只读展示 |
| 开发方式 | Core 行为变更；按用户授权先实现、后补回归验证（不采用 TDD） |

### 行为契约

- Agent 在 CODE 阶段复用并补充现有测试；没有相关测试时必须在项目测试目录自行创建测试。
- CODE 只有在真实测试文件和结构化测试策略均有效时才能完成。
- 已进入 TEST 的旧任务若缺少或漂移测试策略，自动返回 CODE 补建，不要求用户预先提供测试命令。
- TEST 只执行策略登记的单 argv 命令，并继续经过既有 RUN_TESTS Approval、`shell=False`、超时和脱敏边界。
- 教师测试、评分文件和保护路径不可修改或登记为 Agent 自建测试；无法构造可执行测试时进入 WAITING_INPUT。
- 不修改 Approval、Checkpoint、Provider 协议或 CLI 命令形式；旧 TaskState 缺少新可选字段时兼容加载。

### 验收

- 无测试项目可完成“创建测试→登记策略→审批执行→TEST_REPORT”闭环。
- 已有测试项目可复用并补充覆盖；策略文件、测试文件哈希或命令不匹配时零 dispatch 并返回 CODE。
- 测试失败沿用 REVIEW→CODE 重试；测试修改后必须重新登记策略。
- 识别到零测试时不能标记通过；未知数量必须明确展示为未知。
- AgentLoop、Router、Phase Gate、Policy、Approval、State、TUI 回归及全量质量门通过。

### 实施结果（2026-07-30）

- 已新增不可变 `TestStrategy`、测试文件 SHA-256、规范化 argv digest、任务级原子 `test_strategy.json` 和 CODE-only `record_test_strategy`。
- `TaskState.test_strategy_digest` 为向后兼容可选字段；CODE Gate 同时要求源码修改和已登记策略，旧 TEST 任务缺策略时先服从失败/Rollback 路由，否则自动返回 CODE。
- TEST 上下文只暴露已登记命令、框架、测试文件和覆盖映射；执行前校验状态摘要、策略摘要、命令 argv、测试文件哈希和保护路径，失败时零 dispatch 并回 CODE。
- Agent 可通过既有 `write_file`/`edit_file` 创建或补充测试，继续经过 Source Write Checkpoint/Approval；测试执行继续经过 RUN_TESTS Approval。
- 标准输出明确报告 `no tests ran`、`collected 0 items` 或 `0 tests` 时归类为 `no_tests`，不能标记通过。
- Application Service/TUI 只读投影新增“测试策略已登记/未登记”；Mock Demo 已迁移为复用并登记现有 unittest。
- Review 收敛：`record_review` 成功即写入 `REVIEW.md` 状态并自动完成 Review；失败测试回到 CODE，成功测试进入 DELIVER，不再依赖模型额外调用 `finish_phase`。
- Review 无进展保护：重复读取同一证据第一次仅回灌纠错提示，第二次以 `review_progress_stalled` 阻塞；Provider/Parse 历史错误不会污染后续 `max_steps_exceeded`。
- 测试环境反馈：测试策略登记检查首个 argv 可解析性；Provider Context 公开只读运行环境摘要；命令启动、WSL 服务和权限类失败归类为 `environment_error`，不保存完整输出。
- 本轮验证：相关回归 `151 passed`；兼容回归 `14 passed`；全量 `1436 passed, 17 skipped`；Ruff 与 MyPy（124 个源码文件）通过，`git diff --check` 通过。`uv build --offline` 仍因本地缓存缺少 `setuptools>=68` 未通过。
- 恢复后新鲜验证：S10 相关 `300 passed`；最终全量 `1427 passed, 17 skipped, 1 failed`，唯一失败为实施前已有的 `max_trace_events` 实际默认 `1000` 与旧测试期望 `40` 不一致；Ruff 全仓通过；MyPy `124` 个源码文件通过；`git diff --check` 通过。
- `uv build --offline` 未通过：任务专属空缓存无法解析 `setuptools>=68`；`--no-build-isolation` 也因当前虚拟环境未安装 `setuptools` 失败。未联网安装依赖，未改变锁文件。

---

## S10-R1：测试失败诊断与自主修复闭环

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已实现；离线构建受本地 `setuptools>=68` 缓存缺失阻断 |
| 分支 | `codex/agent-test-strategy` |
| 依赖 | S10 |
| 范围 | TEST 失败证据、REVIEW 修复决策、CODE 定向修复、原策略复测与无进展保护 |
| 开发方式 | Core 行为变更；按用户授权先实现、后补回归验证（不采用 TDD） |

### 行为契约

- 失败测试生成任务级、脱敏、有摘要绑定的 `test_failure.json`；Agent 通过独立 `record_remediation` 提交修复目标，不再用 `record_review` 兼任失败修复。
- `modify_source`、`modify_test`、`replace_test_strategy`、`rerun_for_diagnosis`、`request_input` 与 `rollback` 使用确定性分流；测试通过后才允许 `record_review` 完成最终审查。
- 修复决策必须绑定当前 failure digest；源码/测试修复只能写入声明且未受保护的路径，策略替换必须重新登记真实可执行命令。
- 自主修复在真正应用时消耗一次 retry budget；诊断复测和人工输入不消耗预算。重复失败通过规范化 fingerprint 判定并在无进展时停止空转。
- Windows runner 输出按字节安全解码；WSL/Git Bash 权限和启动失败归类为 `environment_error`，不得误导 Agent 修改业务源码。
- 旧任务缺少新字段时兼容加载；旧失败报告在 resume 时生成受限 legacy failure，不手工改写 state、报告或测试策略。
- Provider、Approval、Checkpoint、受保护文件与单 argv `shell=False` 边界保持不变；不自动安装依赖、修改系统权限或切换 Provider。

### 验收

- assertion failure 可完成“失败记录→modify_source→审批修改→绑定策略复测→通过”闭环。
- 测试文件修复会使旧策略失效并要求重登；受保护测试零写入拒绝。
- WSL/Git Bash `E_ACCESSDENIED` / `WinError 5` 被识别为环境错误，并可安全切换到已安装的项目原生 runner。
- stale remediation、越界路径、伪造内部记录和损坏摘要均 fail-closed。
- 同一 failure fingerprint 第一次重复进入 REVIEW，第二次进入 WAITING_INPUT 或明确 BLOCKED，不无限读取证据。
- task-001 fixture 可在不手工修改 state 的前提下完成 legacy 失败建档与恢复。
- AgentLoop、Router、Phase Gate、Policy、Provider Schema、State、Context、TUI 只读投影、Mock Demo 和全量质量门均有新鲜验证证据。

---

## S11-R1：Action 与文件 Tool 通用失败恢复闭环

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已实现；全量质量门与离线构建通过 |
| 分支 | `codex/s11-recovery-core` |
| 依赖 | S10-R1 |
| 范围 | Action ParseError、白名单 Policy denial、五个文件 Tool 失败的持久化防循环 |
| 开发方式 | 逐个行为 RED → GREEN → 回归验证 |

### 行为契约

- 首次同类失败允许修正，第二次强制更换 Action，第三次立即 `BLOCKED`；不同失败指纹开始新轮次，`max_steps` 仅作外层保险。
- Action 摘要不包含 `reason`；活动失败和重复次数保存到 state v1 的可选字段，Resume 后不清零。
- Provider 成功返回已解码对象后清零 Provider 连续失败计数；后续 `parse_action()` 失败只使用 S11 恢复阶梯。
- 只为 `read_file`、`list_files`、`search_text`、`write_file`、`edit_file` 补充稳定错误码和恢复接入；写结果无法确定时继续立即 `INCONSISTENT`。
- 修正后的普通 Action 必须重新经过 Phase Gate、Tool/Path Policy、Approval 和 Checkpoint；无关成功不清理活动失败。

### 文件边界

- 通用失败模型、TaskState 可选字段与恢复协调器。
- AgentLoop 的 Parse、Policy、文件 Tool 失败入口、Policy 前 guard 与共享成功后处理。
- ToolRegistry 和五个文件工具的稳定 `error_code`。
- 相关单元/集成测试、`docs/PLAN.md` 与 `docs/AGENT_LOG.md`。

### 非目标

- 不引入 RecoveryDecision、Recovery Ledger、CAS/state revision、全局恢复预算、新配置项或完整 ProgressDetector。
- 不迁移测试专用修复、RecoveryService、Approval 拒绝防循环或 Provider 错误类型。

### 验收

- 相同 Parse、Policy 或文件 Tool 失败第三次在 `max_steps=100` 下仍提前阻断，且被 guard 的 Action 零 Policy/零 dispatch。
- 仅修改 `reason` 不能绕过 guard；合法新目标仍经过现有 Approval/Checkpoint 安全链。
- 活动失败、重复次数和恢复模式可跨 AgentLoop Resume 重建；匹配的成功动作后清理。
- 写入效果未知、State/Checkpoint 持久化异常不降级为自主重试。
- 聚焦回归、全量 pytest、Ruff、MyPy、离线 build 和 `git diff --check` 均以本轮新鲜结果记录。

### 实施结果（2026-08-02）

- 新增不可变 `FailureRecord` 与 `RecoveryCoordinator`，统一 Action ParseError、白名单 Policy denial 和五个文件 Tool 失败的指纹、重复计数、恢复模式、活动状态与脱敏 Observation。
- `TaskState` 保持 schema v1，新增可选 `active_failure` 并严格校验；Resume 可重建活动失败，`BLOCKED` 状态不会再次调用 LLM；成功动作按保守匹配清理活动失败。
- Action digest 只包含 `type`、`phase`、`tool_name`、`args`，排除 `reason`；第二次重复 Action 在 Policy 前拦截，第三次同类失败提前阻塞。
- `ToolResult.error_code` 向后兼容；Registry 与五个文件工具补充稳定错误码，未知写入效果继续沿用既有 `INCONSISTENT` fail-closed 路径。
- AgentLoop 保留既有测试专用修复、Approval、Checkpoint、RecoveryService 与 Provider 协议重试路径，仅在 S11-R1 范围接入统一失败闭环。
- 新鲜验证：聚焦回归 `244 passed, 2 skipped in 6.30s`；全量 `1465 passed, 17 skipped in 108.13s`；Ruff `All checks passed!`；MyPy `Success: no issues found in 130 source files`；`git diff --check` 通过；`uv build --offline` 成功生成 sdist 与 wheel。
- 验证临时目录、`dist/`、`build/` 和 `src/hancode.egg-info/` 按用户要求保留；未提交、未推送。

---

## S12-R1：TUI 协作式安全暂停

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已实现；全量质量门受既有工作区收集/静态问题阻断 |
| 分支 | `main`（用户明确指定） |
| 依赖 | S11-R1、S5-R2 TUI Operation 边界 |
| 范围 | 当前 TUI 会话内的协作式暂停与既有 `/resume` 恢复 |
| 开发方式 | Core → Runtime → Application → TUI 的逐行为 RED → GREEN → 回归 |

### 行为契约

- 新增单次运行级、线程安全的内存 `PauseToken`；`/pause` 和操作菜单只请求暂停，不取消 Provider、测试或工具进程。
- AgentLoop 只在安全点暂停：Provider 调用前、解析后的 Policy/Approval/Checkpoint/dispatch 前、已批准 Action 或 Rollback 前，以及完整工具操作后的下一轮入口。
- 达到安全点先将 `TaskStatus.PAUSED` 持久化，再记录 `run_paused` Trace；任一持久化失败均 fail-closed 为 `INCONSISTENT`。
- 普通 run 遇到 PAUSED 零 Provider、零工具并返回 `task_paused`；`/resume` 将其转回 RUNNING、记录 `run_resumed` 后沿既有 Router 继续。
- TUI 以 request ID 绑定活动 Token；暂停请求期间保持 busy，只有 Worker 返回 PAUSED 后才解除 busy。迟到 Worker 不得清除新运行的 Token。

### 非目标

- 不支持跨进程、跨 TUI 会话、任务目录 marker 或 CLI `task pause`。
- 不实现硬停止、Textual Worker cancel、Provider/测试/工具进程终止或取消暂停请求。
- 不在 Checkpoint—dispatch 原子区间、State/Trace 持久化或工具执行中间暂停。

### 验收

- State/Router 覆盖 PAUSED 序列化、普通 run 零执行、`resumable=True` 与 resume 转回 RUNNING。
- AgentLoop 覆盖调用前、Provider 返回后、已批准 Action/Rollback 前及工具完成后的协作式暂停；无 Token 行为保持不变。
- TUI 覆盖 `/pause`、菜单启用、重复请求、非运行拒绝、busy 等待、安全请求隔离，且不调用 Worker cancel。
- 聚焦测试、全量 pytest、Ruff、MyPy、既有构建门禁与 `git diff --check` 留存本轮新鲜证据；同步 SPEC、架构、TUI 使用说明和 AGENT_LOG。

---

## S13：Task-scoped Persistent Runtime Memory

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] R0–R5 已完成；全量质量门通过 |
| 目标分支 | `codex/task-runtime-memory` |
| 依赖 | S11-R1 通用失败恢复、S12-R1 安全暂停、T19 ContextBuilder |
| 主贡献 | Task-scoped runtime memory + deterministic feedback + reversible coding state |
| 总范围 | 当前 task 的工具摘要、内容寻址快照、跨进程恢复、确定性 Context 注入和按需检索 |

### 问题与成功标准

当前 AgentLoop 只把本轮 observation 临时放入下一次 Prompt；后续 observation 会覆盖它，resume 也不会恢复完整工具结果。Trace 为审计而省略正文，`project_memory.md` 则是人工维护的跨任务背景，二者都不能承担 task runtime memory。

S13 保持 Provider 无状态，由 Harness 自动记录当前 task 已执行工具的安全结果。成功标准是：模型在多轮及跨进程 resume 后仍能获得最近行为、已读文件索引和少量热点正文；未自动注入的历史可通过只读 Memory Tool 恢复；写入、rollback 和外部文件变化不会让旧快照冒充当前文件；最终 Prompt 始终受统一预算约束。

### 冻结边界

- `project_memory.md` 继续由人维护，不自动接收 task memory；不实现 Durable Facts 晋升或跨 task / 跨项目共享。
- 不保存完整 conversation history，不在 Provider 内追加消息，不使用数据库、pgvector、embedding、向量检索或 LLM 自动压缩/总结。
- `state.json` 保持 schema v1，不放入大体积 memory 字段；`memory/`、trace、checkpoint 和阶段产物继续各自承担独立职责。
- Memory blob 只能来自 `read_file`、`list_files`、`search_text`、`get_diff` 已经完成路径治理和脱敏的 ToolResult；Recorder 不重新读取原始文件生成 blob。
- Memory 不进入 `hancode export`、交付产物或默认 Git 提交范围；MVP 不新增专用 Memory TUI 浏览器。

### 统一数据与接口契约

任务目录新增惰性创建的：

```text
.hancode/tasks/<task_id>/memory/
├── index.json
├── events.jsonl
└── blobs/<sha256>.txt|json
```

`events.jsonl` 是 append-only 权威记录；`index.json` 是可由合法事件前缀恢复的派生索引。每条 `MemoryRecord` 固定包含 `schema_version`、`memory_id`、`seq`、`task_id`、`phase`、`kind`、`tool_name`、`success`、安全摘要、`error_code`、规范化路径、blob 引用/摘要/大小/媒体类型、`workspace_generation`、`checkpoint_id`、`invalidates` 和记录摘要。`stale` 由事件重放得出，不回写旧记录。

核心接口：

```python
class MemoryStore(Protocol):
    def ensure_capacity(self, task_id: str, *, reserved_bytes: int) -> None: ...
    def record_tool_result(
        self, task_id: str, *, phase: Phase, action: Action,
        result: ToolResult, observation: object, state: TaskState,
    ) -> MemoryRecord: ...
    def record_rollback(
        self, task_id: str, *, phase: Phase, result: RollbackResult,
        observation: object, state: TaskState,
    ) -> MemoryRecord: ...
    def read(self, task_id: str, memory_id: str, *, start_line: int, end_line: int) -> MemorySlice: ...
    def search(self, task_id: str, query: MemoryQuery) -> tuple[MemorySearchHit, ...]: ...

class MemoryContextPacker(Protocol):
    def build(self, *, task_id: str, phase: Phase, state: TaskState,
              observation: object | None) -> MemoryContext: ...
```

`ContextBuilder.build()` 增加可选 `observation`，在内部合并 phase context、observation 和 `MemoryContext` 后统一执行 `max_context_chars` 预算。AgentLoop 不再在 ContextBuilder 返回后追加 observation。

新增配置及默认值：

| 配置 | 默认值 | 语义 |
| --- | ---: | --- |
| `max_memory_blob_bytes` | `1_048_576` | 单 blob 最大 UTF-8 字节数 |
| `max_memory_task_bytes` | `33_554_432` | 单 task Memory 总容量 |
| `max_memory_recent_events` | `8` | 每轮最近摘要上限 |
| `max_memory_file_entries` | `32` | 每轮有效文件索引上限 |
| `max_memory_hot_contents` | `2` | 每轮热点文件正文上限 |

旧配置缺少这些字段时使用默认值；新模板和配置中心使用同一默认值真源。`max_memory_task_bytes` 统计 `events.jsonl`、`index.json` 和全部 blob 的实际文件字节，不计同目录原子临时文件；Memory 有界且不自动删除历史，超限返回 `memory_blob_too_large` 或 `memory_quota_exceeded`。

### S13-R0：文档契约冻结

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已完成 |
| 开发方式 | 用户明确不采用 TDD；只做文档一致性检查 |
| 允许修改 | `docs/SPEC.md`、`docs/PLAN.md`、`docs/AGENT_LOG.md` |

验收：

- SPEC 将 runtime memory、反馈闭环、可回退状态列为三项并列主贡献。
- 明确 Project Memory、Task Runtime Memory、Trace、Checkpoint 和 TaskState 的职责边界。
- 冻结存储格式、公开接口、预算顺序、失效语义、错误状态、配置默认值、后续任务依赖和非目标。
- SPEC 与活动计划无“memory 只是最低支撑维度”等冲突表述；AGENT_LOG 保留实施前的历史边界。Git diff 只新增三份目标文档的 R0 改动，不覆盖用户已有测试修改。

### S13-R1：Memory 领域模型、配置与 Filesystem Store

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已实现；全量质量门与离线构建通过 |
| 依赖 | S13-R0 |
| 开发方式 | RED → GREEN → REFACTOR |

范围：新增不可变 Memory 模型和严格 schema；实现 blob 内容寻址、事件追加、index 原子替换、配额、task identity、序号/摘要校验、链接防护和跨进程加载；配置模板、ConfigLoader 与配置中心同步五个字段。

允许修改：新增 `src/hancode/core/memory.py`、`src/hancode/storage/memory.py` 和对应新测试；修改 `core/config.py`、`core/project_config.py`、`interfaces/tui/config_presenters.py`、项目配置模板及既有 config 测试；同步 `docs/PLAN.md`、`docs/AGENT_LOG.md`。配置页面只有在 Red 证明 presenter 不能自动覆盖新增字段时才允许做最小相邻修改。

原子顺序固定为 blob 临时写入/替换 → event append + flush/fsync → index 同目录原子替换。崩溃留下的新建未引用 blob应在本次失败补偿中删除；合法事件比 index 更新时允许补建并产生 `memory_index_recovered` 审计信号；非法 index、损坏事件、缺失 blob 或摘要不符返回 `memory_corrupt`。

Red 测试至少覆盖：严格 round trip、相同内容两事件一 blob、旧 task 惰性初始化、合法落后 index 恢复、非法身份/序号/摘要、缺失 blob、symlink/junction、单 blob 和总配额、旧配置兼容及模板/UI 默认值一致。

实施结果（2026-08-04）：

- 新增不可变 `MemoryBlob`、`MemoryRecordDraft`、`MemoryRecord`、`MemoryIndex`、`MemorySnapshot` 与 Load/Append Result；严格校验 schema、ID/seq、POSIX 相对路径、blob 四元组、generation、失效目标和 canonical SHA-256。
- 新增 `FilesystemMemoryStore.load/append/ensure_capacity`；以 `events.jsonl` 为权威重放，使用轻量派生 index、内容寻址 `.txt/.json` blob、flush/fsync 与同目录原子替换，支持跨实例恢复和 `memory_index_recovered`。
- 新 blob 已写但 event 未提交时补偿未引用 blob；event 已提交而 index 首次替换失败时立即重放恢复。非法 index、缺失/篡改 blob、事件身份/序号/摘要漂移和权威日志缺失统一 fail-closed。
- task Memory 路径逐层拒绝 symlink、junction/reparse point；配额按 UTF-8 blob 字节及 prospective events/index/blob 实际字节计算，去重内容不重复计费，既有超限数据仍可只读加载。
- 五项配置接入 `PROJECT_CONFIG_DEFAULT_ITEMS`、`HanCodeConfig`、ConfigLoader 与“运行时记忆”配置分组；旧配置只在内存补默认值，ConfigScreen 复用通用 presenter，无需相邻页面改动。
- TDD 聚焦回归 `127 passed`；全量 pytest `1518 passed, 17 skipped in 147.62s`；Ruff 全仓通过；MyPy `133` 个源码文件无错误；`uv build --offline` 成功生成 sdist/wheel；`git diff --check` 通过。
- Windows 受限沙箱的 pytest basetemp 和默认 uv cache 曾分别触发 `WinError 5`；使用同一命令在沙箱外重跑后通过。按用户要求未清理 `.tmp/hancode-s13-r1/`、`dist/` 或 `src/hancode.egg-info/`，清理由用户自行执行。

### S13-R2：Recorder、Mutation 与 Rollback 一致性

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已实现；全量质量门与离线构建通过 |
| 依赖 | S13-R1 |
| 开发方式 | RED → GREEN → REFACTOR |

将 `MemoryStore` 接入 Filesystem AgentLoop ports 和 Engine。执行顺序固定为 dispatch → FeedbackBuilder → Memory persist → observation 附 `memory_ref` → trace。所有真正 dispatch 的工具产生元数据摘要；摘要不得包含正文、stdout、stderr、command、Action args 或 reason。

允许修改：`src/hancode/runtime/agent_loop.py`、`src/hancode/runtime/engine.py`、S13-R1 的 Memory 模型/Store，以及 AgentLoop、adapter、Approval resume 和 rollback 的直接回归测试；同步 `docs/PLAN.md`、`docs/AGENT_LOG.md`。不得顺带改写 Provider、Phase Router 或现有 Recovery 状态机。

`read_file` 建立 `latest_by_path` 文件快照；其他白名单 blob 仅作为可检索 payload。成功 `write_file`/`edit_file`、`mutation_applied=None` 和成功 rollback 追加 invalidation、增加 generation 并保留历史 blob。mutation 前预留最大元数据事件空间；只读结果持久化失败为 `BLOCKED`，已成功 mutation/rollback 后失效失败为 `INCONSISTENT`。

Red 测试至少覆盖：全工具摘要、四类 blob allow-list、memory_ref、无正文 Trace、write/edit 失效、未知写入效果、rollback 失效、Approval resume exactly-once、持久化异常的 BLOCKED/INCONSISTENT 分流以及 Memory 故障后零 Provider 继续调用。

实施结果（2026-08-04）：

- `FilesystemAgentLoopPorts` 与 `Engine` 注入单一 `FilesystemMemoryStore`；AgentLoop 和 approved Action 均要求显式 MemoryStore，不引入静默 no-op 实现。
- 正常工具执行固定为 dispatch → FeedbackBuilder → `record_tool_result()` → observation `memory_ref` → Trace；恢复后的失败 observation 继续保留同一 memory_ref。
- Recorder 仅从已完成的 ToolResult 生成安全摘要：`read_file` 写文本快照并更新文件映射，`list_files`、`search_text`、`get_diff` 写 canonical JSON payload；普通工具只写元数据。Trace 只保留计数、状态、Memory ID、摘要和 generation，绝不写正文、stdout/stderr、命令或 Action 参数。
- 成功 write/edit 与 `mutation_applied=None` 生成失效事件；路径型失效在没有已有 read 快照时仍增加 generation。成功 rollback 按已恢复路径失效当前快照并写 rollback 审计字段。
- 写入前按固定保留额预检 Memory 配额；只读记录失败进入 BLOCKED 并停止 Provider；成功或效果未知的写入、成功 rollback 的失效记录失败进入 INCONSISTENT。已知无 mutation 的 checkpointed write 在阻断前严格 abort/reload checkpoint 状态。
- 新增/更新 Memory Store、AgentLoop、反馈、Provider 失败和课程保护回归；聚焦回归 `189 passed`，全量 pytest `1528 passed, 17 skipped in 192.76s`；Ruff `All checks passed!`；MyPy `Success: no issues found in 133 source files`；`uv build --offline` 成功生成 sdist/wheel。
- Windows 受限 sandbox 的短窗口曾在 120 秒前终止全量 pytest；使用同一专属 basetemp 与延长窗口重跑后通过。按用户要求保留 `.tmp/hancode-s13-r2/` 及本轮构建产物，清理由用户自行执行。

### S13-R3：Memory Context Packer 与统一预算

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已完成；Windows approval 重试修复保留，全量门禁通过 |
| 依赖 | S13-R2 |
| 开发方式 | RED → GREEN → REFACTOR |

自动注入最近事件摘要、最新有效文件索引和最多两个 `read_file` 热点正文。热点排序固定为 `state.files_changed` 路径优先、同 phase、较新 seq、路径字典序；当前 observation 或 `source_snippets` 已包含的正文不得重复注入。

允许修改：新增 `src/hancode/runtime/memory.py`；修改 `src/hancode/runtime/context.py`、`src/hancode/runtime/agent_loop.py`、`src/hancode/runtime/engine.py`、`src/hancode/tooling/file_tools.py`、`src/hancode/storage/memory.py` 和对应 context/file-tool/AgentLoop/Memory Store 测试；同步 `docs/PLAN.md`、`docs/AGENT_LOG.md`。`engine.py` 负责装配 Packer，`storage/memory.py` 只新增按 task ID 与 memory ID 的已验证 blob 读取，二者均为 R3 接线所必需的最小边界。为修复本任务全量验证中稳定复现的 Windows approval manifest `os.replace` 短暂锁竞争，额外允许最小修改 `src/hancode/storage/approvals.py` 及其直接回归测试；只重试 Windows `PermissionError`，不改变其他 approval 语义。安全指纹探针只返回摘要，不新增任意文件读取接口。

在热点注入及后续有效检索前，复用 file tool 的路径/敏感文件边界，只计算当前脱敏内容 SHA-256。缺失、摘要变化或路径变为不安全时追加 invalidation；探针不把正文返回给 Memory 层。

统一预算保留顺序为：最小骨架与 phase 必需证据 → 当前 observation → 活动失败与最近人工回答 → memory 摘要/索引 → 热点正文 → 其他可选项目上下文。按相反顺序裁剪；最终 canonical JSON 必须 `<= max_context_chars`，无法容纳最小骨架时返回 `context_budget_too_small`。

Red 测试至少覆盖：跨三个工具步骤仍记住首个文件、跨 AgentLoop 实例恢复、热点排序/去重、内部和外部变化排除 stale、不同 task 隔离、超大 observation + memory 的最终预算以及最小预算失败。

实施结果（2026-08-04）：R4 开始前修复统一预算中可选项目上下文晚于 Memory 热点裁剪的顺序回归；R3 聚焦 `180 passed`，全量 pytest `1533 passed, 17 skipped in 128.22s`，Ruff、MyPy、离线 build 与 `git diff --check` 通过。既有 approval Windows `PermissionError` 短暂锁竞争重试修复保持不变。

### S13-R4：`memory_read` 与 `memory_search`

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已完成；R3 前置与 R4 全部质量门通过 |
| 依赖 | S13-R3 |
| 开发方式 | RED → GREEN → REFACTOR |

两个工具在所有 phase 可用，均为只读、无需 Approval/Checkpoint，且只能访问 Registry 绑定的当前 task：

允许修改：新增 `src/hancode/tooling/memory_tools.py`；修改 `src/hancode/core/memory.py`、`src/hancode/storage/memory.py`、`src/hancode/runtime/memory.py`、`src/hancode/runtime/agent_loop.py`、`src/hancode/tooling/factory.py`、`src/hancode/core/tool_specs.py`、`src/hancode/core/actions.py`、`src/hancode/policy/tool_policy.py`，以及 Memory Tool、Memory Store、AgentLoop、Feedback、parser、policy、registry/factory 和 Provider Catalog 的直接回归测试；同步 `docs/PLAN.md`、`docs/AGENT_LOG.md`。保留 R3 的 approval Windows 重试修复。不得修改 Provider 实现、Checkpoint/Rollback、TaskState schema、Trace schema、export、TUI 或 Context 预算策略，不得增加通用路径参数或绕过现有 ToolPolicy。

- `memory_read(memory_id, start_line=1, end_line=200)`：最多 200 行，输出受 `max_observation_bytes` 约束；允许读取 stale 历史，但必须返回 stale、失效原因、generation 和“不可视为当前文件”的标记。
- `memory_search(query, path=None, phase=None, include_stale=False, limit=5)`：`limit` 仅允许 1–20；只搜索当前 task 的摘要与 blob。排序依次为有效记录、路径命中、摘要命中、正文命中、同 phase、较新 seq、memory ID。

Memory Tool 自身只记录访问摘要，不复制 blob。先将 R3 的 freshness 检查提取为 `MemoryFreshnessChecker`，供 Packer、`memory_read` 和 `memory_search` 复用；一次调用最多追加一条批量 invalidation，持久化或完整性失败必须 fail-closed。

纵向切片与验收顺序：

1. `memory_read` 当前 task 文本 blob tracer bullet。
2. stale 内部失效、外部 fingerprint 变化及权威性警告。
3. JSON 确定性格式化分页、200 行限制、超大单行和精确输出预算。
4. `memory_search` 摘要、路径、正文匹配及固定排序。
5. stale 默认排除/显式包含、phase/path 过滤和 task 隔离。
6. `memory_access` Recorder 元数据，无 blob、query 或正文。
7. ToolSpec、ActionParser、Policy、Registry 与 Provider Catalog 在所有 phase 一致。
8. blob 损坏、task identity/link 错误和 freshness 写入失败在再次调用 Provider 前进入 `BLOCKED`。
9. 跨 AgentLoop 实例恢复后 `memory_search` → `memory_read` 可取回 R1-R3 历史。

最终验证：R3/R4 Memory 聚焦回归；ActionParser、ToolPolicy、Registry/factory、Provider Catalog、AgentLoop 与 Feedback 回归；全量 pytest、Ruff、MyPy、离线 build 和 `git diff --check`。只有 R3 前置门禁与 R4 全部新鲜验证通过后才标记完成。

实施进度（2026-08-04）：

- 新增不可变 `MemoryQuery`、`MemorySlice`、`MemorySearchHit`，Store 提供 task-bound `read()`/`search()`；读取时验证 blob，JSON 确定性 pretty-print 后分页，搜索使用 Unicode `casefold()` 子串与冻结排序。
- 新增共享 `MemoryFreshnessChecker`，R3 Packer、`memory_read`、`memory_search` 复用单次批量失效；stale 历史可读但明确非权威，完整性与 freshness 写入错误穿透 Registry 并在 AgentLoop 中直接 `BLOCKED`。
- 两工具由 ToolSpec 自动进入 Parser、Policy 与 Provider Catalog；默认 Registry 仅在 task-bound 配置中注册。Memory access Recorder 只写目标/行范围/stale 或命中 ID/error code，不复制 blob、query 或正文。
- 跨独立 AgentLoop 实例的 `memory_search` → `memory_read` 恢复回归通过。当前 R3/R4、parser、policy、registry/factory、catalog、AgentLoop 与 Feedback 聚焦回归为 `309 passed`；Ruff 全仓通过；MyPy `135 source files` 无错误。最终全量 pytest、离线 build 与 diff check 待文档同步后执行。
- 最终验证：全量 pytest `1575 passed, 17 skipped in 101.73s`；Ruff `All checks passed!`；MyPy `Success: no issues found in 135 source files`；`uv build --offline` 成功生成 sdist/wheel；`git diff --check` 通过。R3 前置门禁与 R4 新鲜验证均满足，S13-R4 标记完成。

### S13-R5：端到端 Demo、文档同步与质量门

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已完成；Mock Demo、文档与质量门通过 |
| 依赖 | S13-R4 |
| 开发方式 | RED → GREEN → REFACTOR；最后人工文档审查 |

MockLLM Demo 固定演示：读取 A(v1) → 其他工具调用 → 销毁并恢复 AgentLoop → 自动获得 A 索引/热点 → `memory_search/read` → 写入 A(v2) 使 v1 stale → 测试失败反馈 → rollback → v2 保留为历史但不自动注入 → 重新读取得到 v1。

允许修改：`src/hancode/demo_support/runner.py`、直接相关 Mock Demo 测试、`README.md`、`docs/系统架构.md`、配置说明、`docs/PLAN.md`、`docs/AGENT_LOG.md`；若 export 回归证明 allow-list 漂移，只允许在既有 export 模块和对应测试做最小修复。

同步 README、系统架构、配置说明和 AGENT_LOG；确认 export allow-list 不包含 `memory/`。最终运行 S13 聚焦回归、全量 pytest、Ruff、MyPy、`uv sync --locked --extra dev`、离线 build、Mock Demo 和 `git diff --check`，并记录本轮新鲜结果、环境阻断和未完成风险。

实施结果（2026-08-04）：

- MockLLM Demo 在首个阶段读取 `src/calculator.py` 初始快照；首轮测试失败后由新 AgentLoop resume，通过 task-bound `memory_search`/`memory_read` 恢复当前 v2；每个 stage 都重新创建 AgentLoop，继续使用同一 Filesystem Memory。
- 首次 source write 后再次读取 calculator v2，后续测试失败与自动 rollback 使 v1/v2 都保留为 stale 历史；rollback 后显式读取 v1，默认检索不再返回 stale v2，Context 也不会把它当作当前文件。
- Memory Tool 访问只落 `memory_access` 元数据，未复制 query 或 blob；新增 Demo 回归同时验证跨阶段恢复、stale 映射、历史正文和 export allow-list 不包含 `memory/`。
- README 与系统架构同步 `.hancode/tasks/<task>/memory/` 结构、五项 Memory 配置、stale 语义和离线 Demo 流程；`export` 的六项 artifact allow-list 保持不变。
- R5 聚焦回归 `67 passed`；`uv sync --locked --extra dev` 成功；Mock Demo 脚本与 `hancode demo --provider mock` 均返回 `completed`；`uv build --offline` 成功生成 sdist/wheel。
- 全量 pytest 中间一次为 `1575 passed, 17 skipped`，重复 Demo 在既有审批消费的 `state.json` 原子替换处出现 `state_write_error`；4 次独立工作区复现全部完成，当前代码最终全量为 `1576 passed, 17 skipped in 166.98s`。文档同步后的全仓 Ruff、MyPy 与 `git diff --check` 均通过，证据已回填 AGENT_LOG；该 Windows 文件锁竞争仍是环境层低频风险，未纳入 R5 越界修复。

### S13-R6：文件快照正确性与热点连续性

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已完成；专项测试与相关静态检查通过 |
| 依赖 | S13-R5 |
| 开发方式 | 直接实现后补回归测试；本任务不采用 TDD |

目标：同一路径被再次读取时，旧快照在查询视图中确定性标记为 superseded/stale，但不增加 workspace generation；写入或 rollback 后历史快照继续保持 stale。经过 freshness 检查的 `latest_by_path` 是当前文件权威来源，无关路径 mutation 不得仅因全局 generation 变化移除当前热点正文。

允许修改：`src/hancode/core/memory.py`、`src/hancode/storage/memory.py`、`src/hancode/runtime/memory.py`、直接相关 Memory 模型/Store/Tool/Context 测试，以及 `docs/PLAN.md`、`docs/AGENT_LOG.md`。不得在本任务实现 blob 读取优化、崩溃恢复、compaction、长单行续传或 recent event 分层。

实现约束：`superseded_by` 由既有 append-only event 重放派生，不修改持久化 `MemoryRecord` schema，不追加 supersession event，也不增加 generation。`memory_read` 与 `memory_search` 将 superseded 和 invalidated 统一视为 stale；显式 `include_stale=True` 仍可恢复历史。热点资格依赖 freshness 检查后的当前映射和文本媒体类型，不再要求 record generation 等于全局 generation。

回归测试至少覆盖：连续读取同一路径后旧快照 stale、默认搜索排除旧快照、显式搜索和读取可恢复旧正文、写入后同路径两份快照均 stale，以及读取 A 后写入 B 时 A 仍保留在 file index 与 hot contents。

专项验证：Memory 模型、Store、Tool、Context 测试；相关 Ruff、MyPy 与 `git diff --check`。按用户要求，本任务不运行全量 pytest、全仓静态检查或 build，全部后续小任务完成后统一执行最终质量门。

实施结果（2026-08-04）：

- `_validate_replay()` 重放时派生 `superseded_by`：某路径出现新的成功 `read_file` 快照时，把该路径上一份 current 快照记入 `superseded_by`，不增加 generation、不新增事件、不改持久化 schema。`MemorySnapshot` 增加派生字段 `superseded_by`。
- `MemorySlice`、`MemorySearchHit` 增加 `superseded_by`；`read()`/`search()` 将 invalidated 或 superseded 统一视为 stale，superseded 场景 `invalidation_reason="superseded"`、`current_file_authoritative=False`；`memory_read`/`memory_search` 输出同步暴露 `superseded_by`。默认搜索排除 superseded 快照，`include_stale=True` 仍可恢复历史正文。
- `MemoryContextPacker` 热点资格与 `hot_eligible` 移除 `record.workspace_generation == generation` 限制，只依赖 freshness 检查后的 `latest_by_path`、文本媒体类型和去重条件；无关路径 mutation 抬升 generation 后当前文件仍保留在 file index 与 hot contents。
- 新增回归：同路径重复读取旧快照 stale 且 generation 不变、写入后同路径全部快照 stale、默认搜索排除 superseded、显式搜索/读取恢复旧正文、读取 A 后写入 B 时 A 仍 hot。因新增字段增大最小元数据，`test_memory_read_enforces_line_and_exact_utf8_output_budgets` 预算由 500 调整为 550，截断语义不变。
- 专项验证：`tests/test_memory_models.py tests/test_memory_store.py tests/test_memory_tools.py tests/test_memory_context.py` 55 passed；相关 Ruff、MyPy 通过；`git diff --check` 仅 LF/CRLF 提示，无空白错误。按用户要求本任务未跑全量门禁。

### S13-R7：Verified Blob 单次读取与单次加载搜索

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已完成；专项测试与相关静态检查通过 |
| 依赖 | S13-R6 |
| 开发方式 | 直接实现后补回归测试；本任务不采用 TDD |

目标：消除 verified blob 的 TOCTOU 重复读取窗口，返回的字节必须与刚完成 SHA-256 校验的字节一致；让一次 `read()`/`search()` 请求只执行一次 `load()`，同一请求内相同内容寻址 blob 只读取和哈希一次。

允许修改：`src/hancode/storage/memory.py`、直接相关 Memory Store/Tool/Context 测试，以及 `docs/PLAN.md`、`docs/AGENT_LOG.md`。不得改动崩溃恢复、compaction、长行续传、recent 分层或公开 Memory Tool 输出协议。

实现约束：新增内部 `_read_verified_blob()`，单次读取后校验长度与摘要并直接返回该字节；`read_blob_bytes()` 校验后不再二次读取路径。`read()` 只加载一次并直接读取已验证 blob；`search()` 入口只 `load()` 一次，循环使用请求内 `dict[blob_ref, bytes]` 缓存。缺失、篡改、symlink、junction 仍统一 fail-closed。

专项验证：Memory Store、Tool、Context 测试；相关 Ruff、MyPy 与 `git diff --check`。按用户要求本任务不运行全量门禁。

实施结果（2026-08-04）：

- 新增 `_read_verified_blob()`：单次 `read_bytes()` 后校验长度与 SHA-256 并返回该字节，`_validate_blob()` 改为其只校验包装。`read_blob_bytes()` 校验后不再二次读取路径，消除 TOCTOU 窗口。
- `read()` 只 `load()` 一次并直接读取已验证 blob，不再经 `read_blob_bytes()` 触发第二次 `load()`；`search()` 入口只 `load()` 一次，循环用请求内 `dict[blob_ref, bytes]` 缓存，相同内容寻址 blob 在 search 循环内只读取哈希一次。
- 缺失、篡改、symlink、junction 仍统一 `memory_corrupt`/`memory_path_link_not_allowed` fail-closed。
- 新增回归：`_read_verified_blob` 返回其哈希过的字节且只读一次；`search()` 的 `load()` 恰好一次、共享 blob 读取次数为 `load` 期 N 次 + search 缓存 1 次。
- 专项验证：`tests/test_memory_store.py tests/test_memory_tools.py tests/test_memory_context.py` 49 passed；`storage/memory.py` 及三个测试文件 Ruff 通过；`storage/memory.py` MyPy 通过；`git diff --check` 仅 LF/CRLF 提示。

### S13-R8：Event Tail 与 Orphan Blob 崩溃恢复

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已完成；专项测试与相关静态检查通过 |
| 依赖 | S13-R7 |
| 开发方式 | 直接实现后补回归测试；本任务不采用 TDD |

目标：进程在事件写入或 blob 提交后崩溃时可安全恢复——合法完整前缀加未换行不完整尾部可被截断恢复，已提交但无 event 引用的 orphan blob 可被清理；中间损坏或不可信 index 时继续 fail-closed。

允许修改：`src/hancode/storage/memory.py`、直接相关 Memory Store 测试，以及 `docs/PLAN.md`、`docs/AGENT_LOG.md`。不得改动 compaction、长行续传、recent 分层或公开 Memory Tool 输出协议。

实现约束：仅当 `index.json` 存在、合法且不超前于完整前缀时，才截断最后一条未换行的不完整 event，并产生 `memory_event_tail_recovered`；index 缺失、损坏、超前或完整前缀 replay 失败时抛 `memory_corrupt`，不依据不可信 index 截断。load 完成 replay 后计算 referenced blob 集合，仅删除严格符合内容寻址命名（64 位 hex + `.txt`/`.json`）且未被引用的普通 blob，产生 `memory_orphan_blob_removed`；symlink、junction、临时文件、非普通文件与已引用 blob 一律不动。

专项验证：Memory Store 测试；相关 Ruff、MyPy 与 `git diff --check`。按用户要求本任务不运行全量门禁。

实施结果（2026-08-04）：

- `load()` 在 `_read_records` 前调用 `_recover_incomplete_event_tail()`：仅当 `events.jsonl` 结尾缺换行且存在可信 index 时，用完整前缀 replay 加 index 匹配校验后原子截断不完整尾部，产生 `memory_event_tail_recovered`；index 缺失、task 不符、`next_seq` 与完整前缀不一致或 replay 失败一律 `memory_corrupt`。完整前缀通过 `_InMemoryEvents` 包装复用现有 `_read_records`。
- replay 成功后 `_remove_orphan_blobs()` 计算 referenced blob 集合，仅删除严格匹配 `[0-9a-f]{64}\.(txt|json)` 且未被引用的普通文件，产生 `memory_orphan_blob_removed`；symlink/junction/reparse、非内容寻址命名（如临时或杂项文件）、已引用 blob 一律不动。审计信号累加不再互相覆盖。
- 新增回归：可信 index 下截断不完整尾部并保留完整记录；index 缺失时不完整尾部 fail-closed；orphan blob 被清理而已引用 blob 和非内容寻址文件保留。
- 专项验证：`tests/test_memory_store.py` 42 passed；`storage/memory.py` 与测试文件 Ruff 通过；`storage/memory.py` MyPy 通过；`git diff --check` 无空白错误。

### S13-R10：超长单行的字节续传

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已完成；专项测试与相关静态检查通过 |
| 依赖 | S13-R8 |
| 开发方式 | 直接实现后补回归测试；本任务不采用 TDD |

目标：当单行本身超过 observation budget 时，除返回前缀外还提供 `next_byte_offset`，配合新参数 `start_byte_offset` 使 minified JSON、生成代码和超长字符串的剩余部分能被完整恢复；普通多行分页仍用 `next_start_line`。

允许修改：`src/hancode/core/memory.py`、`src/hancode/storage/memory.py`、`src/hancode/tooling/memory_tools.py`、`src/hancode/core/tool_specs.py`、直接相关 Memory 模型/Store/Tool 与 ToolSpec/parser/registry 测试，以及 `docs/PLAN.md`、`docs/AGENT_LOG.md`。不得改动 compaction、recent 分层、Context 预算策略或增加通用路径参数。

实现约束：`MemorySlice` 增加 `start_byte_offset` 与 `next_byte_offset`；`store.read` 接受 `start_byte_offset`，只对 `start_line` 的 UTF-8 字节做续传切片，落在多字节字符中间时 `memory_invalid_record` fail-closed。`memory_read` 透传 `start_byte_offset`；`_fit_memory_slice` 单行超预算时返回带 `[TRUNCATED]` 前缀并设置 `next_byte_offset` 指向下一段起点，读完该行后恢复标准行分页。ToolSpec `memory_read` schema 增加 `start_byte_offset`。

专项验证：Memory 模型、Store、Tool、ToolSpec/parser/registry 测试；相关 Ruff、MyPy 与 `git diff --check`。按用户要求本任务不运行全量门禁。

实施结果（2026-08-04）：

- `MemorySlice` 增加 `start_byte_offset`（默认 0）与 `next_byte_offset`（默认 None）。`store.read()` 接受 `start_byte_offset`，只对 `start_line` 对应行做 UTF-8 字节续传切片；offset 越界或落在多字节字符中间返回 `memory_invalid_record`。
- `_fit_memory_slice` 单行超预算时用 `_largest_fitting_prefix_chars` 计算可容纳字符前缀，返回 `content` 前缀 + `[TRUNCATED]` 并将 `next_byte_offset` 设为 `start_byte_offset + 已消费字节`；多行分页仍走 `next_start_line`，读完该行后恢复标准行分页。
- ToolSpec `memory_read` schema 增加 `start_byte_offset`（integer, minimum 0, default 0）；registry 以 `action.args` kwargs 透传，无需额外接线。
- 新增回归：超长单行按字节 offset 逐段拼回完整内容；预算测试断言单行截断时 `next_byte_offset > 0`。因新增两个整型字段增大最小元数据，`test_memory_read_enforces_line_and_exact_utf8_output_budgets` 预算 550→600，续传测试用 800。
- 专项验证：`tests/test_memory_models.py tests/test_memory_store.py tests/test_memory_tools.py tests/test_action_schema.py tests/test_action_parser.py tests/test_tool_factory.py tests/test_tool_registry.py` 135 passed；相关 Ruff、MyPy 通过；`git diff --check` 无空白错误。

### S13-R11：Recent Events 分层

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已完成；专项测试与相关静态检查通过 |
| 依赖 | S13-R10 |
| 开发方式 | 直接实现后补回归测试；本任务不采用 TDD |

目标：避免连续 `memory_read`/`memory_search` 产生的 `MEMORY_ACCESS` 记录挤掉真正有价值的 recent events（read_file、test failure、invalidation、rollback）。

允许修改：`src/hancode/runtime/memory.py`、直接相关 Context 测试，以及 `docs/PLAN.md`、`docs/AGENT_LOG.md`。不得改动存储格式、公开 Memory Tool 输出协议或 Context 预算裁剪策略。

实现约束：`recent_events` 分层——substantive 记录（`TOOL_RESULT`、`INVALIDATION`、`ROLLBACK`）取最近 `max_memory_recent_events` 条；`MEMORY_ACCESS` 单独最多保留 2 条，排在 substantive 之后。`MEMORY_ACCESS` 仍完整保留在持久化事件日志，仅从自动 Context 分流。

专项验证：Context 测试；相关 Ruff、MyPy 与 `git diff --check`。按用户要求本任务不运行全量门禁。

实施结果（2026-08-04）：

- `MemoryContextPacker.build()` 将 `recent_events` 分层：substantive 记录（`TOOL_RESULT`/`INVALIDATION`/`ROLLBACK`）取最近 `max_memory_recent_events` 条，`MEMORY_ACCESS` 单独最多保留 `_MAX_RECENT_MEMORY_ACCESSES=2` 条并排在 substantive 之后。`MEMORY_ACCESS` 仍完整保留在持久化事件日志，仅从自动 Context 分流。
- 新增回归：8 次 memory_search 访问后，read_file 仍在 recent、access 事件恰 2 条且位于 substantive 之后、持久化日志仍保留全部 8 条 access。
- 专项验证：`tests/test_memory_context.py tests/test_context_builder.py` 24 passed；`runtime/memory.py` 与 Context 测试 Ruff 通过；`runtime/memory.py` MyPy 通过；`git diff --check` 无空白错误。

### S13-R9：容量闭环（可审计历史 Blob 淘汰）

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已完成；专项测试与相关静态检查通过 |
| 依赖 | S13-R8 |
| 开发方式 | 直接实现后补回归测试；本任务不采用 TDD |

目标：达到 `max_memory_task_bytes` 时不再永久阻塞。在 append 触发配额压力时，先对可淘汰的历史 blob 做可审计的内容淘汰以腾出空间，再判定是否仍超限；保留全部 record 元数据与事件日志。

冻结契约：

1. `memory_id` 永久稳定；compaction 不删除事件、不重编号、不改 seq/generation 语义。
2. 只淘汰 blob 文件内容，写独立 `memory/evicted.json` manifest 记录被淘汰的 `content_sha256`；load 时产生 `memory_blob_evicted` 审计信号。
3. `memory_read` 对已淘汰正文返回 `memory_content_evicted`（非完整性错误，作为失败 ToolResult 返回，不阻塞循环）。
4. quota 继续统计完整 event log 与存活 blob；被淘汰 blob 文件已删除，自然不再计入。
5. 淘汰资格：仅当某 blob 的全部引用 record 都已 stale（invalidated 或 superseded）且不被任何当前 `latest_by_path` 文件快照引用时可淘汰；当前文件快照、活跃记录正文一律保留。按 blob 字节从大到小淘汰直到 prospective ≤ 配额；仍超限则 `memory_quota_exceeded`，不静默破坏历史引用。
6. 原子顺序：先原子写 manifest 标记淘汰，再删除 blob 文件；崩溃留下“已标记未删”的 blob 下次 load/compaction 可安全再删。load 时 blob 文件缺失且在 manifest 中视为已淘汰跳过，缺失但不在 manifest 仍 `memory_corrupt`。

允许修改：`src/hancode/core/memory.py`（如需错误码）、`src/hancode/storage/memory.py`、`src/hancode/tooling/memory_tools.py`（错误码映射）、直接相关 Memory Store/Tool 测试，以及 `docs/PLAN.md`、`docs/AGENT_LOG.md`。不得改动 recent 分层、长行续传或 Context 预算策略。

专项验证：Memory Store、Tool 测试；相关 Ruff、MyPy 与 `git diff --check`。按用户要求本任务不运行全量门禁。

实施结果（2026-08-04）：

- `append()` 在配额判定处新增 compaction：prospective 超限时调用 `_compact_evictable_blobs()` 淘汰可淘汰历史 blob 后重算，仍超限才 `memory_quota_exceeded`。
- `_compact_evictable_blobs()` 仅淘汰“全部引用 record 已 stale（invalidated/superseded）且不被任何 `latest_by_path` 当前快照引用”的 blob，按字节从大到小；先原子写 `evicted.json`（schema_version=1 + sorted content_sha256）再删 blob 文件；跳过链接与不存在文件。
- `load()` 读取 manifest 并透传到 `_read_records`/`_validate_blob`：blob 缺失且在 manifest 视为已淘汰跳过，缺失但不在 manifest 仍 `memory_corrupt`；有淘汰记录时产生 `memory_blob_evicted` 审计信号。
- `read()` 对已淘汰正文返回新错误 `memory_content_evicted`（非 `_INTEGRITY_ERRORS`，作为失败 ToolResult，不阻塞循环）；`search()` 跳过已淘汰 blob 内容匹配。`memory_id`、事件日志、seq/generation 语义不变。
- 新增回归：superseded 大 blob 在配额压力下被淘汰且 manifest/审计正确、record 元数据保留；已淘汰正文 `memory_read` 返回 `memory_content_evicted`。
- 专项验证：`tests/test_memory_store.py tests/test_memory_tools.py tests/test_memory_context.py` 56 passed；`storage/memory.py`、`tooling/memory_tools.py` 与测试 Ruff 通过；两源文件 MyPy 通过；`git diff --check` 无空白错误。

### S13 追踪修复：remediation 范围直达模型（消除 read_file 死循环）

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已完成；全量 pytest + Ruff + MyPy 通过 |
| 依赖 | S13-R11（recent 分层）之后 |
| 开发方式 | TDD；先红后绿 |

目标：task-003 trace 显示模型 56 次 read_file（23 次读 index.html）、8 次 edit_file 全被 `remediation_planned_path_required` 拒绝后陷入 read→edit→denied→memory_search 循环。根因是 CODE 阶段看不到 remediation 决策，模型被迫去 memory 猜。目标是让 `planned_paths` 对模型始终可见，消除"查找"需求。

修改范围（5 点）：

1. `src/hancode/runtime/context.py`：CODE 阶段存在 failed 状态与 remediation 时注入 `sections.remediation_scope`（kind/planned_paths/digest）；stale binding 抛 `test_failure_invalid`；`_TRUNCATION_ORDER[CODE]` 末位加 `remediation_scope`。
2. `src/hancode/policy/tool_policy.py`：`_evaluate_remediation_path` 拒绝时 suggested_fix 携带排序后的允许 planned_paths。
3. `src/hancode/providers/prompt_contract.py`：CODE 契约指引读 remediation_scope/test_remediation.json 且明言 remediation 不入 memory；REVIEW 契约声明决策持久化位置；`BASE_SYSTEM_CONTRACT` 决策程序新增"读失败后切换读法而非重试同一 memory 工具"。
4. `src/hancode/core/tool_specs.py`：memory_search 描述声明内部决策不入 memory；`src/hancode/storage/memory.py` `_memory_content_unavailable` suggested_fix 指引改读 test_remediation.json。
5. 测试：`tests/test_context_builder.py`（注入/省略/stale 三用例）、`tests/test_tool_policy.py`（拒绝消息含路径）、`tests/test_memory_store.py`（suggested_fix 含 test_remediation.json）、`tests/test_action_schema.py`（memory_search 描述）、`tests/providers/test_prompt_builder.py`（契约断言）。

边界：不改 remediation 决策本身（modify_test 不含源码路径属决策问题，不在本轮）；不改 Context 预算策略；不改 memory 存储格式。

验证结果（2026-08-05）：

- 全量 pytest：`1607 passed, 17 skipped`。
- Ruff：`All checks passed!`（context/tool_policy/prompt_contract/tool_specs/storage_memory + 5 测试文件）。
- MyPy：`Success: no issues found in 5 source files`。
- 提交：未提交；保留 `main` 工作区改动。

## S14：Deliver 学习发布管线

| 元信息 | 值 |
| --- | --- |
| 状态 | [~] R0 文档契约已完成；R1-R7 运行时实现未开始 |
| 依赖 | S4 统一 Delivery Pipeline、S10-R1 测试失败恢复、S13 Runtime Memory |
| 开发方式 | R0 文档冻结；R1 起逐任务 RED → GREEN → REFACTOR |

### 问题与成功标准

当前 Deliver 能证明最终文件、测试和需求覆盖状态，但不能稳定回答学生为什么选择当前方案、经历了哪些失败、如何修复，以及经验如何迁移。S14 将 Deliver 定义为把结构化过程证据编译成提交包、学习包和审计包的发布阶段，而不是由 LLM 在末尾重新阅读完整 Trace 并自由总结。

成功标准：结构化证据是唯一机器权威源；Markdown 是可重新生成且保留学生笔记的学习视图；核心需求具备 `R-* → D-* → C-* → T-* / F-* → K-*` 可追踪链；硬门禁只决定能否 `completed`，学习质量不足写入 `learning_warnings`；发布可选择 `submission`、`learning`、`audit` 三种 Profile。

### 冻结边界

- 保持现有六阶段和 `completed / blocked / failed` 终态，不新增学习专用 TaskStatus。
- `state.json` 仍是任务生命周期权威；`learning/evidence.json` 与 `learning/traceability.json` 是学习证据与关系权威；Markdown 不参与反向重建机器状态。
- Deliver 不修改业务代码，不从完整 Trace 临时推断设计理由，不接受无有效证据引用的知识结论。
- 自动生成区域与学生区域分离；重新渲染只替换 `<!-- hancode:generated:start/end -->` 包围的内容。
- 本轮 R0 只修改 `docs/SPEC.md`、`docs/系统架构.md`、`docs/PLAN.md`、`docs/AGENT_LOG.md`，不修改运行时代码、模板或测试。

### S14-R0：SPEC 与架构契约冻结

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已完成；SPEC、架构、PLAN、AGENT_LOG 已同步 |
| 允许修改 | `docs/SPEC.md`、`docs/系统架构.md`、`docs/PLAN.md`、`docs/AGENT_LOG.md` |
| 非目标 | Python 实现、模板落盘、CLI/TUI、export 行为变更 |

验收：文档同时定义三类发布包、七份阶段 Markdown、稳定证据 ID、追加式学习事件、`KnowledgeCard`、五步发布管线、硬门禁/学习告警、generated/student 分区、三种导出 Profile，以及后续 R1-R7 的依赖顺序；定向检索不得遗留“Deliver 只检查两个文件存在即可完成”的权威描述。

### S14-R1：学习证据领域模型与 Store

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已完成（专项通过；全量留待 R1-R7 收尾） |
| 允许修改 | `core/state.py`、`core/config.py`、`core/project_config.py`、`core/learning_evidence.py`、`storage/workspace.py`、`storage/learning_store.py`、对应测试 |

新增 `RequirementEvidence`、`DecisionEvidence`、`ChangeEvidence`、`TestAttemptEvidence`、`FailureEvidence`、`RecoveryEvidence`、`KnowledgeCard`、`TraceabilityLink` 与稳定 ID 校验；实现 `learning/events.jsonl`、`learning/evidence.json`、`learning/traceability.json` 的 task identity、schema、digest、原子写入、追加/重放和链接拒绝。不得复用 Runtime Memory 作为交付证据源。

预期 Red：损坏或跨 task 证据 fail-closed；重复/未知 ID 拒绝；事件只能追加；同一输入确定性生成相同 digest。

实际实现（R1.1/R1.2/R1.3）：
- R1.1 兼容层：`TaskState` 增 `learning_contract_version: int | None`（旧 state 读取不自动升级）；`artifacts` 增 `IMPLEMENTATION.md`（load 接受旧 6 键/新 7 键并归一化）；`HanCodeConfig` 增 `submission_paths`（仅接受项目内相对路径，拒绝绝对/`..`/`.hancode` 内部/符号链接逃逸）；`init_task_workspace` 写 `learning/` 目录、7 键 artifacts 与 `learning_contract_version=1`。
- R1.2 `core/learning_evidence.py`：九个 frozen 模型 + `LearningSnapshot`；`EvidenceKind`/`format_evidence_id`/`is_valid_evidence_id`/`parse_evidence_kind` 集中校验前缀 `R/D/P/C/K`（4 位）、`T/F`（6 位）、`REC`（4 位）；`TraceabilityLink` 固定 8 种关系。
- R1.3 `storage/learning_store.py`：append-only 哈希链事件日志（9 种 SPEC 冻结 event_type），fsync 写入，`evidence.json` 派生投影可删可重建；task identity/seq/previous_digest/schema 校验；尾部半行只取完整前缀，中间损坏/digest 断裂 fail-closed。
- 决策：事件命名采用 SPEC 冻结 9 种；Recovery 使用独立 `REC-*` 前缀（需在架构 §S14.2 补记）；digest 复用现有 `delivery_coverage_digest`。
- 验证：`pytest tests/test_s14_learning_store.py tests/test_s14_learning_models.py tests/test_state.py tests/test_config.py tests/test_workspace.py tests/test_memory_store.py` 238 passed；Ruff/MyPy 新增改动文件通过。

### S14-R2：Code 学习记录与学生笔记保护

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 确定性核心已完成（渲染器 + LearningService 三闭环）；ToolPolicy/PhaseGate 门禁与 AgentLoop 自动 record_change 接线随 R5 编排切换统一实施 |
| 允许修改 | `delivery_support/renderer.py`、`app/learning_service.py`、对应测试 |

实现 `IMPLEMENTATION.md`，由 checkpoint、Diff、changed files、需求/计划/测试 ID 确定性生成事实部分；LLM 解释只能引用真实符号和证据 ID。所有阶段 Markdown 支持 generated/student 分区，重渲染不得覆盖学生的“我的理解 / 仍不理解 / 教师或同伴反馈”。

预期 Red：`test_implementation_report_links_diff_and_checkpoint`、`test_render_preserves_student_notes`、越界或不存在引用拒绝。

实际实现：
- R2.4 `delivery_support/renderer.py`：`replace_generated_region` 仅重写 `<!-- hancode:generated:start/end -->` 之间内容；无标记文档把原文保留为学生笔记并在顶部插入 generated 区；标记重复/嵌套/顺序错误 fail-closed；写前 secret 扫描；幂等。
- R2.1/R2.2/R2.3 `app/learning_service.py`：`record_requirements`（→SPEC.md）、`record_plan`（→PLAN.md，同时生成 `D-*`/`P-*`）、`record_change`（→IMPLEMENTATION.md，AgentLoop 驱动、非 LLM 工具）。均先 append 事件到 `learning/events.jsonl`，从完整事件前缀重建 `LearningSnapshot`，分配稳定 ID，校验证据引用（未知 `R-*`/`D-*`/`P-*` 返回 `learning_reference_invalid`），再渲染 generated 区并原子写入、同步 state artifact。
- 边界：本轮不改 `core/phases.py`、`tooling/tool_policy.py`、`runtime/agent_loop.py`；SPEC/PLAN phase 的 `write_file` 拒绝与 AgentLoop 自动记录 change 留待 R5 与主循环收敛时接线，避免新旧行为交错。
- 验证：`pytest tests/test_s14_learning_service.py tests/test_s14_renderer.py` 15 passed；回归 `tests/test_delivery.py tests/test_workspace.py tests/test_export.py` 65 passed；Ruff/MyPy 新文件通过。

### S14-R3：历史测试尝试与失败修复链

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 数据记录与渲染已完成（LearningService 扩展 + TEST_REPORT.md）；与 record_test/Router 的 `latest_test_status` 接线随 R5 统一 |
| 允许修改 | `app/learning_service.py`、对应测试 |

将测试证据从单一 `latest_test_report_sha256` 扩展为 `test_attempts[] + latest_test_attempt_id`；`latest_test_status` 继续供路由使用。`TEST_REPORT.md` 渲染全部有效尝试，并把 `FailureEvidence`、`RecoveryEvidence` 与后续验证测试串成完整链。

预期 Red：`test_delivery_preserves_failed_test_attempts`；失败历史不能被最终通过覆盖；存在失败历史时必须验证 `F-* → C-* → T-*`。

实际实现：
- `LearningService.record_test_attempt`（→`T-*`，事件 `TestExecuted`）、`record_failure`（→`F-*`，`FailureDiagnosed`，校验 `test_attempt_id` 存在）、`record_recovery`（→`REC-*`，`FixApplied`/`RollbackExecuted`，校验 `failure_id` 存在）。
- `TEST_REPORT.md` 渲染测试策略、全部有效尝试表、失败记录与对应恢复；后来的 passing 尝试不覆盖历史失败（全部尝试均保留为独立 `T-*`）。
- 决策落地：Recovery 使用独立 `REC-*` 前缀。
- 验证：`pytest tests/test_s14_test_history.py` 4 passed；合并 `tests/test_s14_learning_service.py` 共 10 passed；Ruff/MyPy 通过。

### S14-R4：需求追踪与 KnowledgeCard

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已完成（TraceabilityBuilder + record_review/record_knowledge） |
| 允许修改 | `runtime/traceability_builder.py`、`app/learning_service.py`、对应测试 |

实现需求追踪矩阵和带证据引用的 `KnowledgeCard`。`record_knowledge` 只接受结构化卡片；每个 `evidence_refs` 必须存在、属于当前 task 且类型允许。卡片包含 problem、context、principle、solution、applicable/not-applicable、common mistake 和 transfer example。

预期 Red：`test_core_requirement_has_full_traceability_chain`、`test_knowledge_card_requires_valid_evidence_refs`、`test_delivery_rejects_ungrounded_learning_claims`。

实际实现：
- `runtime/traceability_builder.py`：`build_traceability(snapshot)` 仅从 `LearningSnapshot` 构建 8 种固定关系链与需求 coverage；核心需求 covered 需同时存在引用该需求的 change 与引用它（直接或经 change）的 passing test；整体通过不隐式覆盖未关联需求。
- `LearningService.record_review`（→REVIEW.md，`RequirementReviewed`，校验 requirement/change/test 引用）、`record_knowledge`（→KNOWLEDGE.md，`KnowledgeExtracted`，分配 `K-*`）。
- KnowledgeCard 硬约束：`transfer_example` 必填（工具层拒绝）；`evidence_refs` 必须存在且至少一个 R/D/P/C/F/REC 加至少一个 C/T/F，否则 `learning_reference_invalid`。
- 验证：`pytest tests/test_s14_traceability.py tests/test_s14_knowledge.py` 9 passed；Ruff/MyPy 通过。

### S14-R5：Delivery 编排、Validator 与 Artifact Renderer

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] Collect/Validate 与学习契约决策已完成（`evaluate_learning` 并行路径）；旧 `DeliveryPipeline` 完全 cutover 与 AgentLoop 自动 record_change/ToolPolicy 门禁作为后续接线项，避免破坏既有 S4 交付与上千回归 |
| 允许修改 | `delivery_support/collector.py`、`delivery_support/validator.py`、`app/delivery_service.py`、`core/delivery_evidence.py`、对应测试 |

将现有 `DeliveryPipeline` 收敛为编排器，内部协作 `LearningEvidenceCollector`、`TraceabilityBuilder`、`DeliveryValidator`、`ArtifactRenderer`、`DeliveryPublisher`，依次执行 Collect → Validate → Synthesize → Reflect → Publish。先实现硬门禁与 `learning_warnings`，再渲染 `IMPLEMENTATION.md`、`TEST_REPORT.md`、`REVIEW.md`、`KNOWLEDGE.md`、`DELIVERABLES.md`。

预期 Red：核心需求无实现/测试证据、最新测试/Build/Diff 失效、知识引用无效、敏感信息命中均阻止 completed；缺候选方案、反思、迁移示例或“为什么”只产生 warning。

实际实现：
- `delivery_support/collector.py`：`collect_learning_delivery` 只收集 `TaskState`、`LearningSnapshot`、Traceability 与 Build 需求，不写文件、不改状态。
- `delivery_support/validator.py`：`validate_learning_delivery` 按 S14.6 产出硬 blocker（核心需求未 covered、最新测试未过、Build 未过、stale 覆盖、失败缺修复链、KnowledgeCard 引用无效）与 warning（无候选方案、无 KnowledgeCard、change 理由过短）。
- `core/delivery_evidence.py`：`DeliveryResult` 增 `submission_eligible`/`learning_contract_status`/`learning_warnings`（带默认值，向后兼容既有构造）。
- `app/delivery_service.py`：`evaluate_learning` 组合 Collect→Validate，输出 submission 资格与契约状态；旧任务（`learning_contract_version is None`）标 `legacy_unverified` 且 `submission_eligible=false`，不改历史生命周期状态。
- 后续接线项：将 `evaluate_learning` 接入 finalize/Router、AgentLoop 在成功修改后自动 `record_change`、SPEC/PLAN phase 拒绝 `write_file`；这些改动侵入主循环，单列后续任务，避免本轮引入大范围回归。
- 验证：`pytest tests/test_s14_delivery_gate.py tests/test_s14_delivery_service.py` 6 passed；回归 `tests/test_delivery.py tests/test_s4_delivery_e2e.py tests/test_s4_review_remediation.py tests/test_agent_loop.py tests/test_cli.py` 149 passed；Ruff/MyPy 通过。

### S14-R6：Submission / Learning / Audit 发布 Profile

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已完成（`ExportProfile` + `export_task_profile` + `DeliveryService.export_profile`）；CLI/TUI `--profile` 参数接线随 R7/后续 UI 任务 |
| 允许修改 | `storage/export.py`、`app/delivery_service.py`、对应测试 |

扩展 `hancode export --profile submission|learning|audit`。Submission 仅包含课程提交所需 README、`DELIVERABLES.md`、源码和 manifest；Learning 包含 `LEARNING_INDEX.md`、SPEC、PLAN、IMPLEMENTATION、TEST_REPORT、REVIEW、KNOWLEDGE 与 `final.diff`；Audit 包含 manifest、结构化证据、脱敏 Trace、checkpoint manifest 和需求追踪。三个 Profile 使用 staging 原子发布、防覆盖和 fail-closed 路径检查。

预期 Red：`test_submission_export_excludes_internal_runtime_files`、`test_learning_export_contains_all_phase_artifacts`；Audit 不导出 checkpoint 原始快照、凭据、Runtime Memory blob 或未脱敏 Trace。

实际实现：
- `storage/export.py`：`ExportProfile(SUBMISSION/LEARNING/AUDIT)` + `export_task_profile`（无默认 profile，显式选择）；每个 profile 显式 allow-list、staging 原子 rename、防覆盖、link/junction fail-closed，写自描述 manifest（含 status/submission_eligible/learning_contract_status/blockers/learning_warnings/evidence_digest）。
- submission：README + DELIVERABLES + `submission_paths` 精确文件 + delivery-manifest；learning：七份阶段 Markdown + final.diff + LEARNING_INDEX + learning-manifest；audit：evidence.json + traceability.json + audit-manifest；均排除 state/trace/memory/凭据/原始 checkpoint。
- `DeliveryService.export_profile` 作为 facade；旧 `export`/`export_task_artifacts` 保留兼容。
- 验证：`pytest tests/test_s14_export_profiles.py tests/test_export.py` 9 passed；Ruff/MyPy 通过。

### S14-R7：TUI 反思与学习浏览

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 应用服务层完成（ReflectionService + LearningInspectionService）；Textual 组件/命令接线作为后续 UI 任务 |
| 允许修改 | `app/reflection_service.py`、`app/learning_inspection_service.py`、对应测试 |

在不改变硬门禁的前提下，增加自测问题、学生反思、KnowledgeCard 与追踪链浏览；未填写仅显示 `learning_warnings`。TUI 继续只通过 Application Service 读写，不直接解析或覆盖结构化证据。

实际实现：
- `app/reflection_service.py`：`ReflectionSection(MY_UNDERSTANDING/OPEN_QUESTIONS/PEER_FEEDBACK)`；`save_reflection` 权威存 `learning/reflections.json`（原子写 + fsync），用 monotonic `revision` 乐观锁防丢更新，secret 命中拒绝；投影到 Markdown 学生区（generated 区保留，Markdown 不作反向权威）。
- `app/learning_inspection_service.py`：只读 `overview()` 投影 `LearningSnapshot` + traceability，为 TUI/CLI 提供 KnowledgeCard 列表与需求覆盖视图，不改状态或事件。
- 后续 UI 任务：Textual KnowledgeCard/追踪链/Reflection 编辑/Export Profile 选择组件通过上述服务接线。
- 验证：`pytest tests/test_s14_reflection.py tests/test_s14_learning_inspection.py` 5 passed；Ruff/MyPy 通过。

### S14 依赖顺序与最终质量门

```text
R0 文档契约
→ R1 证据模型与 Store
→ R2 Implementation/学生笔记
→ R3 测试历史
→ R4 Traceability/KnowledgeCard
→ R5 Validator/Renderer/编排
→ R6 三类发布 Profile
→ R7 TUI 反思与浏览
```

每个实现任务独立完成 TDD 与相关回归；S14 最终统一运行全量 pytest、Ruff、MyPy、`uv sync --locked --extra dev`、离线 build、Mock Demo、三种 export E2E 和 `git diff --check`。没有新鲜证据不得把对应任务标记为完成。

---

## S15：CODE 可写目标发现与探索收敛

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 快速修复完成；专项与全量门禁通过 |
| 分支 | `main` |
| 依赖 | S13、S14 现有运行时 |
| 开发方式 | 小任务快速实现，专项回归后全量门禁 |
| 配置边界 | 不修改 `.hancode/project.json`，配置由用户后续调整 |
| 工件边界 | 不修改 `.hancode/tasks/task-001/**` |

### 目标

修复 CODE 阶段无法从不存在的可写目录直接开始、`list_files` 输出被仓库噪声淹没，以及模型连续重复只读探索而没有 source write 时运行时无法纠偏的问题。

### 小任务与允许修改文件

1. **可写目标引导**：`src/hancode/runtime/context.py`、`src/hancode/providers/prompt_contract.py` 及对应上下文/提示词测试。Context 只告警，不提前创建目录；合法 `write_file` 已负责创建父目录。
2. **遍历去噪**：`src/hancode/tooling/file_tools.py`、`tests/test_file_tools.py`。`list_files` 与 `search_text` 在进入目录前剪枝常见 VCS、虚拟环境、依赖和缓存目录，并保留现有路径安全与敏感信息保护。
3. **CODE 无进展保护**：`src/hancode/runtime/agent_loop.py`、`tests/test_agent_loop.py`。CODE 阶段无 source write 时，重复成功只读探索先注入反馈，再重复则按交互配置进入 `ask_user` 或 `blocked`，不得重复派发工具。

### 验收标准

- `sections.writable_roots` 明确列出可写目标；不存在的目标目录有告警，模型可直接使用 `write_file` 创建。
- 默认目录遍历不包含 `.git`、`.venv`、`__pycache__`、`node_modules`、`.mypy_cache`、`.pytest_cache`、`.ruff_cache` 等噪声。
- CODE 阶段连续重复只读探索且 `source_edits_this_phase == 0` 时，运行时产生明确反馈并最终阻止无进展循环。
- 现有 TEST/REVIEW 重复探索保护、路径安全、审批和 checkpoint 行为不回归。

### 验证

专项运行 `tests/test_file_tools.py`、`tests/test_context_builder.py`、`tests/test_agent_loop.py`、`tests/providers/test_prompt_builder.py` 及相关路径/策略回归；完成后运行全量 pytest、Ruff、MyPy 和 `git diff --check`。验证结果回写本卡和 `docs/AGENT_LOG.md`。

### 实际修复与验证（2026-08-06）

- `runtime/context.py` 在 CODE context 中保留 `sections.writable_roots`，并对尚不存在的可写根注入 `writable_roots_warning`；不在上下文构建时创建目录。
- `providers/prompt_contract.py` 明确可写根可能尚不存在，模型应直接调用 `write_file`，由工具创建缺失父目录，不应重复 `list_files` 或修改配置。
- `tooling/file_tools.py` 使用 top-down walker，在进入目录前剪枝 `.git`、`.venv`、`venv`、`env`、`__pycache__`、`node_modules`、`.mypy_cache`、`.pytest_cache`、`.ruff_cache`，并拒绝目录链接/越界路径；原敏感路径、凭据别名和 UTF-8 保护保持不变。
- `runtime/agent_loop.py` 在 CODE 且 `source_edits_this_phase == 0` 时记录成功只读探索；重复动作先写 `code_exploration_repeated` 反馈，再重复时按交互配置进入 `WAITING_INPUT` 或以 `code_progress_stalled` 阻塞，重复动作不会再次派发。
- 配置、task-001 工件、`core/config.py` 根目录安全限制均未修改。
- 专项及相关回归：`462 passed, 4 skipped`。
- 全量 pytest：`1707 passed, 17 skipped`。
- 全仓 Ruff：`All checks passed!`。
- 全仓 MyPy：`Success: no issues found in 145 source files`。
- `git diff --check` 通过；全量测试首次 120 秒超时后使用更长超时复跑并通过，未发现测试断言失败。

---

## S16：TUI 凭据输入的系统剪贴板支持

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 快速修复完成；TUI 专项与静态检查通过 |
| 分支 | `main` |
| 依赖 | S8 配置中心、Textual Input |
| 开发方式 | 小范围快速修复与专项回归 |
| 安全边界 | API Key 只在内存中经过输入控件并写入 Keyring，不进入日志、Trace 或 `project.json` |

### 根因

Textual `Input` 的 `Ctrl+V` 只读取 Textual 自己维护的内部 clipboard，不读取操作系统剪贴板；外部终端粘贴还依赖 bracketed paste 支持。当前凭据输入框只继承默认行为，因此逐字输入可用，但常规系统剪贴板粘贴可能无内容。

### 修改范围

- `src/hancode/interfaces/tui/config_dialogs.py`：凭据输入控件支持 Windows/macOS/Linux 固定系统剪贴板命令，使用 `shell=False`、短超时和无日志输出；保留 Textual bracketed paste 与内部 clipboard 回退。
- `tests/test_config_tui_s8.py`：覆盖 `Ctrl+V` 将系统剪贴板内容填入密码输入框且不改变脱敏/Keyring 行为。
- `docs/PLAN.md`、`docs/AGENT_LOG.md`：记录任务与验证证据。

### 验收标准

- API Key 输入框逐字输入和系统剪贴板粘贴均可用。
- 粘贴内容不显示明文，不写入 `project.json`、Trace 或普通日志。
- 粘贴失败时不抛出未处理异常，仍可手动输入或使用终端 bracketed paste。

### 实际修复与验证（2026-08-06）

- 新增 `CredentialInput`，`Ctrl+V`、`Ctrl+Shift+V`、`Shift+Insert` 均优先读取系统剪贴板；Windows 使用 PowerShell `Get-Clipboard -Raw`，macOS 使用 `pbpaste`，Linux 依次尝试 `wl-paste`、`xclip`、`xsel`。
- 所有外部命令使用固定参数、`shell=False`、1 秒超时和脱敏边界；剪贴板内容只进入当前输入控件，保留 Textual bracketed paste 与内部 clipboard 回退。
- TUI 专项：`12 passed`。
- Ruff：通过；MyPy：`config_dialogs.py` 无错误。
- 相关配置/凭据回归：`130 passed, 1 skipped`。
- 全量 pytest：`1709 passed, 17 skipped`。
- 全仓 Ruff：通过；全仓 MyPy：`Success: no issues found in 145 source files`。
- 本任务改动范围的 `git diff --check` 通过；全局检查仅命中并行修改的 `README.md` 文件末尾空行，未修改该非本任务文件。

---

## S17：Runtime Steering（运行中对话调整）

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] R1-R4/TUI 子卡已实现；完整 Prepare—Commit—Apply 仍为后续任务 |
| 分支 | `main`（遵循本卡 §恢复包策略，不建分支、不 commit） |
| 依赖 | S5 TUI 契约、S12-R1 协作式暂停、S9 Approval、S11 恢复 |
| 开发方式 | 纵向 TDD（RED → GREEN → REFACTOR），逐子卡独立交付 |
| 安全边界 | Steering 不得绕过系统规则、ToolPolicy、Approval、Checkpoint、Phase Gate；正文经 `redact_text` 脱敏，纯敏感内容拒绝；单进程 writer |

### 问题与成功标准

主流 Agent 允许用户在模型运行过程中提交新要求并让 Agent 重新规划。HanCode 需要一个 deterministic、可测试、可审计的 Runtime Steering 机制：用户在 Agent 运行中提交的新要求作为高优先级运行时约束，持续进入后续每轮 Context，且不破坏原子操作边界与安全机制。

S17 拆分为多张子卡逐步交付。本阶段已交付 **S17-R1/R2/R3/R4 与 S17-TUI**；完整 Prepare—Commit—Apply 副作用边界搬迁仍留给后续独立任务。

### S17-P0：Provider Prompt 的 Steering 权威契约

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已实现；Prompt 专项验证通过（2026-08-06） |
| 依赖 | S17-R1、S17-R2、S17-R3、S17-R4 |
| 开发方式 | RED → GREEN → REFACTOR |

范围：把 Runtime Steering 的优先级、sequence 覆盖和当前 run 持续有效语义明确写入 Provider-facing system contract，确保模型不会把原始目标、旧计划或 observation 误当成高于 Steering 的指令。

允许修改：

- `src/hancode/providers/prompt_contract.py`
- `src/hancode/providers/prompt_builder.py`
- `tests/providers/test_prompt_builder.py`
- `docs/PLAN.md`、`docs/SPEC.md`、`docs/系统架构.md`、`docs/AGENT_LOG.md`

验收标准：

- `task_context.user_interventions.effective` 被声明为当前 run 提交的用户指令集合，并在整个 run 内持续有效。
- 较大 sequence 覆盖冲突的较小 sequence。
- Steering 冲突时高于原始任务目标、旧计划和 observation。
- Steering 不得覆盖 system rules、phase gates、ToolPolicy、Approval 或 Checkpoint。
- 文本 Prompt 与 native tool-calling Prompt 都包含该契约；不改变既有 Action/Function 输出格式。

### S17-P0 实际实现与验证（2026-08-06）

- `providers/prompt_contract.py` 新增共享 `RUNTIME_STEERING_CONTRACT`，嵌入 `BASE_SYSTEM_CONTRACT`；明确 `task_context.user_interventions.effective`、当前 run 持续有效、sequence 覆盖和安全边界。
- `providers/prompt_builder.py` 让 native tool-calling system message 复用相同 Steering 契约，保持既有 Function Tool 输出格式。
- `tests/providers/test_prompt_builder.py` 新增普通文本和 native Prompt 契约断言；Prompt 专项：`37 passed`。

### 冻结边界（S17 整体非目标，后续单独立卡）

- `CANCEL`、`NOTE`、`SUPERSEDED`、`/steer`、`/stop`。
- Provider 请求硬取消、Shell 进程组终止、Worker 强制终止、已开始操作自动回滚。
- 跨进程文件锁、多 HanCode 进程同时写同一任务、WebSocket/远程控制。

### 并发模型限制

MVP 支持单进程、TUI 线程与 Agent Worker 线程并发、同进程内多 Store 实例访问同一日志；**不支持**两个独立 HanCode 进程同时操作同一 task workspace。

---

### S17-R1：InterventionStore、Snapshot 与 Context 注入（基础切片）

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已实现；全量质量门与构建通过（2026-08-06） |
| 依赖 | S5、S9、S11 |
| 开发方式 | RED → GREEN → REFACTOR |

范围：落地 Runtime Steering 的持久化事实来源与 Context 注入基础，使当前 run 的 Steering 能够持续进入后续每轮 Context。

允许修改：

- `src/hancode/core/interventions.py`（新增）
- `src/hancode/core/state.py`（新增 `active_run_id` 可选字段）
- `src/hancode/storage/interventions.py`（新增）
- `src/hancode/runtime/context.py`（`build` 增参并注入 Steering）
- `src/hancode/runtime/agent_loop.py`（生成 Snapshot、注入 Context、Provider 前 `mark_delivered`）
- `src/hancode/runtime/engine.py`、`src/hancode/app/task_service.py`（透传 `intervention_store` 与 run identity）
- 对应新增/扩充测试；`docs/SPEC.md`、`docs/系统架构.md`、`docs/PLAN.md`、`docs/AGENT_LOG.md`。

禁止修改 `.hancode/tasks/task-001/**`。

核心语义：

- Steering 是持续运行约束：当前 `run_id` 下 `PENDING`/`DELIVERED`/`CONSUMED` 全部持续注入后续每轮 Context。
- `SteeringSnapshot` 由 `AgentLoop` 生成并显式传入 `ContextBuilder`；ContextBuilder 不直接读取 Store。
- 优先级：系统规则 > ToolPolicy/Approval/Checkpoint/Phase Gate > 当前 run 最新 Steering > 任务原始目标 > 旧计划与 observation。较大 sequence 冲突时覆盖较小 sequence，但不绕过安全机制。

明确非目标（S17-R1 内不做，留给 R2+）：

- revision 并发线性化 `commit_action` 与 `REPLAN`（R2）。
- Prepare—Commit—Apply 副作用边界重构（R3）。
- Approval `run_id` 与 `steering_revision_at_request` 绑定与失效（R4）。
- orphan RUNNING 恢复与完整 run 生命周期表、`WAITING_APPROVAL` 提交 Steering、TUI 接入（后续子卡）。

Red 测试至少覆盖：

- Store：两条 Steering task-global sequence 严格递增；新 Store 实例可重放；均为 PENDING；多 Store 实例共享同一路径锁；secret redaction；纯敏感输入拒绝；日志损坏 fail-closed；`mark_delivered` 幂等；CONSUMED 重放。
- Snapshot/Context：PENDING/DELIVERED/CONSUMED 均进 `effective`；`awaiting_acknowledgement` 只含未确认；sequence 升序稳定；旧 `run_id` 不进入新 run Context；ContextBuilder 不直接读 Store；Steering 不被预算静默删除；预算不足返回 `intervention_context_budget_exceeded`。
- run identity：`/run` 创建并持久化 `active_run_id`；`/resume` 复用；`COMPLETED/FAILED/INCONSISTENT` 清除；`active_run_id` 已存在时 `/run` 拒绝。
- 回归：`InterventionStore` 为 `None` 时 `AgentLoop` 行为不变。

### 实际实现与验证（2026-08-06）

- `core/interventions.py`（新增）：`InterventionKind/Status/EventType`、`DeliveryStatus`、`InterventionEvent`（frozen+slots，`ive-XXXXXX` 事件 ID）、`InterventionRecord`（`iv-XXXXXX`）、`SteeringSnapshot`、`DeliveryResult`，`content` 仅 SUBMITTED 携带。
- `storage/interventions.py`（新增）：append-only `interventions.jsonl` + `os.fsync`；模块级路径锁按 `os.path.normcase(resolve())` 索引；`submit/prepare_context/mark_delivered/mark_consumed/current_revision`；重放严格校验（schema/task_id/run_id/事件 ID 连续/SUBMITTED sequence 连续递增/生命周期转换/跨 run 拒绝/content 位置），损坏 fail-closed；`redact_text` 脱敏与纯敏感拒绝；`mark_delivered` 与 CONSUMED 幂等。
- `core/state.py`：新增可选 `active_run_id`，按既有 5 处 additive 模式（字段集、可选集、dataclass、`__post_init__`、`load_state`、`save_state`）落地，旧 `state.json` 仍可加载。
- `runtime/context.py`：`ContextBuilder.build` 与 `build_context` 增加 `user_interventions`/`intervention_revision`；输出 `user_interventions.{revision, effective, awaiting_acknowledgement}`（sequence 升序，正文经 `redact_text`）；预算不足且存在 Steering 时返回 `intervention_context_budget_exceeded`，不静默删除。
- `runtime/agent_loop.py`：新增 `InterventionStorePort` 与可选 `intervention_store`；每轮 `_prepare_steering_snapshot`（无 store 或无 `active_run_id` 返回 None，保持旧行为）→ 注入 Context → Provider 前 `_mark_steering_delivered`。
- `runtime/engine.py`、`app/task_service.py`：透传 `intervention_store`（引擎默认注入 `InterventionStore`）；`TaskService.run/resume` 落地最小 run 生命周期（`/run` 创建并持久化 `active_run_id`；已存在时拒绝 `task_run_already_active`；`/resume` 复用；`COMPLETED/FAILED/INCONSISTENT` 清除）。
- 专项：`test_interventions_store.py`(10)、`test_interventions_context.py`(5)、`test_interventions_runtime.py`(7)；相关回归 `test_context_builder/test_state/test_agent_loop/test_task_service` 通过。
- 全量 pytest：`1730 passed, 17 skipped`。
- Ruff：`All checks passed!`；MyPy：`Success: no issues found in 147 source files`。
- `uv build` 生成 sdist 与 wheel 成功（`--offline` 仅因 setuptools 未进缓存而失败，非代码问题）。
- `git diff --check` 通过；未修改 `.hancode/tasks/task-001/**`。

### 恢复包策略

直接在 `main` 修改，不创建分支/worktree、不 stage、不 commit、不 push。每个纵向切片全绿后在仓库外会话 artifacts 目录用 `git diff --binary` 保存 `slice-N.patch`，untracked 文件复制到 `slice-N/untracked/`；不污染 Git 状态；临时测试缓存需清理。

### 验证

每切片跑聚焦 pytest（`tests/test_interventions_store.py`、`tests/test_interventions_context.py`、`tests/test_context_builder.py`、`tests/test_agent_loop.py`、`tests/test_state.py`）；全部完成后跑全量 `pytest`、`ruff`、`mypy`、离线 `uv build`、`git diff --check`。Windows 使用隔离 `basetemp` 与 `UV_CACHE_DIR`。验证结果回写本卡与 `docs/AGENT_LOG.md`。

---

### S17-R2：revision 并发线性化（commit_action + 陈旧输出丢弃）

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已实现；全量质量门与构建通过（2026-08-06） |
| 依赖 | S17-R1 |
| 开发方式 | RED → GREEN → REFACTOR |

范围：为每个 Provider Action 提供针对 Steering 的确定性线性化，使运行中到达的新 Steering 能让越过 snapshot 的旧决策失效并重新规划，且不产生半副作用。

允许修改：

- `src/hancode/core/interventions.py`（`ActionCommitStatus`/`ActionCommitResult`）
- `src/hancode/storage/interventions.py`（`commit_action` + 幂等 ledger `action_commits.jsonl`）
- `src/hancode/runtime/agent_loop.py`（mark_delivered STALE 丢弃、Provider 返回后 revision 检查、commit 门 REPLAN）
- 对应新增/扩充测试；`docs/PLAN.md`、`docs/SPEC.md`、`docs/系统架构.md`、`docs/AGENT_LOG.md`。

核心语义：

- 每个 Action 绑定生成它时的 `SteeringSnapshot.revision`；执行前调用 `commit_action()`。
- Steering `submit` 与 `commit_action` 争用同一路径锁：Steering 先取锁则 revision 增大、旧 Action 返回 `REPLAN` 且不产生副作用；Action 先取锁则 `COMMITTED`，后到 Steering 在下一轮生效。
- 幂等 ledger 按 `commit_key` 记录首次结果，crash-retry 返回同一结果。
- AgentLoop 在三处丢弃陈旧输出：Provider 前 `mark_delivered` 返回 STALE、Provider 返回后 `current_revision` 变化、commit 门返回 REPLAN；三者都不消耗 recovery budget、不写旧 parse failure、不派发工具。

明确非目标（留给 R3/R4）：

- Prepare—Commit—Apply 副作用边界重构与 `acknowledge`（CONSUMED）标记：本轮 commit 门 `acknowledge=False`，Steering 保持 effective，CONSUMED 标记延后至 R3。
- Approval `run_id`/`steering_revision_at_request` 绑定与失效（R4）。
- TUI 接入。

Red 测试至少覆盖：

- Store：revision 未变 `COMMITTED`；Steering 先到 `REPLAN` 且不 acknowledge；`commit_key` 幂等（仅一条 ledger）；跨 Store 实例共享 ledger；ledger 损坏 fail-closed；空 `commit_key` 拒绝。
- AgentLoop：`mark_delivered` STALE→replan 信号；DELIVERED 非 stale；Provider 窗口 revision 变化检测；commit 门 REPLAN；无 store 时不阻断。

### 实际实现与验证（2026-08-06）

- `core/interventions.py`：新增 `ActionCommitStatus`(COMMITTED/REPLAN) 与 `ActionCommitResult`。
- `storage/interventions.py`：新增 `commit_action`（共享路径锁下线性化、幂等 ledger `action_commits.jsonl` + `os.fsync`、REPLAN 不 acknowledge、损坏 fail-closed）与 `_CommitLedgerEntry`。
- `runtime/agent_loop.py`：`InterventionStorePort` 增 `current_revision`/`commit_action`；`_mark_steering_delivered` 返回 STALE 信号并在 Provider 前丢弃（`stale_context_discarded`）；Provider 返回后 `_steering_revision_changed` 丢弃（`stale_context_discarded`）；有效 Action 前 commit 门 `_commit_steering_action` 返回 REPLAN 时丢弃（`stale_action_discarded`）；均不消耗 recovery budget。
- 专项：`test_interventions_commit.py`(7)、`test_interventions_runtime.py` 新增 5、`test_interventions_store.py` 回归。
- 全量 pytest：`1742 passed, 17 skipped`。
- Ruff：`All checks passed!`；MyPy：`Success: no issues found in 147 source files`。
- `uv build`：sdist + wheel 成功。
- `git diff --check` 通过；未修改 `.hancode/tasks/task-001/**`。

### 2026-08-07 — `/help` 左右箭头切换焦点

- 修改：左侧分类列表获得焦点时，按 `→` 切换到右侧命令列表；右侧命令列表获得焦点时，按 `←` 返回左侧分类列表；搜索框继续保留左右箭头编辑行为。
- 提示：帮助弹窗操作提示补充 `←→ 切换列表`。
- 验收：新增 `/help` 焦点切换回归，确认左右切换不影响现有上下浏览和搜索。

---

### /help 帮助界面改版（2026-08-07）

本次按用户确认的设计直接更新现有 TUI，不新增任务卡，不调整命令解析或业务流程。

- 新增 `src/hancode/interfaces/tui/help.py`：提供四类命令导航、全局搜索、命令说明、新手建议和 Esc 关闭行为。
- `src/hancode/interfaces/tui/app.py`：`/help` 从单行通知改为打开 `HelpScreen`，并增加帮助弹窗布局样式。
- 新增 `tests/test_tui_help.py`：覆盖打开帮助、搜索命令和关闭弹窗。
- 验证：帮助专项 `1 passed`；TUI 聚焦回归 `39 passed`；相关 Ruff 通过；相关 MyPy `Success: no issues found in 2 source files`。

### `/help` 视觉修正（2026-08-07）

- 分类导航和底部提示改为纯文字，移除表情与装饰符号。
- 命令区与“新手建议”区统一为可伸展高度并顶部对齐，修正内部框线上下边界不一致。
- 回归验证：TUI 聚焦回归 `39 passed`；Ruff 通过；MyPy 对相关 2 个源文件无错误。
- 分类导航支持在搜索框保持焦点时使用 `↑/↓` 循环切换，右侧内容同步刷新；点击分类仍可用。
- 移除“新手建议”面板及其专用布局样式，右侧内容区仅保留分类标题和命令列表。

---

### S17-TUI：运行中普通文本 Steering 接入

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已实现；全量质量门与构建通过（2026-08-06） |
| 依赖 | S17-R1、S17-R2、S5 TUI Operation Worker |
| 开发方式 | RED → GREEN → REFACTOR |

范围：让用户在 Agent Worker 运行期间直接输入普通文本，文本作为当前 run 的 Steering 持久化；不启动第二个 mutation Worker。`WAITING_INPUT` 仍回答问题，`WAITING_APPROVAL` 的普通文本由 R4 接入 Steering 并自动 resume，显式 `/approve` 或 `/reject` 保持不变，`PAUSED` 仍要求显式 `/resume`。

允许修改：

- `src/hancode/app/intervention_service.py`（新增）
- `src/hancode/interfaces/tui/commands.py`（`STEER` plain-text intent 与 busy 路由）
- `src/hancode/interfaces/tui/app.py`（Steering service 注入、提交与确认提示）
- 对应 TUI/service 测试；`docs/PLAN.md`、`docs/SPEC.md`、`docs/系统架构.md`、`docs/AGENT_LOG.md`。

核心语义：

- TUI UI 线程同步调用 `InterventionService.submit` 写入 Store；不通过 `TuiOperation`，不调用 `run_worker`，不创建第二个 mutation Worker。
- Service 从 `TaskState.active_run_id` 校验当前运行身份，并复用 Store 的长度、脱敏和纯敏感拒绝边界。
- AgentLoop 已通过 `InterventionStore` 每轮读取当前 run Snapshot；TUI 写入与 Worker 读取由同一路径模块锁串行化，下一轮 Context 可见。
- 普通文本优先级保持：`WAITING_APPROVAL -> STEER`（不隐式决定 Approval）、`WAITING_INPUT -> ANSWER`、busy -> `STEER`、无活动任务 -> `CREATE_TASK`、其余 -> `REJECT`。

Red 测试至少覆盖：

- busy RUNNING 普通文本分类为 `STEER`。
- `WAITING_INPUT` 继续回答；`WAITING_APPROVAL` 普通文本转 Steering，不隐式 approve/reject。
- `submit_steering` 调用注入的 InterventionService、显示 sequence/安全点提示、不启动第二个 Worker。
- Service 校验 active run、空内容、缺任务、长度、脱敏和纯敏感拒绝。

### 实际实现与验证（2026-08-06）

- `app/intervention_service.py` 新增 `InterventionService`/`SteeringSubmission`；读取 `active_run_id` 后提交 Store，不回显正文，不启动 Worker。
- `interfaces/tui/commands.py` 新增 `PlainTextIntent.STEER` 与 `busy` 参数；`interfaces/tui/app.py` 新增 `submit_steering`，普通文本在 busy 状态写 Store 并提示“将在下一个安全点生效”。
- 新增 `tests/test_intervention_service.py` 5 项、`tests/test_tui_steering.py` 2 项；`test_tui_commands.py` 新增 busy/优先级 3 项。
- TUI 专项回归：`32 passed`（service/steering/commands）；app/controller/e2e/worker/hitl 回归：`63 passed`；边界修正后组合专项 `48 passed`。
- 全量 pytest：`1755 passed, 17 skipped`；首次全量运行有 1 个既有 WAITING_INPUT placeholder 时序失败，单测复跑与第二次全量均通过。
- Ruff：`All checks passed!`；MyPy：`Success: no issues found in 148 source files`。
- `uv build`：sdist + wheel 成功；`git diff --check` 通过；未修改 `.hancode/tasks/task-001/**`。

---

### S17-TUI-R2：常驻输入与协作式打断

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已实现；TUI 输入回归与全量质量门通过（2026-08-07） |
| 依赖 | S17-R1、S17-R2、S17-R4、S17-TUI |
| 开发方式 | 直接修复；保留回归验证 |

范围：输入框始终接受用户文本；有 active run 时普通文本写入 Steering，不再依赖 TUI Worker 的 `busy`、`PauseToken` 或 `request_id` 才能提交。正在运行的 Worker 不启动第二个 Worker，Worker 已结束但 run 仍有效时自动 resume。

验收标准：

- running 状态、TUI `busy=False` 或 PauseToken 已清除时仍可提交 Steering。
- active task 与另一个 running task 不一致时拒绝写入，防止任务串线。
- `WAITING_INPUT` 继续作为回答；`WAITING_APPROVAL` 继续 Steering 并自动 resume；PAUSED 接受 Steering 但不隐式 resume。
- 已开始的模型请求、工具调用和 checkpoint 不被强制终止，Steering 在下一个安全点生效。

### S17-TUI-R2 实际实现与验证（2026-08-07）

- `interfaces/tui/commands.py`：有 active task 且不在 `WAITING_INPUT` 时，普通文本统一路由为 `STEER`，不再依赖 `busy` 快照。
- `interfaces/tui/app.py`：以 `active_task_id` 路由提交，保留不同 running task 的串线保护；SteeringService 负责校验真实 `active_run_id`；Worker 忙时不启动第二个 Worker，Worker 已结束且任务仍为 RUNNING/WAITING_APPROVAL 时自动 resume，PAUSED 不隐式恢复。
- 测试覆盖：idle running view、PauseToken/request 状态过期、非 Agent Worker 忙、WAITING_APPROVAL 自动 resume；TUI 专项 `36 passed`。
- 全量 pytest：`1776 passed, 15 skipped`；Ruff、MyPy、`uv build`、`git diff --check` 通过。

---

### S17-R4：Approval 绑定、失效与二次提交门

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已实现；全量质量门通过（2026-08-06） |
| 依赖 | S17-R1、S17-R2、S17-R3、S17-TUI |
| 开发方式 | RED → GREEN → REFACTOR |
| 并发边界 | 单 HanCode 进程；TUI 与 Agent Worker 共享 InterventionStore 路径锁 |

范围：将 Approval 绑定到创建它的 `run_id` 与 Steering revision；当 Steering 改变审批前提时，使 PENDING/APPROVED Approval 失效，并在批准 Action 执行前再次通过独立 Approval commit gate。WAITING_APPROVAL 下普通文本作为 Steering 提交，不隐式批准或拒绝。

允许修改：

- `src/hancode/core/approvals.py`
- `src/hancode/runtime/approval_request.py`
- `src/hancode/storage/approvals.py`
- `src/hancode/runtime/agent_loop.py`
- `src/hancode/interfaces/tui/commands.py`
- `src/hancode/interfaces/tui/app.py`
- 对应 Approval、AgentLoop、TUI 测试；`docs/PLAN.md`、`docs/SPEC.md`、`docs/系统架构.md`、`docs/AGENT_LOG.md`。

核心语义：

- 新 Approval manifest 保存 `run_id` 与 `steering_revision_at_request`；新创建记录必须有真实绑定。
- 缺少新字段的旧 manifest 不静默补造绑定：PENDING/APPROVED 在恢复时显式过期，EXECUTING/CONSUMED fail-closed。
- 只有 PENDING/APPROVED 可以过期；EXECUTING/CONSUMED 禁止过期。
- 过期双写顺序固定为 manifest EXPIRED、清理 pending pointer、恢复 RUNNING、写 `approval_expired_by_intervention` Trace、重新规划。
- `/approve` 后的 Action 在 EXECUTING、Checkpoint、Tool dispatch 之前，使用独立 Approval commit key 再次调用 `commit_action()`；REPLAN 时不得执行旧 Action。
- Steering 正文不进入 Approval manifest 的 Trace 或普通日志。

非目标：CANCEL/STOP、跨进程文件锁、完整 Prepare—Commit—Apply 副作用搬迁。后者仍需独立任务继续完成。

Red 测试至少覆盖：

- Approval 新字段 round-trip、旧 manifest 缺字段显式失效。
- PENDING/APPROVED revision 或 run_id 不匹配过期且零 dispatch。
- EXPIRED/REJECTED + WAITING_APPROVAL 半完成恢复。
- EXECUTING/CONSUMED 禁止过期。
- Approval 二次 commit gate 的 COMMITTED/REPLAN、独立 commit key 与幂等。
- 非 checkpoint Approval 在 dispatch 前进入 EXECUTING。
- 批准 Action 成功后 Steering acknowledge。
- WAITING_APPROVAL 普通文本成为 Steering 并自动 resume；`/approve`/`/reject` 不回归。

### S17-R4 实际实现与验证（2026-08-06）

- `core/approvals.py`、`runtime/approval_request.py`：Approval manifest 新增并校验 `run_id` 与 `steering_revision_at_request`；新创建记录必须绑定真实 run，旧 manifest 保持显式 unbound。
- `storage/approvals.py`：增加 project/task/approval identity 校验；收紧 `PENDING → APPROVED/REJECTED`、`APPROVED → EXECUTING`、`EXECUTING → CONSUMED`；仅 PENDING/APPROVED 可过期，EXPIRED/REJECTED 清理幂等。
- `runtime/agent_loop.py`：恢复时校验 run/revision；PENDING/APPROVED 漂移按 manifest EXPIRED、清理 pointer、RUNNING、写 `approval_expired_by_intervention` Trace 后重新规划；旧 EXECUTING/CONSUMED 绑定异常 fail-closed；批准 Action 使用独立 Approval commit key，在 checkpoint/dispatch 前二次调用 `commit_action()`；非 checkpoint Action 也先进入 EXECUTING。
- `interfaces/tui/commands.py`、`interfaces/tui/app.py`：WAITING_APPROVAL 普通文本只作为 Steering，不隐式 approve/reject，提交后自动 resume；显式 `/approve`/`/reject` 保持原流程。
- 测试：新增 `test_approval_r4_binding.py`，补充 ApprovalStore、AgentLoop、TUI 回归；全量 pytest：`1774 passed, 15 skipped`。
- Ruff：`All checks passed!`；MyPy：改动 6 个源文件 `Success: no issues found`；未修改 `.hancode/tasks/task-001/**`。
- 提交：未提交；继续保留 `main` 工作区改动。

剩余边界：完整 Prepare—Commit—Apply 副作用搬迁、CANCEL/STOP、跨进程文件锁仍未实现。

### 重复只读动作修复（2026-08-07）

- freshness checker：读取策略与写入策略分离；可读但不可写的 `.hancode/project.json` 不再被标记为 `unsafe`，避免无意义地递增 workspace generation 并丢失目录读取证据。
- runtime memory：将 `action_constraints.forbidden_repeats` 改为 `action_guidance.reusable_evidence`，表达“可复用证据”而不是绝对禁止；目录读取证据不再仅因 generation 变化被丢弃。
- AgentLoop：SPEC、PLAN、CODE 共用重复探索 guard；首次重复只给出 memory_search/memory_read 引导，memory 检索后允许再次读取；只有连续重复且仍有当前证据时才进入 stalled/交互边界。
- 验证：第一轮相关回归 `131 passed`；AgentLoop 回归 `66 passed`；Ruff 通过；未修改 `.hancode/tasks/task-001/**`，未提交、未推送。

### 重复 memory 动作修复（2026-08-07）

- 根因：上一轮为允许合理重读而完全跳过 `memory_read` / `memory_search` 的重复 guard，导致同一 memory 片段可以无限读取。
- 修复：memory_search 按 query/path/phase、memory_read 按 memory_id/行范围参与动作身份；只有搜索返回新 hit 或读取新证据时才释放文件重读边界；重复的相同 memory 动作进入 warning/stalled。
- SPEC 契约明确下一写入目标必须是 `artifact_targets.SPEC.md`，memory_search 必须提供 query，memory_read 只能读取搜索返回的 memory_id。
- 验证：相关回归 `133 passed`；Ruff、MyPy 通过；未修改 `.hancode/tasks/task-001/**`，未提交、未推送。

### `/help` 右侧命令列表滚动浏览（2026-08-07）

- 将右侧命令内容从静态长文本改为 `ListView`，每条命令独立显示并支持终端高度不足时滚动。
- 焦点在搜索框/左侧分类时，↑/↓继续切换分类；焦点进入右侧命令列表后，↑/↓只移动命令选中项，分类和搜索变化会重置命令索引。
- 验证：TUI help/commands/steering 回归 `30 passed`；Ruff、MyPy 通过；未提交、未推送。

---

### S17-R3：Steering 确认（acknowledge / CONSUMED）

| 元信息 | 值 |
| --- | --- |
| 状态 | [x] 已实现；全量质量门与构建通过（2026-08-06） |
| 依赖 | S17-R2 |
| 开发方式 | RED → GREEN → REFACTOR |

范围：把 R2 里 `acknowledge=False` 留下的缺口补上——只有当 Action 真正通过 policy 并成功进入 apply（工具派发成功、FINISH_PHASE 成功）时，才把它实际处理过的 Steering（`snapshot.delivery_sequences`）标为 CONSUMED；策略拒绝、recovery 拒绝、parse 失败、REPLAN、ASK_USER 等待一律不标记。

允许修改：

- `src/hancode/runtime/agent_loop.py`（`_acknowledge_steering` helper + 成功 choke point 接入 + `InterventionStorePort.mark_consumed`）
- 对应扩充测试；`docs/PLAN.md`、`docs/SPEC.md`、`docs/系统架构.md`、`docs/AGENT_LOG.md`。

核心语义：

- 确认只发生在确认成功 apply 的 choke point，复用 R1 已测的 `mark_consumed`，不重复写 commit ledger。
- 确认标记 `snapshot.delivery_sequences`——即该 Action 实际观察到的记录；快照之后到达的新 Steering 不在其中，保持 effective，下一轮继续注入。
- 确认为 best-effort 审计元数据：`mark_consumed` 失败不破坏已 apply 的 Action，Steering 保持 effective。
- CONSUMED 记录仍持续注入 Context 的 `effective`（符合规范"CONSUMED 不代表失效"），仅从 `awaiting_acknowledgement` 移除。

明确非目标（留给后续）：

- 全量 Prepare—Commit—Apply 副作用边界搬迁（把所有旧决策副作用移到统一提交门之后）体量大、风险集中，本轮不做；R3 只在既有成功点补确认。
- Approval `run_id`/`steering_revision_at_request` 绑定与失效（R4）。
- TUI 接入。

Red 测试至少覆盖：

- 工具派发成功后 Steering 被 acknowledge（`mark_consumed` 收到 `delivery_sequences`）。
- policy 拒绝时不 acknowledge。

### 实际实现与验证（2026-08-06）

- `runtime/agent_loop.py`：新增 `_acknowledge_steering`（无 store/无 snapshot/无 delivery 时短路；`mark_consumed` 失败吞掉不破坏已 apply 状态；成功写 `intervention_consumed` trace）；在 TOOL_CALL 成功 `continue` 前与 FINISH_PHASE 成功 `continue` 前调用；`InterventionStorePort` 增 `mark_consumed`。
- 测试：`test_agent_loop.py` 新增 `test_steering_acknowledged_after_successful_tool_dispatch`、`test_steering_not_acknowledged_on_policy_denial`；`_build_loop`/`SpyContextBuilder` 支持可选 `intervention_store` 与 steering kwargs。
- 专项：`test_agent_loop.py` 64 passed；interventions + task_service 回归 55 passed。
- 全量 pytest：`1744 passed, 17 skipped`。
- Ruff：`All checks passed!`；MyPy：`Success: no issues found in 147 source files`。
- `uv build`：sdist + wheel 成功。
- `git diff --check` 通过；未修改 `.hancode/tasks/task-001/**`。
