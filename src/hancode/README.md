# `hancode` 源代码

这里是 HanCode Harness 内核的 Python 实现目录。当前工作树对应 M4，已经完成
T1-T18 中的基础骨架、最小 AgentLoop、Tool Governance 与可恢复状态机制；后续任务会继续
补充反馈闭环、交付产物、凭据管理和 CLI。

## 当前已实现

### 基础骨架

- `models.py`：共享数据模型、Phase、TaskStatus 和 Action 相关类型。
- `errors.py`：结构化错误类型和错误码。
- `config.py`：项目配置加载与默认课程文件保护规则。
- `workspace.py`：Project Workspace / Task Workspace 初始化和目录边界。
- `state.py`：以 `state.json` 为唯一机器状态源的任务状态存储。
- `phases.py`：`spec -> plan -> code -> test -> review -> deliver` 阶段枚举和门禁。
- `router.py`：依据任务状态、产物和测试结果选择下一阶段。

### Agent Loop 基础

- `actions.py`：Action schema 和 ActionParser。
- `llm.py`：可注入的 LLM 抽象与 MockLLM。
- `agent_loop.py`：固定执行 `context -> LLM -> parse -> policy -> tool -> feedback`
	的最小受控循环。

### Tool Governance

- `tools.py`：统一 `ToolResult` 和确定性 `ToolRegistry` 分发。
- `file_tools.py`：带 project-root containment 和基础脱敏的文件读写、列表和文本搜索。
- `path_policy.py`：将路径分类为 `protected`、`artifact`、`source` 或 `out_of_scope`。
- `tool_policy.py`：依据 Phase、TaskState 和路径区域评估工具调用，默认拒绝越界或
	受保护写入。

### 可恢复状态

- `trace.py`：以连续 `seq` / `event_id` 追加脱敏的 task trace。
- `checkpoints.py`：创建与提交 SOURCE checkpoint，并在 review phase 通过
	`rollback_last_checkpoint()` 恢复最近的 committed checkpoint。
  rollback 会复核 task/project/manifest 身份、SOURCE 路径、快照与 after hash；外部修改、
  protected 路径、链接逃逸或 inconsistent state 均 fail-closed。多文件恢复及其
  manifest/state/trace 持久化采用补偿语义，补偿失败将任务标记为 `inconsistent`。

## 当前边界

当前版本已经提供可独立测试的 Tool Governance 与可恢复状态基础，但以下能力仍按
`docs/PLAN.md` 的后续任务推进：

- ContextBuilder、FeedbackBuilder 与 retry / rollback 集成。
- `TEST_REPORT.md`、`REVIEW.md`、`KNOWLEDGE.md` 和 `DELIVERABLES.md` 生成。
- CLI、CredentialProvider、package build 和 CI 分发流程。

因此，当前目录还不是完整的最终 Harness 入口；不要从本目录 README 推断尚未
实现的 CLI 或交付流程已经可用。

## 设计约束

- 核心机制由 HanCode 自己实现，不依赖 LangChain、AutoGen、CrewAI、LlamaIndex
	agent runner 或宿主 Coding Agent 的高层循环。
- 核心测试使用 MockLLM、临时 workspace 和可注入的工具实现，不依赖网络、真实
	LLM 或 API key。
- 工具失败返回结构化 `ToolResult` 或策略决策，不直接向用户暴露原始异常内容。
- 路径检查采用 canonical path 和 fail-closed 语义；课程文件、凭据文件和 Harness
	状态文件不能通过普通 source write 修改。
- `state.json` 是状态机的机器真相；Markdown 产物用于人类阅读和交付，不作为唯一
	状态源。

## 验证

在仓库根目录运行：

```powershell
$env:PYTHONPATH = "src"
uv run --no-sync pytest -p no:cacheprovider
uv run --no-sync ruff check src tests
uv run --no-sync mypy src
```

M4 在当前 Windows 环境的已知情况：symlink 相关场景可能因为系统权限被跳过；
需要在允许创建文件 symlink 的 CI 或主机上复验 canonical-path 分支。
