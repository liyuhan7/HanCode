# 源代码目录

实现代码仅在以下条件满足后才会添加：

1. `SPEC.md` 已完成。
2. `PLAN.md` 已完成。
3. 冷启动验证已完成。
4. 初始实现任务已批准。

最终的课程项目 Harness 内核将包括：

- WorkspaceSpec / WorkspaceRouter
- Phase Mode / Phase Gate
- ContextBuilder
- ToolRegistry / ToolPolicy
- TraceLogger
- CheckpointManager / Rollback
- AgentLoop
- LLM 抽象层 / MockLLM
- Feedback sensors
- Knowledge Delivery
- Credential management
- CLI

这些模块必须由 HanCode 自己实现，不能依赖现成 agent framework 的高层循环。
