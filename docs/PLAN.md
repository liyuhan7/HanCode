# HanCode 实现计划

> 状态：设计草案  
> 仓库处于规范和规划阶段。完整实现必须在 SPEC、PLAN 和冷启动验证完成后开始。  
> **For agentic workers:** REQUIRED SUB-SKILL: 使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 按任务卡逐项执行。实现任务必须使用 TDD：先红、再绿、再重构。

## 项目定位

HanCode 是一个为学生课程项目调校的 Coding Agent Harness。它的核心是 AI 辅助编码的控制回路：修改代码、运行测试、根据失败自我修正、失败超限时回退。实现计划必须把这条回路落到确定性代码机制中，而不是依赖提示词或宿主智能体行为。

主线保持一致：

- Feedback Loop 管测试信号的分类与回灌，驱动 Agent 针对性修复。
- Checkpoint Rollback 管代码修改前快照与失败后的可回退恢复。
- Tool Policy 管工具权限与课程文件保护。
- Phase Mode 管需求、计划、编码、测试、审查、交付各阶段的工具权限。
- Workspace 分层管课程项目级与任务级上下文隔离（支撑维度）。
- Knowledge Delivery 管最终的项目复盘、错误记录和知识沉淀。

## 全局规则

- 遵循 Superpowers 工作流：`brainstorming` -> `writing-plans` -> `using-git-worktrees` -> `subagent-driven-development` / `executing-plans` -> `test-driven-development` -> `requesting-code-review` -> `finishing-a-development-branch`。
- 在 `SPEC.md`、`PLAN.md`、冷启动验证和 `SPEC_PROCESS.md` 修订记录完成前，不得修改 `src/hancode/` 下的 harness kernel 实现模块。
- 实现任务使用 TDD：先写失败测试并观察红色结果，再写最小实现，再重构。
- 每个实现任务使用独立 worktree 或独立执行会话。
- 每个任务完成后更新本文件状态、提交 hash、验证结果，并在 `docs/AGENT_LOG.md` 记录过程证据。
- 核心机制测试不得依赖网络、真实 LLM、真实 API key 或宿主编码智能体能力。
- 不得提交真实凭据，不得在日志、trace、README、测试快照或错误信息中打印 secret。
- 不引入 LangChain `AgentExecutor`、AutoGen、CrewAI、LlamaIndex agent runner 或宿主编码智能体 runner 充当交付 harness 内核。
- `state.json` 是唯一机器状态源；Markdown 产物可读可编辑，但不作为状态机唯一依据。
- `docs/SPEC.md` 是需求契约；`docs/系统架构.md` 是实现组织参考；二者冲突时以 `docs/SPEC.md` 为准。

## MVP 与 post-MVP 边界

MVP 必须完成：

- Python 3.11+ 包结构、CLI 入口和 MockLLM 模式。
- Project Workspace / Task Workspace 文件系统隔离。
- `spec -> plan -> code -> test -> review -> deliver` 六阶段路由与门禁。
- Action schema、ActionParser、MockLLM、AgentLoop、ToolRegistry、ToolExecutor。
- PathClassifier、ToolPolicy、课程文件保护和受限测试命令。
- TraceLogger、CheckpointManager、Rollback、retry budget。
- FeedbackBuilder 的确定性失败分类与 observation 回灌。
- ContextBuilder 的 phase-based 最小上下文选择。
- TEST_REPORT、REVIEW、KNOWLEDGE、DELIVERABLES 生成。
- MockLLM 机制演示：policy denial、测试失败反馈、retry、强制 rollback。
- Python package build 与 CI `unit-test` job。

post-MVP：

- 单 task 单活跃 runner 的并发锁。
- blocked 后的 resume 断点续跑语义。
- pending checkpoint 的启动崩溃恢复。
- `confirm_before_write` 写前人工确认。
- Docker demo image。
- 复杂 TUI、WebUI、多语言测试命令扩展、完整 Git 分支管理。

## 任务依赖图

```text
M0 规划与冷启动
  T0 统一规划文档与冷启动验证准备

M1 骨架（串行）
  T1 Workspace 初始化
    -> T2 配置与状态模型
    -> T3 PhaseGate 与 WorkspaceRouter

M2 主贡献回路（部分并行）
  T3 -> T4 ActionParser / MockLLM / AgentLoop
  T3 -> T5 ToolRegistry / PathClassifier / ToolPolicy
  T5 -> T6 TraceLogger / CheckpointManager / Rollback
  T2 -> T7 ContextBuilder
  T4, T5, T6 -> T8 FeedbackBuilder 失败分类与 retry 回灌 ★

M3 集成与交付
  T4, T5, T6, T7, T8 -> T9 Knowledge Delivery 与 MockLLM demo
  T9 -> T10 CLI / 凭据 / package / CI

★ = 主贡献核心任务，优先保证。
并行组 A：T4 与 T5 可在 T3 完成后并行。
并行组 B：T7 可在 T2 完成后独立推进，不依赖 T4/T5。
并行组 C：T6 依赖 T5，但可与 T7 并行。
```

## 里程碑

| 里程碑 | 完成条件 | 对应 SPEC 验收 |
| --- | --- | --- |
| M0 计划可冷启动 | `docs/PLAN.md` 能让陌生 agent 仅凭 SPEC + PLAN 尝试 1-2 个任务，并把问题记录到 `docs/SPEC_PROCESS.md` | 通用要求 §4.3, §4.5 |
| M1 骨架可跑 | MockLLM 能驱动 task 创建与 phase 路由；缺 SPEC / PLAN 时业务代码写入被拒 | SPEC FR-1, FR-2, FR-10, FR-11, §10.5, §10.9 |
| M2 主贡献闭环 | 测试失败分类 -> observation -> retry budget -> 强制 rollback 在 MockLLM 下确定性复现 | SPEC FR-7, FR-14, FR-15, §10.11, §10.13, §11.8 |
| M3 可交付 | `hancode demo --provider mock` 全流程生成 trace、TEST_REPORT、REVIEW、KNOWLEDGE、DELIVERABLES；package build 与 CI unit-test 通过 | SPEC §10.1, §10.18, §10.21 |

## 任务卡片

### 任务 0：统一 PLAN 并准备冷启动验证

| 元信息 | 值 |
| --- | --- |
| 状态 | [~] 进行中 |
| 依赖 | 无 |
| 可并行 | 不并行；这是实现前置任务 |
| Worktree / PR | 当前规划分支；实现阶段另建 worktree |
| 主贡献相关 | 否 |
| Commit | 完成后填写实际 hash |

**目标**  
生成可执行、可追溯、可冷启动验证的 `docs/PLAN.md`，使陌生 agent 能仅凭 `docs/SPEC.md` 和本计划理解任务边界。

**涉及文件**

