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

其中 `demo` 只支持 `mock`，是确定性的离线演示；`auth` 只管理凭据边界，不会把 secret 打到 stdout。

命令行为边界：

- `init` 只初始化项目级 `.hancode` 工作区，不创建任务或修改课程业务代码。
- `export` 只复制 state 声明的交付物到新的输出目录，不能覆盖已有目录，也不能把输出放进 `.hancode`。

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

MockLLM 是当前可运行的确定性路径：它使用固定 Action 序列、无需真实凭据、无需网络，并用于验证 Phase Gate、Tool Policy、Feedback、Trace、Checkpoint 和 Delivery 等 Harness 机制。

CredentialProvider 已提供 provider 凭据状态与安全存取边界，但真实 Provider 执行尚未实现。配置了 `openai_compatible` 或 `anthropic` 凭据，不代表当前 CLI 已经可以执行真实模型任务。

## 已知限制

当前 README 只描述已经可用的能力，不把未来能力写成现成能力：

- `hancode run` 尚未实现。
- REPL/TUI/WebUI 尚未实现。
- 真实 Provider 执行尚未实现；当前可运行 Demo 只有 MockLLM。
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
