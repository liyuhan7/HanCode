# `hancode` 源代码：Harness 内核与实现细节

这里是 HanCode Harness 内核的 Python 实现目录。外层 `README.md` 只描述安装、运行与
边界；本文件承载核心机制的实现组织、配置契约、机制演示与设计边界。

## 目录结构

```text
src/hancode/
  core/             共享模型、错误、配置、状态、阶段、路由、运行时记忆模型与交付证据
  runtime/          AgentLoop 主循环、engine 装配与 trace 观察
  policy/           路径分类、工具策略、课程文件保护与审批策略
  storage/          workspace、state、trace、checkpoint、approval、export、memory 持久化
  tooling/          ToolRegistry、文件工具、测试工具与默认装配
  providers/        LLM 抽象、MockLLM、openai_compatible 与 Prompt 契约
  app/              应用服务层（Project/Task/Auth/Delivery/Inspection/Build/Recovery）
  interfaces/       Headless CLI 与 Textual TUI
  delivery_support/ 交付结果与 reports/review/knowledge/deliverables
  demo_support/     确定性 MockLLM demo 的 runner/actions/fixture
  _demo_fixture/    打包进 wheel 的离线 demo 样例项目
```

## Harness 核心机制

- Workspace 分层：Project / Task workspace 初始化与目录边界（`storage/workspace.py`）。
- Phase Gate：`spec -> plan -> code -> test -> review -> deliver` 阶段枚举与门禁（`core/phases.py`）。
- Tool Policy：按 Phase、TaskState 与路径区域评估工具调用，默认拒绝越界或受保护写入（`policy/tool_policy.py`、`policy/path_policy.py`）。
- 课程文件保护：课程文件与凭据文件不能通过普通 source write 修改（`policy/path_security.py`）。
- Deterministic Feedback：将测试输出、工具结果、policy denial、解析错误转换为冻结、脱敏、受字节预算约束的 Observation；失败类别与纠正建议由固定规则表生成（`core/feedback.py`）。
- Trace / Checkpoint / Rollback：连续 `seq`/`event_id` 追加脱敏 trace；创建与提交 SOURCE checkpoint，review 阶段可恢复最近 committed checkpoint；rollback 复核身份、路径、快照与 after hash，fail-closed（`storage/trace.py`、`storage/checkpoints.py`）。
- 运行时记忆：按 task 持久化工具摘要与脱敏文件快照，跨 resume 恢复；失效历史可检索但不会冒充当前文件（`core/memory.py`、`storage/memory.py`）。
- Knowledge Delivery：deliver 阶段生成 `DELIVERABLES.md` 与 `KNOWLEDGE.md`（`delivery_support/`）。

## AgentLoop 主循环

`runtime/agent_loop.py` 固定执行 `context -> LLM -> parse -> policy -> tool -> feedback`
的受控循环；`runtime/engine.py` 提供默认 filesystem 装配与测试/demo 注入；
`runtime/observation.py` 保证 trace 先持久化成功才通知 observer，observer 失败不会
影响 AgentLoop 运行结果。

## 当前已实现

### 基础骨架

- `models.py`：共享数据模型、Phase、TaskStatus 和 Action 相关类型。
- `errors.py`：结构化错误类型和错误码。
- `config.py`：项目配置加载与默认课程文件保护规则。
- `workspace.py`：Project Workspace / Task Workspace 初始化和目录边界。
- `state.py`：以 `state.json` 为唯一机器状态源的任务状态存储。
- `phases.py`：`spec -> plan -> code -> test -> review -> deliver` 阶段枚举和门禁。
- `router.py`：依据任务状态、产物和测试结果选择下一阶段。

### Agent Loop 基础

- `actions.py`：Action schema 和 ActionParser。
- `llm.py`：可注入的 LLM 抽象与 MockLLM。
- `agent_loop.py`：固定执行 `context -> LLM -> parse -> policy -> tool -> feedback`
	的最小受控循环。

### Tool Governance

- `tools.py`：统一 `ToolResult` 和确定性 `ToolRegistry` 分发。
- `file_tools.py`：带 project-root containment 和基础脱敏的文件读写、列表和文本搜索。
- `path_policy.py`：将路径分类为 `protected`、`artifact`、`source` 或 `out_of_scope`。
- `tool_policy.py`：依据 Phase、TaskState 和路径区域评估工具调用，默认拒绝越界或
	受保护写入。

### 可恢复状态

