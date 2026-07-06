# 测试

根据 TDD（测试驱动开发）原则，测试将在实现代码之前编写。

最终的测试套件必须包含针对以下内容的确定性模拟 LLM 测试：

- 智能体循环（agent loop）
- 工具调度（tool dispatch）
- 护栏拦截（guardrail interception）
- 反馈循环（feedback loop）
- 记忆（memory）
- 停止条件（stop conditions）
- 凭据处理（credential handling）
- 命令行界面行为（CLI behavior）