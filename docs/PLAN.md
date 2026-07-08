# HanCode 实现计划

> 状态：设计草案  
> 仓库处于规范和规划阶段。完整实现必须在 SPEC、PLAN 和冷启动验证完成后开始。

## 项目定位

HanCode 是一个为学生课程项目调校的 Coding Agent Harness。它的核心是 AI 辅助编码
的控制回路——修改代码、运行测试、根据失败自我修正、失败超限时回退——并通过阶段
门禁、工具权限控制、执行追踪和 Checkpoint 回退机制，把这条回路约束在受控、可纠错、
可复盘的边界内。

主线保持一致：

- Feedback Loop 管测试信号的分类与回灌，驱动 Agent 针对性修复。
- Checkpoint Rollback 管代码修改前快照与失败后的可回退恢复。
- Tool Policy 管工具权限与课程文件保护。
- Phase Mode 管需求、计划、编码、测试、审查、交付各阶段的工具权限。
- Workspace 分层管课程项目级与任务级上下文隔离（支撑维度）。
- Knowledge Delivery 管最终的项目复盘、错误记录和知识沉淀。

## 任务状态图例

- [ ] 未开始
- [~] 进行中
- [x] 已完成

## 全局规则

- 遵循 Superpowers 工作流。
- 对实现任务使用 TDD：先写失败测试，再写最小实现，再重构。
- 每个任务使用新鲜子智能体或单独执行会话。
- 每个任务完成后更新 `PLAN.md` 和 `AGENT_LOG.md`。
- 不得提交真实凭据。
- 不引入复杂 Web UI、数据库、pgvector、MCP 工具市场、多用户系统或企业级权限系统。
- 不使用 LangGraph、AutoGen、CrewAI 等现成 Agent Framework 替代 HanCode 内核。

## MVP 与 post-MVP 边界

MVP 优先保证主贡献回路闭环与六维度最低可运行：feedback 分类、checkpoint、
rollback、retry budget、ToolPolicy 课程文件保护、MockLLM 驱动的 spec→deliver
全流程。以下加固项属 post-MVP（P2），在 MVP 闭环稳定后再实现，不阻塞主线：

- 单 task 单活跃 runner 的并发锁。
- blocked 后的 resume 断点续跑语义。
- pending checkpoint 的启动崩溃恢复。
- `confirm_before_write` 写前人工确认。
- 跨盘符 / UNC 路径的完整规范化（MVP 覆盖 `..`、符号链接和大小写逃逸即可）。

---

## 任务 0：课程项目定位与模板准备

- 状态：[~]
- 目标：明确项目定位、核心叙事、`.hancode/` 结构和 demo 描述，使其服务学生课程项目场景。
- 文件：
  - `README.md`
  - `SPEC.md`
  - `PLAN.md`
  - `AGENT_LOG.md`
  - `.hancode/`
  - `tests/`
- 实现说明：
  - 覆盖 Workspace、Phase Gate、Tool Policy、Trace Logging、Checkpoint Rollback、MockLLM Testing 方向。
  - 增加课程项目导向的 `.hancode/` 模板。
  - 使用学生成绩统计 CLI 作为课程项目 demo。
- 验证：
  - `python -m pytest`
  - `python -m ruff check src tests`
  - `python -m mypy src`
- 提交：
  - TODO

---

## 任务 1：SPEC 与冷启动验证

- 状态：[ ]
- 目标：完成课程项目导向的 `SPEC.md`，并用不同智能体冷启动验证。
- 文件：
  - `SPEC.md`
  - `SPEC_PROCESS.md`
  - `AGENT_LOG.md`
- 预期检查：
  - SPEC 包含问题陈述、用户故事、功能规约、非功能需求、架构、数据模型、凭据与分发、技术选型、验收标准、风险。
  - SPEC 包含 Coding Agent Harness 的领域与机制设计。
  - 主贡献维度是 deterministic feedback loop and reversible coding state。
- 验证：
  - 使用第二个不同类型 agent 仅凭 `SPEC.md` + `PLAN.md` 尝试 1-2 个任务。
  - 将问题和修订记录到 `SPEC_PROCESS.md`。
- 提交：
  - TODO

---

## 任务 2：WorkspaceSpec 与 `.hancode/` 初始化

- 状态：[ ]
- 依赖：任务 1
- 目标：实现课程项目导向的 WorkspaceSpec 和本地 `.hancode/` 初始化。
- 文件：
  - `src/hancode/workspace.py`
  - `src/hancode/config.py`
  - `tests/test_workspace.py`