- `docs/PLAN.md`：重写为依赖图、里程碑、任务卡片和需求追溯表。
- `docs/SPEC_PROCESS.md`：记录 PLAN 生成与冷启动验证安排。
- `docs/AGENT_LOG.md`：记录本次 writing-plans 活动。

**SPEC 依据**

- `docs/SPEC.md` §10 验收标准。
- `docs/SPEC.md` §11 领域与机制设计。
- `docs/agent-guides/workflow.md` Phase Gate 与 Cold-Start Validation。

**接口契约**

```text
输入：docs/SPEC.md、docs/系统架构.md、课程通用要求、A 类 Harness 要求。
输出：docs/PLAN.md 固定任务卡结构。
不变量：实现任务不得在冷启动验证前修改 src/hancode/ harness kernel。
错误处理：若冷启动 agent 无法执行某任务，记录到 SPEC_PROCESS.md 并修订 SPEC/PLAN。
```

**预期失败测试（TDD 红阶段，先写这些，先跑出红）**

- 本任务是规划任务，不写 runtime 测试。
- 文档验证锚点：
  - `test_plan_contains_dependency_graph`：断言 `docs/PLAN.md` 包含 `## 任务依赖图`。
  - `test_plan_contains_traceability_table`：断言 `docs/PLAN.md` 包含 `## 需求→任务追溯`。
  - `test_plan_tasks_use_fixed_card_fields`：断言每个任务卡包含 `元信息`、`SPEC 依据`、`接口契约`、`预期失败测试`、`非目标 / 边界`。

**实现要点（绿阶段最小实现的方向，非逐行）**

- 保留已有定位、全局规则和 MVP 边界。
- 把原粗粒度任务改为固定卡片。
- 在追溯表中覆盖全部 P0/P1 harness 机制。
- 在冷启动验证前不新增 `src/hancode/` 实现模块。

**验证步骤（可复制粘贴执行）**

```powershell
Get-Content -Raw -Encoding UTF8 docs\PLAN.md
Select-String -Path docs\PLAN.md -Pattern '## 任务依赖图','## 里程碑','## 需求→任务追溯','### 任务 8'
git status --short
```

完成判定：上述命令能读出新结构，且 `git status --short` 只显示规划相关文档变化。

**非目标 / 边界**

- 不实现 harness kernel。
- 不改测试占位文件。
- 不启动真实 LLM。

---

### 任务 1：创建 Workspace 初始化机制

| 元信息 | 值 |
| --- | --- |
| 状态 | [ ] 未开始 |
| 依赖 | 任务 0 |
| 可并行 | 不并行；后续任务依赖 workspace 结构 |
| Worktree / PR | `codex/workspace-init` -> PR 创建后填写 |
| 主贡献相关 | 否，支撑维度 |
| Commit | 完成后填写实际 hash |

**目标**  
实现 Project Workspace 与 Task Workspace 初始化，使 `.hancode/` 能稳定保存项目记忆、任务状态、trace、checkpoint 和阶段产物。

**涉及文件**

- `src/hancode/workspace.py`：新建，承载 `WorkspaceManager`、路径解析和 task workspace 初始化。
- `src/hancode/models.py`：新建，承载共享 dataclass / pydantic 模型。
- `tests/test_workspace.py`：新建，覆盖 workspace 初始化与 task 隔离。

**SPEC 依据**

- SPEC FR-10：Project Workspace 与 Task Workspace。
- SPEC §7.3 文件持久化映射。
- SPEC §10.6 Workspace 与任务隔离验收。
- 系统架构 §5.5 Persistence Layer。

**接口契约**

```python
from pathlib import Path

def init_project_workspace(project_root: Path, project_id: str, course_name: str, assignment_name: str) -> Path: ...
def init_task_workspace(project_root: Path, task_id: str) -> Path: ...
def task_path(project_root: Path, task_id: str) -> Path: ...
```

输入：课程项目根目录、project ID、course name、assignment name、task ID。  
输出：`.hancode/` 与 `.hancode/tasks/<task_id>/` 的实际路径。  
不变量：不同 task 的 `state.json`、`trace.jsonl`、`history.jsonl`、`checkpoints/` 不混用。  
错误处理：workspace root 不存在时创建；路径不在 project root 内时返回结构化错误或抛出项目自定义异常。

**预期失败测试（TDD 红阶段，先写这些，先跑出红）**

- `test_workspace_initializes_project_files`
  - 构造：`tmp_path` 作为 project root。
  - 断言：生成 `.hancode/project.json`、`project_memory.md`、`course_context.md`、`experience.md`。
- `test_task_workspace_initializes_required_artifacts`
  - 构造：调用 `init_task_workspace(tmp_path, "task-001")`。
  - 断言：生成 `SPEC.md`、`PLAN.md`、`TEST_REPORT.md`、`REVIEW.md`、`KNOWLEDGE.md`、`DELIVERABLES.md`、`state.json`、`trace.jsonl`、`history.jsonl`、`checkpoints/`。
- `test_workspace_has_separate_history`
  - 构造：创建 `task-001` 和 `task-002`。
  - 断言：两个 task 的 history 与 trace 路径不同。

**实现要点（绿阶段最小实现的方向，非逐行）**

- 使用 `Path.resolve()` 做 root 内路径约束。
- 初始化 Markdown 文件时写入最小标题，不写空白文件。
- `state.json` 初始化为机器可读 JSON，包含 `task_id`、`status="created"`、`current_phase="spec"`、`artifacts`、`retry_budget_remaining=2`。

**验证步骤（可复制粘贴执行）**

```powershell
python -m pytest tests/test_workspace.py -v
python -m ruff check src/hancode/workspace.py src/hancode/models.py tests/test_workspace.py
python -m mypy src/hancode/workspace.py src/hancode/models.py
```

完成判定：上述全绿，并且 task 隔离测试证明不同 task 的 trace/history/checkpoint 不混用。

**非目标 / 边界**

- 不实现 ContextBuilder。
- 不实现 checkpoint 文件快照。
- 不实现真实 LLM 或 CLI。

---

### 任务 2：实现配置加载与状态模型

| 元信息 | 值 |
| --- | --- |
| 状态 | [ ] 未开始 |
| 依赖 | 任务 1 |
| 可并行 | 完成后释放任务 3 与任务 7 |
| Worktree / PR | `codex/config-state` -> PR 创建后填写 |
| 主贡献相关 | 否，支撑维度 |
| Commit | 完成后填写实际 hash |

**目标**  
实现配置对象、状态读写和启动一致性检查，使 AgentLoop、ToolPolicy、ContextBuilder 能共享同一机器状态源。

**涉及文件**

- `src/hancode/config.py`：新建，承载 `HanCodeConfig` 与配置加载。
- `src/hancode/state.py`：新建，承载 `TaskState`、`StateStore` 与 state reconciliation。
- `src/hancode/errors.py`：新建，承载结构化错误类型。
- `tests/test_config.py`：新建，覆盖默认配置与非法配置。
- `tests/test_state.py`：新建，覆盖 state 读写和不一致检测。

