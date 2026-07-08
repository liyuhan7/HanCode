# HanCode

HanCode 是一个为学生课程项目调校的 Coding Agent Harness。它的核心是 AI 辅助编码
的控制回路——修改代码、运行测试、根据失败自我修正、失败超限时回退——并把这条
回路调校到学生场景：失败反馈带学习导向提示，危险动作集包含课程文件保护，阶段
门禁要求先理解需求再编码。

> a coding-agent harness tuned for student course projects, centered on a
> deterministic feedback loop and reversible coding state, with phase-gated
> coding, trace logging, and course-file governance.

## 核心叙事

- Feedback Loop 管测试信号的分类与回灌，驱动 Agent 针对性修复。
- Checkpoint Rollback 管代码修改前快照与失败后的可回退恢复。
- Tool Policy 管工具权限与课程文件保护（教师测试、评分脚本不可篡改）。
- Phase Mode 管需求、计划、编码、测试、审查、交付各阶段的工具权限。
- Workspace 分层管课程项目级与任务级上下文隔离（支撑维度）。
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

`examples/.hancode-template/` 是 HanCode 的运行时数据示例和模板，用来展示 Project Workspace、Task
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

1. `docs/SPEC.md` 完成。
2. `docs/PLAN.md` 完成。
3. 使用不同的编码智能体完成冷启动验证。
4. 规范/计划的修订记录在 `docs/SPEC_PROCESS.md` 中。

## 技术栈

- Python 3.11+
- pytest
- ruff
- mypy
- pydantic
- typer
- keyring
- Docker（可选 MockLLM demo 环境）

## 安全性

不得将任何真实的 API 密钥、令牌或凭据提交到此仓库。

HanCode 使用 `keyring` 作为首选凭据存储方式，`.env` 只作为本地开发后备方案。
凭据状态检查只能显示是否存在，不得回显明文。

## 分发方式

MVP 分发格式为 Python package（wheel / sdist）。Docker 仅作为可选 MockLLM demo 环境，不作为核心 Harness 机制或必需分发路径。最终 README 将包含：

- 安装命令
- `hancode --help`
- `hancode demo --provider mock`
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
