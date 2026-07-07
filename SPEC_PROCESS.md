# 规范制定过程记录

本文档记录了如何使用 Superpowers 方法制定项目规范和实现计划。

## 1. 头脑风暴概述

头脑风暴于 2026-07-06 至 2026-07-07 期间进行，使用的主开发智能体为 OpenAI Codex，触发的主要 Superpowers 技能为 `using-superpowers` 和 `brainstorming`。

初始项目想法是构建一个轻量级 Coding Agent Harness，覆盖 agent loop、工具分发、治理护栏、反馈、记忆、配置、凭据管理和 Docker 分发。早期方向曾考虑把“反馈闭环深度”作为主要贡献，包括确定性反馈传感器、失败分类和 MockLLM 多轮自我修正。

随着讨论推进，项目方向发生了两次重要收敛：

1. 用户提出更关注 workspace / workplace 隔离、上下文充分利用，以及每轮 loop 修改后的 checkpoint / rollback。
2. 用户进一步明确课程项目场景中的真实痛点不是“让 AI 更快完成作业”，而是“学生用 AI 做完作业但知识不沉淀”。

因此，当前 SPEC 的问题陈述收敛为：HanCode 是面向学生课程项目的轻量级 Coding Agent Harness，用 Workspace 分离、Phase Gate、Tool Policy、Trace Logging 和 Checkpoint Rollback 约束 AI 辅助开发过程，使需求理解、计划、编码、测试、审查和 deliver 阶段的知识沉淀可复盘、可验证。

## 2. 关键迭代 1

### 智能体问题 / 建议

智能体首先询问 HanCode 的主贡献维度是否应设为“反馈闭环深度”，即以确定性反馈传感器、失败分类和 MockLLM 多轮自我修正作为项目亮点。

### 我的决策

用户否定了这个默认方向，指出自己更想做“记忆系统”，具体亮点是 workspace / workplace 隔离、上下文充分利用，以及修改回退机制。用户还提供了 Zleap-Agent 作为 workspace-first 思路参考。

### 导致的变更

项目主贡献从“反馈闭环深度”调整为“Workspace-scoped context and reversible coding state”。反馈闭环仍作为 harness 的基础能力保留，但不再作为主贡献。SPEC 后续需要突出 Project Workspace、Task Workspace、Phase Mode、ContextBuilder、Trace、Checkpoint 和 Rollback。

## 3. 关键迭代 2

### 智能体问题 / 建议

用户提供了《HanCode 基本抽象设计》，其中提出：

- Project Workspace 绑定项目级上下文。
- Task Workspace 绑定一次用户任务。
- Phase Mode 控制 spec、plan、code、test、review、deliver 阶段能力。
- Context Builder 按 workspace 和 phase 选择性装配上下文。
- Tool Policy 控制工具权限和风险。
- Checkpoint / Rollback 支持代码修改恢复。
- Trace 记录 agent 执行过程。

智能体据此建议把 HanCode 的主贡献定义为 “Workspace-scoped memory and reversible working state”。

### 我的决策

用户确认了分层 workspace 思路，并选择 `.hancode/` 作为 HanCode 当前运行目录下的运行时数据根目录。用户同时选择 checkpoint 粒度为“每轮 agent loop 一个 checkpoint”，即一轮内多个文件改动可以一起回退。

### 导致的变更

SPEC 中的机制设计需要采用：

- Project Workspace / Task Workspace / Phase Mode 的层级结构。
- `.hancode/` 作为本地运行时状态目录。
- loop-level checkpoint，而不是单文件级或整 task 级 checkpoint。
- rollback 作为 review 或失败恢复路径的一部分。

## 4. 关键迭代 3

### 智能体问题 / 建议

在一次“项目重定位与轻量重构”请求中，智能体将项目进一步写成“面向学生课程项目的轻量级 Coding Agent Harness”，并引入 `KNOWLEDGE.md`、`DELIVERABLES.md`、`TEST_REPORT.md` 等课程项目产物作为 deliver 阶段材料。

### 我的决策

用户随后追问“课程项目产物是什么”以及“为什么现在要做这个”，表明这部分表述容易让项目看起来像课程作业管理器，而不是 Coding Agent Harness。随后用户要求重新进行 SPEC 设计，并从问题陈述开始一步步沉淀。

在重新设计第 1 节时，用户明确指出核心痛点是：学生用 AI 做完作业但知识不沉淀。用户选择“整体过程不沉淀”作为痛点范围，并选择“课程项目 Coding Agent Harness”作为解决方案形态。