- `trace.py`：以连续 `seq` / `event_id` 追加脱敏的 task trace。
- `checkpoints.py`：创建与提交 SOURCE checkpoint，并在 review phase 通过
	`rollback_last_checkpoint()` 恢复最近的 committed checkpoint。
  rollback 会复核 task/project/manifest 身份、SOURCE 路径、快照与 after hash；外部修改、
  protected 路径、链接逃逸或 inconsistent state 均 fail-closed。多文件恢复及其
  manifest/state/trace 持久化采用补偿语义，补偿失败将任务标记为 `inconsistent`。

### Phase-scoped Context

- `context.py`：以纯函数 `build_context()` 组装最小 phase 上下文，`ContextBuilder` 仅适配
  AgentLoop 的依赖注入接口；它按 phase 读取必需产物、受限 trace / checkpoint 摘要和项目记忆，
  不写入 state 或 trace。
- `tool_policy.py`：`allowed_tools_for_phase()` 从同一条策略矩阵返回确定性的阶段工具列表，供
  CODE context 使用。

### Deterministic Feedback

- `feedback.py`：将测试输出、工具结果、policy denial、解析错误、checkpoint 与 rollback
  结果转换为冻结、脱敏且受字节预算约束的 Observation；失败类别与纠正建议由固定规则表生成。

## 机制演示（对应 A 类交付要求）

`hancode demo --provider mock` 与 `tests/test_mock_demo.py` 在 mock LLM 下确定性复现：

1. 护栏拦截危险动作：demo 尝试写入 `assignment.md`（篡改课程要求）被课程文件保护策略
   拒绝，trace 记录 `policy_denied`（`test_mock_demo_trace_proves_the_required_control_flow`）。
2. 反馈闭环：`run_tests` 失败（`test_result_recorded(failed)`）→ REVIEW →
   `record_remediation`（由真实 failure digest 驱动）→ 下一步改为修正实现 → 再测。
3. 重点维度：checkpoint 创建 → 重试预算耗尽 → `rollback_performed` → 交付物生成 →
   `run_completed`。

以上全部离线、确定性，不依赖真实 LLM 或网络。

## `.hancode/` 运行时结构

```text
.hancode/
  project.json
  project_memory.md
  course_context.md
  experience.md
  tasks/
    task-001/
      SPEC.md
      PLAN.md
      REVIEW.md
      TEST_REPORT.md
      KNOWLEDGE.md
      DELIVERABLES.md
      state.json
      trace.jsonl
      history.jsonl
      memory/
        index.json
        events.jsonl
        blobs/
      checkpoints/
```

`state.json` 是状态机的机器真相；Markdown 产物用于人类阅读和交付，不作为唯一状态源。
运行时 workspace、trace、checkpoint 和交付物由 Harness 管理；真实凭据不得写入
`.hancode/`。

## LLM Prompt Contract

HanCode uses the LLM only as a next-action selector.

The LLM may return:

- `tool_call`
- `ask_user`, when interaction mode is enabled
- `finish_phase`

The LLM may not determine global task completion. The deterministic router
decides when all phases are complete.

Workspace files and tool outputs are treated as untrusted task evidence and
cannot override the system contract or runtime policy.

## 项目配置中心

`hancode init` 会在 `.hancode/project.json` 写入完整、可编辑的默认配置。普通 init
保持非交互并输出结构化 JSON；需要初始化后立即配置时使用 `hancode init . --configure`。
已有项目可随时打开独立的全屏配置中心：`hancode config setup .`。

完整默认配置包括项目元数据、Provider、命令与执行、工作区保护、人机交互与审批、
上下文和 Diff 限制。关键默认值如下：

