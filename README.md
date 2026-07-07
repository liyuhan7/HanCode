# HanCode

HanCode 是一个面向学生课程项目的轻量级 Coding Agent Harness。它通过 Workspace
隔离、阶段门禁、工具权限控制、执行追踪和 Checkpoint 回退机制，引导 Agent
按课程项目流程完成需求分析、计划制定、编码实现、测试验证、审查交付与知识沉淀。

> lightweight coding-agent harness for student course projects, with
> workspace-scoped execution, phase-gated coding, trace logging,
> checkpoint-based rollback, and knowledge-oriented delivery.

## 核心叙事

- Project Workspace 管课程项目级上下文与长期经验。
- Task Workspace 管单次课程任务的 SPEC、PLAN、Trace、Checkpoint 和学习产物。
- Phase Mode 管需求、计划、编码、测试、审查、交付各阶段的工具权限。
- Checkpoint Rollback 管代码修改失败后的恢复。
- Knowledge Delivery 管最终的项目复盘、错误记录和知识沉淀。

## Harness 机制

HanCode 的底层 Harness 机制包括：

- Workspace 分离
- Phase Gate
- Tool Policy
- Trace Logging
- Checkpoint Rollback
- MockLLM Testing

这些机制共同服务于小规模课程项目的受控开发流程。

## 非目标

HanCode 第一版不做：

- competitive programming assistant
- 大型自主软件开发 Agent
- 复杂 Web UI
- 多用户系统
- 企业级 Agent 平台
- 完整 Git 分支管理
- MCP 工具市场

## 课程项目流程

HanCode 使用固定的轻量 Phase Mode：

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

HanCode 采用课程项目导向的轻量本地目录：

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
        ckpt-001/
          manifest.json
          files/
```

`.hancode/` 是 HanCode 的运行时数据示例和模板，用来展示 Project Workspace、Task
Workspace、Trace、Checkpoint 和知识沉淀的边界。真实凭据不得写入该目录。

## Demo 任务

课程项目 Demo 任务是：

> 根据课程作业要求，实现一个学生成绩统计 CLI 项目：
>
> 1. 从 CSV 文件读取学生成绩；
> 2. 计算平均分、最高分、最低分；
> 3. 支持按课程筛选；
> 4. 输出统计结果；
> 5. 编写测试；
> 6. 生成 README、TEST_REPORT 和 KNOWLEDGE。

Demo 应展示完整流程：

```text
spec -> plan -> code -> test -> review -> deliver
```

并展示 `trace.jsonl` 记录全过程、code phase 修改前创建 checkpoint、deliver phase
生成 `DELIVERABLES.md` 和 `KNOWLEDGE.md`。

## 项目阶段

本仓库处于规范和规划阶段。源码目录只有占位文件，尚未实现 Harness 内核。

在以下条件满足之前，不得开始完整实现：

1. `SPEC.md` 完成。
2. `PLAN.md` 完成。
3. 使用不同的编码智能体完成冷启动验证。
4. 规范/计划的修订记录在 `SPEC_PROCESS.md` 中。

## 技术栈

- Python 3.11+
- pytest
- ruff
- mypy
- pydantic
- typer
- keyring
- Docker

## 安全性

不得将任何真实的 API 密钥、令牌或凭据提交到此仓库。

HanCode 使用 `keyring` 作为首选凭据存储方式，`.env` 只作为本地开发后备方案。
凭据状态检查只能显示是否存在，不得回显明文。

## 分发方式

分发格式为 Docker。最终 README 将包含：

- 构建命令
- 运行命令
- 凭据设置
- 已知限制

## 验证

可运行的检查命令：

```powershell
python -m pytest
python -m ruff check src tests
python -m mypy src
```

设计测试范围覆盖 Phase Gate、Tool Policy、Trace Logging、Checkpoint Rollback、
ContextBuilder、Knowledge Delivery 和 MockLLM 控制流。