### 导致的变更

SPEC 第 1 节被重新写入为：

- “为什么做”：学生使用 AI 完成课程项目后，需求理解、设计决策、测试失败、错误修复和经验迁移没有沉淀。
- “怎么做”：HanCode 用 Workspace 分离、Phase Gate、Tool Policy、Trace Logging 和 Checkpoint Rollback 组织 AI 辅助开发过程。
- “怎么验证”：通过 trace、测试报告、checkpoint 和阶段产物提供可检查证据。

用户还修正了阶段表述：HanCode 只有 spec、plan、code、test、review、deliver 六个阶段；知识沉淀归入 deliver 阶段，而不是独立 phase。

## 5. 已采纳的 AI 建议

以下建议被采纳：

- 将 harness 机制明确写成确定性代码机制，而不是提示词要求。原因是 Coding Agent Harness 作业要求核心机制在移除真实 LLM 后仍可用 MockLLM 或 stub 测试。
- 采用 Project Workspace / Task Workspace / Phase Mode 的层级结构。原因是它能支撑上下文隔离、工具权限控制和任务级状态管理。
- 采用 loop-level checkpoint。原因是它贴合用户提出的“一轮 loop 修改了哪些文件，可以直接撤销”的需求，比单文件 checkpoint 更符合 agent loop 语义。
- 在问题陈述中采用“学生学习价值是为什么做，工程控制价值是怎么做，课程评估价值是怎么验证”的叙事结构。原因是它能同时保持课程项目定位和 harness 机制深度。
- 在第 1 节不直接点名 `KNOWLEDGE.md`。原因是问题陈述应先讲清知识沉淀概念，具体文件设计放到功能规约和数据模型中。

## 6. 被拒绝或修订的 AI 建议

以下建议被拒绝或修订：

- “反馈闭环深度”作为主贡献被修订。原因是用户更关注 workspace 隔离、上下文利用和修改回退。
- 把 HanCode 表述成通用开发者工具的方向被弱化。原因是用户要服务学生课程项目场景，但仍保留 Coding Agent Harness 本质。
- 把知识沉淀写成独立 phase 的表述被修订。原因是用户明确要求阶段只有 spec、plan、code、test、review、deliver 六个，知识沉淀应归入 deliver。
- 将 `KNOWLEDGE.md`、`DELIVERABLES.md` 放在问题陈述中点名的建议被拒绝。原因是这会过早进入文件设计，削弱问题陈述的概念清晰度。
- 在 README/SPEC 中出现“本次重定位”“原有机制保留”等修改过程话语的写法被用户指出并修订。正式文档应呈现稳定项目定位，而不是编辑过程。

## 7. 冷启动验证

### 使用的第二个智能体

尚未进行。

要求：第二个智能体必须与主开发智能体不同，并且不能获得当前对话历史或隐藏上下文。

### 尝试的任务

尚未进行。计划在 `SPEC.md` 与 `PLAN.md` 定稿后，让第二个智能体从 `PLAN.md` 中选择 1-2 个小任务尝试实现。

### 提供的上下文

尚未进行。届时只能提供 `SPEC.md` 和 `PLAN.md`。

### 暂停或提问的地方

尚未进行。

### 误解之处

尚未进行。

### SPEC / PLAN 修订

尚未进行。冷启动验证后，需要记录第二个智能体暴露的 SPEC / PLAN 缺陷，以及关键修订前后差异。

## 8. 对头脑风暴技能的反思

当前阶段的反思：

- 做得好的地方：brainstorming 通过连续追问把项目从“泛化的 coding harness”推进到“面向学生课程项目、解决 AI 作业过程不沉淀”的更具体问题；也帮助区分了为什么做、怎么做、怎么验证。
- 令人沮丧的地方：智能体一开始倾向于把主贡献设成反馈闭环深度，这是常见但不符合用户真实意图的 harness 亮点；后续又一度把课程项目产物写得过重，让项目看起来偏课程管理而不是 harness。
- 隐含假设：智能体默认“更完整的交付产物”会提升项目价值，但用户更关心的是知识沉淀与 harness 控制之间的边界，不希望文档显得像新增复杂系统。
- 对项目的改善：通过用户多次修正，当前 SPEC 第 1 节已经形成稳定叙事：学生学习价值是目的，工程控制机制是实现方式，trace、测试报告、checkpoint 和阶段产物是验证证据。
