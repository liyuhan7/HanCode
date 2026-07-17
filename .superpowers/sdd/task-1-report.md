# T21-R1 Task 1 实施报告

## 改动

- `src/hancode/file_tools.py`：扩展 `.env`、`credentials`/`secrets` 等目录和常见 key/token/certificate 文件名的统一拒绝；`write_file` 改为同目录临时文件 + `os.replace` 原子替换，失败时清理临时文件并保留旧目标字节。
- `src/hancode/workspace.py`：新任务从项目配置读取 `retry_budget`；`_is_link` 增加 Python 3.11 可用的 Windows reparse-point 属性检测。
- `src/hancode/checkpoints.py`：在快照目录创建前按 `max_checkpoints_per_task` fail-closed，返回 `checkpoint_limit_exceeded`。
- `src/hancode/trace.py`：在追加写入前按 `max_trace_events` fail-closed，返回 `trace_event_limit_exceeded`。
- `tests/`：新增上述行为的确定性回归测试；`docs/AGENT_LOG.md` 添加记录。

## TDD 证据

先新增 10 个测试并运行，观察到 `10 failed`：凭据路径未拦截、原子替换依赖未接入、retry 仍硬编码 2、checkpoint/trace 上限未拒绝。随后实现最小代码；专项测试转绿。

## 验证命令与真实输出

- `uv run --extra dev pytest tests/test_file_tools.py tests/test_workspace.py tests/test_checkpoints.py tests/test_trace.py -q`：`133 passed, 6 skipped`。
- `uv run --extra dev ruff check src/hancode/checkpoints.py src/hancode/config.py src/hancode/file_tools.py src/hancode/trace.py src/hancode/workspace.py tests/test_checkpoints.py tests/test_file_tools.py tests/test_trace.py tests/test_workspace.py`：`All checks passed!`。
- `uv run --extra dev mypy src/hancode/checkpoints.py src/hancode/config.py src/hancode/file_tools.py src/hancode/trace.py src/hancode/workspace.py`：`Success: no issues found in 5 source files`。
- 全量 `uv run --extra dev pytest -q`：`542 passed, 9 skipped, 3 failed`。失败为既有/并行变更相关：`tests/test_course_file_protection.py` 两个只读保护流程使用会抛断言的 `StubTraceAppender`，实际返回 `trace_write_failed` 而非原断言的 `policy_denied`；另一个 `test_config_loads_defaults` 因暂时扩展默认 protected patterns，已在本任务中恢复，单测复验通过。

## 剩余风险

- 全量测试的两个 course-file protection trace stub 失败尚未在本任务范围内改动 AgentLoop；需由主任务整合时判断是否属于并行基线问题。
- FileTools 为无 config 参数 API，额外常见凭据文件名规则与项目自定义 `protected_patterns` 不会自动同步；现有默认策略覆盖范围已保持兼容。
- 仍未实现 checkpoint pruning、edit/run 工具、trace 并发锁和 pending checkpoint 恢复（均为 T21-R1 其他任务范围）。

## 提交

- `b91ed75`（实现提交；本报告/AGENT_LOG 哈希回填作为后续文档提交）。
