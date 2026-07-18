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

## 9. 关键迭代 4

### 智能体问题 / 建议

在完成数据模型、凭据与分发设计、技术选型和验收标准草稿后，用户对 §7 数据模型和 §10 验收标准进行了逐节评审。评审指出：

- TraceEvent 缺少唯一 ID，导致 KnowledgeItem 无法稳定引用 trace。
- `state_transition` 字段缺少结构语义说明。
- Project Memory、Course Context、Experience 在文件映射中出现，但未说明它们与 Project 实体的关系。
- `files_changed` 的写入时机不明确。
- WorkspaceRouter、FeedbackBuilder、ResultBuilder 在架构中出现，但验收标准中没有独立验收锚点。
- `completed` 与 `blocked` 在存在未测试风险时的判定边界不清。
- Mock Mode 入口、符号链接逃逸、TUI slash command、打包和 CI 范围存在一致性问题。

### 我的决策

用户要求修正后写入。修订采用“补齐机制定义，不扩大 MVP 范围”的原则：

- TraceEvent 增加 `event_id`，并明确 `KnowledgeItem.source_trace_id` 引用该 ID。
- `state_transition` 只记录状态变化，无变化时为 `null`。
- Project 的附属文档不作为独立状态机实体，而作为 Project Workspace 的附属文档被 ContextBuilder 按需读取。
- `files_changed` 只在 code phase 的业务代码修改成功后更新，test/review 只读。
- §10 新增 WorkspaceRouter、FeedbackBuilder、ResultBuilder 三个独立验收节。
- 风险不再引入额外风险状态，而统一进入 `risks[]`；核心需求覆盖且测试通过时可 completed，否则 blocked。
- Python package build 与 CI unit-test 被列为 MVP 交付验证要求，但不改变 Harness Core 边界。

### 导致的变更

SPEC 第 7 节和第 10 节完成一致性修订；系统架构文档的 MVP 范围同步补充 package build 与 CI unit-test 验证要求。状态枚举收敛为 `created`、`running`、`blocked`、`failed`、`completed`、`inconsistent`，不再使用额外风险状态作为任务最终状态。

## 10. 关键迭代 5

### 智能体问题 / 建议

在 SPEC 第 1 至第 10 节完成后，智能体检查通用要求和 Coding Agent Harness 额外要求，发现通用要求中的“风险与未决问题”尚未形成独立章节，A 类 Harness 要求的“领域与机制设计”也尚未集中呈现。虽然动作、反馈、危险动作和记忆机制已经分散出现在功能规约、架构、数据模型和验收标准中，但评分时不便直接定位。

### 我的决策

用户要求先处理“领域与机制设计”。该节采用独立章节，集中回答 Coding Agent Harness 的四类机制问题：

- coding 领域中 Agent 能执行哪些动作 / 工具；
- 哪些客观反馈信号能判断行为是否正确；
- 哪些危险动作必须被治理护栏拦截；
- 跨会话和跨任务需要记住什么；
- HanCode 的主贡献维度如何通过 workspace-scoped memory 和 reversible coding state 落地。

### 导致的变更

SPEC 新增 `## 11. 领域与机制设计`，把 HanCode 的主贡献明确为 `workspace-scoped course-project memory + reversible coding state`，并补充动作 / 工具、客观反馈信号、危险动作、记忆与上下文机制、代码模块映射和 MockLLM 机制演示路径。

## 11. 关键迭代 6

### 智能体问题 / 建议

在“领域与机制设计”写入后，SPEC 仍缺少通用要求中的“风险与未决问题”。智能体建议该节不要写成泛泛的项目管理风险，而应聚焦可能让 Coding Agent Harness 出问题的环节：AgentLoop 卡死、ToolPolicy 拦截不稳定、ContextBuilder 污染上下文、checkpoint 失效、凭据泄露、MockLLM 测试不足、TUI 与 core 边界不清等。

### 我的决策

用户确认写入。该节采用风险清单、未决问题和风险优先级的结构，并区分缓解策略与仍需 PLAN / 实现阶段验证的内容。

### 导致的变更

SPEC 新增 `## 12. 风险与未决问题`，覆盖 Agent 行为与控制流、上下文与记忆、工具与文件安全、Checkpoint 与 Rollback、凭据与日志泄露、测试与验证、课程项目价值等风险，并列出真实 LLM provider、Docker、多语言项目、HITL、Git 集成、checkpoint 粒度、冷启动验证和 TUI 复杂度等未决问题。

## 12. 关键迭代 7

### 智能体问题 / 建议

在完成 SPEC 主体后，用户要求从 SPEC 质量角度评估一致性、可测试性和抽象性。其中一致性问题已被用户处理，后续重点转向抽象性：SPEC 中存在 Python 接口签名、具体测试函数名、`.gitignore` 模板和低层调用链等实现细节，使 SPEC 容易变成架构设计或实现计划。