**SPEC 依据**

- SPEC FR-9：配置加载与运行约束。
- SPEC §7.4 `state.json` 状态约束。
- SPEC §7.8 数据一致性。
- SPEC §10.7 ConfigLoader 验收。
- 系统架构 §6.1 ConfigLoader。

**接口契约**

```python
from pathlib import Path

class HanCodeConfig: ...
class TaskState: ...

def load_config(project_root: Path, task_id: str) -> HanCodeConfig: ...
def load_state(task_root: Path) -> TaskState: ...
def save_state(task_root: Path, state: TaskState) -> None: ...
def reconcile_state(task_root: Path, state: TaskState) -> TaskState: ...
```

输入：project root、task ID、task root、已有 `state.json`。  
输出：配置对象与任务状态对象。  
不变量：`state.json` 是唯一机器状态源；发现 artifact 漂移时进入 `inconsistent`，不自动回写为 completed。  
错误处理：JSON 损坏时返回 `blocked` 或抛出结构化配置错误；`max_steps <= 0`、`retry_budget < 0` 拒绝启动。

**预期失败测试（TDD 红阶段，先写这些，先跑出红）**

- `test_config_loads_defaults`
  - 构造：最小 `.hancode/project.json`。
  - 断言：`max_steps == 30`、`retry_budget == 2`、`max_checkpoints_per_task == 5`。
- `test_invalid_retry_budget_is_rejected`
  - 构造：`retry_budget = -1`。
  - 断言：加载失败，错误字段包含 `retry_budget`。
- `test_state_json_is_single_machine_source`
  - 构造：`state.json.artifacts.SPEC = false`，但文件系统存在 `SPEC.md`。
  - 断言：reconcile 后状态为 `inconsistent`，不把 SPEC 自动置为 true。
- `test_state_parse_error_blocks_task`
  - 构造：损坏的 `state.json`。
  - 断言：返回 blocked 错误摘要。

**实现要点（绿阶段最小实现的方向，非逐行）**

- 优先使用标准库 dataclass；若使用 pydantic，仅用于配置校验。
- 状态枚举限制为 `created`、`running`、`blocked`、`failed`、`completed`、`inconsistent`。
- 默认 protected patterns 包含作业说明、教师测试、评分脚本、样例数据、`.env` 和凭据文件。

**验证步骤（可复制粘贴执行）**

```powershell
python -m pytest tests/test_config.py tests/test_state.py -v
python -m ruff check src/hancode/config.py src/hancode/state.py src/hancode/errors.py
python -m mypy src/hancode/config.py src/hancode/state.py src/hancode/errors.py
```

完成判定：配置与状态测试全绿，且不一致检测不会自动修复 `state.json`。

**非目标 / 边界**

- 不实现 CLI 配置命令。
- 不实现 OS keyring。
- 不实现 task 并发锁。

---

### 任务 3：实现 PhaseGate 与 WorkspaceRouter

| 元信息 | 值 |
| --- | --- |
| 状态 | [ ] 未开始 |
| 依赖 | 任务 2 |
| 可并行 | 完成后 T4、T5 可并行 |
| Worktree / PR | `codex/phase-router` -> PR 创建后填写 |
| 主贡献相关 | 否，控制流基础 |
| Commit | 完成后填写实际 hash |

**目标**  
实现无副作用的 phase 路由和阶段门禁，使缺少前置产物时不能进入 code phase，非 code phase 不能修改业务代码。

**涉及文件**

- `src/hancode/phases.py`：新建，承载 `Phase`、`RoutingDecision`、`WorkspaceRouter`、phase artifact 规则。
- `tests/test_phase_gate.py`：新建，覆盖阶段路由与门禁。

**SPEC 依据**

- SPEC FR-11：课程项目 Phase Gate。
- SPEC §6.2 phase 数据流。
- SPEC §10.5 Phase Gate 验收。
- 系统架构 §6.5 WorkspaceRouter。

**接口契约**

```python
from dataclasses import dataclass
from enum import Enum

class Phase(str, Enum): ...

@dataclass(frozen=True)
class RoutingDecision:
    phase: Phase
    reason: str
    rollback_required: bool = False

def select_next_phase(state: TaskState) -> RoutingDecision: ...
def can_write_artifact(phase: Phase, artifact_name: str) -> bool: ...
def can_write_source(phase: Phase, state: TaskState) -> bool: ...
```

输入：`TaskState` 与目标 action 所在 phase。  
输出：`RoutingDecision` 或写入判定。  
不变量：router 是纯函数，不直接写 `state.json`。  
错误处理：状态为 `inconsistent` 时拒绝高风险动作；未知 phase 返回 blocked 决策。

**预期失败测试（TDD 红阶段，先写这些，先跑出红）**

- `test_spec_phase_rejects_edit_file`
  - 构造：当前 phase 为 `spec`，action 试图写 source。
  - 断言：`can_write_source` 为 false。
- `test_plan_required_before_code_phase`
  - 构造：SPEC 完成但 PLAN 未完成。
  - 断言：router 返回 `plan`，不是 `code`。
- `test_code_phase_allows_edit_file`
  - 构造：SPEC 与 PLAN 均完成，当前 task 可进入 code。
  - 断言：`can_write_source(Phase.CODE, state)` 为 true。
- `test_deliver_phase_rejects_source_write`
  - 构造：phase 为 `deliver`。
  - 断言：业务代码写入被拒。

**实现要点（绿阶段最小实现的方向，非逐行）**

- 把 artifact 写入白名单按 phase 固定：spec 写 `SPEC.md`，plan 写 `PLAN.md`，test 写 `TEST_REPORT.md`，review 写 `REVIEW.md`，deliver 写 `KNOWLEDGE.md` 和 `DELIVERABLES.md`。
- 测试失败后路由到 review；retry budget 耗尽时设置 `rollback_required=True`。
- router 不读取 Markdown 内容，只读 `TaskState.artifacts` 和测试状态字段。

**验证步骤（可复制粘贴执行）**

```powershell
python -m pytest tests/test_phase_gate.py -v
python -m ruff check src/hancode/phases.py tests/test_phase_gate.py
python -m mypy src/hancode/phases.py
```

完成判定：阶段门禁测试全绿，且 router 无文件写入副作用。

**非目标 / 边界**

- 不实现 ToolPolicy 路径分类。
- 不实现 AgentLoop。
- 不解析 Markdown 产物作为状态源。

---

### 任务 4：实现 ActionParser、MockLLM 与 AgentLoop 骨架

