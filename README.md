# HanCode

HanCode 是一个面向学生课程项目的 headless CLI Coding Agent Harness。当前仓库对外可用的入口是命令行：它提供确定性的离线 MockLLM 演示、工作区初始化、交付物导出，以及凭据状态与存取边界管理。

它的核心关注点是把 AI 辅助编码过程限制在可追踪、可回退、可验证的边界内：修改前建立 checkpoint，失败时回退，工具权限受控，凭据不明文回显，MockLLM demo 不依赖网络或真实 API。

## Harness 核心机制

- Workspace 分层隔离课程项目级和任务级上下文。
- Phase Gate 限制 spec、plan、code、test、review、deliver 各阶段的可用动作。
- Tool Policy 和课程文件保护策略阻止危险或越界写入。
- Feedback Loop 对测试失败分类并回灌修复建议。
- Trace Logging、Checkpoint Rollback 和 Knowledge Delivery 让过程可审计、可回退、可交付。
- MockLLM 使用确定性 Action 序列验证核心机制，不依赖真实模型。

## 当前可用命令

仓库当前实现并暴露的 CLI 命令如下：

- `hancode init [PROJECT_ROOT]`
- `hancode demo --provider mock`
- `hancode export --task <TASK_ID> --out <OUTPUT_DIR> [--project-root <PROJECT_ROOT>]`
- `hancode auth status --provider <provider>`
- `hancode auth login --provider <provider>`
- `hancode auth update --provider <provider>`
- `hancode auth clear --provider <provider>`
- `hancode run <GOAL> [--task-id <TASK_ID>] [--project-root <PROJECT_ROOT>]`
- `hancode task create <GOAL> [--task-id <TASK_ID>] [--project-root <PROJECT_ROOT>]`
- `hancode task run <TASK_ID> [--project-root <PROJECT_ROOT>]`
- `hancode task resume <TASK_ID> [--project-root <PROJECT_ROOT>]`
- `hancode task status <TASK_ID> [--project-root <PROJECT_ROOT>]`
- `hancode task answer <TASK_ID> [--interaction-id <ID>] [--answer-file <PATH>] [--project-root <PROJECT_ROOT>]`
- `hancode task approval <TASK_ID> [--project-root <PROJECT_ROOT>]`
- `hancode task approve <TASK_ID> [--approval-id <ID>] [--project-root <PROJECT_ROOT>]`
- `hancode task reject <TASK_ID> [--approval-id <ID>] [--reason <TEXT>] [--project-root <PROJECT_ROOT>]`
- `hancode task list [--project-root <PROJECT_ROOT>]`
- `hancode tui [--project-root <PROJECT_ROOT>]`

其中 `demo` 只支持 `mock`，是确定性的离线演示；`auth` 只管理凭据边界，不会把 secret 打到 stdout；`tui` 启动交互式终端会话，见下文「终端交互（TUI）」。

命令行为边界：

- `init` 只初始化项目级 `.hancode` 工作区，不创建任务或修改课程业务代码。
- `export` 只复制 state 声明的交付物到新的输出目录，不能覆盖已有目录，也不能把输出放进 `.hancode`。
- `run` 创建带 goal 的任务并立即启动 AgentLoop。
- `task create` 只创建任务，不运行 Agent。
- `task run` 以 `resume=False` 运行已有任务。
- `task resume` 以 `resume=True` 恢复 blocked 或可恢复状态。
- `task status` 查询任务当前状态。
- `task answer` 从 stdin 或 UTF-8 answer file 提交待处理问题的回答，不回显回答全文。
- `task approval` 展示待批准操作的工具、目标文件和 bounded/redacted diff 预览。
- `task approve` 批准待处理操作，随后 `task resume` 会直接执行该操作而不再调用 Provider；操作幂等（重复批准即成功），与已拒绝冲突时返回退出码 `4`。
- `task reject` 拒绝待处理操作并可附带 `--reason`，恢复后 AgentLoop 将拒绝作为反馈继续；操作幂等，与已批准冲突时返回退出码 `4`。
- `task list` 列出当前项目所有任务。
- `tui` 启动基于 Textual 的交互式终端会话。

当任务需要人工输入时，`task run` 和根级 `run` 返回 JSON 状态 `waiting_input`，并使用退出码 `4`；使用 `task status` 查看问题，提交回答后执行 `task resume`。

当任务命中审批门（由 `.hancode/project.json` 的 `approval_mode` 控制，默认 `disabled`）时返回状态 `waiting_approval`；使用 `task approval` 查看待批操作及 diff 预览，`task approve` 或 `task reject` 决策后执行 `task resume`。审批决策会在恢复时复核操作 digest 与目标文件 hash：任一失效则失败关闭（`waiting_approval` 转 `inconsistent`），绝不重复源文件写入。

## 课程项目流程