### 我的决策

用户要求“做迁移而不是删减”。因此本轮采用分层承载原则：

- `SPEC.md` 保留需求契约、机制不变量、数据实体、凭据安全约束和客观验收标准。
- `docs/系统架构.md` 承接模块接口、Provider 调用链、默认忽略 / 导出规则和测试命名清单。
- 后续 `PLAN.md` 再把测试命名清单和架构细节转化为实现任务。

### 导致的变更

- SPEC 的 `CredentialProvider` 从 Python 接口签名改为能力契约表。
- SPEC 的真实 LLM 调用链改为抽象链路，并引用系统架构文档中的时序设计。
- SPEC 的 `.gitignore` 具体模板和导出命令形态迁移到 `docs/系统架构.md`。
- SPEC 第 10 节移除逐模块 `test_*` 函数名清单，只保留 pass/fail 验收判定；完整测试命名清单迁移到系统架构文档的 MockLLM 测试架构章节。
- SPEC 的组件图、实体图和机制模块表补充“逻辑层级”声明，避免被误读为强制实现结构。

## 13. 关键迭代 8

### 智能体问题 / 建议

用户随后要求关注可测试性，并给出系统评估：当前 SPEC 能测试“机制是否发生”，但对“产物质量是否足够”的 pass/fail 边界仍不够清晰。主要风险集中在 `write_file` / `edit_file` 边界、ContextBuilder 最小上下文、脱敏规则、Knowledge / Review 结构、性能阈值、CLI 行为、结构化错误、keyring 测试策略、Demo trace 断言和 Docker 可选边界。

### 我的决策

采用“集中测试契约”的方式修订，而不是把每个功能小节都扩写成长测试设计：

- 在当时草稿中，曾建议 FR-3 补充可写 Action 必须携带 `target_kind=artifact|source`。
- 在非功能性性能需求中补充小型项目规模、ContextBuilder 时间、MockLLM demo 时间和 checkpoint 快照范围。
- 在 SPEC 第 10 节新增 `### 10.21 可测试性约定`，集中定义跨模块 pass/fail 规则。

### 导致的变更

SPEC 新增测试契约，覆盖可写 Action 判定、ContextBuilder include / exclude、统一 secret fixture、Markdown 产物最低结构、REVIEW 需求覆盖表、结构化错误字段、CLI / TUI 命令验收矩阵、fake keyring 测试策略、demo trace 必含事件序列、Docker 可选边界和性能测试口径。

> 说明：`target_kind` 显式字段方案在关键迭代 9 中被 `PathClassifier` 路径推导方案取代，保留本段作为过程记录。

## 14. 关键迭代 9

### 智能体问题 / 建议

在 SPEC 可测试性补强后，用户要求制定架构一致性修订方案，重点解决 `SPEC.md` 与 `docs/系统架构.md` 之间的契约矛盾。主要矛盾包括：可写 Action 是否显式携带 `target_kind`、启动 reconcile 是否自动回写 `state.json.artifacts`、TraceEvent 事件名是否以 SPEC 为权威，以及架构文档中配置、凭据命令、checkpoint pruning、结构化错误和 CLI exit code 是否齐全。

### 我的决策

用户确认采用 HanCode 架构一致性修订方案 v1.3，并明确三项关键决策：

- 写入边界采用 `PathClassifier` 根据路径推导 artifact / source / protected zone，不要求 Action 显式携带 `target_kind`。
- `state.json` 保持唯一机器状态源；启动对账发现 state 与文件系统不一致时进入 `inconsistent`，记录 trace，并阻止高风险动作，不自动回写 `state.json`。
- TraceEvent 事件名以 SPEC 为权威；架构文档必须向 SPEC 对齐，并补齐 `event_id` 和 `state_transition`。

### 导致的变更

- SPEC 中 FR-3、ToolPolicy 验收和 §10.21 可测试性约定从 `target_kind` 改为 `PathClassifier` 路径分类。
- SPEC TraceEvent 表补齐 `state_reconciled`、`state_inconsistent` 以及架构文档使用的生命周期事件。
- 系统架构文档补齐 v1.3 修订记录、CredentialProvider、Config 字段、CLI exit code、`/auth` slash commands、`hancode export`、checkpoint pruning、rollback 副作用、结构化错误字段、ContextBuilder 限制和 REVIEW / KNOWLEDGE 结构化最低标准。
- 系统架构文档的 reconcile 语义改为只检查一致性，不自动重建或回写 `state.json.artifacts`。

## 15. 关键迭代 10

### 智能体问题 / 建议