- 预期失败的测试：
  - `test_workspace_has_separate_history`
  - 初始化生成 `project.json`、`project_memory.md`、`course_context.md`、`experience.md`。
  - 初始化生成 `tasks/task-001/` 下的 SPEC、PLAN、REVIEW、TEST_REPORT、KNOWLEDGE、DELIVERABLES、state、trace、history 和 checkpoints。
- 验证：
  - `python -m pytest tests/test_workspace.py`
- 提交：
  - TODO

---

## 任务 3：Phase Mode 与 Phase Gate

- 状态：[ ]
- 依赖：任务 2
- 目标：实现 `spec -> plan -> code -> test -> review -> deliver` 的轻量 phase gate。
- 文件：
  - `src/hancode/phases.py`
  - `src/hancode/state.py`
  - `tests/test_phase_gate.py`
- 预期失败的测试：
  - `test_spec_phase_rejects_edit_file`
  - `test_plan_required_before_code_phase`
  - `test_code_phase_allows_edit_file`
  - deliver phase 不允许修改业务代码。
- 验证：
  - `python -m pytest tests/test_phase_gate.py`
- 提交：
  - TODO

---

## 任务 4：Action Schema、MockLLM 与 AgentLoop

- 状态：[ ]
- 依赖：任务 3
- 目标：实现可注入 MockLLM 的自有 agent loop，不依赖现成 agent runner。
- 文件：
  - `src/hancode/actions.py`
  - `src/hancode/llm.py`
  - `src/hancode/agent_loop.py`
  - `tests/test_actions.py`
  - `tests/test_llm.py`
  - `tests/test_agent_loop.py`
- 预期失败的测试：
  - MockLLM 按顺序返回动作。
  - action parser 拒绝未知动作和格式错误动作。
  - `test_max_steps_prevents_infinite_loop`
  - agent loop 在执行工具前调用 ToolPolicy。
- 验证：
  - `python -m pytest tests/test_actions.py tests/test_llm.py tests/test_agent_loop.py`
- 提交：
  - TODO

---

## 任务 5：ToolRegistry 与课程项目 ToolPolicy

- 状态：[ ]
- 依赖：任务 3
- 目标：实现工具注册、工具权限和课程项目保护规则。
- 文件：
  - `src/hancode/tools.py`
  - `src/hancode/tool_policy.py`
  - `tests/test_tool_policy.py`
- 预期失败的测试：
  - `test_tool_not_allowed_in_workspace_is_denied`
  - `test_edit_file_requires_reason`
  - `test_policy_protects_assignment_files`
  - `test_policy_protects_teacher_tests_or_grading_scripts`
  - 禁止没有 `SPEC.md` 时修改业务代码。
  - 禁止没有 `PLAN.md` 时修改业务代码。
  - 禁止绕过测试或评分脚本。
- 验证：
  - `python -m pytest tests/test_tool_policy.py`
- 提交：
  - TODO

---

## 任务 6：TraceLogger、CheckpointManager 与 Rollback

- 状态：[ ]
- 依赖：任务 5
- 目标：实现工具调用 trace、loop-level checkpoint 和最近 checkpoint 回退。
- 文件：
  - `src/hancode/trace.py`
  - `src/hancode/checkpoints.py`
  - `tests/test_trace.py`
  - `tests/test_checkpoints.py`
- 预期失败的测试：
  - `test_edit_file_creates_checkpoint`
  - `test_rollback_last_checkpoint_restores_file`
  - 所有工具调用必须写入 trace。
  - rollback 输出恢复文件列表和 checkpoint ID。
- 验证：
  - `python -m pytest tests/test_trace.py tests/test_checkpoints.py`
- 提交：
  - TODO

---

## 任务 7：ContextBuilder 与课程上下文

- 状态：[ ]
- 依赖：任务 2、任务 3
- 目标：实现按 phase 装配上下文，不全量加载历史。
- 文件：
  - `src/hancode/context.py`
  - `tests/test_context_builder.py`
- 预期失败的测试：
  - `test_context_builder_includes_course_context`
  - code phase 必须包含 `SPEC.md` 和 `PLAN.md`。
  - review phase 必须包含测试结果、修改文件和 checkpoint 信息。
  - deliver phase 必须包含 SPEC、PLAN、TEST_REPORT、REVIEW、KNOWLEDGE 和 trace 摘要。
