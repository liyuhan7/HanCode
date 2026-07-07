# HanCode 规范

> 状态：设计草案  
> 项目类型：A · Coding Agent Harness

## 1. 问题陈述

学生在课程项目中使用 AI 辅助编码时，往往能够更快得到可运行代码或最终答案，但学习过程本身容易被压缩甚至消失。需求如何理解、方案为什么这样设计、代码改动经历了哪些尝试、测试失败如何定位、最终结果是否真正覆盖作业要求，这些本应体现学习和工程判断的过程信息，常常没有被记录下来。结果是项目可能完成了，但学生难以复盘自己做了什么、为什么这样做、哪里出错、下次如何迁移经验。

HanCode 要解决的问题不是“让 AI 更快替学生写完作业”，而是构建一个面向学生课程项目的轻量级 Coding Agent Harness，让 AI 辅助开发过程变得可控、可追踪、可回退、可复盘。HanCode 通过 Workspace 分离、Phase Gate、Tool Policy、Trace Logging 和 Checkpoint Rollback，将一次课程项目任务组织为 spec、plan、code、test、review、deliver 六个阶段。Agent 不能在缺少需求和计划时直接修改代码，也不能在不合适的阶段使用高风险工具；每轮关键操作都会被记录，代码修改前会形成 checkpoint，失败时可以回退。

HanCode 的主要价值在于帮助学生把 AI 生成结果转化为可学习的工程过程。对学生而言，它提供需求、计划、测试、错误修复和复盘记录，并在 deliver 阶段沉淀知识，而不是只得到答案；对工程过程而言，它用确定性代码机制约束 agent 行为，而不是只依赖提示词；对课程评估而言，它通过 trace、测试报告、checkpoint 和阶段产物提供可检查证据，方便验证任务是否按合理流程完成。

## 2. 目标用户

HanCode 的目标用户是正在完成编程类课程项目的学生。这类学生不是单纯的代码消费者，而是需求理解、设计决策、测试验证和复盘过程的主要承担者。他们正在完成小型课程项目，例如软件工程课程设计、AI4SE 项目、数据处理脚本、命令行工具或其他可通过本地测试验证的编程作业。

这类学生通常会使用 AI 辅助编码，但他们真正需要的不是让 AI 直接替自己完成最终代码，而是在 AI 参与的过程中保留学习和工程判断。对他们来说，关键问题包括：是否理解了课程要求，是否知道方案为什么这样设计，是否能解释测试失败和修复过程，是否能确认实现覆盖了作业要求，以及是否能把本次项目经验沉淀为下次可复用的知识。

因此，HanCode 面向的学生需要一个受控的 Coding Agent Harness：它既允许 AI 参与需求分析、计划制定、编码实现、测试验证、审查交付，也要求每个阶段留下可检查记录。HanCode 不面向所有使用 AI 的学生，也不面向非编程类作业；第一版聚焦小型、单人、可本地运行和测试的课程项目。

## 3. 用户故事

### 用户故事 1：Spec — 需求理解沉淀

作为一名学生，我希望 HanCode 在开始编码前引导我把课程作业要求整理成清晰的需求说明，包括目标、输入输出、约束、评分点和验收标准，以便我不是在没有理解作业要求的情况下直接让 AI 生成代码。

### 用户故事 2：Plan — 设计决策记录

作为一名学生，我希望 HanCode 在编码前生成实现计划，说明为什么采用当前方案、任务如何拆分、预计修改哪些文件、每一步如何验证，以便我能理解 AI 辅助实现背后的设计决策，并能在后续测试阶段回溯每一步的验证依据。

### 用户故事 3：Code — 受控编码与修改记录

作为一名学生，我希望 HanCode 只在允许的 code phase 修改业务代码，并在修改前记录 checkpoint、在修改后记录 changed files，以便我能够知道本轮 AI 到底改了什么，并为后续审查阶段提供回退依据。

### 用户故事 4：Test — 测试失败经验沉淀

作为一名学生，我希望 HanCode 在代码修改后运行测试并记录测试命令、测试结果、失败现象和错误摘要，以便我能够复盘测试失败如何暴露问题，而不是只看到 AI 修复后的结果。

### 用户故事 5：Review — 作业要求覆盖检查

作为一名学生，我希望 HanCode 在交付前根据需求说明、测试结果和 checkpoint 信息审查实现是否覆盖课程作业要求、是否存在未测试风险、是否需要回退或继续修改，以便我能判断“完成”是否真实成立。

