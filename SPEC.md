# HanCode 规范

> 状态：草稿  
> 项目类型：A · 编码智能体框架

## 1. 问题陈述

TODO

HanCode 旨在实现一个轻量级的编码智能体框架。

该项目关注 LLM 周围的工程层：智能体循环、动作解析、工具调度、护栏、反馈传感器、记忆、配置、凭据处理和分发。

## 2. 目标用户

TODO

潜在用户包括：

- 学习 AI4SE 工程工作流的学生
- 希望拥有小型且可检查的编码智能体框架的开发者
- 需要确定性模拟 LLM 演示的评估者
- 希望理解编码智能体在提示词之外如何工程化实现的用户

## 3. 用户故事

TODO

此处应编写至少五个 INVEST 风格的用户故事。

示例占位符：

### 用户故事 1

作为一名开发者，我希望 HanCode 能够读取目标仓库中的文件，以便在修改代码之前进行检查。

### 用户故事 2

作为一名开发者，我希望 HanCode 只能在配置的工作区内部写入文件更改，以免意外修改项目之外的文件。

### 用户故事 3

作为一名开发者，我希望 HanCode 在做出更改后运行测试，以便获得客观反馈。

### 用户故事 4

作为一名评估者，我希望 HanCode 能够使用 MockLLM 运行，以便核心机制可以在无网络访问的情况下进行确定性测试。

### 用户故事 5

作为一名用户，我希望危险命令在执行前被拦截，以便不安全的行为需要批准或被阻止。

## 4. 功能规范

TODO

本节应描述每个模块，包括：

- 输入
- 行为
- 输出
- 边界条件
- 错误处理

计划中的模块：

1. 智能体循环（Agent loop）
2. LLM 抽象层（LLM abstraction）
3. 动作模式与解析器（Action schema and parser）
4. 工具调度器（Tool dispatcher）
5. 文件工具（File tools）
6. Shell 命令工具（Shell command tool）
7. 护栏（Guardrails）
8. 反馈传感器（Feedback sensors）
9. 记忆（Memory）
10. 配置（Configuration）
11. 凭据管理（Credential management）
12. 命令行界面（CLI）
13. 机制演示（Mechanism demo）

## 5. 非功能需求

### 5.1 安全性与凭据威胁模型

TODO

本节应说明：

- HanCode 可能使用哪些密钥
- 凭据存储在哪里
- 凭据如何输入
- 凭据如何更新
- 凭据如何清除
- 为什么不得提交凭据
- `.env` 文件和进程环境变量的风险

### 5.2 可用性

TODO

HanCode 应提供清晰的 CLI 命令和可读的错误信息。

### 5.3 可观测性

TODO

HanCode 应记录高级智能体步骤，而不泄露密钥。

### 5.4 性能

TODO

HanCode 预期在小型教学或演示仓库上运行。

## 6. 系统架构

TODO

计划中的架构：

```text
用户任务
  ↓
CLI
  ↓
配置加载器
  ↓
智能体循环
  ↓
上下文构建器
  ↓
LLM / MockLLM
  ↓
动作解析器
  ↓
护栏
  ↓
工具调度器
  ↓
工具结果
  ↓
反馈传感器
  ↓
记忆 / 上下文更新
  ↓
智能体循环
```

## 7. 数据模型

TODO

潜在的实体：

- `AgentState`（智能体状态）
- `Message`（消息）
- `Action`（动作）
- `ToolResult`（工具结果）
- `GuardrailDecision`（护栏决策）
- `FeedbackReport`（反馈报告）
- `MemoryEntry`（记忆条目）
- `Config`（配置）
- `CredentialStatus`（凭据状态）

## 8. 凭据与分发设计

TODO

计划中的凭据设计：

- 使用操作系统密钥环（keyring）作为首选的凭据存储方式
- 仅允许将 `.env` 作为开发环境的后备方案
- 绝不打印密钥值
- 绝不提交真实的凭据
- 提供设置、检查、更新和清除凭据的命令

计划中的分发方式：

- 基于 Docker 的分发
- 最终 README 应包含构建和运行命令
- CI 应运行测试并构建容器镜像

## 9. 技术选型与理由

TODO

计划中的技术栈：

- Python 3.11+
- pytest 用于测试
- ruff 用于代码检查
- mypy 用于类型检查
- pydantic 用于动作和数据模式
- typer 用于 CLI
- keyring 用于凭据存储
- Docker 用于分发

## 10. 领域与机制设计

本节是编码智能体框架项目所必需的。

### 10.1 Actions / Tools

TODO

Planned actions:

- `read_file`
- `write_file`
- `list_files`
- `run_command`
- `run_tests`
- `remember`
- `finish`

### 10.2 Objective Feedback Signals

TODO

Planned feedback signals:

- pytest result
- command exit code
- stdout and stderr
- lint result
- type check result
- structured failure classification

### 10.3 Dangerous Actions and Guardrails

TODO

Planned dangerous actions:

- deleting files outside workspace
- writing outside workspace
- shell commands containing destructive patterns
- commands that access secrets
- network or publish commands if disabled by config

Planned guardrail behavior:

- allow safe action
- block dangerous action
- require human approval for sensitive action

### 10.4 Memory Requirements

TODO

Planned memory content:

- project conventions
- previous failures
- accepted design decisions
- known test commands
- repeated error patterns

Memory should be retrieved on demand, not loaded fully into every LLM request.

### 10.5 Main Contribution Dimension

TODO

Planned main contribution:

> Feedback loop depth: deterministic feedback sensors, failure classification, and multi-turn self-correction driven by MockLLM tests.

## 11. Acceptance Criteria

TODO

Examples:

- HanCode has a self-implemented agent loop.
- HanCode can run with MockLLM without network access.
- Guardrails block dangerous actions deterministically.
- Feedback sensors classify failed tests.
- A mechanism demo shows failure injection and self-correction.
- `make test` or equivalent command runs all tests.
- CI runs on every push and pull request.
- README explains installation, running, credential setup, and known limitations.

## 12. Risks and Open Questions

TODO

Potential risks:

- agent loop becomes too large
- feedback mechanism is too shallow
- guardrails rely too much on prompts instead of code
- memory retrieval becomes vague or untestable
- credential handling is incomplete
- Docker distribution is not validated on a clean machine