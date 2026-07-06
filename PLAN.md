# HanCode 实现计划

> 状态：草稿  
> 在 SPEC 和 PLAN 通过冷启动验证之前，不得开始实现。

## 任务状态图例

- [ ] 未开始
- [~] 进行中
- [x] 已完成

## 全局规则

- 遵循 Superpowers 工作流。
- 对实现任务使用 TDD（测试驱动开发）。
- 在实现之前编写会失败的测试。
- 每个任务使用全新的子智能体。
- 使用 Git 工作树管理独立功能分支。
- 每个任务完成后更新本文件。
- 在 `AGENT_LOG.md` 中记录智能体活动。
- 不得提交真实的凭据。

---

## 任务 0：仓库初始化

- 状态：[ ]
- 目标：创建初始的 GitHub 仓库结构。
- 文件：
  - `README.md`
  - `SPEC.md`
  - `PLAN.md`
  - `SPEC_PROCESS.md`
  - `AGENT_LOG.md`
  - `REFLECTION.md`
  - `.gitignore`
  - `.env.example`
  - `pyproject.toml`
  - `Makefile`
  - `.github/workflows/ci.yml`
- 实现说明：
  - 创建文档占位符。
  - 创建 Python 源代码和测试目录。
  - 添加占位测试以保持 CI 通过。
- 验证：
  - 仓库初始化成功。
  - 没有提交密钥。
  - 初始提交已推送到 GitHub。
  - `python -m pytest` 通过。
  - `python -m ruff check src tests` 通过。
  - `python -m mypy src` 通过。
- 提交：
  - TODO

---

## 任务 1：头脑风暴与 SPEC 完成

- 状态：[ ]
- 目标：使用 Superpowers 头脑风暴工作流完成 `SPEC.md`。
- 文件：
  - `SPEC.md`
  - `SPEC_PROCESS.md`
  - `AGENT_LOG.md`
- 实现说明：
  - 不编写源代码实现。
  - 使用智能体提出澄清性问题。
  - 记录至少三次关键的规范迭代。
  - 明确定义编码智能体框架的机制设计。
- 验证：
  - SPEC 包含所有必需的通用章节。
  - SPEC 包含必需的编码智能体框架章节：领域与机制设计。
  - 主要贡献维度已明确选择。
- 提交：
  - TODO

---

## 任务 2：PLAN 完成

- 状态：[ ]
- 目标：使用 Superpowers 编写计划工作流完成 `PLAN.md`。
- 文件：
  - `PLAN.md`
  - `SPEC_PROCESS.md`
  - `AGENT_LOG.md`
- 实现说明：
  - 将实现分解为小任务。
  - 每个任务应可由一个子智能体在一次专注会话中完成。
  - 每个实现任务必须包含预期会失败的测试计划。
  - 标记依赖关系和可并行执行的任务。
- 验证：
  - 每个任务都有目标、文件、实现说明和验证步骤。
  - 依赖关系明确。
  - 可并行执行的任务已标记。
- 提交：
  - TODO

---

## 任务 3：冷启动验证

- 状态：[ ]
- 目标：使用不同的编码智能体验证 SPEC 和 PLAN。
- 文件：
  - `SPEC_PROCESS.md`
  - `SPEC.md`
  - `PLAN.md`
- 实现说明：
  - 使用与主开发智能体不同的编码智能体。
  - 开始一个全新的会话。
  - 仅提供 `SPEC.md` 和 `PLAN.md`。
  - 让第二个智能体尝试 1–2 个任务。
  - 不提供口头解释或隐藏上下文。
- 验证：
  - 记录了第二个智能体提出的问题。
  - 记录了误解之处。
  - 根据发现结果修订了 SPEC 和 PLAN。
  - 记录了关键的前后差异。
- 提交：
  - TODO

---

## 任务 4：验证后的项目骨架

- 状态：[ ]
- 依赖：
  - 任务 1
  - 任务 2
  - 任务 3