HanCode 使用固定的轻量流程：

```text
spec -> plan -> code -> test -> review -> deliver
```

- `spec`：分析课程项目要求，生成 `SPEC.md`，不得修改业务代码。
- `plan`：根据 `SPEC.md` 拆解实现任务，生成 `PLAN.md`，不得修改业务代码。
- `code`：按 `PLAN.md` 修改代码，修改前必须创建 checkpoint。
- `test`：运行测试，记录测试命令和结果，生成或更新 `TEST_REPORT.md`。
- `review`：检查需求符合性、代码质量、测试结果和是否需要 rollback。
- `deliver`：生成最终总结、`DELIVERABLES.md`、`KNOWLEDGE.md`，输出结构化结果。

## `.hancode/` 运行时结构

HanCode 使用课程项目导向的轻量本地目录：

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
      checkpoints/
```

运行时 workspace、trace、checkpoint 和交付物由 Harness 管理；真实凭据不得写入 `.hancode/`。

## 安装与分发

开发环境要求：Python 3.11+、uv，以及 Windows 10+、macOS 13+ 或 Linux x86_64 环境。

从源码安装并准备开发环境：

```powershell
uv venv --python 3.11
uv sync --locked --extra dev
```

构建 Python wheel / sdist：

```powershell
uv build
```

在目标机安装当前 wheel：

```powershell
uv tool install dist/hancode-0.1.0-py3-none-any.whl
```

安装完成后可直接使用 `hancode` 命令。Docker 不是当前必需分发路径。

## 快速开始：MockLLM

MockLLM 不需要真实凭据、网络或远程模型。源码环境下运行：

```powershell
uv run hancode --help
uv run hancode demo --provider mock
```

### wheel 安装后的命令

wheel 安装后运行：

```powershell
hancode --help
hancode demo --provider mock
```

Demo 输出结构化 JSON，展示固定的受控流程和交付产物；它不是交互式 shell，也不是长期运行服务。

Demo 使用 Python 的临时目录。运行环境的 `TEMP/TMP` 必须指向当前用户可写、可清理的目录；受限沙箱或 ACL 异常时可能返回结构化错误 `cli_internal_error`，应先修复临时目录权限再重试。

Demo 的内置测试命令为 `python -m unittest discover -s tests -q`，模拟真实项目配置的 `test_command`；运行环境必须保证 `python` 可在 `PATH` 中被 `subprocess.run`（`shell=False`）找到，否则 demo 会返回 `run_tests` 结构化失败。

## 凭据安全

当前支持的 provider 是 `mock`、`local`、`openai_compatible`、`anthropic`。

凭据解析优先级是：

```text
keyring -> env -> dotenv -> missing
```

映射关系是：

- `openai_compatible` → `OPENAI_API_KEY`
- `anthropic` → `ANTHROPIC_API_KEY`

凭据相关命令示例：

```powershell
hancode auth status --provider openai_compatible
hancode auth login --provider openai_compatible
hancode auth update --provider openai_compatible
hancode auth clear --provider openai_compatible
```

安全边界：

- `mock` 和 `local` 不需要凭据；运行 MockLLM 不会调用 secret 读取接口。
- `auth login` 和 `auth update` 使用隐藏输入，不能通过命令行参数传入 key。
- `auth status` 只返回配置状态、来源和掩码，不回显明文。
- `keyring` 是首选存储；环境变量和 `.env` 只作为读取来源。
- `.env` 会以明文保存值，存在明文风险；不要提交 `.env`，不要把 key 写入 README、trace、checkpoint 或项目目录。
- 不得提交真实 API 密钥、令牌或其他凭据。本文档不包含任何 key 值。
- 如果当前来源是环境变量或 `.env`，`auth clear` 不会修改外部来源，必须先手动清除对应值。

## MockLLM 与真实 Provider

MockLLM 是确定性离线路径：它使用固定 Action 序列、无需真实凭据、无需网络，用于验证 Phase Gate、Tool Policy、Feedback、Trace、Checkpoint 和 Delivery 等 Harness 机制。

`openai_compatible` Provider 已实现：配置 `provider_base_url` 和凭据后，`hancode run` 可以通过真实 OpenAI-Compatible API 生成 Action。Provider 重试不消耗任务 retry budget；Provider 失败后任务进入 `blocked` 而非 `inconsistent`，可以 `task resume` 恢复。`anthropic` 和 `local` 尚未实现。

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
  "provider_max_output_tokens": 2048,
  "provider_max_response_bytes": 1048576,
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

回答会经过长度限制和脱敏后持久化；API key、密码、token 和其他凭据不得通过 ASK_USER 提供，凭据必须使用 `hancode auth login`。

## 终端交互（TUI）

`hancode tui` 启动一个基于 Textual 的交互式终端会话，把上述 headless 能力包装成类似 Coding Agent 的实时界面：

```powershell
hancode tui --project-root .
```

会话内的完整链路：

```text
输入课程项目目标
→ 创建并运行 task
→ 实时展示 phase / tool / test / checkpoint / risk
→ Agent 请求澄清时暂停并聚焦输入框
→ 直接回答，自动 resume
→ 查看允许的产物与最终状态
```

界面元素与命令：

- 直接输入自然语言目标会创建并运行任务；任务等待输入时，输入内容作为回答并自动 resume。任务等待批准时，明文输入不会决策，必须使用 `/approve` 或 `/reject`。
- Slash 命令：`/task <goal>`、`/tasks`、`/use <task-id>`、`/run`、`/resume`、`/approve`、`/reject <理由>`、`/status`、`/diff [task|latest] [path]`、`/test`、`/checkpoints`、`/delivery`、`/trace [event-id]`、`/artifacts`、`/open <name>`、`/export <directory>`、`/build`、`/rollback`、`/clear`、`/help`、`/quit`。
- PhaseBar 展示 `spec → plan → code → test → review → deliver` 六阶段状态，只反映持久化状态，不自行推进。
- ActivityLog 逐条显示 TraceEvent；DetailPanel 展示事件、Diff、Test Report、Checkpoint、Delivery、Artifact 和 Build 摘要。
- Approval 和 Rollback 使用显式 Modal；Y/N/Esc 只在 Modal 获得焦点时生效，窄终端自动切换为纵向布局。

设计边界（TUI 只是展示层，不绕过 Harness 内核）：

- TUI 只通过应用服务（TaskService / InteractionService / ApprovalService / InspectionService / ChangeInspectionService / DeliveryInspectionService / CheckpointInspectionService / DeliveryService / BuildService / RecoveryService）操作，不直接调用 AgentLoop、工具、state 或 trace 写入。
- **审批需显式决策**：批准/拒绝是不可逆的外向操作，等待批准时明文输入被拒绝并提示使用 `/approve`、`/reject <理由>`，绝不由零散输入推断决策；决策后自动 resume（批准执行操作，拒绝作为反馈继续）。
- Trace 先持久化成功才进入界面；界面观察失败不影响 AgentLoop 运行结果。
- **回答不回显**：提交后只显示 `Answer submitted · N chars`，回答正文不进入界面、trace 或错误信息。
- 产物预览使用固定 allow-list（`SPEC.md`、`PLAN.md`、`TEST_REPORT.md`、`REVIEW.md`、`KNOWLEDGE.md`、`DELIVERABLES.md`），不浏览任意源码或凭据文件。
- 同一会话同一时刻只运行一个任务；`/rollback` 必须显式确认，运行中不强制终止。
- 不提供任意 shell passthrough，不接收 `!command`。

`hancode tui` 是显式入口；非 TTY 环境不会隐式进入 TUI，`hancode --help` 始终可用。

## 已知限制

当前 README 只描述已经可用的能力，不把未来能力写成现成能力：

- `hancode run` 已实现 Headless 任务入口。默认 mock Provider 因 MockLLM action 耗尽会以 `blocked` 结束；配置 `openai_compatible` 和凭据后可由真实模型驱动。
- `anthropic` 和 `local` Provider 尚未实现。
- ASK_USER 支持 Headless CLI 与 `hancode tui` 的暂停、回答持久化和 resume。
- `hancode tui` 提供交互式终端会话；不支持多任务并行、流式 Token、自由聊天、任意 shell、强制取消或代码编辑器。
- Streaming 尚未实现。
- WebUI 尚未实现。
- Demo 使用固定的离线 fixture，不是开放式自然语言编码会话。
- Docker 不是当前必需分发路径，也不作为本任务的可运行交互入口。
- 支持 Python 3.11+；OS keyring 后端是否可用取决于目标机配置。`TEMP` / `TMP` 不可写时 MockLLM demo 无法完成临时 workspace 生命周期。部分 Windows symlink/junction 测试可能因权限跳过。

## 验证命令

以下命令与当前仓库契约一致，可用于本地验证：

```powershell
uv sync --locked --extra dev
uv build
uv run hancode --help
uv run hancode demo --provider mock
uv run pytest
uv run ruff check src tests scripts
uv run mypy src
```

核心机制测试使用 MockLLM、stub、临时文件系统和确定性输入，不依赖真实 LLM、真实 API key 或网络。

## 项目定位与非目标

HanCode 的定位是课程项目场景里的受控 Coding Agent Harness，围绕 workspace 隔离、phase gate、trace logging、checkpoint rollback、工具治理、反馈闭环和凭据边界展开。

当前版本不面向竞赛编程助手、大型自主软件开发 Agent、企业级 Agent 平台、多用户系统、复杂 Web 应用或 MCP 工具市场。