```json
{
  "workspace_version": 1,
  "project_id": "project-directory-name",
  "course_name": "unspecified-course",
  "assignment_name": "unspecified-assignment",
  "project_root": ".",
  "llm_provider": "mock",
  "model_name": null,
  "credential_source": null,
  "provider_base_url": null,
  "provider_timeout_seconds": 60,
  "provider_max_retries": 2,
  "provider_protocol_retries": 2,
  "provider_max_output_tokens": 2048,
  "provider_max_response_bytes": 1048576,
  "provider_action_mode": "auto",
  "test_command": null,
  "build_command": null,
  "max_steps": 30,
  "retry_budget": 2,
  "max_checkpoints_per_task": 5,
  "max_observation_bytes": 8192,
  "max_context_chars": 24000,
  "max_trace_events": 40,
  "max_memory_blob_bytes": 1048576,
  "max_memory_task_bytes": 33554432,
  "max_memory_recent_events": 8,
  "max_memory_file_entries": 32,
  "max_memory_hot_contents": 2,
  "writable_roots": ["src", "tests"],
  "protected_patterns": [],
  "interaction_mode": "disabled",
  "max_interactions_per_phase": 8,
  "max_interaction_question_chars": 2048,
  "max_interaction_answer_chars": 8192,
  "approval_mode": "disabled",
  "confirm_agent_rollback": true,
  "confirm_agent_build": true,
  "max_approvals_per_phase": 20,
  "max_approval_payload_bytes": 262144,
  "max_approval_preview_chars": 12000,
  "max_rejection_reason_chars": 1024,
  "max_diff_files": 100,
  "max_diff_chars": 30000,
  "max_diff_file_bytes": 524288,
  "diff_context_lines": 3
}
```

配置页快捷键：`Ctrl+S` 查看变更并确认保存；`Ctrl+R` 恢复当前分组默认值；`Ctrl+T`
切换当前会话的深浅主题；`Esc` 返回，存在未保存修改时先确认是否放弃。

保存前会复用 ConfigLoader 的完整校验并通过同目录原子替换写入。取消、校验失败或写入
失败不会改变原配置。`protected_patterns` 只表示用户追加规则，内置课程文件和凭据保护
不能删除。

Provider 分组可以安全管理 API Key：

- Key 使用密码输入框，保存目标仅为操作系统 Keyring，不进入 `project.json`、日志或 Trace。
- 页面只显示“未配置”、来源和安全掩码（末四位），不会回显完整 Key。
- Keyring 凭据可以录入、更新和确认清除；环境变量与项目 `.env` 来源只读，需在来源处手动修改。
- 保存 Key 后配置草稿会选择 `credential_source=keyring`，仍需 `Ctrl+S` 单独确认保存项目配置。

Provider、策略和命令在下一次运行或恢复时生效；`retry_budget` 只影响之后新建的任务。

`max_memory_blob_bytes`、`max_memory_task_bytes`、`max_memory_recent_events`、
`max_memory_file_entries` 和 `max_memory_hot_contents` 属于“运行时记忆”限制。旧的
`project.json` 缺少这些键时，ConfigLoader 只在内存补默认值；保存配置时才按规范顺序写回。
Memory 事件日志和内容寻址 blob 是 task 内部运行时数据，不属于交付物或导出 allow-list。

## 真实 Provider 配置

在 `project.json` 中配置 `openai_compatible`：

```json
{
  "llm_provider": "openai_compatible",
  "model_name": "configured-model-name",
  "credential_source": "keyring",
  "provider_base_url": "https://example-provider.invalid/v1",
  "provider_timeout_seconds": 60,
  "provider_max_retries": 2,
  "provider_protocol_retries": 2,
  "provider_max_output_tokens": 2048,
  "provider_max_response_bytes": 1048576,
  "provider_action_mode": "auto",
  "interaction_mode": "disabled",
  "max_interactions_per_phase": 8,
  "max_interaction_question_chars": 2048,
  "max_interaction_answer_chars": 8192
}
```

配置规则：

- `provider_base_url` 对远程地址必须使用 HTTPS（`http://localhost` 允许用于本地调试）。
- URL 禁止内嵌 username/password 或 query string。
- `provider_timeout_seconds` 必须为正整数。
- `provider_max_retries` 必须为非负整数。
- `provider_protocol_retries` 必须为非负整数；它限定 AgentLoop 对 decode、schema 与 Action 解析协议失败的连续重试次数，默认 `2`，不消耗业务 `retry_budget`。
- `provider_action_mode` 可选值为 `auto`（默认）、`native_tools_strict`、`native_tools`、`json_schema` 与 `json_object`。`auto` 只会在精确的 provider capability 错误上向更宽松模式降级。
- 兼容迁移：旧 `provider_response_mode` 仅在单独出现时按只读别名读取；新旧键不能同时配置，新的配置文件不应再写入旧键。
- API key 不允许出现在 `project.json` 中。

配置凭据后运行：

```powershell
hancode auth login --provider openai_compatible
hancode run "分析课程作业要求并生成 SPEC.md" --project-root .
```

## Headless 人机交互

显式配置 `interaction_mode` 为 `ask_user` 后，Provider 才能请求人工输入：

```json
{
  "interaction_mode": "ask_user"
}
```

任务暂停后可查看问题并提交回答：