- 目标：在规范批准后创建最终的源代码骨架。
- 文件：
  - `src/hancode/agent_loop.py`
  - `src/hancode/llm.py`
  - `src/hancode/actions.py`
  - `src/hancode/tools.py`
  - `src/hancode/guardrails.py`
  - `src/hancode/feedback.py`
  - `src/hancode/memory.py`
  - `src/hancode/config.py`
  - `src/hancode/credentials.py`
  - `src/hancode/cli.py`
  - `tests/`
- 预期失败的测试：
  - SPEC 完成后补充 TODO。
- 验证：
  - SPEC 完成后补充 TODO。
- 提交：
  - TODO

---

## 任务 5：LLM 抽象层与 MockLLM

- 状态：[ ]
- 依赖：
  - 任务 4
- 目标：实现可注入的 LLM 抽象层和确定性的 MockLLM。
- 文件：
  - `src/hancode/llm.py`
  - `tests/test_llm.py`
- 预期失败的测试：
  - MockLLM 按顺序返回预设响应。
  - MockLLM 记录收到的提示词。
  - 智能体代码可以使用 LLM 接口而无需知道是真实还是模拟。
- 验证：
  - `python -m pytest tests/test_llm.py`
- 提交：
  - TODO

---

## 任务 6：动作模式与解析器

- 状态：[ ]
- 依赖：
  - 任务 5
- 目标：定义动作数据结构和解析器。
- 文件：
  - `src/hancode/actions.py`
  - `tests/test_actions.py`
- 预期失败的测试：
  - 解析有效的 `read_file` 动作。
  - 解析有效的 `write_file` 动作。
  - 解析有效的 `run_command` 动作。
  - 拒绝格式错误的动作。
  - 拒绝未知的动作类型。
- 验证：
  - `python -m pytest tests/test_actions.py`
- 提交：
  - TODO

---

## 任务 7：工具调度器与文件工具

- 状态：[ ]
- 依赖：
  - 任务 6
- 目标：实现安全文件操作的工具调度。
- 文件：
  - `src/hancode/tools.py`
  - `tests/test_tools.py`
- 预期失败的测试：
  - 调度 `read_file`。
  - 调度 `write_file`。
  - 拒绝未知工具。
  - 返回结构化的工具结果。
- 验证：
  - `python -m pytest tests/test_tools.py`
- 提交：
  - TODO

---

## 任务 8：护栏

- 状态：[ ]
- 依赖：
  - 任务 6
  - 任务 7
- 目标：实现针对危险动作的确定性护栏。
- 文件：
  - `src/hancode/guardrails.py`
  - `tests/test_guardrails.py`
- 预期失败的测试：
  - 阻止在工作区外写入。
  - 如果策略要求，阻止在工作区外读取。
  - 阻止危险的 shell 命令，如 `rm -rf /`。
  - 允许工作区内的安全命令。
- 验证：
  - `python -m pytest tests/test_guardrails.py`
- 提交：
  - TODO

---

## 任务 9：反馈传感器

- 状态：[ ]
- 依赖：
  - 任务 7
- 目标：实现测试反馈传感器和失败分类。
- 文件：
  - `src/hancode/feedback.py`
  - `tests/test_feedback.py`
- 预期失败的测试：
  - 分类 pytest 通过的结果。
  - 分类 pytest 失败的结果。
  - 提取有用的错误摘要。
  - 将命令结果转换为反馈报告。
- 验证：
  - `python -m pytest tests/test_feedback.py`
- 提交：
  - TODO

---

## 任务 10：智能体循环

- 状态：[ ]
- 依赖：
  - 任务 5
  - 任务 6
  - 任务 7
  - 任务 8
  - 任务 9
- 目标：实现自包含的智能体循环。
- 文件：
  - `src/hancode/agent_loop.py`
  - `tests/test_agent_loop.py`
- 预期失败的测试：
  - 智能体调用 MockLLM。
  - 智能体解析动作。
  - 智能体在执行工具前运行护栏检查。
  - 智能体调度被允许的动作。
  - 智能体将工具结果反馈到下一轮循环。
  - 智能体在收到 `finish` 时停止。
- 验证：
  - `python -m pytest tests/test_agent_loop.py`
- 提交：
  - TODO

---

## 任务 11：反馈循环机制演示

- 状态：[ ]
- 依赖：
  - 任务 10