在架构一致性修订完成后，用户要求重新核对 SPEC 与系统架构是否偏离课程需求，并参考另一个 workspace-first 的 harness 项目审视记忆系统。评审指出：项目主体是 coding agent，"面向课程学习"是差异化外壳；但当时主贡献维度写作 `workspace-scoped memory + reversible coding state`，把记忆放在首位，与实际做深的部分（治理 / 回退 / 反馈）存在深度倒挂。参考项目的记忆能力依赖其自研检索引擎，而 A 类要求「若以记忆为重点，其存储与检索必须自己实现」，照搬会引入不必要的深度负担。

### 我的决策

用户确认将主贡献维度从记忆重定位到 coding agent 的核心回路，记忆降为基础维度的最低可运行实现：

- 主贡献维度定为 `deterministic feedback loop + reversible coding state`，对齐 A.4(D) 建议的反馈 / 治理重点维度，也对齐已做深的 checkpoint 与 rollback。
- 记忆保持 workspace 分层 + phase-based 上下文选择，不引入向量检索或上下文压缩，主动排除「记忆为重点须自实现检索」的评审约束。
- 反馈闭环补充确定性测试失败分类（syntax / import / assertion / exception / timeout），作为唯一新增的深度投入。
- 危险动作叙事把课程文件保护提级为场景差异化的一等治理目标。
- checkpoint 加固项（并发锁、resume、pending 崩溃恢复、写前确认）划入 post-MVP，保 MVP 回路先闭环。

### 导致的变更

- SPEC §11.6 主贡献维度改为反馈回路 + 可回退编码状态；§11.5 记忆显式声明为基础维度最低实现。
- SPEC §11.3 新增测试失败分类小节；§10.11 FeedbackBuilder 验收补充分类判定；§11.8 主贡献演示改为失败分类 → retry → 强制 rollback 的完整回路。
- SPEC §1 问题陈述与 §11.4 危险动作叙事重心转向编码控制回路与课程文件保护。
- 系统架构 §6.11 新增 `FeedbackReport` 数据结构与分类规则；§12.4 补充失败分类测试命名。
- PLAN、README、AGENTS 和 agent-guides 的定位段与主贡献表述同步为 coding agent 主体；PLAN 补充 MVP 与 post-MVP 边界。

### 参考项目说明

参考的 workspace-first 记忆思路仅作为设计比对，未引入其检索引擎或任何包依赖；HanCode 的 workspace 分层为自实现的文件系统结构。

## 16. 关键迭代 11

### 智能体问题 / 建议

在 SPEC、系统架构和主贡献维度逐步稳定后，用户进一步指出原 `PLAN.md` 仍然过粗：它列出了任务名称、目标和测试名，但对陌生 agent 来说缺少统一定位入口、任务依赖、并行关系、里程碑验收和需求追溯。这样的 PLAN 不利于冷启动验证，也不利于后续 subagent-driven 开发时把每个任务独立交给新鲜 agent。

智能体据此建议按 `superpowers:writing-plans` 的精神增强 PLAN：任务必须能被一个没有对话历史的工程 agent 直接执行，包含清晰文件边界、接口契约、红阶段测试、绿阶段实现方向、可复制验证命令和非目标边界。

### 我的决策

用户给出并确认了 HanCode 的最终 PLAN 格式，不采用另建 `docs/superpowers/plans/...` 的默认路径，而是直接维护课程要求指定的 `docs/PLAN.md`。最终结构确定为：

- 保留开头的状态 / 定位段、全局规则、MVP 与 post-MVP 边界。
- 新增 `任务依赖图`，用纯文本树表达串行、并行和主贡献核心任务。
- 新增 `里程碑`，用 M1 / M2 / M3 对齐骨架、主贡献闭环和最终交付。
- 主体使用统一 `任务卡片` 模板。
- 末尾新增 `需求→任务追溯表`，把 SPEC 的 FR、验收和主贡献章节映射到任务。

任务卡片字段固定为：

- 元信息：状态、依赖、可并行、Worktree / PR、主贡献相关、Commit。
- 目标：一句话说明可验收结果。
- 涉及文件：列出 source、test、docs 或 scripts 的职责。
- SPEC 依据：指向 SPEC 章节、验收章节和系统架构参考。
- 接口契约：写清公开函数 / 类型边界、输入、输出、不变量和错误处理。
- 预期失败测试：列出 TDD 红阶段必须先写并先跑失败的测试。
- 实现要点：说明最小绿阶段方向，但不展开成逐行实现。
- 验证步骤：给出可复制命令。
- 非目标 / 边界：防止陌生 agent 越界扩张。

### 导致的变更

后续 `docs/PLAN.md` 应从“任务清单”升级为“冷启动可执行的实现合同”。这个变更不改变 SPEC 的需求内容，而是改变 PLAN 的承载方式：