| 元信息 | 值 |
| --- | --- |
| 状态 | [ ] 未开始 |
| 依赖 | 任务 3 |
| 可并行 | 与任务 5 可并行 |
| Worktree / PR | `codex/agent-loop` -> PR 创建后填写 |
| 主贡献相关 | 是，主循环基础 |
| Commit | 完成后填写实际 hash |

**目标**  
实现自有 agent loop 骨架，使 MockLLM action 序列能通过 parse -> policy -> tool -> feedback 的受控链路运行，并受 `max_steps` 限制。

**涉及文件**

- `src/hancode/actions.py`：新建，承载 action schema、parser 和 parse error。
- `src/hancode/llm.py`：新建，承载 `LLMClient` 协议、`MockLLM`。
- `src/hancode/agent_loop.py`：新建，承载 `AgentLoop`。
- `tests/test_actions.py`：新建，覆盖 action 解析。
- `tests/test_llm.py`：新建，覆盖 MockLLM。
- `tests/test_agent_loop.py`：新建，覆盖 max steps 与 policy 调用。

**SPEC 依据**

- SPEC FR-1：AgentLoop 主循环。
- SPEC FR-2：LLM 抽象与 MockLLM。
- SPEC FR-3：Action 解析与校验。
- SPEC §10.1 AgentLoop 验收。
- 系统架构 §6.2 AgentLoop、§6.9 ActionParser、§6.14 LLMClient / MockLLM。

**接口契约**

```python
from typing import Protocol, Any

class LLMClient(Protocol):
    def next_action(self, context: dict[str, Any]) -> dict[str, Any]: ...

class MockLLM:
    def __init__(self, actions: list[dict[str, Any]]) -> None: ...
    def next_action(self, context: dict[str, Any]) -> dict[str, Any]: ...

def parse_action(raw: dict[str, Any]) -> Action | ParseError: ...

class AgentLoop:
    def run(self, task_id: str) -> AgentRunResult: ...
```

输入：结构化 context、MockLLM action 序列、工具注册表、policy、state。  
输出：`AgentRunResult`，包含 status、steps、tool calls、risks、final observation。  
不变量：LLM 不直接访问文件系统，不直接执行工具；所有 action 执行前必须经过 parser 与 policy。  
错误处理：action 格式错误转为 observation；MockLLM 序列耗尽返回 blocked；超过 max_steps 返回 blocked。

**预期失败测试（TDD 红阶段，先写这些，先跑出红）**

- `test_mock_llm_returns_actions_in_order`
  - 构造：两个 action。
  - 断言：两次 `next_action` 依次返回。
- `test_mock_llm_exhaustion_blocks_loop`
  - 构造：空 action 序列。
  - 断言：AgentLoop 结果 status 为 `blocked`。
- `test_action_parser_rejects_unknown_tool`
  - 构造：`tool_name="unknown_tool"`。
  - 断言：返回 parse error 或 validation error。
- `test_action_parser_requires_reason_for_write_actions`
  - 构造：`edit_file` 缺少 reason。
  - 断言：解析失败或 action 标记 invalid。
- `test_max_steps_prevents_infinite_loop`
  - 构造：MockLLM 连续返回 wait / no-op，`max_steps=2`。
  - 断言：第 3 步前停止，status 为 `blocked`。
- `test_agent_loop_calls_policy_before_tool`
  - 构造：spy policy 与 spy tool。
  - 断言：policy 调用发生在 tool 调用前。

**实现要点（绿阶段最小实现的方向，非逐行）**

- action 字段至少包含 `tool_name`、`args`、`reason`、`phase`。
- `finish` action 表示 LLM 请求结束，但是否 completed 由 ResultBuilder 或 loop 状态判定，不由 LLM 单方决定。
- AgentLoop 第一版只接收依赖注入的 stub policy、stub tool registry、stub feedback builder，T5/T8 再替换为真实实现。

**验证步骤（可复制粘贴执行）**

```powershell
python -m pytest tests/test_actions.py tests/test_llm.py tests/test_agent_loop.py -v
python -m ruff check src/hancode/actions.py src/hancode/llm.py src/hancode/agent_loop.py
python -m mypy src/hancode/actions.py src/hancode/llm.py src/hancode/agent_loop.py
```

完成判定：MockLLM 可驱动 loop，parse error、policy denial、max_steps 均不会执行工具。

**非目标 / 边界**

- 不实现真实 LLM provider。
- 不实现复杂 prompt 模板。
- 不实现真实文件工具。

---

### 任务 5：实现 ToolRegistry、PathClassifier 与 ToolPolicy

| 元信息 | 值 |
| --- | --- |
| 状态 | [ ] 未开始 |
| 依赖 | 任务 3 |
| 可并行 | 与任务 4 可并行 |
| Worktree / PR | `codex/tool-policy` -> PR 创建后填写 |
| 主贡献相关 | 是，治理护栏基础 |
| Commit | 完成后填写实际 hash |

**目标**  
实现工具注册、路径三区分类和课程文件保护策略，使越权工具、受保护文件、无 reason 写入、缺 SPEC/PLAN 写入都被确定性拒绝。

**涉及文件**

- `src/hancode/tools.py`：新建，承载 `ToolRegistry`、`ToolExecutor`、结构化 `ToolResult`。
- `src/hancode/path_policy.py`：新建，承载 `PathClassifier` 与 path zone。
- `src/hancode/tool_policy.py`：新建，承载 `ToolPolicy` 与 `PolicyDecision`。
- `tests/test_tools.py`：新建，覆盖工具注册和不存在工具。
- `tests/test_path_policy.py`：新建，覆盖路径分类和逃逸。
- `tests/test_tool_policy.py`：新建，覆盖治理规则。

**SPEC 依据**

- SPEC FR-4：ToolRegistry 与工具分发。
- SPEC FR-5：ToolPolicy 治理护栏。
- SPEC FR-13：课程文件保护策略。
- SPEC §10.9 ToolPolicy 验收。
- SPEC §11.4 危险动作与治理护栏。
- 系统架构 §6.15 PathClassifier。

**接口契约**

```python
from enum import Enum

class PathZone(str, Enum):
    ARTIFACT = "artifact"
    SOURCE = "source"
    PROTECTED = "protected"
    OUTSIDE = "outside"

def classify_path(project_root: Path, target: str, protected_patterns: list[str]) -> PathZone: ...
def evaluate_policy(action: Action, phase: Phase, state: TaskState, config: HanCodeConfig) -> PolicyDecision: ...
```

输入：action、phase、state、config、目标路径。  
输出：`PolicyDecision`，包含 `allowed`、`reason`、`requires_checkpoint`、`rule_id`。  
不变量：可写 action 的目标路径由 `PathClassifier` 推导，不要求 action 自带 `target_kind`。  
错误处理：路径无法分类、路径逃逸、protected zone、未知工具、缺 reason 均拒绝且不得执行工具。

**预期失败测试（TDD 红阶段，先写这些，先跑出红）**