- 验证：
  - `python -m pytest tests/test_context_builder.py`
- 提交：
  - TODO

---

## 任务 8：测试报告、审查与 Knowledge Delivery

- 状态：[ ]
- 依赖：任务 6、任务 7
- 目标：实现主贡献回路的反馈分类、课程项目交付产物和最终结构化输出。
- 文件：
  - `src/hancode/delivery.py`
  - `src/hancode/feedback.py`
  - `tests/test_delivery.py`
  - `tests/test_feedback.py`
- 预期失败的测试：
  - `test_feedback_classifies_syntax_error`
  - `test_feedback_classifies_import_error`
  - `test_feedback_classifies_assertion_failure`
  - `test_feedback_classification_is_deterministic_on_fixture`
  - `test_feedback_hint_matches_category`
  - `test_code_change_requires_test_or_risk_note`
  - `test_deliver_requires_knowledge_file`
  - `test_deliver_requires_deliverables_file`
  - 测试失败并 rollback 时输出 checkpoint、恢复文件、未完成需求和下一步建议。
- 实现说明：
  - `FeedbackBuilder` 将 `run_tests` 输出确定性分类为 `syntax_error`、`import_error`、
    `assertion_failure`、`error_exception`、`timeout_or_crash`、`unknown`，
    并附随类别确定的纠正建议（见 `SPEC.md` §11.3.1）。
- 验证：
  - `python -m pytest tests/test_delivery.py tests/test_feedback.py`
- 提交：
  - TODO

---

## 任务 9：课程项目 Demo

- 状态：[ ]
- 依赖：任务 4、任务 5、任务 6、任务 7、任务 8
- 目标：用 MockLLM 确定性演示学生成绩统计 CLI 项目流程。
- 文件：
  - `examples/course_project_grade_cli/`
  - `scripts/demo_course_project.py`
  - `tests/test_course_project_demo.py`
- Demo 任务：
  - 从 CSV 文件读取学生成绩。
  - 计算平均分、最高分、最低分。
  - 支持按课程筛选。
  - 输出统计结果。
  - 编写测试。
  - 生成 README、TEST_REPORT 和 KNOWLEDGE。
- 预期失败的测试：
  - spec phase 生成 `SPEC.md`。
  - plan phase 生成 `PLAN.md`。
  - code phase 修改前创建 checkpoint。
  - test phase 生成 `TEST_REPORT.md`。
  - review phase 检查需求符合性和测试结果。
  - deliver phase 生成 `DELIVERABLES.md` 和 `KNOWLEDGE.md`。
  - `trace.jsonl` 记录全过程。
- 验证：
  - `python -m pytest tests/test_course_project_demo.py`
- 提交：
  - TODO

---

## 任务 10：凭据、CLI、Docker 与 CI

- 状态：[ ]
- 依赖：任务 9
- 目标：完成真实 LLM 可选路径、CLI、Docker 分发和 CI。
- 文件：
  - `src/hancode/credentials.py`
  - `src/hancode/cli.py`
  - `Dockerfile`
  - `.github/workflows/ci.yml`
  - `README.md`
- 预期失败的测试：
  - CLI 显示帮助。
  - CLI 可运行课程项目 demo。
  - 凭据状态检查不打印密钥。
  - Docker 镜像可以构建并运行帮助命令。
- 验证：
  - `python -m pytest`
  - `python -m ruff check src tests`
  - `python -m mypy src`
  - `docker build -t hancode .`
  - `docker run --rm hancode --help`
- 提交：
  - TODO

---

## 必需课程项目测试名

实现阶段至少覆盖：

- `test_spec_phase_rejects_edit_file`
- `test_plan_required_before_code_phase`
- `test_code_phase_allows_edit_file`
- `test_edit_file_requires_reason`
- `test_edit_file_creates_checkpoint`
- `test_rollback_last_checkpoint_restores_file`
- `test_workspace_has_separate_history`
- `test_tool_not_allowed_in_workspace_is_denied`
- `test_code_change_requires_test_or_risk_note`
- `test_max_steps_prevents_infinite_loop`
- `test_deliver_requires_knowledge_file`
- `test_deliver_requires_deliverables_file`
- `test_context_builder_includes_course_context`
- `test_policy_protects_assignment_files`
- `test_policy_protects_teacher_tests_or_grading_scripts`