### 用户故事 6：Deliver — 最终复盘与知识沉淀

作为一名学生，我希望 HanCode 在最终交付时整理本次任务的需求理解、设计决策、测试经验、错误修复和可复用知识，以便我在完成课程项目后仍能复盘学习过程，并把经验迁移到后续项目。

## 4. 功能性需求

HanCode 的功能性需求按业务需求、用户级需求和系统级需求三层展开。业务需求说明项目要达成的价值目标，用户级需求说明学生在课程项目流程中需要完成的任务，系统级需求说明 Harness 必须提供的确定性机制。

### 4.1 业务需求

| 编号 | 业务需求 | 优先级 | 说明 |
| --- | --- | --- | --- |
| BR-1 | 沉淀课程项目中的需求理解过程 | P0 | 学生必须先理解作业目标、输入输出、约束、评分点和验收标准，避免直接进入 AI 生成代码。 |
| BR-2 | 沉淀 AI 辅助开发中的设计决策 | P1 | 学生需要知道方案为什么这样设计、任务如何拆分、哪些文件会被修改、每一步如何验证。 |
| BR-3 | 沉淀测试失败、修复和审查经验 | P1 | 测试失败到修复的过程具有高学习价值，需要通过测试报告和审查记录保留下来。 |
| BR-4 | 支持可回退的受控代码尝试 | P2 | 代码修改前形成 checkpoint，使学生可以安全试错，并在失败时恢复到明确状态。 |
| BR-5 | 验证实现是否覆盖课程作业要求 | P2 | 交付前需要基于 SPEC、测试结果和改动记录检查需求覆盖、未测试风险和回退必要性。 |
| BR-6 | 形成可复用的项目知识沉淀 | P3 | deliver 阶段需要把需求理解、设计决策、测试经验和错误修复转化为可迁移的项目经验。 |

### 4.2 用户级需求

| 编号 | 对应业务需求 | 用户级需求 |
| --- | --- | --- |
| UR-1 | BR-1 | 学生能够在 spec phase 将课程作业要求整理为 `SPEC.md`，并在缺少 `SPEC.md` 时无法进入代码修改。 |
| UR-2 | BR-2 | 学生能够在 plan phase 生成 `PLAN.md`，记录实现步骤、设计理由、预计改动文件和验证方式。 |
| UR-3 | BR-4 | 学生能够在 code phase 让 Agent 修改业务代码，但每次修改前必须创建 checkpoint，并记录本轮 changed files。 |
| UR-4 | BR-3 | 学生能够在 test phase 运行测试，并把测试命令、测试结果、失败原因和未测试风险记录到 `TEST_REPORT.md`。 |
| UR-5 | BR-5 | 学生能够在 review phase 检查实现是否覆盖作业要求、代码质量是否可接受、测试是否充分，以及是否需要 rollback。 |
| UR-6 | BR-6 | 学生能够在 deliver phase 生成 `DELIVERABLES.md` 和 `KNOWLEDGE.md`，完成最终交付清单与学习复盘。 |

### 4.3 系统级需求

系统级需求分为两类：第一类定义 HanCode 作为 Coding Agent Harness 必须具备的基础能力；第二类定义这些基础能力在学生课程项目场景中的特定化规则。

#### 4.3.1 Harness 基础能力需求

##### FR-1：AgentLoop 主循环

- 输入：用户任务、当前 workspace 状态、phase、配置、LLM 客户端和可用工具集合。
- 行为：执行“构造上下文 → 调用 LLM → 解析 Action → 校验策略 → 分发工具 → 记录结果 → 回灌反馈 → 判断是否停止”的主循环。
- 输出：结构化执行结果，包括状态、执行步数、工具调用记录、最终产物和风险信息。
- 边界条件：必须受 `max_steps` 限制；不能在 policy denial 后绕过策略继续执行同一高风险动作。
- 错误处理：LLM 输出不可解析、工具执行失败、策略拒绝、达到最大步数或关键上下文缺失时，返回明确状态并写入 trace。

##### FR-2：LLM 抽象与 MockLLM

- 输入：结构化上下文、系统指令、当前 phase 和可用 action schema。
- 行为：通过统一接口调用真实 LLM 或 MockLLM；MockLLM 用于离线、确定性地驱动单元测试和机制演示。
- 输出：LLM 返回的候选 action 或完成信号。
- 边界条件：核心机制测试不得依赖网络或真实 LLM；MockLLM 必须能稳定复现指定 action 序列。
- 错误处理：真实 LLM 调用失败时返回可诊断错误；MockLLM action 序列耗尽时返回 blocked 或 failed 状态。

