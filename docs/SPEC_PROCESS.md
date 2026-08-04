# 规范制定过程记录

本文档记录了如何使用 Superpowers 方法制定项目规范和实现计划。

## 1. 头脑风暴概述

头脑风暴于 2026-07-06 至 2026-07-08 期间进行，使用的主开发智能体为 OpenAI Codex，触发的主要 Superpowers 技能为 `using-superpowers`、`brainstorming` 和 `writing-plans`。整个过程先从模糊的 Coding Agent Harness 想法出发，再逐步收敛到课程项目场景、主贡献机制、SPEC 抽象边界、系统架构一致性和可冷启动执行的 PLAN 格式。

初始项目想法是构建一个轻量级 Coding Agent Harness，覆盖 agent loop、工具分发、治理护栏、反馈、记忆、配置、凭据管理和分发。早期方向曾在“反馈闭环深度”和“workspace-scoped memory”之间摆动：前者更贴近 A 类 Harness 推荐的机制深挖方向，后者更贴近用户对 workspace / task 隔离、上下文利用和 checkpoint / rollback 的兴趣。经过多轮评审后，最终结论是：HanCode 的主体仍是 coding agent harness，课程学习是差异化场景，记忆是支撑维度而不是主贡献。

最终沉淀出的项目定位是：HanCode 是面向学生课程项目的轻量级 Coding Agent Harness，目标不是让 AI 更快替学生完成作业，而是让 AI 辅助编码过程中的需求理解、计划、代码修改、测试失败、错误修复、审查和交付复盘可控、可追踪、可回退、可复盘。其主贡献维度收敛为 `deterministic feedback loop + reversible coding state`：代码修改前创建 checkpoint，修改后运行测试获得客观信号，失败由 `FeedbackBuilder` 确定性分类并回灌，重试预算耗尽时强制 rollback。

围绕这个定位，SPEC 最终承担需求契约角色：说明问题陈述、用户故事、功能规约、非功能需求、架构边界、数据模型、凭据与分发、验收标准、领域与机制设计、风险与未决问题。`docs/系统架构.md` 承接实现组织细节，例如模块接口、调用链、TraceEvent、PathClassifier、CredentialProvider、FeedbackReport 和测试命名。`docs/PLAN.md` 则被设计为冷启动可执行的实现合同，使用任务依赖图、里程碑、统一任务卡片和需求到任务追溯表，帮助陌生 agent 仅凭 SPEC + PLAN 开始执行 TDD 任务。

当前已完成一次扩展上下文冷启动验证：使用 OpenCode 搭载 GLM-5.2，在不提供主开发对话历史或隐藏 memory 的前提下，让第二个 agent 依据 `系统架构.md`、`SPEC.md` 和 `PLAN.md` 尝试 T1 / T2。该验证证明 PLAN 的前两个实现任务可以被陌生 agent 启动并产出可运行代码；由于额外提供了系统架构文档，本文件将其记录为“扩展上下文冷启动验证”，并把暴露的问题回写为正式开发约束。至此，SPEC / PLAN / 冷启动记录阶段门收口，后续可以从 T1 开始正式实现。

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

已进行一次冷启动验证。

- 第二个智能体：OpenCode。
- 模型：GLM-5.2。
- 主开发智能体：OpenAI Codex。
- 验证目录：`D:\agent-leanring\demo`。
- 验证性质：扩展上下文冷启动验证。第二个智能体没有获得主开发对话历史、隐藏 memory 或口头解释，但提供的文件包含 `系统架构.md`，因此不是严格的“仅 SPEC + PLAN”验证。

### 尝试的任务

尝试并完成了前两个基础任务：

- T1：共享模型与错误类型。
- T2：Workspace 初始化。

第二个智能体产出的主要文件包括：

- `src/hancode/models.py`
- `src/hancode/errors.py`
- `src/hancode/workspace.py`
- `tests/test_models.py`
- `tests/test_errors.py`
- `tests/test_workspace.py`
- `pyproject.toml`

独立复核时运行了以下命令：

```powershell
python -m pytest -p no:cacheprovider
python -m ruff check src tests
python -m mypy src
```

验证结果：

- pytest：19 passed。
- ruff：All checks passed。
- mypy：Success: no issues found。
- secret 模式扫描：未发现真实凭据形态。

### 提供的上下文

实际提供的上下文为：

- `系统架构.md`
- `SPEC.md`
- `PLAN.md`

未提供：

- 主开发阶段的对话历史。
- 主开发智能体 memory。
- 口头解释。
- 主仓中除上述三份文档之外的辅助说明。

与课程要求的差异：