- 目标：使用 MockLLM 演示确定性的故障注入和自我修正。
- 文件：
  - `tests/test_feedback_loop_demo.py`
  - `examples/broken_project/`
  - `scripts/demo_feedback_loop.py`
- 预期失败的测试：
  - 第一个 MockLLM 动作引入或保留了一个错误。
  - 反馈传感器报告失败。
  - 第二个 MockLLM 动作在收到反馈后改变行为。
  - 最终反馈通过。
- 验证：
  - `python -m pytest tests/test_feedback_loop_demo.py`
- 提交：
  - TODO

---

## 任务 12：记忆

- 状态：[ ]
- 依赖：
  - 任务 10
- 目标：实现简单的持久化记忆和检索。
- 文件：
  - `src/hancode/memory.py`
  - `tests/test_memory.py`
- 预期失败的测试：
  - 写入记忆条目。
  - 检索相关的记忆条目。
  - 不无条件加载所有记忆。
- 验证：
  - `python -m pytest tests/test_memory.py`
- 提交：
  - TODO

---

## 任务 13：配置

- 状态：[ ]
- 依赖：
  - 任务 8
  - 任务 9
- 目标：实现配置加载。
- 文件：
  - `src/hancode/config.py`
  - `tests/test_config.py`
- 预期失败的测试：
  - 加载工作区路径。
  - 加载允许的工具列表。
  - 加载测试命令。
  - 加载护栏策略。
  - 拒绝无效配置。
- 验证：
  - `python -m pytest tests/test_config.py`
- 提交：
  - TODO

---

## 任务 14：凭据管理

- 状态：[ ]
- 依赖：
  - 任务 13
- 目标：实现安全的凭据管理。
- 文件：
  - `src/hancode/credentials.py`
  - `tests/test_credentials.py`
- 预期失败的测试：
  - 通过抽象层存储凭据。
  - 检查凭据状态而不泄露密钥。
  - 更新凭据。
  - 清除凭据。
  - 回退行为已记录。
- 验证：
  - `python -m pytest tests/test_credentials.py`
- 提交：
  - TODO

---

## 任务 15：命令行界面（CLI）

- 状态：[ ]
- 依赖：
  - 任务 10
  - 任务 13
  - 任务 14
- 目标：实现 CLI 命令。
- 文件：
  - `src/hancode/cli.py`
  - `tests/test_cli.py`
- 预期失败的测试：
  - CLI 显示帮助信息。
  - CLI 可以运行模拟演示。
  - CLI 可以检查凭据状态。
  - CLI 不打印密钥值。
- 验证：
  - `python -m pytest tests/test_cli.py`
- 提交：
  - TODO

---

## 任务 16：Docker 分发

- 状态：[ ]
- 依赖：
  - 任务 15
- 目标：添加基于 Docker 的分发方式。
- 文件：
  - `Dockerfile`
  - `README.md`
  - `.github/workflows/ci.yml`
- 预期失败的测试：
  - Docker 镜像构建成功。
  - 容器可以运行帮助命令。
- 验证：
  - `docker build -t hancode .`
  - `docker run --rm hancode --help`
- 提交：
  - TODO

---

## 任务 17：CI 完成

- 状态：[ ]
- 依赖：
  - 任务 16
- 目标：确保 CI 运行测试、代码检查、类型检查和 Docker 构建。
- 文件：
  - `.github/workflows/ci.yml`
- 预期失败的测试：
  - CI 在测试失败时失败。
  - CI 在干净分支上通过。
- 验证：
  - GitHub Actions 在推送和拉取请求时通过。
- 提交：
  - TODO

---

## 任务 18：最终文档

- 状态：[ ]
- 依赖：
  - 所有实现任务
- 目标：完成最终文档。
- 文件：
  - `README.md`
  - `AGENT_LOG.md`
  - `REFLECTION.md`
  - `SPEC_PROCESS.md`
  - `PLAN.md`
- 实现说明：
  - README 包含安装、运行、凭据设置、分发方式、已知限制。
  - AGENT_LOG 包含按任务记录的过程证据。
  - REFLECTION 由学生撰写。
- 验证：
  - 文档完整。
  - 没有真实的凭据存在。
  - 最终测试套件通过。
- 提交：
  - TODO