##### FR-3：Action 解析与校验

- 输入：LLM 原始输出或 MockLLM 预设输出。
- 行为：将输出解析为结构化 Action，至少包含 `tool_name`、`args`、`reason`、`phase` 等字段。
- 输出：合法 Action、完成信号或解析错误。
- 边界条件：未知工具、缺失参数、缺失 reason、phase 不匹配的 action 不得进入工具执行。
- 错误处理：解析失败时将错误作为 observation 回灌给 AgentLoop，并写入 trace。

##### FR-4：ToolRegistry 与工具分发

- 输入：结构化 Action、工具注册表和当前 workspace。
- 行为：根据 `tool_name` 查找并执行对应工具，统一封装工具输入、输出和异常。
- 输出：工具执行结果，包括成功结果、失败结果或策略拒绝结果。
- 边界条件：未注册工具不得执行；工具只能访问当前 workspace 允许的路径和能力。
- 错误处理：工具不存在、参数非法或执行异常时返回结构化错误，并写入 trace。

##### FR-5：ToolPolicy 治理护栏

- 输入：Action、当前 phase、workspace 状态、工具参数、reason 和配置规则。
- 行为：在工具执行前进行确定性策略检查，拦截越权修改、高风险操作、缺少前置产物、缺少 checkpoint 或缺少 reason 的请求。
- 输出：allow、deny 或 require_checkpoint 的策略判定。
- 边界条件：策略判定必须由代码完成，不能只依赖提示词；所有拒绝必须给出可读原因。
- 错误处理：策略拒绝时不得执行工具，并将拒绝原因回灌给 AgentLoop。

##### FR-6：ContextBuilder 与记忆选择

- 输入：Project Workspace、Task Workspace、当前 phase、配置、最近执行状态和关键产物。
- 行为：按 phase 选择最小必要上下文，向 LLM 提供课程背景、任务产物、测试结果、审查信息或 trace 摘要。
- 输出：结构化 prompt context。
- 边界条件：不得无条件加载全部历史；不同 task 的 history、trace 和 checkpoint 不得混用。
- 错误处理：当前 phase 所需关键上下文缺失时返回错误，并阻止进入依赖该上下文的操作。

##### FR-7：反馈回灌机制

- 输入：工具执行结果、测试结果、policy denial、解析错误、checkpoint 或 rollback 结果。
- 行为：把客观反馈整理为 observation，作为下一轮 AgentLoop 的输入，使 Agent 能基于失败原因调整下一步动作。策略拒绝时，必须将拒绝原因和纠正建议作为 observation 回灌，使 Agent 能调整 action，而不是重复提交同类违规请求。
- 输出：结构化 observation。
- 边界条件：反馈必须来自确定性工具结果或系统判定，不能只由 LLM 自行判断。
- 错误处理：反馈无法生成时，AgentLoop 应停止或进入 blocked 状态，而不是继续盲目执行。

##### FR-8：TraceLogger

- 输入：phase 切换、LLM 决策、action 解析、policy 判定、工具调用、反馈、checkpoint、rollback 和最终结果。
- 行为：将关键事件追加写入 `trace.jsonl`。
- 输出：可复盘、可测试、可审查的执行轨迹。
- 边界条件：trace 不得记录真实凭据；不得把大文件内容完整写入日志。
- 错误处理：trace 写入失败时阻止继续执行高风险工具，并返回日志不可用错误。

##### FR-9：配置加载与运行约束

- 输入：项目配置、任务配置、默认配置和环境变量状态。
- 行为：加载 LLM provider、模型名称、workspace 路径、phase 策略、工具权限、测试命令、构建命令和 `max_steps`。
- 输出：供 AgentLoop、ContextBuilder、ToolPolicy 和工具层使用的配置对象。
- 边界条件：配置不得包含明文真实凭据；凭据只允许通过安全来源读取状态或引用。
- 错误处理：配置缺失、格式错误或不安全配置出现时，启动失败并返回修复建议。

#### 4.3.2 学生课程项目特定化需求

##### FR-10：Project Workspace 与 Task Workspace