- `test_tool_not_allowed_in_workspace_is_denied`
  - 构造：未注册工具或未授权工具。
  - 断言：policy denied，tool 未执行。
- `test_edit_file_requires_reason`
  - 构造：`edit_file` 缺少 reason。
  - 断言：denied，rule_id 指向 reason 缺失。
- `test_policy_protects_assignment_files`
  - 构造：写 `assignment.md` 或课程说明。
  - 断言：classified as protected，denied。
- `test_policy_protects_teacher_tests_or_grading_scripts`
  - 构造：写 `tests/teacher_test.py` 或 `grading.py`。
  - 断言：denied。
- `test_policy_rejects_path_escape`
  - 构造：目标路径 `../outside.py`。
  - 断言：zone 为 `outside`，denied。
- `test_policy_requires_spec_and_plan_before_source_write`
  - 构造：state 中 SPEC 或 PLAN 未完成。
  - 断言：source write denied。
- `test_code_phase_source_write_requires_checkpoint`
  - 构造：code phase 中合法 source write。
  - 断言：allowed 且 `requires_checkpoint=True`。

**实现要点（绿阶段最小实现的方向，非逐行）**

- allow-list 优先识别 artifact zone，再叠加 protected patterns。
- Windows 路径使用 `Path.resolve()` 与大小写归一化比较。
- MVP 不提供通用 `run_shell`；只允许配置好的 `run_tests`。
- policy denial 必须包含纠正建议，供 FeedbackBuilder 回灌。

**验证步骤（可复制粘贴执行）**

```powershell
python -m pytest tests/test_tools.py tests/test_path_policy.py tests/test_tool_policy.py -v
python -m ruff check src/hancode/tools.py src/hancode/path_policy.py src/hancode/tool_policy.py
python -m mypy src/hancode/tools.py src/hancode/path_policy.py src/hancode/tool_policy.py
```

完成判定：课程文件保护、路径逃逸、缺 reason、缺 SPEC/PLAN、未注册工具全部被确定性拒绝。

**非目标 / 边界**

- 不做 HITL 审批流程。
- 不实现通用 shell 执行器。
- 不修改教师测试或评分脚本。

---

### 任务 6：实现 TraceLogger、CheckpointManager 与 Rollback

| 元信息 | 值 |
| --- | --- |
| 状态 | [ ] 未开始 |
| 依赖 | 任务 5 |
| 可并行 | 与任务 7 可并行 |
| Worktree / PR | `codex/trace-checkpoint` -> PR 创建后填写 |
| 主贡献相关 | 是，可回退编码状态核心 |
| Commit | 完成后填写实际 hash |

**目标**  
实现事件级 trace、业务代码修改前 checkpoint 和最近 checkpoint rollback，使失败恢复可测试、可审计、可复盘。

**涉及文件**

- `src/hancode/trace.py`：新建，承载 `TraceLogger`、`TraceEvent`。
- `src/hancode/checkpoints.py`：新建，承载 `CheckpointManager`、manifest、rollback。
- `tests/test_trace.py`：新建，覆盖 JSONL 事件、脱敏、写失败处理。
- `tests/test_checkpoints.py`：新建，覆盖创建、恢复、排除规则和 manifest 损坏。

**SPEC 依据**

- SPEC FR-8：TraceLogger。
- SPEC FR-14：Checkpoint 与 Rollback。
- SPEC §7.5 TraceEvent 事件模型。
- SPEC §7.6 Checkpoint 数据模型。
- SPEC §10.12 TraceLogger 验收。
- SPEC §10.13 Checkpoint / Rollback 验收。
- 系统架构 §6.12 TraceLogger、§6.13 CheckpointManager。

**接口契约**

```python
def append_trace(task_root: Path, event: TraceEvent) -> None: ...
def create_checkpoint(task_root: Path, files: list[Path], reason: str) -> CheckpointManifest: ...
def rollback_last_checkpoint(task_root: Path) -> RollbackResult: ...
```

输入：task root、事件、即将修改的 source files、rollback 请求。  
输出：JSONL trace、checkpoint manifest、恢复文件列表。  
不变量：checkpoint 不包含 `.env`、凭据文件、受保护课程文件、教师测试、评分脚本、样例数据。  
错误处理：trace 写失败阻止高风险工具；manifest 损坏时 rollback failed / blocked，不盲目恢复。

**预期失败测试（TDD 红阶段，先写这些，先跑出红）**

- `test_trace_appends_jsonl_event_with_event_id`
  - 构造：写入一个 `phase_started`。
  - 断言：`trace.jsonl` 一行合法 JSON，含 `event_id`、`event_type`、`phase`。
- `test_trace_redacts_secret_like_values`
  - 构造：事件包含 `Authorization: Bearer fake-secret-123`。
  - 断言：trace 不包含原始 secret。
- `test_edit_file_creates_checkpoint`
  - 构造：合法 source write 前调用 checkpoint。
  - 断言：生成 manifest 和 before hash。
- `test_rollback_last_checkpoint_restores_file`
  - 构造：修改文件后 rollback。
  - 断言：文件内容恢复，结果包含 restored files。
- `test_checkpoint_excludes_env_and_protected_files`
  - 构造：文件列表含 `.env` 与 teacher test。
  - 断言：manifest 不包含这些路径。
- `test_damaged_manifest_blocks_rollback`
  - 构造：损坏 manifest JSON。
  - 断言：rollback 返回 failed / blocked，写入错误摘要。

**实现要点（绿阶段最小实现的方向，非逐行）**

- `event_id` 使用 task 内递增格式，如 `evt-000001`。
- manifest 记录 `checkpoint_id`、`task_id`、`phase`、`reason`、`files`、hash、created_at、status。
- rollback 成功后写 trace，并更新 state 中 latest checkpoint / rollback 信息。
- checkpoint 只快照 action args 推导出的目标文件集合。

**验证步骤（可复制粘贴执行）**

```powershell
python -m pytest tests/test_trace.py tests/test_checkpoints.py -v
python -m ruff check src/hancode/trace.py src/hancode/checkpoints.py
python -m mypy src/hancode/trace.py src/hancode/checkpoints.py
```

完成判定：trace、checkpoint、rollback 测试全绿，且 secret fixture 不出现在 trace 或 manifest 中。

**非目标 / 边界**

- 不实现 checkpoint pruning。
- 不实现 git-based rollback。
- 不恢复 protected files。

---

### 任务 7：实现 ContextBuilder 与 workspace-scoped memory

| 元信息 | 值 |
| --- | --- |
| 状态 | [ ] 未开始 |
| 依赖 | 任务 2 |
| 可并行 | 与任务 6 可并行 |
| Worktree / PR | `codex/context-builder` -> PR 创建后填写 |
| 主贡献相关 | 否，支撑维度 |
| Commit | 完成后填写实际 hash |