- 课程要求的严格冷启动是仅提供 `SPEC.md` + `PLAN.md`。
- 本次额外提供了 `系统架构.md`。这有利于检查 PLAN 是否能落到代码接口，但会降低“SPEC + PLAN 本身是否足够自解释”的证据强度。
- 因此，本次结论记录为“扩展上下文冷启动验证完成”。正式开发可以开始，但后续实现必须按照当前 `docs/PLAN.md` 中回写后的任务卡执行，而不是照搬冷启动 demo。

### 暂停或提问的地方

未发现第二个智能体留下明确的暂停提问记录。它直接实现了 T1 / T2，并在 `PLAN.md` 中把 T1 / T2 标记为完成。

这暴露出一个过程记录缺口：冷启动目录没有 `SPEC_PROCESS.md` 或 `AGENT_LOG.md`，因此无法审计第二个智能体是否先观察到红阶段失败、是否遇到不确定点、是否曾做出被人工纠正的判断。

### 误解之处

本次冷启动暴露了以下误解或不一致：

1. 严格路径语义不一致。主仓课程交付物位于 `docs/SPEC.md`、`docs/PLAN.md` 和 `docs/系统架构.md`，但冷启动目录把 `SPEC.md`、`PLAN.md`、`系统架构.md` 放在根目录；同时 `PLAN.md` 内仍保留 `docs/` 路径表述。第二个智能体仍能继续实现，但这说明冷启动材料的目录形态需要被固定。
2. 过程证据缺失。`PLAN.md` 要求每个任务更新 `docs/AGENT_LOG.md`，但冷启动目录没有该文件，也没有等价记录，因此不能证明 TDD 红阶段真实发生。
3. T1 / T2 状态记录不够精确。`PLAN.md` 中 T1 的 Commit 字段写为“19 tests pass”，但 19 是 T1 + T2 的总测试数，不是 T1 单独的测试数。
4. 代码质量暴露了早期契约缺口：`init_project_workspace()` / `init_task_workspace()` 会覆盖已有 project / task 证据文件，和 HanCode 的 trace、history、state 可复盘目标冲突。
5. `init_task_workspace()` 可以在缺少 project workspace 元数据时创建 task，削弱 Project Workspace 先于 Task Workspace 的层级约束。
6. `pyproject.toml` 目标为 Python 3.10，而 PLAN / SPEC 当前写的是 Python 3.11+。

### SPEC / PLAN 修订

本轮已将关键发现回写到 `docs/PLAN.md` 的 T1 / T2 任务卡。正式实现时应特别遵守以下点：

- 冷启动材料目录应保持与主仓一致，优先提供 `docs/SPEC.md`、`docs/PLAN.md` 和按需可读的 `docs/系统架构.md`；若复制到临时目录，应保留 `docs/` 层级。
- T2 Workspace 初始化任务卡应明确：初始化必须幂等，不能覆盖已有 `state.json`、`trace.jsonl`、`history.jsonl`、checkpoint 或 Markdown 产物；需要 reset 时必须是单独显式动作。
- T2 应明确：Task Workspace 初始化必须依赖已存在且有效的 Project Workspace，不能静默创建半完整 `.hancode/`。
- T1 应明确 `OperationResult.status` 的类型边界：若表示任务状态则复用 `TaskStatus`，若表示操作结果则新增独立枚举，避免任意字符串扩散。
- `pyproject.toml` 与 PLAN / SPEC 的 Python 版本要求应统一为 Python 3.11+，除非明确把 3.10 作为兼容目标。

冷启动结论：

- 从“陌生 agent 是否能依据文档启动 T1 / T2 并产出可运行代码”看，本次验证有效。
- 从过程复盘角度看，本次验证也暴露了上下文范围、红阶段证据和 workspace 初始化语义的不足，这些不足已经转化为后续任务约束。
- 阶段门收口：可以进入正式开发，但每个实现任务必须重新执行 TDD 红绿重构、验证和代码审查，冷启动 demo 只作为验证样本，不作为可直接合并代码。

## 8. 对头脑风暴技能的反思

当前阶段的反思：

- 做得好的地方：brainstorming 通过连续追问把项目从“泛化的 coding harness”推进到“面向学生课程项目、解决 AI 作业过程不沉淀”的更具体问题；也帮助区分了为什么做、怎么做、怎么验证。
- 令人沮丧的地方：智能体一开始倾向于把主贡献设成反馈闭环深度，这是常见但不符合用户真实意图的 harness 亮点；后续又一度把课程项目产物写得过重，让项目看起来偏课程管理而不是 harness。
- 隐含假设：智能体默认“更完整的交付产物”会提升项目价值，但用户更关心的是知识沉淀与 harness 控制之间的边界，不希望文档显得像新增复杂系统。
- 对项目的改善：通过用户多次修正，当前 SPEC 第 1 节已经形成稳定叙事：学生学习价值是目的，工程控制机制是实现方式，trace、测试报告、checkpoint 和阶段产物是验证证据。