- `docs/SPEC.md` 继续作为需求契约，回答要做什么、为什么做、完成标准是什么。
- `docs/系统架构.md` 继续作为架构展开，承接数据结构、模块边界、调用链和测试命名细节。
- `docs/PLAN.md` 负责把 SPEC / 架构转译成能被 subagent 独立执行的任务卡。

PLAN 的任务依赖最终收敛为 T1-T27 的细粒度任务链：

- M1 基础骨架：T1 共享模型与错误类型 → T2 Workspace 初始化 → T3 ConfigLoader / T4 StateStore → T5 PhaseGate → T6 WorkspaceRouter。
- M2/M3 Action 与 Governance：T7-T10 完成 Action / MockLLM / AgentLoop 基础，T11-T15 完成 ToolRegistry、FileTools、PathClassifier、ToolPolicy 和课程文件保护。
- M4/M5 主贡献回路：T16-T18 完成 Trace / Checkpoint / Rollback，T19-T21 完成 ContextBuilder、FeedbackBuilder 和 feedback / retry / rollback 集成。
- M6/M7 集成交付：T22-T23 完成交付产物和 MockLLM 机制 demo，T24-T27 完成 CLI、凭据、package / CI 和 README。

其中 FeedbackBuilder 失败分类、Trace / Checkpoint / Rollback 和 MockLLM demo 是主贡献回路的核心验证任务；Workspace memory 仍作为支撑维度实现最低可运行版本，不扩展成向量检索或复杂记忆系统。

## 17. 关键迭代 12

### 智能体问题 / 建议

在准备执行 `docs/PLAN.md` 的前置任务时，智能体发现当前计划已经扩展到 T1-T27，但部分文档仍保留旧版任务编号、根目录路径或 Docker 作为 MVP 分发格式的说法。这会影响冷启动验证：第二个 agent 可能找不到真实文件路径，或按旧任务编号选择不合适的验证任务。

### 我的决策

执行 T0 只做规划与过程文档一致性修订，不进入 `src/hancode/` 实现。仓库级课程交付物统一写作 `docs/SPEC.md`、`docs/PLAN.md`、`docs/SPEC_PROCESS.md` 和 `docs/AGENT_LOG.md`；`.hancode/tasks/.../SPEC.md` 这类运行时任务产物仍保留无 `docs/` 前缀。

### 导致的变更

- `docs/PLAN.md` 中 T0 的状态、路径、验证命令和冷启动说明对齐当前仓库结构。
- 冷启动候选任务改为当前任务编号下的 T1/T2/T5/T13，并把 T20 作为可选主贡献检查。
- README 的分发说明对齐 `docs/SPEC.md`：MVP 使用 Python package，Docker 只是可选 MockLLM demo 环境。

### 对正式开发的影响

冷启动验证已经完成并记录。T0 不再阻塞实现阶段；后续正式开发从 T1 开始，必须使用当前 `docs/PLAN.md` 中已回写冷启动发现的任务卡。

正式开发时，每个实现 agent 应优先检查任务卡是否足够独立：

- 是否能从 `SPEC 依据` 找到机制契约。
- 是否能从 `接口契约` 写出最小实现。
- 是否能从 `预期失败测试` 先进入红阶段。
- 是否能从 `非目标 / 边界` 避免引入真实 LLM、复杂 WebUI、Docker demo 或现成 agent framework。

如果实现 agent 仍需要口头解释某个任务如何开始，说明 PLAN 的任务卡还不够完整，应先修订 PLAN，而不是继续实现。

## 18. T27 README 与当前交付能力对齐

T27 将 README 从实现阶段占位说明更新为可供陌生用户执行的运行与分发文档。README 现在以当前 headless CLI 为事实来源，列出 `init`、`demo --provider mock`、`export` 和带 `--provider` 的 auth 命令，并给出 Python 3.11+、uv 锁定依赖、wheel 构建和安装步骤。

本次修订明确区分了已经实现的 CredentialProvider 凭据边界和未实现的真实 Provider 执行：MockLLM demo 不需要真实凭据或网络；keyring 是首选来源，环境变量和 `.env` 只作为读取来源；`.env` 的明文风险、外部来源需要人工清除以及禁止提交真实 API 密钥均在 README 中说明。

README 的已知限制明确记录当前没有 `hancode run`、REPL/TUI/WebUI、真实 Provider 执行和 Docker 必需分发路径，避免把 SPEC 中规划的能力误写成当前可用功能。新增 `tests/test_readme.py` 将这些关键文档承诺转成确定性文本契约。

T27 已取得 README 专项 TDD Red（`4 failed、1 passed`）和 Green（`6 passed`）证据；全量验证、独立 wheel 冷启动 smoke、两阶段新鲜评审和最终清理结果由实现完成后继续回填。