**目标**  
实现按 phase 选择最小必要上下文的 ContextBuilder，使课程规则、任务产物、测试结果、checkpoint 和 trace 摘要按需进入 LLM 上下文。

**涉及文件**

- `src/hancode/context.py`：新建，承载 `ContextBuilder`、上下文预算和 trace 摘要选择。
- `tests/test_context_builder.py`：新建，覆盖 phase include/exclude、task 隔离和截断。

**SPEC 依据**

- SPEC FR-6：ContextBuilder 与记忆选择。
- SPEC FR-12：课程项目上下文构造。
- SPEC §11.5 记忆与上下文机制。
- SPEC §10.8 ContextBuilder 验收。
- 系统架构 §6.8 ContextBuilder。

**接口契约**

```python
def build_context(project_root: Path, task_id: str, phase: Phase, config: HanCodeConfig) -> dict[str, str]: ...
```

输入：project root、task ID、phase、config。  
输出：结构化 context 字典，包含 phase、course context、task artifacts、trace summary。  
不变量：不得无条件加载全部历史；不得混入其他 task 的 trace、history、checkpoint。  
错误处理：code phase 缺 SPEC/PLAN 时返回 blocked context 或明确风险；context 超预算时按规则截断。

**预期失败测试（TDD 红阶段，先写这些，先跑出红）**

- `test_context_builder_includes_course_context`
  - 构造：project workspace 有 `course_context.md`。
  - 断言：context 包含课程背景与评分标准摘要。
- `test_code_phase_context_requires_spec_and_plan`
  - 构造：code phase 缺 PLAN。
  - 断言：context 标记 missing prerequisite，不能假装可编码。
- `test_review_phase_includes_test_report_changed_files_and_checkpoint`
  - 构造：存在 TEST_REPORT、changed files、checkpoint manifest。
  - 断言：review context 包含三者摘要。
- `test_deliver_phase_includes_required_artifacts`
  - 构造：SPEC、PLAN、TEST_REPORT、REVIEW、trace。
  - 断言：deliver context 包含这些输入。
- `test_context_builder_does_not_mix_other_task_trace`
  - 构造：两个 task 都有 trace。
  - 断言：task-001 context 不含 task-002 trace。
- `test_context_builder_respects_max_context_chars`
  - 构造：超长 project_memory。
  - 断言：context 总长度不超过配置预算，并保留课程规则优先。

**实现要点（绿阶段最小实现的方向，非逐行）**

- 先加载课程要求和当前 task 关键产物，再加载 project memory / experience。
- trace 摘要最多取 `max_trace_events` 条。
- 截断时保留课程规则、当前 phase 必需产物和最近失败信息。

**验证步骤（可复制粘贴执行）**

```powershell
python -m pytest tests/test_context_builder.py -v
python -m ruff check src/hancode/context.py tests/test_context_builder.py
python -m mypy src/hancode/context.py
```

完成判定：各 phase 上下文测试全绿，且不同 task 的 trace/history 不混用。

**非目标 / 边界**

- 不实现向量检索。
- 不实现嵌入模型或上下文压缩模型。
- 不把 project experience 置于课程要求之上。

---

### 任务 8：实现 FeedbackBuilder 失败分类与 retry 回灌

| 元信息 | 值 |
| --- | --- |
| 状态 | [ ] 未开始 |
| 依赖 | 任务 4, 任务 5, 任务 6 |
| 可并行 | 不并行；主贡献闭环任务 |
| Worktree / PR | `codex/feedback-loop` -> PR 创建后填写 |
| 主贡献相关 | 是，主贡献回路核心 |
| Commit | 完成后填写实际 hash |

**目标**  
实现确定性测试失败分类、policy denial / parse error / rollback observation 回灌和 retry budget 消耗，使失败分类 -> 针对性修复 -> 强制 rollback 可复现。

**涉及文件**

- `src/hancode/feedback.py`：新建，承载 `FeedbackBuilder`、`FeedbackReport`、失败分类规则和 hint 表。
- `src/hancode/agent_loop.py`：修改，接入 feedback、retry budget 和 review 路由。
- `tests/test_feedback.py`：新建，覆盖失败分类和 observation。
- `tests/test_feedback_loop.py`：新建，覆盖 MockLLM 下的 retry 与 rollback 闭环。

**SPEC 依据**

- SPEC FR-7：反馈回灌机制。
- SPEC FR-15：测试报告与审查记录。
- SPEC §11.3.1 测试失败分类。
- SPEC §11.6 主贡献维度。
- SPEC §11.8 MockLLM 机制演示。
- SPEC §10.11 FeedbackBuilder 验收。
- 系统架构 §6.11 FeedbackBuilder。

**接口契约**