- 输入：课程项目目录、项目元数据和 task ID。
- 行为：Project Workspace 管理课程项目级上下文和长期经验；Task Workspace 管理单次任务的 SPEC、PLAN、trace、checkpoint 和学习产物。
- 输出：`.hancode/` 下的项目级文件与 task 级目录。
- 边界条件：任务之间的执行历史、trace 和 checkpoint 必须隔离；项目级经验只按需进入上下文。
- 错误处理：workspace 缺失时创建必要结构；元数据损坏时停止执行并提示修复。

##### FR-11：课程项目 Phase Gate

- 输入：目标 phase、当前 task 状态、已存在产物和目标 action。
- 行为：维护 `spec`、`plan`、`code`、`test`、`review`、`deliver` 六个阶段的执行约束。
- 输出：允许进入阶段、拒绝进入阶段或要求补充前置产物。
- 边界条件：缺少 `SPEC.md` 或 `PLAN.md` 时不能进入 code phase；只有 code phase 可以主动修改业务代码。
- 错误处理：阶段不合法或前置产物缺失时返回明确拒绝原因，并写入 trace。

##### FR-12：课程项目上下文构造

- 输入：`course_context.md`、`project_memory.md`、`experience.md`、SPEC、PLAN、TEST_REPORT、REVIEW、KNOWLEDGE 和 trace 摘要。
- 行为：按当前 phase 构造课程项目上下文；code phase 必须看到 SPEC 和 PLAN；review phase 必须看到测试结果、changed files 和 checkpoint 信息；deliver phase 必须看到 SPEC、PLAN、TEST_REPORT、REVIEW 和 trace 摘要。
- 输出：面向课程项目任务的结构化上下文。
- 边界条件：课程要求、评分标准、提交格式和教师限制条件优先于历史经验。
- 错误处理：关键课程上下文缺失时在输出中标记风险，不得假装已覆盖作业要求。

##### FR-13：课程文件保护策略

- 输入：文件路径、工具 action、当前 phase、workspace 配置和 protected patterns。
- 行为：保护作业说明、教师测试、评分脚本、样例数据和课程提供的约束文件，禁止 Agent 未经明确授权修改或删除。
- 输出：allow 或 policy denial。
- 边界条件：教师测试和评分脚本不得被删除；测试失败不得通过绕过测试、删除测试或修改评分脚本解决。
- 错误处理：发现受保护文件修改请求时拒绝执行，记录 trace，并要求学生明确确认或调整计划。

##### FR-14：Checkpoint 与 Rollback

- 输入：即将修改的文件集合、当前 task 状态、rollback 请求和 retry budget。
- 行为：code phase 修改业务代码前创建 checkpoint；review phase 可根据测试和审查结果触发 rollback；当同一任务的修复重试次数超过配置上限时，必须强制 rollback 到上一 checkpoint。
- 输出：checkpoint ID、manifest、被恢复文件列表、剩余 retry budget 和 rollback 结果。
- 边界条件：checkpoint 只覆盖当前任务允许修改的业务文件；rollback 不应影响作业说明、教师测试、评分脚本或样例数据；重试次数超过配置上限时，默认上限为 2，必须强制 rollback 到上一 checkpoint，不得继续修改。
- 错误处理：checkpoint 缺失、manifest 损坏或文件恢复失败时停止 rollback，并保留错误记录。

##### FR-15：测试报告与审查记录

- 输入：测试命令、测试输出、changed files、SPEC、PLAN、checkpoint 信息和未测试说明。
- 行为：在 test phase 生成或更新 `TEST_REPORT.md`；在 review phase 生成或更新 `REVIEW.md`，记录测试结果、失败原因、需求覆盖、代码质量问题、未测试风险和 rollback 建议。
- 输出：测试报告和审查记录。
- 边界条件：代码修改后必须运行相关测试；无法运行测试时必须记录原因和风险。
- 错误处理：测试失败时，AgentLoop 必须将 phase 切换到 review，由 review phase 判断继续修改、记录风险或 rollback；不得直接返回 completed。

##### FR-16：Knowledge Delivery

- 输入：SPEC、PLAN、TEST_REPORT、REVIEW、trace 摘要、最终文件状态和课程交付要求。
- 行为：deliver phase 生成 `DELIVERABLES.md` 和 `KNOWLEDGE.md`，整理交付物清单、需求覆盖、测试情况、关键设计决策、错误修复经验和可迁移知识。
- 输出：最终课程项目交付摘要、交付物清单和知识沉淀文件。
- 边界条件：deliver phase 不应修改业务代码；缺少 `KNOWLEDGE.md` 或 `DELIVERABLES.md` 时不得返回 completed 状态。
- 错误处理：缺少测试或审查记录时必须在风险中说明，并把最终状态标记为 failed、skipped 或 completed_with_risks。

