# HanCode

HanCode 是一个面向学生课程项目的 headless CLI Coding Agent Harness。当前仓库对外可用的入口是命令行：它提供确定性的离线 MockLLM 演示、工作区初始化、交付物导出，以及凭据状态与存取边界管理。

它的核心关注点是把 AI 辅助编码过程限制在可追踪、可回退、可验证的边界内：修改前建立 checkpoint，失败时回退，工具权限受控，凭据不明文回显，MockLLM demo 不依赖网络或真实 API。

## 核心能力

HanCode 以代码实现受控的编码智能体内核：Workspace 分层隔离、Phase Gate 阶段门禁、Tool Policy 与课程文件保护、确定性 Feedback Loop、Trace Logging / Checkpoint Rollback / 运行时记忆 / 知识沉淀，并用 MockLLM 确定性验证核心机制（不依赖真实模型）。各机制的实现与配置细节见 `src/hancode/README.md`。

## 当前可用命令

HanCode 的命令都以 `hancode` 开头：`demo` 只支持 `mock`（确定性离线演示），`auth` 只管理凭据边界，`tui` 启动交互式终端会话。

- `hancode init [PROJECT_ROOT]`：`init` 只初始化项目级 `.hancode` 工作区，不创建任务或修改课程业务代码。
- `hancode demo --provider mock`：确定性离线演示。
- `hancode export --task <TASK_ID> --out <OUTPUT_DIR>`：`export` 只复制 state 声明的交付物到新的输出目录，不能覆盖已有目录，也不能把输出放进 `.hancode`。
- `hancode auth status --provider <provider>`：查看凭据状态，不回显明文。
- `hancode auth login --provider <provider>`：隐藏输入录入凭据。
- `hancode auth update --provider <provider>`：更新凭据。
- `hancode auth clear --provider <provider>`：清除凭据。
- `hancode run <GOAL> [--project-root <PROJECT_ROOT>]`：创建带 goal 的任务并立即启动 AgentLoop。
- `hancode task create <GOAL>`、`task run`、`task resume`、`task status`、`task list`、`task answer`、`task approval`、`task approve`、`task reject <TASK_ID>`：任务生命周期与人工交互（回答不回显，审批/回退需显式决策）。
- `hancode tui [--project-root <PROJECT_ROOT>]`：交互式终端会话，见「终端交互（TUI）」。

快速体验 TUI：

```powershell
hancode tui --project-root .
```

启动后直接输入课程项目目标即可创建并运行任务，或输入 `/task <goal>` 指定任务；`/help` 查看全部 Slash 命令，`Ctrl+T` 切换深浅主题。运行中的实时状态（phase / tool / test / checkpoint / risk）、暂停澄清、审批与回退 Modal、产物查看都在界面内完成，完整说明见「终端交互（TUI）」。

任务需要人工输入时返回 `waiting_input`（退出码 `4`）：用 `task status` 查看问题，`task answer` 提交回答，`task resume` 恢复。命中审批门（`approval_mode` 控制，默认 `disabled`）时返回 `waiting_approval`：用 `task approval` 查看待批操作，`task approve`/`task reject` 决策后 `task resume`；恢复时复核操作 digest 与目标文件 hash，任一失效则失败关闭（`waiting_approval` 转 `inconsistent`），绝不重复源文件写入。

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

项目已发布到 PyPI，可直接安装：

```powershell
pip install hancode
# 或隔离安装为命令行工具：
uv tool install hancode
```

安装完成后可直接使用 `hancode` 命令。

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

Demo 输出结构化 JSON，展示固定的受控流程和交付产物；它不是交互式 shell，也不是长期运行服务。`hancode export` 只复制 state 声明的交付物，不会导出 task 下的 `memory/` 目录。

Demo 使用 Python 的临时目录。运行环境的 `TEMP/TMP` 必须指向当前用户可写、可清理的目录；受限沙箱或 ACL 异常时可能返回结构化错误 `cli_internal_error`，应先修复临时目录权限再重试。

Demo 的内置测试命令为 `python -m unittest discover -s tests -q`，模拟真实项目配置的 `test_command`；运行环境必须保证 `python` 可在 `PATH` 中被 `subprocess.run`（`shell=False`）找到，否则 demo 会返回 `run_tests` 结构化失败。

## 凭据安全

当前已实现的 provider 是 `mock`、`openai_compatible`；`local` 与 `anthropic` 尚未实现。

凭据解析优先级是：

```text
keyring -> env -> dotenv -> missing
```

映射关系是：

