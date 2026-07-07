# 智能体活动日志

本文件记录所有重要的智能体辅助开发活动。

## 日志格式

每条记录应包含：

- 时间戳
- 任务 ID
- 使用的 Superpowers 技能
- 使用的智能体
- 关键提示词 / 上下文
- 智能体输出摘要
- 提交哈希 / PR 链接
- 人工干预
- 经验教训

---

## 记录条目

### 2026-07-07 __:__ — 任务 0 — 课程项目定位确认

- 使用的技能：Superpowers brainstorming 语境下的规划确认
- 使用的智能体：OpenAI Codex
- 关键提示词 / 上下文：
  - HanCode 面向学生课程项目，是轻量级 Coding Agent Harness。
  - 核心机制包括 Workspace 分离、Phase Gate、Tool Policy、Trace Logging、Checkpoint Rollback、MockLLM Testing。
  - `.hancode/`、Phase Mode、ContextBuilder、ToolPolicy、Demo 和测试叙事均服务课程项目流程。
- 摘要：
  - README、SPEC、PLAN 使用课程项目定位。
  - `.hancode/` 模板采用 Project Workspace / Task Workspace / Knowledge Delivery 结构。
  - Demo 使用学生成绩统计 CLI 课程项目。
- 人工干预：
  - 用户明确要求最小破坏式修改，不引入复杂 Web UI、数据库、MCP 工具市场或企业级权限系统。
- 提交：
  - TODO
- 经验教训：
  - 课程项目场景要求 Harness 不只控制代码修改，还要沉淀 TEST_REPORT、REVIEW、KNOWLEDGE 和 DELIVERABLES。

### 2026-__-__ __:__ — 任务 0 — 仓库初始化

- 使用的技能：手动初始化 / Superpowers 工作流准备
- 使用的智能体：ChatGPT 指导
- 关键提示词 / 上下文：
  - HanCode 的初始仓库设置。
  - 项目类型：AI4SE 期末项目 A · 编码智能体框架。
- 摘要：
  - 初始化了仓库结构。
  - 添加了文档占位符。
  - 添加了 `.gitignore` 和 `.env.example`。
  - 添加了 Python 打包元数据。
  - 添加了占位测试和 CI 工作流。
- 人工干预：
  - TODO
- 提交：
  - TODO
- 经验教训：
  - TODO
