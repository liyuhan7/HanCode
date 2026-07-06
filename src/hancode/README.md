# 源代码目录

实现代码仅在以下条件满足后才会添加：

1. `SPEC.md` 已完成。
2. `PLAN.md` 已完成。
3. 冷启动验证已完成。
4. 初始实现任务已批准。

最终的框架内核将包括：

- 智能体循环（agent loop）
- LLM 抽象层
- 动作解析器（action parser）
- 工具调度器（tool dispatcher）
- 护栏（guardrails）
- 反馈传感器（feedback sensors）
- 记忆（memory）
- 配置（configuration）
- 凭据管理（credential management）
- 命令行界面（CLI）