```python
from enum import Enum

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
输出：`FeedbackReport` / `Observation`，包含 category、summary、hint、risk、next_step。  
不变量：同一输入分类结果稳定；反馈来自确定性工具结果或系统判定，不来自 LLM 自我评价。  
错误处理：无法分类但 exit code 非零时返回 `unknown`，保留摘要并提示人工检查。

**预期失败测试（TDD 红阶段，先写这些，先跑出红）**

- `test_feedback_classifies_syntax_error`
  - 构造：输出包含 `SyntaxError`。
  - 断言：`failure_category == SYNTAX_ERROR`。
- `test_feedback_classifies_import_error`
  - 构造：输出包含 `ModuleNotFoundError`。
  - 断言：`failure_category == IMPORT_ERROR`。
- `test_feedback_classifies_assertion_failure`
  - 构造：输出包含 `AssertionError` 或 pytest assertion diff。
  - 断言：`failure_category == ASSERTION_FAILURE`。
- `test_feedback_classifies_error_exception`
  - 构造：输出包含 `KeyError` 或 `TypeError` 栈帧。
  - 断言：`failure_category == ERROR_EXCEPTION`。
- `test_feedback_classifies_timeout_or_crash`
  - 构造：`timed_out=True` 或非正常退出。
  - 断言：`failure_category == TIMEOUT_OR_CRASH`。
- `test_feedback_classification_is_deterministic_on_fixture`
  - 构造：同一 fixture 跑两次。
  - 断言：两次 report 完全相等。
- `test_feedback_hint_matches_category`
  - 构造：assertion failure。
  - 断言：hint 提醒回看 PLAN 验证依据。
- `test_policy_denial_becomes_observation`
  - 构造：ToolPolicy 拒绝 protected file。
  - 断言：observation 包含拒绝原因和纠正建议。
- `test_retry_budget_exhaustion_forces_rollback`
  - 构造：MockLLM 连续两轮测试失败，`retry_budget=2`。
  - 断言：预算归零后调用 rollback，trace 记录 rollback，loop 保持 review / blocked。

**实现要点（绿阶段最小实现的方向，非逐行）**

- 分类优先级：syntax -> import -> assertion -> timeout/crash -> error exception -> unknown。
- 分类在完整输出上执行，摘要截断在分类之后执行。
- hint 由 category 查表，不调用 LLM。
- AgentLoop 在测试失败后进入 review；retry budget 未耗尽时允许定向回 code；耗尽后强制 rollback。

**验证步骤（可复制粘贴执行）**

```powershell
python -m pytest tests/test_feedback.py tests/test_feedback_loop.py -v
python -m ruff check src/hancode/feedback.py src/hancode/agent_loop.py tests/test_feedback.py tests/test_feedback_loop.py
python -m mypy src/hancode/feedback.py src/hancode/agent_loop.py
```

完成判定：失败分类、policy denial 回灌、retry budget、强制 rollback 全链路测试全绿。

**非目标 / 边界**

- 不让真实 LLM 判断失败类别。
- 不自动安装缺失依赖。
- 不绕过测试或修改教师测试来制造通过结果。

---

### 任务 9：实现 Knowledge Delivery 与 MockLLM 机制 Demo

| 元信息 | 值 |
| --- | --- |
| 状态 | [ ] 未开始 |
| 依赖 | 任务 4, 任务 5, 任务 6, 任务 7, 任务 8 |
| 可并行 | 不并行；集成任务 |
| Worktree / PR | `codex/mock-demo-delivery` -> PR 创建后填写 |
| 主贡献相关 | 是，主贡献演示 |
| Commit | 完成后填写实际 hash |

**目标**  
实现 TEST_REPORT、REVIEW、KNOWLEDGE、DELIVERABLES 和 MockLLM demo，使课程项目全流程与主贡献机制可被 trace 证明。

**涉及文件**

- `src/hancode/delivery.py`：新建，承载 report / review / knowledge / deliverable 生成。
- `examples/broken_project/`：补充或整理 MockLLM demo fixture。
- `scripts/demo_mock_loop.py`：新建，可重复运行的 MockLLM 机制演示脚本。
- `tests/test_delivery.py`：新建，覆盖 Markdown 产物最低结构。
- `tests/test_mock_demo.py`：新建，覆盖 demo trace 事件序列。

**SPEC 依据**

- SPEC FR-15：测试报告与审查记录。
- SPEC FR-16：Knowledge Delivery。
- SPEC §10.14 Review / Deliver 验收。
- SPEC §10.21 可测试性约定。
- SPEC §11.8 MockLLM 机制演示。
- 系统架构 §12.4 MockLLM 测试架构。

**接口契约**

```python
def write_test_report(task_root: Path, report: FeedbackReport, command: str) -> Path: ...
def write_review(task_root: Path, coverage: list[RequirementCoverage], risks: list[str]) -> Path: ...
def write_knowledge(task_root: Path, items: list[KnowledgeItem]) -> Path: ...
def write_deliverables(task_root: Path, result: AgentRunResult) -> Path: ...
def run_mock_demo(project_root: Path) -> AgentRunResult: ...
```

输入：task root、测试反馈、需求覆盖、风险、trace 摘要、最终结果。  
输出：`TEST_REPORT.md`、`REVIEW.md`、`KNOWLEDGE.md`、`DELIVERABLES.md` 和 demo trace。  
不变量：deliver phase 不修改业务代码；缺 KNOWLEDGE 或 DELIVERABLES 不得 completed。  
错误处理：缺少测试或 review 时在 `risks[]` 中说明；核心需求未覆盖或测试未通过时 blocked / failed。

**预期失败测试（TDD 红阶段，先写这些，先跑出红）**

- `test_code_change_requires_test_or_risk_note`
  - 构造：有 changed files 但无测试报告。
  - 断言：最终结果包含 risk，不直接 completed。
- `test_deliver_requires_knowledge_file`
  - 构造：deliver phase 缺 `KNOWLEDGE.md`。
  - 断言：status 不为 completed。
- `test_deliver_requires_deliverables_file`
  - 构造：deliver phase 缺 `DELIVERABLES.md`。
  - 断言：status 不为 completed。
- `test_review_contains_requirement_coverage_table`
  - 构造：需求覆盖输入。
  - 断言：`REVIEW.md` 包含需求、证据、状态、风险列。
- `test_knowledge_contains_decisions_failures_and_reusable_lessons`
  - 构造：trace 与反馈项。
  - 断言：`KNOWLEDGE.md` 包含课程知识点、设计决策、测试失败、错误修复、可复用模式。
- `test_mock_demo_trace_contains_policy_denial_feedback_checkpoint_rollback`
  - 构造：运行 MockLLM demo。
  - 断言：trace 包含 `policy_checked` denied、`feedback_generated`、`checkpoint_created`、`rollback_completed`。

**实现要点（绿阶段最小实现的方向，非逐行）**

- Markdown 产物使用稳定标题，便于课程评估和测试断言。
- demo 使用 MockLLM action 序列，不接真实 LLM。
- demo 中至少包含三条路径：policy denial、一次测试失败反馈、两次失败后 rollback。
- `examples/broken_project/` 只作为 fixture，不作为 HanCode 自身实现。

**验证步骤（可复制粘贴执行）**

```powershell
python -m pytest tests/test_delivery.py tests/test_mock_demo.py -v
python scripts/demo_mock_loop.py
python -m ruff check src/hancode/delivery.py scripts/demo_mock_loop.py tests/test_delivery.py tests/test_mock_demo.py
python -m mypy src/hancode/delivery.py
```

完成判定：MockLLM demo 可重复运行，trace 能证明主贡献回路真实发生，交付产物结构满足 SPEC 最低标准。

**非目标 / 边界**

- 不做 WebUI。
- 不用真实 LLM 生成知识总结。
- 不把 `.hancode/` 整体提交为分发产物。

---

### 任务 10：实现 CLI、凭据边界、package build 与 CI

| 元信息 | 值 |
| --- | --- |
| 状态 | [ ] 未开始 |
| 依赖 | 任务 9 |
| 可并行 | 不并行；最终交付任务 |
| Worktree / PR | `codex/cli-package-ci` -> PR 创建后填写 |
| 主贡献相关 | 否，交付与安全边界 |
| Commit | 完成后填写实际 hash |

**目标**  
实现可运行 CLI、凭据状态边界、Python package build 和 CI unit-test job，使 HanCode 能在无真实凭据的 MockLLM 模式下完成演示与课程交付验证。

**涉及文件**

- `src/hancode/cli.py`：新建，承载 Typer CLI。
- `src/hancode/credentials.py`：新建，承载 `CredentialProvider`、fake keyring 测试边界。
- `pyproject.toml`：修改，确认 console script、dev 依赖和 build 元数据。
- `.gitlab-ci.yml`：新建，课程要求的 `unit-test` job。
- `.github/workflows/ci.yml`：视仓库现状同步保留或调整。
- `README.md`：补充分发、安装、运行、key 安全配置、已知限制。
- `tests/test_cli.py`：新建，覆盖 CLI help、demo、exit code。
- `tests/test_credentials.py`：新建，覆盖不打印 secret。
- `tests/test_package_metadata.py`：新建，覆盖包元数据。

**SPEC 依据**

- SPEC §8 凭据与分发设计。
- SPEC §9 技术选型。
- SPEC §10.18 凭据与分发验收。
- SPEC §10.21.6 CLI / TUI 命令行为。
- 通用要求 §3.1 凭据安全、§3.2 分发、§4.8 测试、最终交付清单。
- 系统架构 §5.1 Headless CLI、§18.5 CredentialProvider。

**接口契约**

```python
def credentials_status(provider: str) -> CredentialStatus: ...
def credentials_set(provider: str, secret: str) -> None: ...
def credentials_clear(provider: str) -> None: ...