## 5. 非功能性需求

HanCode 的非功能性需求覆盖性能、安全、可用性、可观测性、可靠性与可恢复性。由于 HanCode 是面向学生课程项目的轻量级 Coding Agent Harness，本节不以高并发或企业级平台能力为目标，而以本地可运行、机制可验证、过程可复盘、失败可恢复为核心质量标准。

### 5.1 性能需求

- HanCode 应能在小型课程项目规模下稳定运行，目标项目规模为单人课程作业、命令行工具、数据处理脚本或小型应用。
- 单次 context 构造应在秒级完成，ContextBuilder 必须按 phase 选择最小必要上下文，避免无差别加载全部历史。
- 单次 context 构造中，不同 task 的 history、trace 和 checkpoint 不得混入当前 context。
- `trace.jsonl`、checkpoint manifest、workspace 元数据应采用轻量文本或 JSON 格式，支持快速追加、读取和调试。
- MockLLM 测试应快速、确定、可一键运行，不依赖网络、真实 LLM 或外部服务。
- `max_steps` 必须限制 AgentLoop 最大执行步数，`retry_budget` 必须限制失败后的重复修改次数，避免无限循环或无界成本。
- Checkpoint 只保存被修改前的必要文件快照，不应对整个项目目录进行无差别复制。

### 5.2 安全需求与凭据威胁模型

HanCode 必须把凭据安全、文件边界和工具治理作为基础安全要求。安全机制应由确定性代码实现，不能只依赖提示词要求 Agent 自觉遵守。

#### 5.2.1 凭据安全要求

- 真实 API key、token、密钥和其他凭据不得硬编码到源码、测试、配置模板、README 示例、trace、日志或错误信息中。
- 凭据不得提交到 Git；`.env`、本地凭据文件、运行时 workspace 和 `.hancode/` 应被明确排除在版本控制之外。
- HanCode 应支持安全凭据来源，优先使用操作系统凭据管理器；也可支持环境变量和 `.env` 文件作为本地开发来源，但必须说明 `.env` 是明文文件。
- 查看凭据状态时只能显示是否已配置、来源类型或脱敏标识，不得回显明文 key。
- 凭据录入、更新和清除流程应可通过 CLI 完成；录入时不得把明文 key 打印到终端输出。
- Docker 分发或其他分发形态不得把真实 key 写入镜像、构建产物或默认配置文件。

#### 5.2.2 凭据威胁模型

| 威胁 | 风险 | 对策 |
| --- | --- | --- |
| 误提交凭据 | key 被提交到公开仓库或课程评审仓库 | `.gitignore` 排除 `.env`、`.hancode/` 和本地凭据文件；测试和文档只使用占位符 |
| 日志泄露 | key 出现在运行日志、trace 或错误输出中 | TraceLogger 和错误处理必须脱敏；禁止记录凭据字段 |
| 异常栈泄露 | LLM provider 或工具异常中携带请求配置 | 异常输出只保留错误类型和摘要，不打印完整请求对象 |
| trace 泄露 | `trace.jsonl` 被提交或分享时包含敏感信息 | trace 不记录明文 key，不记录完整环境变量，不记录大段文件内容 |
| Docker 镜像内嵌 | 构建镜像时把 `.env` 或本地配置复制进镜像 | Docker 构建上下文排除凭据文件；运行时通过安全环境变量或挂载配置注入 |
| 命令行 history 泄露 | 用户通过命令参数传入 key，进入 shell history | CLI 不要求通过命令行参数传入 key；使用隐藏输入或外部凭据来源 |
| checkpoint 快照泄露 | checkpoint 把 `.env` 或含 key 的配置文件纳入快照，rollback 时恢复明文凭据 | CheckpointManager 默认排除 `.env`、本地凭据文件和受保护配置；manifest 不记录凭据内容 |

#### 5.2.3 文件与工具安全要求

