# HanCode

HanCode 是一个面向 AI4SE 期末项目的轻量级编码智能体框架（Coding Agent Harness）。

它旨在演示以下内容：

- 自实现的智能体循环（agent loop）
- 动作解析与工具调度
- 确定性护栏（guardrails）
- 基于反馈的自我修正
- 模拟 LLM 的单元测试
- 安全的凭据处理
- 基于 Docker 的分发

## 当前状态

本仓库目前处于规范和规划阶段。

在以下条件满足之前，不得编写实现代码：

1. `SPEC.md` 已完成。
2. `PLAN.md` 已完成。
3. 使用不同的编码智能体完成冷启动验证。
4. 规范/计划的修订已记录在 `SPEC_PROCESS.md` 中。

## 项目规划方向

HanCode 将实现一个虽小但完整的编码智能体框架。

规划的核心能力是：

> 给定一个编码任务和一个目标仓库，HanCode 组织上下文、向 LLM 或 MockLLM 请求下一步动作、执行允许的工具、阻止危险操作、运行客观反馈检查，并将结果反馈到循环中，直到任务完成或停止。

## 规划的技术栈

- Python 3.11+
- pytest
- ruff
- mypy
- pydantic
- typer
- keyring
- Docker

## 开发规范

本项目遵循 Superpowers 工作流程：

1. 头脑风暴（brainstorming）
2. 编写计划（writing-plans）
3. 使用 Git 工作树（using-git-worktrees）
4. 子智能体驱动开发 / 执行计划（subagent-driven-development / executing-plans）
5. 测试驱动开发（test-driven-development）
6. 请求代码审查（requesting-code-review）
7. 完成开发分支（finishing-a-development-branch）

## 安全性

不得将任何真实的 API 密钥或凭据提交到此仓库。

凭据处理将在 `SPEC.md` 中规定，并在规范阶段之后实现。

## 分发方式

规划的分发格式为 Docker。

最终的 README 说明将包括：

- 构建命令
- 运行命令
- 凭据设置
- 已知限制

## 仓库结构

```text
HanCode/
  src/hancode/              # 源代码，在 SPEC 和 PLAN 验证之后添加
  tests/                    # 测试，按照 TDD 要求在实现之前编写
  examples/broken_project/  # 用于机制演示的示例项目
  docs/                     # 附加文档
  scripts/                  # 辅助脚本
  .github/workflows/        # CI 配置
  SPEC.md                   # 设计规范
  PLAN.md                   # 实现计划
  SPEC_PROCESS.md           # 规范制定过程记录
  AGENT_LOG.md              # 智能体活动日志
  REFLECTION.md             # 最终反思
```

## 重要规则

在 `SPEC.md`、`PLAN.md` 和冷启动验证完成之前，不得编写实现代码。