# CLI commands
hancode init
hancode run "<goal>" --provider mock
hancode demo --provider mock
hancode auth status --provider openai
hancode auth login --provider openai
hancode auth clear --provider openai
hancode export --task task-001 --out deliverables/
```

输入：CLI 参数、隐藏输入凭据、workspace 路径。  
输出：稳定 exit code、脱敏凭据状态、MockLLM demo 结果、导出产物。  
不变量：CLI 不通过命令行参数接收明文 key；`auth status` 只显示 configured/source/masked_id。  
错误处理：provider 未知 exit code 1；配置错误 exit code 2；trace/checkpoint 不可恢复错误 exit code 3。

**预期失败测试（TDD 红阶段，先写这些，先跑出红）**

- `test_cli_help_displays_commands`
  - 构造：`CliRunner().invoke(app, ["--help"])`。
  - 断言：输出含 `demo`、`run`、`auth`、`export`。
- `test_cli_demo_runs_with_mock_provider_without_credentials`
  - 构造：运行 `demo --provider mock`。
  - 断言：exit code 0，输出含 completed / blocked 明确状态，不要求真实 key。
- `test_auth_status_does_not_print_secret`
  - 构造：fake credential provider 返回 fake secret。
  - 断言：输出不含 secret 原文。
- `test_auth_login_does_not_accept_key_argument`
  - 构造：尝试通过 CLI 参数传 key。
  - 断言：命令拒绝或 help 中不存在 key 参数。
- `test_python_package_metadata_has_console_script`
  - 构造：读取 `pyproject.toml`。
  - 断言：`hancode = "hancode.cli:app"`。
- `test_ci_contains_unit_test_job`
  - 构造：读取 `.gitlab-ci.yml`。
  - 断言：存在 job 名 `unit-test`，命令含 `python -m pytest`。

**实现要点（绿阶段最小实现的方向，非逐行）**

- Typer CLI 只调用 TaskController / demo runner，不绕过 core。
- `CredentialProvider.get_secret()` 只允许 provider adapter 调用；CLI/TUI 使用 `status()`。
- README 写清 wheel 安装、MockLLM demo、真实 provider 凭据配置、`.env` 明文风险和已知限制。
- CI 默认只运行 MockLLM 核心测试，不依赖真实 LLM、网络或 secret。

**验证步骤（可复制粘贴执行）**

```powershell
python -m pytest
python -m ruff check src tests scripts
python -m mypy src
python -m build
hancode --help
hancode demo --provider mock
```

完成判定：测试、lint、type check、package build、CLI help、MockLLM demo 全绿；CI 文件包含 `unit-test` job。

**非目标 / 边界**

- Docker demo image 属 post-MVP。
- 不实现真实 provider smoke test 作为 CI 必需项。
- 不实现复杂 WebUI；若课程最终强制线上 WebUI，需要在 SPEC_PROCESS 中记录范围变更并单独补计划。

## 需求→任务追溯

| SPEC 锚点 | 任务 | 状态 |
| --- | --- | --- |
| FR-1 AgentLoop 主循环 | T4, T8 | [ ] |
| FR-2 LLM 抽象与 MockLLM | T4, T9 | [ ] |
| FR-3 Action 解析与校验 | T4, T5 | [ ] |
| FR-4 ToolRegistry 与工具分发 | T5 | [ ] |
| FR-5 ToolPolicy 治理护栏 | T5 | [ ] |
| FR-6 ContextBuilder 与记忆选择 | T7 | [ ] |
| FR-7 反馈回灌机制 | T8 | [ ] |
| FR-8 TraceLogger | T6 | [ ] |
| FR-9 配置加载与运行约束 | T2, T10 | [ ] |
| FR-10 Project Workspace 与 Task Workspace | T1 | [ ] |
| FR-11 课程项目 Phase Gate | T3 | [ ] |
| FR-12 课程项目上下文构造 | T7 | [ ] |
| FR-13 课程文件保护策略 | T5 | [ ] |
| FR-14 Checkpoint 与 Rollback | T6, T8 | [ ] |
| FR-15 测试报告与审查记录 | T8, T9 | [ ] |
| FR-16 Knowledge Delivery | T9 | [ ] |
| §8 凭据与分发设计 | T10 | [ ] |
| §10.21 可测试性约定 | T5, T6, T7, T8, T9, T10 | [ ] |
| §11.3.1 测试失败分类 | T8 | [ ] |
| §11.4 危险动作与治理护栏 | T5 | [ ] |
| §11.5 记忆与上下文机制 | T1, T7 | [ ] |
| §11.6 主贡献维度 | T6, T8, T9 | [ ] |
| §11.8 MockLLM 机制演示 | T9 | [ ] |

## 冷启动验证安排

冷启动验证必须在实现前完成：

1. 使用不同于主开发智能体的第二个 agent。
2. 新 session，不导入当前对话历史或 memory。
3. 只提供 `docs/SPEC.md` 与 `docs/PLAN.md`。
4. 要求第二个 agent 选择 T1 与 T5，或 T3 与 T8 中的 1-2 个任务尝试执行。
5. 要求第二个 agent 遇到不确定处暂停询问，不凭猜测继续。
6. 将暂停点、误解、SPEC / PLAN 缺口和修订前后差异记录到 `docs/SPEC_PROCESS.md`。

## 自检结果

- Spec coverage：FR-1 至 FR-16 均已映射到任务。
- Placeholder scan：任务卡保留用于执行期填写的 PR / Commit 字段；这些字段是课程过程追踪字段，不是实现细节占位。
- Type consistency：`TaskState`、`HanCodeConfig`、`Phase`、`Action`、`PolicyDecision`、`ToolResult`、`FeedbackReport`、`TraceEvent`、`CheckpointManifest` 在任务间命名保持一致。
- Scope check：MVP 聚焦自实现 harness core、MockLLM deterministic tests、主贡献回路和 package/CI；Docker、复杂 TUI、WebUI、多语言扩展保持 post-MVP 或单独补计划。