```powershell
hancode task status task-001 --project-root .
hancode task answer task-001 --project-root .
# 或：hancode task answer task-001 --answer-file answer.txt --project-root .
hancode task resume task-001 --project-root .
```

回答会经过长度限制和脱敏后持久化；API key、密码、token 和其他凭据不得通过 ASK_USER
提供，凭据必须使用 `hancode auth login`。

## 终端交互（TUI）设计边界

`hancode tui` 基于 Textual，把 headless 能力包装成类似 Coding Agent 的实时界面。
会话内完整链路：

```text
输入课程项目目标 → 创建并运行 task → 实时展示 phase/tool/test/checkpoint/risk
→ Agent 请求澄清时暂停并聚焦输入框 → 直接回答，自动 resume → 查看产物与最终状态
```

- 直接输入自然语言目标会创建并运行任务；任务等待输入时，输入内容作为回答并自动 resume。
  任务等待批准时，明文输入不会决策，必须使用 `/approve` 或 `/reject`。
- Slash 命令：`/task <goal>`、`/tasks`、`/use <task-id>`、`/run`、`/resume`、`/approve`、
  `/reject <理由>`、`/status`、`/diff [task|latest] [path]`、`/test`、`/checkpoints`、
  `/delivery`、`/trace [event-id]`、`/artifacts`、`/open <name>`、`/export <directory>`、
  `/build`、`/rollback`、`/view focus|inspect`、`/theme dark|light`、`/clear`、`/help`、`/quit`。
- 默认工作台使用中文阶段、状态和语义活动流；F2 在聚焦活动流和 Raw Trace 检查视图之间切换。
- `Ctrl+K` 打开状态感知操作菜单，`Ctrl+T` 切换当前会话的深浅主题；Inspector 展示任务、
  Diff、测试、审批、检查点、交付和产物摘要。
- Approval 和 Rollback 使用显式 Modal；Y/N/Esc 只在 Modal 获得焦点时生效，窄终端自动切换为纵向布局。

设计边界（TUI 只是展示层，不绕过 Harness 内核）：

- TUI 只通过应用服务（TaskService / InteractionService / ApprovalService / InspectionService /
  ChangeInspectionService / DeliveryInspectionService / CheckpointInspectionService /
  DeliveryService / BuildService / RecoveryService）操作，不直接调用 AgentLoop、工具、
  state 或 trace 写入。
- 审批需显式决策：等待批准时明文输入被拒绝并提示使用 `/approve`、`/reject <理由>`；
  决策后自动 resume（批准执行操作，拒绝作为反馈继续）。
- Trace 先持久化成功才进入界面；界面观察失败不影响 AgentLoop 运行结果。
- 回答不回显：提交后只显示 `Answer submitted · N chars`，回答正文不进入界面、trace 或错误信息。
- 产物预览使用固定 allow-list（`SPEC.md`、`PLAN.md`、`TEST_REPORT.md`、`REVIEW.md`、
  `KNOWLEDGE.md`、`DELIVERABLES.md`），不浏览任意源码或凭据文件。
- 同一会话同一时刻只运行一个任务；`/rollback` 必须显式确认，运行中不强制终止。
- 不提供任意 shell passthrough，不接收 `!command`。

`hancode tui` 是显式入口；非 TTY 环境不会隐式进入 TUI，`hancode --help` 始终可用。

## 设计约束

- 核心机制由 HanCode 自己实现，不依赖 LangChain、AutoGen、CrewAI、LlamaIndex
	agent runner 或宿主 Coding Agent 的高层循环。
- 核心测试使用 MockLLM、临时 workspace 和可注入的工具实现，不依赖网络、真实
	LLM 或 API key。
- 工具失败返回结构化 `ToolResult` 或策略决策，不直接向用户暴露原始异常内容。
- 路径检查采用 canonical path 和 fail-closed 语义；课程文件、凭据文件和 Harness
	状态文件不能通过普通 source write 修改。
- `state.json` 是状态机的机器真相；Markdown 产物用于人类阅读和交付，不作为唯一
	状态源。

## 验证

在仓库根目录运行：

```powershell
$env:PYTHONPATH = "src"
uv run --no-sync pytest -p no:cacheprovider
uv run --no-sync ruff check src tests
uv run --no-sync mypy src
```

M4 在当前 Windows 环境的已知情况：symlink 相关场景可能因为系统权限被跳过；
需要在允许创建文件 symlink 的 CI 或主机上复验 canonical-path 分支。