- ToolPolicy 必须限制工具只能访问当前 workspace 允许的路径。
- 作业说明、教师测试、评分脚本、样例数据和课程提供的约束文件默认受保护，不得被 Agent 未经明确授权修改或删除。
- 测试失败不得通过删除测试、绕过评分脚本、修改教师测试或忽略失败结果解决。
- `edit_file`、`write_file` 等高风险工具必须提供 `reason`，并在修改业务代码前经过 checkpoint 检查。
- 所有工具调用必须写入 trace，以便事后审查越权尝试和策略拒绝原因。

### 5.3 可用性需求

- HanCode 应提供清晰的 CLI 使用方式，使学生能够围绕 task 和 phase 执行课程项目流程。
- CLI 命令应能表达 project、task、phase、demo、test、review、deliver 等核心操作，不要求复杂 Web UI。
- 错误信息必须说明失败原因、被哪条规则拒绝、当前 phase 或 workspace 状态，以及学生下一步应补充的产物或操作。
- 阶段产物文件命名应稳定，包括 `SPEC.md`、`PLAN.md`、`TEST_REPORT.md`、`REVIEW.md`、`KNOWLEDGE.md`、`DELIVERABLES.md`。
- Demo 应展示 `spec → plan → code → test → review → deliver` 完整流程，并能让学习者和评估者观察 trace、checkpoint、测试报告和知识沉淀。
- 最终输出应使用结构化结果，包含状态、task ID、需求覆盖、文件变更、测试结果、checkpoint、rollback、交付物、知识条目、风险和下一步建议。
- 对学生而言，HanCode 不应只输出最终代码，而应让需求理解、计划、测试、审查和复盘过程都能被读取和解释。

### 5.4 可观测性需求

- HanCode 必须记录所有关键执行事件，包括 phase 切换、LLM 决策、action 解析、policy 判定、工具调用、工具结果、feedback、checkpoint、rollback 和最终状态。
- `trace.jsonl` 应采用结构化 JSONL 格式，便于单元测试、离线检查和课程评估。
- 每条 trace 事件应至少包含事件类型、时间、task ID、phase、关联 action、结果状态和错误摘要；不得包含真实凭据。
- Policy denial 必须记录被拒绝的规则、原因和建议修正动作。
- Checkpoint 和 rollback 事件必须记录 checkpoint ID、manifest 路径、涉及文件和恢复结果。
- 测试事件必须记录测试命令、退出状态、摘要结果和失败原因；失败后必须能从 trace 看出 phase 已切换到 review。
- MockLLM 机制演示必须能通过 trace 证明控制流真实发生，包括策略拦截、失败反馈回灌、重试预算消耗和强制 rollback。
- 最终交付结果应能从 trace、`TEST_REPORT.md`、`REVIEW.md` 和 `KNOWLEDGE.md` 交叉验证。

### 5.5 可靠性与可恢复性需求

可靠性与可恢复性单独成节，是因为 HanCode 的核心质量承诺不仅是让 Agent 能执行任务，还要让学生在 AI 辅助编码失败时能够定位问题、限制损失并恢复到明确状态。Checkpoint、retry budget、强制 rollback 和 phase gate 共同构成 HanCode 的恢复机制。

- 代码修改前必须创建 checkpoint；没有 checkpoint 时，`edit_file` 或 `write_file` 不得修改业务代码。
- Checkpoint 应包含 manifest，记录快照时间、task ID、phase、被保护文件列表、被快照文件列表和文件校验信息。
- retry budget 默认值为 2；同一任务的修复重试次数超过配置上限时，AgentLoop 必须强制 rollback 到上一 checkpoint。
- 强制 rollback 后，AgentLoop 应回到 checkpoint 对应的 phase，并将测试失败原因和 rollback 结果作为反馈回灌，避免重复相同错误。
- Rollback 必须恢复 manifest 中记录的业务文件，并记录被恢复文件列表、恢复结果和失败原因。
- Rollback 不得覆盖作业说明、教师测试、评分脚本、样例数据、`.env` 或本地凭据文件。
- 测试失败时，AgentLoop 必须确定性切换到 review phase，不得直接返回 completed。
- Review phase 应根据测试结果、changed files、checkpoint 信息和 retry budget 判断继续修改、记录风险或 rollback。
- Trace 写入失败时，不得继续执行高风险工具，避免发生不可审查的文件修改。
- `max_steps` 必须防止 AgentLoop 无限循环；达到最大步数时应返回 blocked 或 failed，并记录最后状态。
- workspace 元数据损坏、关键产物缺失或 checkpoint manifest 不可读时，HanCode 应停止高风险动作，并给出可恢复错误。