- `openai_compatible` → `OPENAI_API_KEY`

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

`hancode demo --provider mock` 是确定性离线路径：固定 Action 序列、无需真实凭据、无需网络，用于验证 Phase Gate、Tool Policy、Feedback、Trace、Checkpoint 和 Delivery 等 Harness 机制。

### 配置真实 Provider（openai_compatible）

`openai_compatible` Provider 已实现，可接入任何 OpenAI-Compatible API；`anthropic` 和 `local` 尚未实现。三步配置：

1. 录入凭据（隐藏输入，存入系统 Keyring，不回显明文）：

   ```powershell
   hancode auth login --provider openai_compatible
   ```

2. 配置 Provider（用 `hancode init . --configure` 或直接编辑 `.hancode/project.json`）：

   - `llm_provider`：`openai_compatible`
   - `model_name`：使用的模型名
   - `credential_source`：`keyring`
   - `provider_base_url`：OpenAI-Compatible 接口地址，远程必须使用 HTTPS

3. 运行真实 Provider 驱动的任务：

   ```powershell
   hancode run "分析课程作业要求并生成 SPEC.md" --project-root .
   ```

完整配置键、校验规则、Prompt 契约与真实 Provider 配置示例见 `src/hancode/README.md`。

## 终端交互（TUI）

`hancode tui` 启动一个基于 Textual 的交互式终端会话，把 headless 能力包装成类似 Coding Agent 的实时界面：

```powershell
hancode tui --project-root .
```

它提供创建并运行任务、实时展示 phase / tool / test / checkpoint / risk、请求澄清时暂停、直接回答自动 resume、查看允许的产物与最终状态。**回答不回显**，审批与回退走显式 Modal；完整 Slash 命令列表与设计边界见 `src/hancode/README.md`。

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
uv run ruff check src tests
uv run mypy src
```

核心机制测试使用 MockLLM、stub、临时文件系统和确定性输入，不依赖真实 LLM、真实 API key 或网络。

## 项目定位与非目标

HanCode 的定位是课程项目场景里的受控 Coding Agent Harness，围绕 workspace 隔离、phase gate、trace logging、checkpoint rollback、工具治理、反馈闭环和凭据边界展开。

## 目录结构

```text
HanCode/
├── AGENTS.md                  # 本仓库的开发代理工作约定
├── Makefile                   # 常用任务入口（test / lint / typecheck / build）
├── pyproject.toml             # 包元数据、依赖与构建配置（wheel / sdist）
├── README.md                  # 本文件
├── LICENSE                    # MIT 许可证
├── .env.example               # 环境变量模板（不含真实密钥）
├── .gitlab-ci.yml             # GitLab CI（含 unit-test job）
├── .github/workflows/ci.yml   # GitHub Actions CI
├── docs/                      # 交付文档：SPEC / PLAN / SPEC_PROCESS / AGENT_LOG / 系统架构
├── src/hancode/               # Harness 内核（Python 包）
│   ├── app/                   # 应用层：凭据、任务、审批、交付服务
│   ├── core/                  # 核心模型与机制
│   ├── delivery_support/      # 交付物导出与校验
│   ├── demo_support/          # 离线 MockLLM 演示（确定性 fixture）
│   ├── interfaces/            # CLI 与 TUI 入口
│   ├── policy/                # 工具策略、路径安全、审批策略
│   ├── providers/             # LLM Provider（mock / openai_compatible）
│   ├── runtime/               # AgentLoop、memory、feedback、checkpoint
│   ├── storage/               # 运行时存储
│   ├── tooling/               # 工具实现
│   └── _demo_fixture/         # 打包进 wheel 的离线 demo 样例项目
├── examples/
│   ├── broken_project/        # 离线 demo fixture（含 SHA-256 校验）
│   └── .hancode-template/     # 脚手架期望快照
└── tests/                     # 单元 / 集成 / E2E 测试
```

## 第三方依赖与许可证

项目依赖均为宽松许可证，各自的许可证如下（版本约束见 `pyproject.toml`）：

| 依赖 | 许可证 |
|------|--------|
| pydantic | MIT |
| typer | MIT |
| keyring | MIT |
| python-dotenv | BSD-3-Clause |
| httpx | BSD-3-Clause |
| jsonschema | MIT |
| textual | MIT |
| pytest（dev） | MIT |
| ruff（dev） | MIT |
| mypy（dev） | MIT |

本仓库自身的 `LICENSE` 为 MIT（Copyright (c) 2026 liyuhan7）。

