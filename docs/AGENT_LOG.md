# 智能体活动日志

本文件记录所有重要的智能体辅助开发活动。

## 日志格式

每条记录应包含：

- 时间戳
- 任务 ID
- 使用的 Superpowers 技能
- 使用的智能体
- 关键提示词 / 上下文
- 智能体输出摘要
- 提交哈希 / PR 链接
- 人工干预
- 经验教训

---

### 2026-07-18 — T28 — P0 分层结构重组与装配层抽取

- 使用的技能：未使用 `using-superpowers`；按任务卡执行 TDD、兼容迁移和验证。
- 使用的智能体：OpenAI Codex。
- 关键提示词 / 上下文：用户要求只做结构重组和装配层抽取；采用 `storage/`、`tooling/`、`providers/` 等实际包名避开既有平铺文件同名冲突；不重写 AgentLoop、ToolPolicy、Checkpoint、Trace、State 业务逻辑，不引入真实网络 Provider。
- TDD Red：新增 `tests/test_structure_layers.py` 后专项为 6 failed，失败集中在新包缺失、engine 缺失和 Demo 没有 engine factory。
- 实现摘要：
  - 将 core、runtime、policy、storage、tooling 模块迁入分层包，内部 import 改为新路径。
  - 旧平铺模块改为指向新实现的兼容别名；`test_tools.py` 保留普通 re-export，避免 pytest 将兼容源文件识别为导入路径不一致的测试模块。
  - 将 `llm.py` 拆为 `providers/base.py`、`providers/mock.py`，新增 mock-only factory、确定性 prompt 序列化和 action schema 适配。
  - 新增 `runtime/engine.py`，支持默认 filesystem 装配及 provider、registry、trace、max steps 等测试/demo 注入；Demo 改用 engine factory。
  - 将 CLI 实现迁入 `interfaces/cli.py`，旧 `cli.py` 保留入口代理。
- Green：结构专项 `6 passed`；全量 pytest `730 passed, 13 skipped`。
- 验证：Ruff `All checks passed!`；MyPy `Success: no issues found in 61 source files`；compileall、`uv build` 和 `git diff --check` 均通过；`uv build` 日志确认七个新分层包进入 sdist / wheel；`hancode --help`、`hancode demo --provider mock`、`hancode auth status --provider mock` 和临时目录 `hancode init` 均返回成功。
- 提交：未提交，用户未要求创建提交。
- 人工干预：根据用户计划选择 `storage/`、`tooling/` 和保留平铺 delivery/demo 的 P0 范围；明确 P1/P2 延后。
- 经验教训：同名旧模块与新包迁移时，单纯 `from ... import *` 无法保留旧模块级 monkeypatch；模块别名能保持实现身份，但 pytest 收集 `test_tools.py` 时必须使用普通 re-export 保留旧 `__file__`。
- 剩余风险：P1 `app/`、P2 `demo_support/` / `delivery_support/` 尚未拆分；真实远程 Provider 仍未实现。

---

### 2026-07-18 — T29 — P1 应用服务层拆分

- 使用的技能：未使用 `using-superpowers`；按任务卡执行 TDD、兼容迁移和验证。
- 使用的智能体：OpenAI Codex。
- 关键提示词 / 上下文：只抽取应用编排，不改现有 workspace、engine、credential、export 和 CLI public behavior；保留 CLI 的 `credential_provider`、project service 和 delivery service 注入点。
- TDD Red：新增 app 层契约测试后，收集阶段因 `hancode.app` 不存在得到预期 `ModuleNotFoundError`。
- 实现摘要：新增 `ProjectService`、`TaskService`、`AuthService`、`DeliveryService`，分别封装 workspace 初始化、engine run、显式凭据 provider 和 artifact export；`interfaces/cli.py` 改用 Project/Auth/Delivery service。
- 验证：`tests/test_app_layers.py tests/test_cli.py` 通过；后续全量 pytest `741 passed, 13 skipped`，Ruff、MyPy 和 CLI smoke 通过。
- 提交：未提交，用户未要求创建提交。
- 人工干预：未新增 CLI 命令，TaskService 保留为可注入应用 API，不把 task run 暴露为新的 CLI 行为。
- 经验教训：AuthService 必须每次从当前模块级 `credential_provider` 建立门面，才能同时支持 CLI 旧 monkeypatch 和显式依赖注入。
- 剩余风险：真实远程 Provider 仍未实现，属于既有 P0 非目标。

---

### 2026-07-18 — T30 — P2 Demo 与 Delivery 支持包拆分

- 使用的技能：未使用 `using-superpowers`；按任务卡执行 TDD、兼容迁移和验证。
- 使用的智能体：OpenAI Codex。
- 关键提示词 / 上下文：只改变代码布局和 import；必须保持 Delivery Markdown、DeliveryResult、Demo action、fixture digest、trace/state/checkpoint、package data 和旧模块级 monkeypatch 行为。
- TDD Red：新路径契约测试初次运行时，`delivery_support` / `demo_support` 导入均因包不存在而失败。
- 实现摘要：
  - 将 Delivery 核心实现迁入 `delivery_support/result.py`，在 `reports.py`、`review.py`、`knowledge.py`、`deliverables.py` 提供职责化入口；旧 `delivery.py` 别名到同一实现并保留 monkeypatch 语义。
  - 将 Demo runner 迁入 `demo_support/runner.py`，action 序列迁入 `actions.py`，fixture 校验/复制/配置迁入 `fixture.py`；旧 `demo.py` 别名到 runner。
  - 新增 `tests/test_app_layers.py` 覆盖 P1/P2 import、身份、服务注入和 action 确定性。
- Green：P1/P2 专项与现有 CLI、Delivery、Demo 回归通过；全量 pytest `741 passed, 13 skipped`。
- 验证：Ruff `All checks passed!`；MyPy `Success: no issues found in 76 source files`；compileall、`uv build`、`git diff --check` 通过；build 日志确认 `app`、`delivery_support`、`demo_support` 进入 sdist/wheel；`hancode --help`、`hancode demo --provider mock`、`hancode auth status --provider mock` 返回成功。
- 提交：未提交，用户未要求创建提交。
- 人工干预：保留旧 Delivery/Demo 文件为模块别名；没有删除旧入口或引入新的 CLI 命令。
- 经验教训：对结构迁移而言，旧模块必须别名到实际实现模块；否则现有测试对 `save_state`、`_is_link`、registry 和 knowledge 的 monkeypatch 会失效。
- 剩余风险：Delivery 专项中的 13 个平台相关 skip 仍需在具备 symlink 权限的 CI 环境复验；真实远程 Provider 不在本轮范围。

---

### 2026-07-13 — M3 CI 回归 — search_text 凭据 symlink alias

- 问题：Linux CI 的 symlink 场景中，`search_text` 同时报告真实 `.env` 和指向它的 alias；预期只报告 alias。
- 根因：遍历 canonical 路径时，真实凭据文件和 alias 都进入 `skipped_files`，缺少按 canonical 目标去重。
- 修复：在 `src/hancode/file_tools.py` 中记录凭据文件的 canonical 路径；存在非凭据 alias 时隐藏真实凭据路径，没有 alias 时保留原有凭据跳过记录。
- 验证：FileTools 专项 `29 passed, 2 skipped`；Windows 本机因 symlink 权限跳过 alias 用例，需由 Linux CI 复验。

---

## 记录条目

### 2026-07-17 — T21-R1 Task 1 — 安全边界与资源上限

- 使用的技能：test-driven-development。
- 使用的智能体：OpenAI Codex。
- 摘要：FileTools 统一拒绝凭据目录、`.env` 变体和常见密钥/证书文件；新任务读取项目 `retry_budget`；checkpoint 与 trace 达到配置上限时 fail-closed；普通 `write_file` 使用同目录临时文件原子替换；workspace 识别 Python 3.11 Windows reparse point。
- 验证：专项 `tests/test_file_tools.py tests/test_workspace.py tests/test_checkpoints.py tests/test_trace.py` 为 `133 passed, 6 skipped`；Ruff 通过；5 个生产源文件 MyPy 通过。全量曾得 `542 passed, 9 skipped, 3 failed`，其中 2 项为既有 course-file protection trace stub 行为，已记录于任务报告。
- 提交：`b91ed75`（实现提交；本报告/日志回填为后续文档提交）。

---

### 2026-07-17 — T21-R1 Task 2 — 错误优先级与生命周期审计事件

- 使用的技能：test-driven-development。
- 使用的智能体：Claude Opus。
- 背景：Task 1 全量测试遗留 `3 failed`，其中 2 项为 course-file protection trace stub 用例——它们断言"trace 后端完全不可用时，受保护写入仍必须以 `policy_denied` 为主错误被拒"，而 AgentLoop 旧实现让 `trace_write_failed` 覆盖了 `policy_denied`。
- 修复（均 TDD：先失败测试后最小实现）：
  - 错误优先级（对齐修复边界"policy denial 保留为主错误；trace 写失败作为审计风险"）：在**已有既存主错误**的两个平行分支——`policy_denied` 与 `action_parse_failed`——写 trace 失败时，保留业务主错误（policy 拒绝 / 解析错误），trace 失败降级为 `Risk(level="medium")` 附加到结果，仍 fail-closed 不派发工具。新增 `_trace_failure_risk()` 辅助函数与 `test_policy_denial_keeps_primary_error_when_trace_write_fails`、`test_parse_error_keeps_primary_error_when_trace_write_fails`。其余 trace 点（tool_called / source_write_authorized / checkpoint 等变更关卡，及 tool_failed / test_failed / retry_budget_consumed 等无既存业务主错误的点）维持原 fail-closed 语义未改。
  - 生命周期审计事件：补 `phase_started`（阶段切换时，单阶段内不重复）、`phase_completed`（FINISH_PHASE 成功后）、`run_completed`（路由判定 completed 时，含循环内与循环末两条路径）。新增 `test_lifecycle_events_bracket_a_finished_phase`、`test_run_completed_event_is_emitted_on_router_completion`。
  - 失败语义分层：纯审计标记点（phase_started/phase_completed/run_completed/policy_denied）trace 写失败降级为 risk 累加、不掩盖主错误/结果；变更与工具执行点（tool_called、source_write_authorized、checkpoint）保持 fail-closed BLOCK 不变，作为"无未审计变更"的安全底线。用运行内 `pending_risks` 累加器 + `_result` 闭包自动合并 risks。
  - 回归测试同步：更新 `test_agent_loop_result_preserves_non_state_port_boundaries`、`GappedTraceAppender` 注入点、`test_failed_test_retries_through_review_then_decrements_once_on_retry_write` 的精确 trace 序列以反映新增生命周期事件。
- 验证：全量 `uv run pytest -q -p no:cacheprovider` 为 `548 passed, 9 skipped`（较 Task 1 的 3 failed，2 项 course-file protection 转绿，无新增红）；`ruff check src tests --no-cache` 通过；`mypy src` 19 文件无错误；`git diff --check` 干净。
- 同步文档：`PLAN.md` 收窄 T21-R1 非目标句（原"完整生命周期事件矩阵不在本卡内"改为记录已追加 phase/run 生命周期事件、仅 context/action 级矩阵仍不重构），标注组2工具待实现风险（接真实 registry 时 `edit_file` / `run_tests` 会命中 `tools.py:44` "Tool is not registered."）；`系统架构.md` §10A.2 将 reconcile 的 committed checkpoint 快照校验与 pending checkpoint 自动回滚标记 aborted 标注为"未实现 / post-MVP"，与 `reconcile_state()` 仅做 artifact 漂移检测的实现现状对齐。
- 审计条目核对说明：
  - 组3所列"test_trace.py:218 固化反向行为需改"经核实为**行号误标**——该用例测的是 `trace.py::append_trace()` 底层原语契约（写文件失败必须抛 `HanCodeError`），是 loop 层错误优先级决策与 fail-closed 关卡的前提，不能改。真正固化反向行为的是 `test_course_file_protection.py` 两个用例，本批 A 改动后已自动转绿。
  - H① / H② 目标文本在当前仓库不存在：全仓无 `trace_limit_exceeded` 错误码（代码为 `trace_event_limit_exceeded`，PLAN 未写该码，无不一致）、所有 `.md` 无 `journal` 措辞。未做无依据的"修正"。
- 剩余风险 / 非目标（本批未实现，留待后续任务）：
  - 组2内置工具（`edit_file` 恰好一次匹配 + 原子写入、`run_tests` 仅执行配置命令且禁止 `shell=True`、默认工具装配工厂）仍未实现——`tools.py` 当前只提供 `ToolRegistry` dispatch 骨架；接真实 registry 前 `edit_file` / `run_tests` 会在 `tools.py:44` 返回 "Tool is not registered."，仅测试 stub 可用。
  - PathClassifier / config 保护模式已覆盖 `*.key` / `*.pem`；证书类扩展（如 `*.crt` / `*.cer`）与无扩展名、`.pdf`、`requirements.txt` 的分类扩展未在本批处理。
  - pending checkpoint 恢复的完整分支覆盖仍依赖 T21 既有 resume 通道；未新增跨会话 observation 重放。
- 提交：待用户决定。

---

### 2026-07-13 — T16 — TraceLogger

- 使用的技能：karpathy-guidelines；test-driven-development；verification-before-completion。
- 使用的智能体：OpenAI Codex。
- 关键提示词 / 上下文：
  - 在 `feature/M4` worktree 实现 T16；用户确认函数式设计，TraceLogger 负责分配 `event_id` 和 `seq`。
  - 仅新增 `trace.py` 与 `test_trace.py`，并回填 PLAN / AGENT_LOG；不改 AgentLoop、ToolPolicy、CheckpointManager 或 history summary。
- 摘要：
  - 新增不可变 `TraceEvent` 与 `append_trace()`；事件追加到 task root 的 `trace.jsonl`，并以最后一条合法事件计算连续 `seq` 及 `evt-000001` 格式 ID。
  - 对 action、observation、state transition 执行递归复制式脱敏；Authorization、api_key、token、secret、password、credential、private_key 等字段只记录 `[REDACTED]`，字符串超过 4096 字符截断为 `...[TRUNCATED]`。
  - 损坏 trace 或无效既有编号返回 `trace_parse_error`；追加失败返回 `trace_write_error`，不回显底层异常内容。后续高风险调用链可将该错误作为阻断信号。
- 逐项 TDD 证据：
  - Red：先因 `hancode.trace` 不存在得到 `ModuleNotFoundError`；随后编号测试断言第二条仍为 `evt-000001`，安全测试发现假 secret 与完整 4097 字符内容出现在 JSONL，异常测试暴露原始 `JSONDecodeError` / `OSError`，编号完整性测试确认无效末条事件未被拒绝。
  - Green：最小实现分别补齐追加、序号、脱敏截断、结构化错误与编号校验；最终专项为 `8 passed in 0.13s`。
- 验证：
  - `ruff check src/hancode/trace.py tests/test_trace.py --no-cache`：通过。
  - `mypy src/hancode/trace.py`：`Success: no issues found in 1 source file`。
  - 全量 pytest：`354 passed, 4 skipped in 5.14s`；全量 ruff：通过；全量 mypy：`Success: no issues found in 16 source files`。
- 环境备注：受限 sandbox 无法创建 pytest 临时锁文件，且 `uv run --extra dev` 的 editable 构建临时目录被拒绝访问；使用 `$env:PYTHONPATH='src'` 加 `uv run --no-project --with ...` 并在本机环境运行同一测试命令取得验证证据。
- 提交：本任务提交（见 `git log`）。
- 剩余风险：MVP 已逐行验证 task 内历史后分配序号，但尚未实现并发 writer lock、`fsync` 或崩溃后半行恢复；这些与实际 AgentLoop / 高风险工具调用链集成均属于后续任务。

#### 第一阶段评审修正

- 新鲜独立评审发现：仅检查末行会允许中间损坏、重复 ID 或倒退序号的历史继续追加；字符串型凭据和 JSON 编码异常仍可能泄露原始异常；tool 事件字段与 task ID 未验证。
- 修正：追加前逐行验证完整历史的连续 `seq` 与 `event_id`；将 JSON 序列化失败转为 `trace_write_error`；对全部字符串键值形式的敏感文本脱敏；要求 tool action 的名称、参数、原因和 policy decision，要求失败工具事件携带错误摘要，并绑定 task ID 与 task root。
- 验证：新增 7 项回归后 `tests/test_trace.py` 为 `15 passed in 0.23s`；全量为 `361 passed, 4 skipped in 2.65s`；ruff 全仓通过；mypy `src` 为 `Success: no issues found in 16 source files`。

#### 第二阶段安全/质量评审修正

- 新鲜独立评审发现：cookie、AWS access key 和无键名 Bearer token 能绕过原始脱敏；历史 task ID、task-root 布局、tool policy decision/状态与非字符串运行时输入未被充分验证。
- 修正：扩展字段和文本型凭据脱敏；逐行校验历史 task ID；限制 task root 为 `.hancode/tasks/<task_id>`；要求完整 policy decision 与受限工具状态；将非字符串 mapping key 规范化为字符串，并将非字符串 error summary 转为 `invalid_trace_payload`。
- 范围判断：评审提出的并发 writer lock、`flush/fsync` 和进程崩溃半行恢复确有审计耐久性价值，但 `docs/PLAN.md` 将单 task 单活跃 runner 明确列为 post-MVP，且 T16 只承诺单进程函数式 JSONL MVP；本任务不提前实现并发/耐久化机制，保留为后续风险。
- 验证：新增 7 项回归后 `tests/test_trace.py` 为 `22 passed in 0.32s`；最终全量为 `368 passed, 4 skipped in 2.54s`；ruff 全仓通过；mypy `src` 为 `Success: no issues found in 16 source files`。
- Re-verdict 修正：第二阶段代理继续发现受保护短文本仍会原样进入 trace、伪造 `.hancode/tasks/` 布局可通过、非 Mapping payload 会抛原始异常，且 tool event status 与 event type 不一致仍可落盘。所有内容字段现只记录 `[CONTENT_OMITTED]` 与长度；task root 还必须存在有效 `project.json`；payload、policy 字段及工具状态均 fail-closed。
- 最终 Re-verdict 修正：字段名别名（如 `file_content`、`tool_output`、`response_body`）由精确匹配改为规范化前缀/后缀匹配，嵌套内容同样摘要化。
- 最终验证：新增 7 项回归后 `tests/test_trace.py` 为 `29 passed in 0.43s`；全量为 `375 passed, 4 skipped in 3.92s`；ruff 全仓通过；mypy `src` 为 `Success: no issues found in 16 source files`。
- 第二阶段最终 re-verdict：无 Critical、Important 或 Minor；字段别名及嵌套内容摘要、项目 metadata、payload 与工具审计契约均已关闭。并发 writer lock、`fsync` 与崩溃半行恢复仍为已记录的 post-MVP 非目标。

#### 文档收尾（2026-07-13）

- 按 T16 收尾要求只修改文档，不运行测试、不修改 `src/hancode/`。
- `docs/PLAN.md`：补齐完整函数式接口、29 项实际测试名称、最终验证记录、T16 实现边界、FR-8 `[x]` 状态和实现提交 `df39f8c`。
- `docs/系统架构.md`：移除与当前实现不一致的 `schema_version` / `LAST_ERROR` / 旧事件示例，统一为 `seq`、`evt-{seq:06d}`、内容摘要、项目 metadata 校验和结构化错误契约。
- 文档核验：检查 T16 引用、过时事件格式、占位接口和明显笔误；本轮按用户要求未运行测试。

### 2026-07-13 — T17 — CheckpointManager

- 使用的技能：karpathy-guidelines；test-driven-development；systematic-debugging；requesting-code-review；receiving-code-review；verification-before-completion。
- 使用的智能体：OpenAI Codex；第一阶段新鲜契约审查子代理；第二阶段新鲜安全/持久化审查子代理。
- 已实现：
  - 新增函数式 `CheckpointFile` / `CheckpointManifest`、`create_checkpoint()` 与 `commit_checkpoint()`；通过 state 序列生成 `ckpt-NNN`，支持既有 SOURCE 文件与新建 SOURCE 目标的 before/after hash 生命周期。
  - 创建使用临时 checkpoint 目录后 rename；state 或 trace 失败时恢复 state、删除 checkpoint，无法补偿时返回 `checkpoint_compensation_failed`。
  - manifest、快照、checkpoint 根/临时目录均验证 task 边界；拒绝外链 symlink/junction、篡改 ID/project/schema、非法状态、快照缺失/逃逸/哈希不匹配、非法 after hash 和 PROTECTED 路径。
  - manifest reason 与 trace reason 均脱敏敏感赋值和 Bearer token；创建/提交分别写 `checkpoint_created` / `checkpoint_committed`。
- TDD 与审查：
  - Red：最初因 `hancode.checkpoints` 不存在得到 `ModuleNotFoundError`；审查后新增 state/trace 补偿、manifest 篡改、before snapshot 完整性、symlink 边界和 reason 脱敏回归。
  - 第一阶段审查曾发现失败补偿、初始原子发布、manifest 信任边界和 before snapshot 可恢复性缺口；逐项补测试与修复后通过。
  - 第二阶段审查曾发现 `files/`、manifest 链接边界、reason secret 落盘和 after hash 格式缺口；逐项静态复审后无 Critical/Important，结论可合入。
- 验证：
  - 沙箱外专项 `tests/test_checkpoints.py` 为 `40 passed, 4 skipped in 1.93s`；4 个 skip 均因当前 Windows 环境不允许创建文件 symlink。
  - 沙箱外全量 pytest 为 `415 passed, 8 skipped in 5.10s`。
  - Ruff 输出 `All checks passed!`；MyPy `src/hancode/checkpoints.py` 为 `Success: no issues found in 1 source file`；`git diff --check` 通过。
  - 首次全量复验暴露 `tests/test_course_project_scaffold.py` 仍要求 PLAN 保留 `test_edit_file_creates_checkpoint`；已在 T17 测试清单中补回该兼容名称，修复后全量通过。
- 提交：未提交；T17 已完成验证，是否提交由用户决定。
- 剩余风险：T18 rollback、T21 自动调度、跨进程锁/TOCTOU、pending crash reconcile 与 pruning 均不在 T17 范围。

### 2026-07-13 — T18 — RollbackManager

- 使用的技能：karpathy-guidelines；test-driven-development；systematic-debugging；requesting-code-review；verification-before-completion。
- 使用的智能体：OpenAI Codex；第一阶段新鲜契约审查子代理；第二阶段新鲜安全/持久化审查子代理。
- 已实现：
  - 在 `checkpoints.py` 新增冻结的 `RollbackResult` 与函数式 `rollback_last_checkpoint()`；仅允许在一致的 review state 中恢复最新、同 task / project、已提交且可回退的 code checkpoint。
  - manifest 生命周期扩展为 `pending -> committed -> rolled_back`；成功回退后保留 checkpoint 序列和 retry budget，重置 review 后的测试/代码完成标记，并写入开始与结果 trace。
  - 所有 identity、snapshot、PathClassifier、symlink/junction 与 after hash 校验均在写入前完成；冲突或读取错误返回 `blocked`，零业务文件写入。
  - 多文件、manifest、state 与 trace 任一持久化失败均做反向补偿；补偿失败将 state 标记为 `inconsistent`。文件恢复使用同目录、独占创建的随机临时文件，避免预置路径或链接重定向。
- TDD 与两阶段审查：
  - Red：从缺少 rollback 导入开始，再逐项覆盖生命周期、状态复位、冲突、路径/链接边界和补偿。
  - 阶段一发现 after-hash 预检读取错误被误报为 `failed`；已改为 `rollback_conflict` 的 `blocked` 结果并复核通过。
  - 阶段二发现可预测临时路径的链接绕过、inconsistent state 仍可执行回退、以及补偿后结果仍虚报已恢复文件；均以最小代码和回归测试修复，复核后无 Critical/Important。
- 验证：
  - `tests/test_rollback.py tests/test_checkpoints.py` 为 `62 passed, 5 skipped`。
  - 全量 pytest 为 `437 passed, 9 skipped in 8.33s`；9 个 skip 均因当前 Windows 环境不允许创建文件 symlink。
  - Ruff 输出 `All checks passed!`；MyPy 输出 `Success: no issues found in 17 source files`；`git diff --check` 通过。
- 提交：未提交；T18 已完成验证，是否提交由用户决定。
- 剩余风险：Windows 上链接分支仍需在可创建 symlink 的 CI/主机复验；跨进程锁、TOCTOU 完全消除、pending crash reconcile、pruning 与 T21 自动调度不在 T18 范围。

### 2026-07-12 — T15 — 课程文件保护

- 使用的技能：test-driven-development；systematic-debugging。
- 使用的智能体：OpenAI Codex（T15 实现代理）；控制代理负责提交与最终验证。
- 关键提示词 / 上下文：
  - T15 只扩展默认保护模式与受保护写入的结构化反馈；PathClassifier 仍是唯一分类来源，ToolPolicy 仍是唯一写策略评估器。
  - 不新增策略类、HITL 覆盖、删除工具、trace/checkpoint 机制或启发式文件名扫描；不变更 `PathClassifier.classify()` 与 `ToolPolicy.evaluate()` 的公开签名。
- 摘要：
  - `src/hancode/config.py` 为 assignment、requirements、rubric、course_constraints、教师测试、评分脚本、样例、`.env`、credentials 与 secrets 保留基线模式，并补充对应 `**/` 嵌套路径模式；未使用宽泛的 `requirements*`。
  - `src/hancode/tool_policy.py` 保持 `denied_rule="protected_path"`，并将 protected write 的 message 与 suggested_fix 收敛为课程/凭据保护的固定反馈。
  - 新增 `tests/test_course_file_protection.py`，以真实 ToolPolicy 加类型安全测试适配器验证各课程文档、嵌套路径、大小写/反斜杠、protected 优先于 writable root，以及空内容 `write_file` 与 `edit_file` 在 AgentLoop 中均不触发 registry dispatch。
- 逐项 TDD 证据：
  - Red：`$env:PYTHONPATH='src'; $env:UV_CACHE_DIR=Join-Path $env:TEMP 'hancode-uv-cache'; uv run --no-sync pytest tests/test_config.py tests/test_path_classifier.py tests/test_tool_policy.py tests/test_agent_loop.py tests/test_course_file_protection.py -v -p no:cacheprovider` 在沙箱外得到 `23 failed, 109 passed, 2 skipped in 5.76s`，失败原因是新默认保护模式和反馈尚未实现。
  - Green：最小实现后同一命令得到 `132 passed, 2 skipped in 1.25s`。
  - MyPy 修正：首次静态检查发现 frozen `PolicyDecision` 不满足 AgentLoop 需要可写字段的 `PolicyDecisionLike` Protocol；测试改用真实 ToolPolicy 的字段复制适配器，没有放宽生产类型。随后 `uv run --no-sync mypy src/hancode/config.py src/hancode/tool_policy.py tests/test_course_file_protection.py --cache-dir (Join-Path $env:TEMP 'hancode-mypy-cache-t15')` 输出 `Success: no issues found in 3 source files`。
- 评审与范围：
  - 自审确认仅修改默认模式、既有 protected-path 文案与对应测试；没有修改 PathClassifier、ToolPolicy 的公开签名或引入非目标机制。
  - `uv run --no-sync ruff check src/hancode/config.py src/hancode/tool_policy.py tests/test_config.py tests/test_tool_policy.py tests/test_agent_loop.py tests/test_course_file_protection.py` 输出 `All checks passed!`，`git diff --check` 通过。
  - 全量回归随后发现 `tests/test_course_project_scaffold.py` 仍断言已被 T14 计划替换的 `test_edit_file_requires_reason` 与 `test_disabled_tool_is_denied`。该后续修复仅将断言更新为当前计划中的 `test_defensively_denies_write_without_reason` 与 `test_denies_tool_not_allowed_in_phase`，并保留既有的 SPEC 语义检查；这不是全量回归通过的声明。
  - 该回归修复验证：`$env:PYTHONPATH='src'; $env:UV_CACHE_DIR=Join-Path $env:TEMP 'hancode-uv-cache'; uv run --no-sync pytest tests/test_course_project_scaffold.py::test_edit_file_requires_reason tests/test_course_project_scaffold.py::test_tool_not_allowed_in_workspace_is_denied -p no:cacheprovider` 输出 `2 passed in 0.05s`；同环境下 `uv run --no-sync pytest tests/test_course_project_scaffold.py -p no:cacheprovider` 输出 `18 passed in 0.06s`。
  - 第二阶段审查发现 assignment、requirements、rubric、course_constraints 的无扩展名或非 Markdown 变体在可写根下仍会归为 source。人工选择扩展保护范围后，规则改为精确基名、`基名.*` 与目录模式：`requirements.txt` 受保护，`requirements-lock.txt` 等前缀变体不因该规则受保护。
  - 该范围扩展 TDD：先将无扩展名、`.pdf` 与 `requirements.txt` 加入真实 PathClassifier 测试，得到 `10 failed, 6 passed in 0.45s`；最小模式扩展后，`tests/test_config.py tests/test_course_file_protection.py` 为 `69 passed in 1.39s`。
  - 第二阶段复审确认扩展规则关闭绕过面；按其 Minor 建议补充 `requirements-lock.txt` 与嵌套同类路径的负向分类回归，专项为 `2 passed in 0.10s`，固化“精确基名而非前缀匹配”的边界。
  - 最终验证：`uv run --no-sync pytest -p no:cacheprovider` 为 `346 passed, 4 skipped in 3.35s`；Ruff 全量输出 `All checks passed!`；MyPy 全量输出 `Success: no issues found in 15 source files`；`git diff --cached --check` 通过。4 个 skip 均为当前 Windows 环境不允许创建文件 symlink。
- 提交：
  - `cfac049 feat: 完成 T15 课程文件保护`。
- 剩余风险：
  - 当前 Windows 环境的两个既有 symlink 场景仍跳过；T15 的嵌套保护已通过字符串路径确定性覆盖，仍建议在允许创建 symlink 的 CI/主机复验既有 canonical-path 分支。
  - 已清理 `src`/`tests` 下的 `__pycache__`、`.pyc`/`.pyo`、根目录 `.pytest_cache` 与 `.superpowers`；保留 `.venv`。

### 2026-07-12 — T14 — ToolPolicy 基础规则

- 使用的技能：using-superpowers；karpathy-guidelines；executing-plans；using-git-worktrees；test-driven-development；requesting-code-review；receiving-code-review。
- 使用的智能体：OpenAI Codex；第一阶段契约审查智能体；第二阶段质量/安全独立复核。
- 关键提示词 / 上下文：
  - T14 只实现 `ToolPolicy(config).evaluate()` 与 `PolicyDecision`；不执行工具、checkpoint、trace 或状态写入，也不修改 Action、AgentLoop、PathClassifier 的生产代码。
  - T13 PathClassifier 是唯一写入路径分区来源；T14 对 protected/out-of-scope 写入 fail-closed，T15 继续负责课程保护规则扩展。
- 摘要：
  - 新增 `src/hancode/tool_policy.py`：以静态阶段工具矩阵、T5 artifact gate、T13 PathClassifier 和 TaskState 判定工具调用。
  - source write 仅在一致的 code phase 且 SPEC/PLAN 完成时允许，并返回 `requires_checkpoint=True`；不在本任务创建 checkpoint。
  - `finish_phase` 对六阶段使用 artifact、source edit、测试状态和 rollback 状态门禁；`ask_user`、`final` 不触发工具执行。
- 逐项 TDD 证据：
  - Red：新增 `tests/test_tool_policy.py` 后，因 `hancode.tool_policy` 不存在，收集阶段出现预期 `ModuleNotFoundError`。
  - Green：最小实现后 ToolPolicy 专项 22 passed；补齐审查回归后 T14 + AgentLoop 专项 43 passed。
- 两阶段评审：
  - 阶段一发现 3 项 Important：PLAN 仍为旧自由函数接口、拒绝序列化断言不完整、四个 finish gate 拒绝分支缺测；均已在 T14 范围内修复并复验。
  - 阶段二复核 fail-closed 分区、phase/state 优先级、结构化错误、AgentLoop 无 dispatch 集成与范围控制；补充 state current phase 不一致回归后无剩余 Critical/Important。
- 提交：
  - `0c898e8` — `feat: 完成 T14 基础工具策略`：新增 ToolPolicy、结构化决策和完整 T14 测试。
- 验证：
  - T5+T10+T13+T14：82 passed、2 skipped；全量沙箱外：317 passed、4 skipped in 3.45s；Ruff 全量通过；MyPy `src` 为 `Success: no issues found in 15 source files`；`git diff --check` 通过。
- 剩余风险：
  - 两个 T13 symlink 场景在当前 Windows 权限下跳过；T14 对 PathClassifier 的既有 fail-closed 返回值进行策略拒绝，仍应在可创建 symlink 的 CI/主机复验。

### 2026-07-12 — T13 — PathClassifier

- 使用的技能：using-superpowers；karpathy-guidelines；executing-plans；using-git-worktrees；test-driven-development；requesting-code-review；receiving-code-review；verification-before-completion。
- 使用的智能体：OpenAI Codex；第一阶段契约审查智能体；第二阶段质量/安全审查。
- 关键提示词 / 上下文：
  - T13 只实现四区 `PathClassifier(HanCodeConfig)`；不实现 ToolPolicy、phase、checkpoint、trace 或 FileTools 改造。
  - 相对路径先 canonical resolve 并限制在 `allowed_workspace_root`；受保护模式对词法与 canonical 路径均匹配且优先。
- 摘要：
  - 新增 `src/hancode/path_policy.py`，公开 `PathZone`（`protected`、`artifact`、`source`、`out_of_scope`）和 `PathClassifier.classify()`。
  - task root 仅六个精确大小写的直系产物可归入 artifact；任务状态、历史、trace 与 checkpoints 为 protected，其他 task 内文件即使 `.hancode` 被配置成可写根也为 out of scope。
  - source 仅来自配置 `writable_roots`；绝对路径、`..`、resolve 故障和 symlink 逃逸均 fail-closed 为 `OUT_OF_SCOPE`。
- 逐项 TDD 证据：
  - Red：新增 `tests/test_path_classifier.py` 后，专项在收集阶段因 `hancode.path_policy` 不存在得到预期 `ModuleNotFoundError`。
  - Green：最小实现后专项为 26 passed、2 skipped；后续审查补充 artifact 大小写、绝对 workspace 内路径和 task-root/write-root 重叠测试，最终专项为 29 passed、2 skipped。
- 两阶段评审：
  - 阶段一发现 2 项 Important：artifact 白名单错误地 casefold，以及对越界结果的命名质疑。前者已改为精确文件名并有反例测试；后者核对四区契约后保留 `OUT_OF_SCOPE`，因为它是已批准的越界/非法路径唯一返回值。
  - 阶段二发现 1 项 Important：当 `.hancode` 被列为 writable root 时，未知 task 文件会误落入 source；已在 artifact 后封住其余 task 文件并复验。未实现 T14/T15 的策略机制。
- 提交：
  - `6727894` — `feat: 完成 T13 路径分类器`：新增 PathClassifier 与完整 T13 测试。
- 验证：
  - T3+T13：68 passed、2 skipped；最终 T13 专项：29 passed、2 skipped；跳过均因当前 Windows 环境不允许创建文件 symlink。
  - 全量沙箱外：286 passed、4 skipped in 2.55s；Ruff 全量通过；MyPy `src` 为 `Success: no issues found in 14 source files`；`git diff --check` 通过。
- 剩余风险：
  - Windows 符号链接权限受限，两个 T13 symlink 回归在本机跳过；逻辑仍以 canonical resolve fail-closed，需在具备创建 symlink 权限的 CI/主机复验。

### 2026-07-11 — T12 — FileTools 最小读写

- 使用的技能：using-superpowers；karpathy-guidelines；brainstorming；writing-plans；executing-plans；using-git-worktrees；test-driven-development；requesting-code-review；receiving-code-review。
- 使用的智能体：OpenAI Codex；第一阶段契约审查智能体；第二阶段质量/安全审查智能体；控制代理（沙箱外 pytest 验证）。
- 关键提示词 / 上下文：
  - T12 只实现 `read_file`、`write_file`、`list_files`、`search_text` 与基础 root containment；不得提前实现 PathClassifier、ToolPolicy、checkpoint、trace、run_tests 或精确 edit_file。
  - 所有结果使用 T11 `ToolResult`；`.env`/`.env.*` 是 T12 的最小硬安全底线；read/search 输出覆盖 SPEC 最小 secret fixture 脱敏。
- 摘要：
  - 新增 `src/hancode/file_tools.py`：四个函数均返回结构化输出和安全错误摘要，路径 resolve 后必须留在 project root 内，拒绝绝对路径、父级和 symlink 逃逸。
  - 读取和搜索使用 UTF-8；搜索按相对 POSIX 路径和行号稳定排序，并报告不可读、非 UTF-8 和凭据文件；写入预编码后按字节落盘，`bytes_written` 与实际内容一致。
  - `.env`、引号/非引号赋值、Bearer、sk-token 和 JSON secret fixture 均不会完整进入 read/search ToolResult。
- 逐项 TDD 证据：
  - Red：新增测试后因 `hancode.file_tools` 不存在，以预期 `ModuleNotFoundError` 在收集阶段失败。
  - Green：最小实现后沙箱外专项 23 passed、1 skipped；第一阶段新增 2 项脱敏测试先 2 failed 后 2 passed；第二阶段新增安全/编码测试先 5 failed、1 skipped 后 5 passed、1 skipped。
- 两阶段评审：
  - 阶段一发现 1 项 Important：带引号 assignment、JSON password 与 query 原样泄漏；已修复并验证。
  - 阶段二发现 1 项 Critical 与 4 项 Important：symlink alias 绕过 `.env`、resolve 异常外泄、Windows 落盘字节不一致等。批准范围内问题均已修复；通用凭据扫描和并发 TOCTOU 明确留作后续风险。复审无剩余 Critical/Important。
- 提交：
  - `0538bed` — `feat: 完成 T12 文件工具`：新增 FileTools 与完整 T12 测试。
- 验证：
  - T11+T12：40 passed、2 skipped；全量沙箱外：258 passed、2 skipped in 2.58s；两个 skip 均为 Windows 文件 symlink 权限限制。
  - Ruff 全量通过；MyPy `src` 为 `Success: no issues found in 13 source files`；`git diff --check` 通过。
- 剩余风险：
  - `.npmrc`/YAML/ghp/AKIA 等通用凭据扫描、恶意并发 symlink/junction TOCTOU 和极端 symlink loop 不属于 T12 最小 fixture/basic containment，后续安全机制必须统一处理。

### 2026-07-11 — T11 — ToolResult 与 ToolRegistry

- 使用的技能：using-superpowers；karpathy-guidelines；executing-plans；using-git-worktrees；test-driven-development；requesting-code-review；receiving-code-review。
- 使用的智能体：OpenAI Codex；独立只读审查智能体；控制代理（沙箱外全量验证）。
- 关键提示词 / 上下文：
  - T11 只实现统一 `ToolResult`、工具注册与确定性分发；不提前实现 FileTools、ToolPolicy、trace、shell 执行或 FeedbackBuilder。
  - 工具异常的 `error_summary` 只暴露异常类型；重复工具名明确拒绝，避免泄露原始异常内容或静默覆盖。
- 摘要：
  - 新增 `src/hancode/tools.py`，其中 `ToolResult` 统一承载成功、输出、错误摘要、退出码和 stdout/stderr；`ToolRegistry` 仅以 `Action.args` 调用已注册 callable。
  - 未注册工具、非工具 Action、异常、错误返回类型和 action-name 不一致均返回结构化失败结果；异常消息不回显。
  - `AgentLoop` 的 ToolRegistry Protocol 返回类型收紧为 `ToolResult`，T10 的测试 spy 同步对齐。
- 逐项 TDD 证据：
  - Red：首次新增专项测试后，因 `hancode.tools` 不存在，以预期 `ModuleNotFoundError` 在收集阶段失败。
  - Green：最小实现后专项 8 passed；审查补充边界覆盖后 ToolRegistry + AgentLoop 专项 24 passed in 0.09s。
- 审查：
  - 独立只读审查发现 1 项 Important：ToolRegistry Protocol 收紧后测试 spy 仍返回 `object`，使 `mypy src tests` 失败。已修复并复验；另补齐 2 项 Minor 测试覆盖（注册参数、未知工具无副作用）。
- 提交：
  - `a2309db` — `feat: 完成 T11 工具注册与分发`：新增 ToolResult/ToolRegistry、T11 测试，并对齐 AgentLoop 测试接缝。
- 验证：
  - T7-T11 回归：74 passed in 0.12s；T11+T10 专项：24 passed in 0.09s；Ruff 通过；MyPy `src` 为 `Success: no issues found in 12 source files`。
  - 受限沙箱全量 pytest 得到 129 passed、97 个临时目录 `.lock` 权限错误；沙箱外同命令复验为 226 passed in 6.07s。
  - `git diff --check` 通过。
- 剩余风险：
  - `mypy src tests` 尚有 6 项既有错误（LLM context 的 dict 不变性与 Policy Protocol 协变性）；T11 引入的 ToolRegistry Protocol 错误已修复。具体文件工具、策略、trace 与反馈集成继续由 T12-T21 实现。

### 2026-07-11 — T10 — AgentLoop 最小循环骨架

- 使用的技能：using-superpowers；karpathy-guidelines；executing-plans；test-driven-development；requesting-code-review；receiving-code-review；verification-before-completion。
- 使用的智能体：OpenAI Codex；独立只读审查智能体；控制代理（沙箱外全量验证）。
- 关键提示词 / 上下文：
  - T10 只实现可注入的最小控制流，依赖 T6/T8/T9；不能提前实现真实 ToolRegistry、ToolPolicy、ContextBuilder、FeedbackBuilder、trace、retry 或 rollback。
  - `finish_phase` / `final` 经 parser 与 policy 后只结束本次 run，返回 `running`；`MockLLMExhausted` 必须由 loop 转成当前 phase 的完整结构化 `blocked` 错误。
- 摘要：
  - 新增 `src/hancode/agent_loop.py`：定义 T10 所需的依赖 Protocol、`AgentRunResult` 与 `AgentLoop.run(task_id)`；每轮固定执行 context -> LLM -> parser -> policy -> tool -> feedback，并将工具 observation 注入下一轮 context。
  - `tool_call` 只有在 parser 成功且 policy allow 后才 dispatch；parse error、policy denial、MockLLM 耗尽、max_steps 和未支持的 `ask_user` 都停止为 `blocked`，不执行工具。
  - `finish_phase`、`final` 返回 `running`；Router 已完成时以 0 step 返回 `completed`；本任务不保存 state、生成 trace 或解释未来 ToolResult。
- 逐项 TDD 证据：
  - Red：新增 `tests/test_agent_loop.py` 后，专项测试在收集阶段因 `hancode.agent_loop` 不存在以预期 `ModuleNotFoundError` 失败。
  - Green：新增最小 loop 后专项 12 passed；独立审查发现 `final` 缺少独立停止测试，补充该测试后专项 13 passed in 0.04s。
- 审查：
  - 只读审查无 Critical/Important；Minor 为 `final` 分支缺少单独测试。确认该分支已由 `ActionType.FINAL` 与 `FINISH_PHASE` 的同一停止分支实现后，仅新增回归测试并验证通过。
- 提交：
  - `2f7dc5f` — `feat: 完成 T10 AgentLoop`：新增 loop 与 13 项 T10 测试。
- 验证：
  - T8+T9+T10 回归：35 passed in 0.09s；Ruff 通过；MyPy 为 `Success: no issues found in 1 source file`。
  - 全量受限沙箱因 pytest 临时目录 `.lock` 的 `PermissionError` 得到 120 passed、97 errors；同命令沙箱外复验为 218 passed in 1.75s。
  - `git diff --check` 通过。
- 剩余风险：
  - 真实 ToolResult、ToolPolicy、ContextBuilder、FeedbackBuilder、trace、state 持久化、retry 和 rollback 仍由 T11/T14/T19-T21 实现；T10 的 Protocol 是可替换接缝，不是这些模块的最终接口。

### 2026-07-11 — T9 — MockLLM

- 使用的技能：test-driven-development；verification-before-completion。
- 使用的智能体：OpenAI Codex；控制代理（沙箱外全量验证）。
- 关键提示词 / 上下文：
  - T9 只实现确定性、离线的 `LLMClient` Protocol、`MockLLM` 和 `MockLLMExhausted`；不得调用网络、凭据、provider、parser、trace、policy 或工具，也不得提前实现 T10 AgentLoop。
  - 原始 action dict 不作 schema 校验，以便后续 ActionParser 接收 malformed payload；构造、每次输出与 context/history 公开边界均必须隔离可变嵌套值。
- 摘要：
  - 新增 `src/hancode/llm.py`：`MockLLM` 按输入序列深拷贝返回 action，在耗尽检查前深拷贝记录 context，`contexts` 以 tuple 形式返回深拷贝快照。
  - 新增 `MockLLMExhausted`，固定诊断为 `mock_llm_exhausted`、`Provide another mock action or stop the loop as blocked.` 与消息 `MockLLM action sequence exhausted.`；不在 T9 映射 blocked 状态，交由 T10 AgentLoop。
  - 新增 `tests/test_llm.py` 的 8 项测试：顺序、context、确定性、ActionParser 兼容原始输出、耗尽字段/调用记录及输入/输出/history 的防别名语义。
- 逐项 TDD 证据：
  - Red：新增测试后执行 `$env:PYTHONPATH='src'; $env:UV_CACHE_DIR=Join-Path $env:TEMP 'hancode-uv-cache'; uv run --no-sync pytest tests/test_llm.py -v -p no:cacheprovider`，因 `hancode.llm` 不存在在收集阶段以预期 `ModuleNotFoundError` 失败。
  - Green：新增最小标准库实现并以同一命令复跑，8 passed in 0.04s。
- 审查修复（仅测试，未修改 `src/hancode/llm.py`）：
  - 新增 malformed raw action 用例：输入缺少正常 action 字段且 `type` 非法的 dict，断言 `next_action()` 原样返回等值但独立的 dict，证明 MockLLM 不提前抛错、填充字段或执行 schema 校验，保留给 ActionParser 处理。
  - 新增 returned-action 深层隔离用例：两个预设 action 共用同一嵌套 `args`，修改第一次返回值的深层 `path` 后，断言第二次返回值仍为原始 `README.md`，直接覆盖内部队列不受污染的边界。
  - 测试补强证据：本次审查时 `src/hancode/llm.py` 已正确满足这两个契约，因此新增的正式回归测试没有形成新的生产 RED；首次按正式断言运行专项测试即为 `10 passed in 0.04s`。未为制造 RED 而改动生产代码。
  - 验证：T8+T9 回归通过 `22 passed in 0.05s`，`uv run --no-sync ruff check tests/test_llm.py --no-cache` 输出 `All checks passed!`，`git diff --check` 无输出并通过。
- 提交：
  - `a86fd44` — `feat: 完成 T9 MockLLM`：新增 `llm.py` 与初始 `tests/test_llm.py`。
  - `93ae774` — `docs: 回填 T9 验证记录`：首次回填 T9 的 PLAN 与日志验证证据。
  - `3bba8cb` — `test: 补强 T9 MockLLM 审查覆盖`：新增 malformed raw action 透传和深层返回值隔离测试。
  - `e9d14ae` — `docs: 纠正 T9 审查验证记录`：纠正审查补测的验证叙述；此提交不新增测试。
  - `a397ccf` — `docs: 修正 T9 提交记录`：修正日志中的 T9 提交元数据；此提交不新增测试。
  - `c9d0adc` — `docs: 对齐 T9 耗尽契约`：在 PLAN 明确 T9 抛出异常、T10 映射 `blocked` 的职责边界。
  - 后续跨文档契约同步（审查发现；均为文档提交，不是源码/测试提交）：
    - `54cc89b` — `docs: 完整回填 T9 提交审计`：完整回填 T9 审计记录。
    - `0410035` — `docs: 对齐 T10 MockLLM 耗尽状态`：同步 T10 对 `MockLLMExhausted` 的固定 `blocked` 映射。
    - `45b966e` — `docs: 同步 MockLLM 耗尽上位契约`：同步 SPEC 与系统架构中的耗尽职责边界。
    - `8b87619` — `docs: 同步 MockLLM 隔离示例`：同步系统架构中的深拷贝与 `contexts` 隔离示例。
- 提交审计修正（2026-07-11）：逐一核验原有六个提交的主题和变更文件后，补齐此前遗漏的 `3bba8cb`、`c9d0adc`，并将 `e9d14ae`、`a397ccf` 明确标注为文档提交，避免误记为测试提交；审查随后发现的上述四项跨文档契约同步提交亦已完整列入，且均不属于源码或测试提交。
- 后续契约同步审计验证（2026-07-11）：设置既有 `PYTHONPATH=src` 与临时 `UV_CACHE_DIR` 后，`uv run --no-sync pytest tests/test_llm.py -v -p no:cacheprovider` 退出码 0（10 passed in 0.03s）；`git diff --check` 退出码 0、无输出。
- 审计验证证据（2026-07-11）：设置既有 `PYTHONPATH=src` 与临时 `UV_CACHE_DIR` 后，`uv run --no-sync pytest tests/test_llm.py -v -p no:cacheprovider` 退出码 0（10 passed in 0.03s）；`git diff --check` 退出码 0、无输出。
- 验证：
  - 专项：`uv run --no-sync pytest tests/test_llm.py -v -p no:cacheprovider`：8 passed in 0.04s。
  - T8+T9 回归：`uv run --no-sync pytest tests/test_action_parser.py tests/test_llm.py -v -p no:cacheprovider`：20 passed in 0.05s。
  - 静态检查：`uv run --no-sync ruff check src/hancode/llm.py tests/test_llm.py --no-cache`：All checks passed；`uv run --no-sync mypy src/hancode/llm.py --no-incremental`：Success: no issues found in 1 source file。
  - 全量：受限沙箱的 `uv run --no-sync pytest -p no:cacheprovider` 因 `C:\\Users\\24125\\AppData\\Local\\Temp\\pytest-of-24125\\pytest-*\\.lock` 创建锁文件的 `PermissionError` 中断（106 passed, 97 errors）；控制代理在沙箱外以同一命令复验：203 passed in 6.29s。
  - `git diff --check` 通过。
- 剩余风险：
  - T9 不执行 action、不作 schema/policy/path 决策、也不管理 trace 或循环状态；`MockLLMExhausted` 到 blocked 状态的映射与最大步数控制仍属于 T10。
- 审查结论处理：
  - `MockLLMExhausted` 保持运行时异常，不改为 `HanCodeError`；T10 捕获后补齐当前 phase、`denied_rule=None` 和结构化错误字段。
  - `MockLLM` 保持普通可变类且不新增 `reset()`；action 序列和 context 历史已通过深拷贝隔离，足以防止外部别名污染。
  - 将确定性测试重命名为 `test_mock_llm_is_deterministic`，并同步 PLAN 的完整测试清单；历史 Red/Green 数字保留为历史证据。
- Minor 修正验证（2026-07-11）：`tests/test_llm.py` 专项 10 passed；全量 `uv run --no-sync pytest -p no:cacheprovider` 在沙箱外 205 passed；Ruff、MyPy 与 `git diff --check` 通过。

### 2026-07-11 — T8 — ActionParser

- 使用的技能：test-driven-development；systematic-debugging；verification-before-completion。
- 使用的智能体：OpenAI Codex；控制代理（沙箱外全量验证）。
- 关键提示词 / 上下文：
  - T8 仅解析原始 LLM / MockLLM dict；T7 已提供 `Action`、`ActionType`、`ParseError` 和 `Action.from_values()`，必须复用其 schema 校验。
  - 禁止提前实现 policy、PathClassifier、LLM、tool dispatch、observation 或 trace；原始 payload 的顶层字段必须严格固定，并以可信 `current_phase` 进行最终一致性判断。
- 摘要：
  - 在 `src/hancode/actions.py` 新增 `parse_action(raw, current_phase)`：按 payload 类型、缺失字段、多余字段、T7 schema 和 phase 一致性的固定顺序解析。
  - 新增稳定且不回显候选值的 parser 边界错误：`invalid_action_payload`、`missing_action_fields`、`unexpected_action_fields`、`phase_mismatch`；边界错误以 `current_phase.value` 填充 phase 且 `denied_rule=None`。
  - 新增 `tests/test_action_parser.py` 共 12 项参数化/边界测试，覆盖三种合法工具 action、非 dict、缺失/多余顶层字段、未知工具、非法参数、缺失 write reason、非法 phase、phase mismatch、精确边界错误及输入/args 不可变性。
- 逐项 TDD 证据：
  - Red：新增测试后执行 `$env:PYTHONPATH='src'; $env:UV_CACHE_DIR=Join-Path $env:TEMP 'hancode-uv-cache'; uv run --no-sync pytest tests/test_action_parser.py -v -p no:cacheprovider`，12 failed；全部因 `hancode.actions` 尚无 `parse_action` 而出现预期 `AttributeError`。
  - Green：新增最小 parser 边界校验、委托 `Action.from_values()` 与 phase 比对后，以相同命令复跑，12 passed in 0.04s。
  - 静态检查发现两个 walrus 临时变量未使用（ruff F841）；根因是只需布尔集合差而不需错误字段值。移除赋值、保持行为不变后 ruff 通过。
- 审查修复：
  - 将 `unknown_tool`、`invalid_action_args`、`missing_reason` 与 `invalid_phase` 的预期值提升为完整 `ParseError`，覆盖 `error_code`、`message`、`phase`、`denied_rule` 和 `suggested_fix`，以确认 parser 原样透传 T7 schema 错误。
  - Red：先保留旧的 `result.error_code == expected_error` 结构并执行 parser 专项测试，4 failed、8 passed；失败明确表明旧断言只能比较错误码，无法比较完整 `ParseError`。
  - Green：仅改为 `assert result == expected_error`，未修改 `src/hancode/actions.py`；专项 12 passed in 0.03s，T7+T8 回归 43 passed in 0.08s，`git diff --check` 通过。
- 提交：
  - `4afeef1` — `feat: 完成 T8 ActionParser`。
- 验证：
  - 专项：`uv run --no-sync pytest tests/test_action_parser.py -v -p no:cacheprovider`：12 passed in 0.04s。
  - T7+T8 回归：`uv run --no-sync pytest tests/test_action_schema.py tests/test_action_parser.py -v -p no:cacheprovider`：43 passed in 0.06s。
  - 静态检查：`uv run --no-sync ruff check src/hancode/actions.py tests/test_action_parser.py --no-cache` 通过；`uv run --no-sync mypy src/hancode/actions.py --no-incremental`：Success: no issues found in 1 source file。
  - 全量：受限沙箱中 `uv run --no-sync pytest -p no:cacheprovider` 因 `C:\\Users\\24125\\AppData\\Local\\Temp\\pytest-of-24125\\pytest-*\\.lock` 的 `PermissionError` 中断（98 passed, 97 errors）；控制代理使用同一命令在沙箱外复跑：195 passed in 3.83s。
  - `git diff --check` 通过。
- 剩余风险：
  - T8 不执行 action，也不作 policy/path 决策、LLM 调用、observation 或 trace 写入；这些集成属于后续任务。`current_phase` 是调用方提供的可信 Phase，parser 不负责从状态文件取得它。

### 2026-07-11 — T7 — Action Schema

- 使用的技能：using-superpowers；karpathy-guidelines；brainstorming；using-git-worktrees；executing-plans；test-driven-development。
- 使用的智能体：OpenAI Codex。
- 关键提示词 / 上下文：
  - 用户要求先阅读 `AGENTS.md`、Superpowers 工作流与 Karpathy 准则后，在 `feature/M1` 的 `.worktrees/M1` 实施 PLAN 中的 T7。
  - 已确认 T7 只提供类型化 schema 构造与校验；`parse_action(raw)` 留给 T8，且不实现 tool dispatch、PathClassifier、ToolPolicy、phase-current 比对或真实工具执行。
  - 四个 action 类型沿用架构文档：`tool_call`、`finish_phase`、`ask_user`、`final`；MVP 工具参数采用固定 schema，`run_tests` 不接收模型给出的 shell command。
- 摘要：
  - 新增 `src/hancode/actions.py`，提供冻结、slots 化的 `Action`、`ActionType`、`ParseError` 与 `Action.from_values()`。
  - 七个注册工具的参数集合被严格固定；写入类工具要求非空 `reason`，控制 action 不得携带工具名，`ask_user` 只接受非空 `question`。
  - `args` 被防御性复制为只读 mapping；工厂与直接构造共用同一 schema 不变量，避免绕过校验的非法 Action 进入后续机制。
- 逐项 TDD 证据：
  - Red/Green-1：新增测试首先因 `hancode.actions` 不存在而出现 `ModuleNotFoundError`；新增枚举、数据结构与最小工厂后 4 passed。
  - Red/Green-2：写入 action 无 reason、`run_tests` 携带 command、`finish_phase` 携带工具名均错误地返回 Action（3 failed）；补充三项边界校验后 7 passed。
  - Red/Green-3：缺失/多余工具参数、`target_kind`、`ask_user` 空问题、`final` 参数和直接构造绕过均未被拒绝（10 failed）；集中固定 schema 并让构造器复用校验后 26 passed。
  - 回归补强：合法控制 action、未知工具结构化错误不回显候选值和 `args` 不可变；专项最终 30 passed。
  - 审查 Minor 修正：模拟未来工具被注册但未声明参数 schema 时，空参数错误返回 `Action`（1 failed）；显式限制无参数工具为 `run_tests` 与 `rollback_last_checkpoint` 后专项 31 passed。
- 环境与诊断：
  - 受限沙箱中的 pytest 仍会因 Windows 临时目录 ACL 失败；本任务按照既有批准方式设置 `PYTHONPATH=src` 与临时 `UV_CACHE_DIR` 后在沙箱外运行，未修改测试或业务语义来规避环境问题。
- 提交：
  - `18ce975` — `feat: 完成 T7 Action Schema`。
- 验证：
  - 基线：`uv run --no-sync pytest -p no:cacheprovider`：152 passed。
  - 专项：`uv run --no-sync pytest tests/test_action_schema.py -v -p no:cacheprovider`：31 passed。
  - 静态检查：`ruff check src/hancode/actions.py tests/test_action_schema.py --no-cache` 通过；`mypy src/hancode/actions.py --no-incremental` 无问题。
  - 初始最终：`uv run --no-sync pytest -p no:cacheprovider`：182 passed；`git diff --check` 通过。
  - 审查修正后最终：`uv run --no-sync pytest -p no:cacheprovider`：183 passed；`git diff --check` 通过。
- 剩余风险：
  - T8 尚未实现原始 LLM dict 到 `Action.from_values()` 的字段解析与适配；当前 T7 不执行任何 action，因此工具权限、当前 phase 一致性和路径安全仍由后续任务负责。

### 2026-07-11 — T6 — WorkspaceRouter

- 使用的技能：using-superpowers；brainstorming；writing-plans；using-git-worktrees；subagent-driven-development；test-driven-development；systematic-debugging；receiving-code-review；requesting-code-review；verification-before-completion；finishing-a-development-branch。
- 使用的智能体：OpenAI Codex；T6 Implementer；T6 Task Reviewer；T6 Final Reviewer；T6 Priority-Test Fixer。
- 关键提示词 / 上下文：
  - 用户要求在 `feature/M1` 的 `.worktrees/M1` 实现 PLAN 明确列出的 T6；边界仅为确定性 `WorkspaceRouter`，不得实现 AgentLoop、Action Schema、ToolPolicy、checkpoint、trace、文件写入、LLM 调用或 rollback 执行。
  - 任务卡要求六阶段 `Phase`，但 SPEC 同时要求 completed 路由结果；用户选择保留六阶段枚举，以 `RoutingDecision(phase=Phase.DELIVER, completed=True)` 表示终态。
  - T4 的 `TaskState` 已严格验证并冻结固定 artifact / phase-completion 键，因此 Router 只读取已验证状态，不做 Markdown 或文件系统反向推断。
- 摘要：
  - 新增 `src/hancode/router.py`：冻结、slots 化的 `RoutingDecision` 与纯函数 `select_next_phase()`。
  - 路由按不一致/终止状态、SPEC、PLAN、未消费失败测试、retry/checkpoint、code/test/review、deliverable、completed 的固定优先级返回决策；无 checkpoint 的 retry 耗尽明确进入阻塞 review，而不是宣称可 rollback。
  - 新增 `tests/test_router.py` 共 22 项测试，覆盖所有任务卡命名用例、失败状态消费、防止 review 死循环、回滚要求、阶段推进、交付物、终态、无副作用和多条件优先级。
- 逐项 TDD 证据：
  - Red/Green-1：`hancode.router` 缺失，首个路由测试出现 `ModuleNotFoundError`；新增最小模块和 SPEC 分支后通过。
  - Red/Green-2 至 6：依次以缺 PLAN、不一致/blocked/failed、失败测试与 retry、code/test、review/deliver/完成态为 RED，逐段补充最小纯路由；最终初版专项 18 passed。
  - 终审 Important 修复：新增优先级碰撞测试先在正确实现上 GREEN；随后仅临时倒序 `router.py` 分支，得到 4 failed / 18 passed（SPEC-vs-PLAN、SPEC-vs-failed、PLAN-vs-failed、KNOWLEDGE-vs-DELIVERABLES），立即 `git restore --source=HEAD -- src/hancode/router.py` 恢复生产代码，最终专项 22 passed。
- 环境与诊断：
  - 受限沙箱全量 pytest 可稳定复现 `tmp_path` 在 `C:\Users\24125\AppData\Local\Temp\pytest-of-24125\...\.lock` 的 `PermissionError`，造成 33/51 passed 后的大量 setup errors；专项 Router 测试不受影响。
  - 以 `PYTHONPATH=src`、`UV_CACHE_DIR=$env:TEMP\hancode-uv-cache` 在已批准的沙箱外执行同一全量命令，通过 148 passed；确定为 Windows 临时目录 ACL，不是 T6 断言或实现问题。
- 评审：
  - Task Reviewer：初版无 Critical/Important/Minor，确认十条规则和 18 项覆盖。
  - Final Reviewer：发现 Important——单项分支测试不足以保护有序路由的竞争条件；主控复核后确认有效，未改生产逻辑，只补三组竞争条件测试。
  - Re-review：无 Critical、Important 或 Minor；确认四种竞争优先级均被断言锁定。
- 提交：
  - `2716b9a` — `feat: 完成 T6 WorkspaceRouter`。
  - `2a495bc` — `test: 补充 T6 路由优先级覆盖`。
  - 本记录与 PLAN 回写将在独立文档提交中落盘。
- 验证：
  - `$env:PYTHONPATH='src'; $env:UV_CACHE_DIR=Join-Path $env:TEMP 'hancode-uv-cache'; uv run --no-sync pytest tests/test_router.py -v -p no:cacheprovider`：主控复验 22 passed。
  - `uv run --no-sync ruff check src/hancode/router.py tests/test_router.py --no-cache`：All checks passed。
  - `uv run --no-sync mypy src/hancode/router.py --no-incremental`：Success，无问题。
  - `uv run --no-sync pytest -p no:cacheprovider`：主控在补齐优先级碰撞测试后的沙箱外终验为 152 passed（补测前首次 T6 全量验证为 148 passed）。
  - `git diff --check 442f2d2..HEAD`：通过。
- 经验教训：
  - 有序状态机不能只测试单一条件；每个相邻优先级都应有至少一个同时满足的碰撞测试，才能防止未来重排分支改变控制流。
  - 遇到 pytest 临时目录 ACL 时，先区分 setup 层环境故障和断言失败，再在批准的环境中复验；不可为了让沙箱绿而修改业务实现或测试语义。

### 2026-07-11 — T5 — PhaseGate

- 使用的技能：writing-plans；using-git-worktrees；executing-plans；subagent-driven-development；test-driven-development；systematic-debugging；receiving-code-review；requesting-code-review；verification-before-completion。
- 使用的智能体：OpenAI Codex；T5 Implementer；T5 Finish Implementer；T5 Spec Reviewer；T5 Quality Reviewer；T5 Final Reviewer。
- 关键提示词 / 上下文：
  - 用户要求在 `feature/M1` 的 `.worktrees/M1` 中完成 `docs/PLAN.md` 明确列出的 T5，且不得实现 T6/T14 的 router、ToolPolicy、路径分类、checkpoint、trace、文件写入或阶段完成门禁。
  - T5 复用 T1 的 `Phase` 枚举和 T4 的 `TaskState`；T4 已将 artifacts 映射校验为六个固定键并冻结。
  - 用户在代码提交后要求先报告成果、暂不创建新的提交；本记录和 PLAN 回写因此保持未提交。
- 摘要：
  - 新增 `src/hancode/phases.py` 的 `can_write_artifact()` 和 `can_write_source()` 两个纯布尔函数。
  - artifact 白名单精确为 spec=`SPEC.md`、plan=`PLAN.md`、code=空集、test=`TEST_REPORT.md`、review=`REVIEW.md`、deliver=`KNOWLEDGE.md` 与 `DELIVERABLES.md`；未知 phase、非字符串或路径形式 artifact 返回 false。
  - source write 同时要求调用 phase/state phase 均为 code、SPEC/PLAN artifact 标记完成、`inconsistent=False`、status 非 `INCONSISTENT`；不读写文件、不改写 state。
- 逐项 TDD 证据：
  - Red/Green-1：`hancode.phases` 不存在导致 artifact allowlist 测试收集失败；新增最小白名单函数后参数化 6 项通过。
  - Red/Green-2：加入 source gate 测试后因缺少 `can_write_source` 导入失败；实现 code phase 与 SPEC/PLAN 前置条件后，专项阶段性结果为 12 passed。
  - Red/Green-3：新增安全边界测试后，在沙箱外有效 RED 中 `test_inconsistent_state_rejects_source_write` 与 `test_inconsistent_status_rejects_source_write` 均为 expected false、actual true；加入两个不一致判定后专项 18 passed。
- 环境与诊断：
  - 受限沙箱无法初始化默认 `C:\Users\24125\AppData\Local\uv\cache`，pytest 的 `tmp_path` 也会在临时目录 `.lock` 处触发 `PermissionError`；同时设置 `PYTHONPATH=src`、`UV_CACHE_DIR=$env:TEMP\hancode-uv-cache` 并在已批准的沙箱外运行后可稳定执行，确定为环境 ACL 而非代码失败。
- 两阶段评审与最终审查：
  - Spec 初评提出 artifacts 缺少 `SPEC.md`/`PLAN.md` 时索引可能 `KeyError`。主控按 `TaskState.__post_init__` 的固定键集合校验和 `MappingProxyType` 冻结复核后判定该前提对合法 `TaskState` 不可达，未为绕过构造器的非法对象增加冗余分支。
  - Quality 评审：无 Critical/Important；确认 pure gate、phase 对齐、前置产物和双 inconsistent 信号均有真实 workspace 测试。
  - Final Review：无 Critical/Important；Minor 为未显式断言普通未知 artifact 名称。固定集合成员判断当前已正确拒绝该输入，按用户暂不新增提交的要求记录为非阻断测试补强建议。
- 提交：
  - `3c32408` — `feat: 完成 T5 PhaseGate`。
  - 本次文档回写未提交，等待用户后续授权。
- 验证：
  - `$env:PYTHONPATH='src'; $env:UV_CACHE_DIR=Join-Path $env:TEMP 'hancode-uv-cache'; uv run --no-sync pytest tests/test_phase_gate.py -v -p no:cacheprovider`：18 passed in 0.31s。
  - `$env:PYTHONPATH='src'; $env:UV_CACHE_DIR=Join-Path $env:TEMP 'hancode-uv-cache'; uv run --no-sync ruff check src/hancode/phases.py tests/test_phase_gate.py --no-cache`：All checks passed。
  - `$env:PYTHONPATH='src'; $env:UV_CACHE_DIR=Join-Path $env:TEMP 'hancode-uv-cache'; uv run --no-sync mypy src/hancode/phases.py`：Success，无问题。
  - `$env:PYTHONPATH='src'; $env:UV_CACHE_DIR=Join-Path $env:TEMP 'hancode-uv-cache'; uv run --no-sync pytest -p no:cacheprovider`：130 passed in 2.43s。
  - `git diff --check 878b135..HEAD`：通过。
- 经验教训：
  - TaskState 的构造不变量是下游 PhaseGate 的一部分接口契约；评审建议必须先与这种已验证不变量核对，避免为不可达非法状态扩大 API。
  - Windows 上应区分默认 uv/pytest 临时目录 ACL 与实际断言失败；先用隔离缓存和已批准环境复现，才能保留有效 RED/GREEN 证据。

### 2026-07-10 — T4 — StateStore

- 使用的技能：using-superpowers；using-git-worktrees；executing-plans；test-driven-development；verification-before-completion；Superpowers:subagent-driven-development；Superpowers:requesting-code-review
- 使用的智能体：OpenAI Codex；T4 Spec Reviewer；T4 Quality Reviewer；T4 Fix Agent
- 关键提示词 / 上下文：
  - 用户要求完成 `docs/PLAN.md` 中的 T4 StateStore，并在 `feature/M1` 的 `.worktrees/M1` 中继续开发。
  - T4 只实现 `state.json` 机器状态读写、一致性检查和结构化状态错误；不实现 router、trace、Markdown artifact 生成或 T5 以后机制。
  - `docs/SPEC.md` 是高优先级契约：state.json 是唯一机器状态源，artifact drift 进入 inconsistent 且不得自动反向修复。
- 摘要：
  - 新增冻结、slots 化的 `TaskState` 与 `load_state()`、`save_state()`、`reconcile_state()`。
  - 严格解析 schema v1 的 18 个字段、合法 phase/status/test status、固定 phase/artifact 键和非负计数；结构化错误不回显原始 JSON 内容。
  - `save_state()` 使用临时文件 + 原子替换，写失败保留原文件；校验 task_id 隔离；仅允许合法 code→code/test 变更 `files_changed`。
  - `reconcile_state()` 双向检测 artifact 漂移，返回 inconsistent，不回写 artifact 标志、不自动修复、不清除既有 inconsistent。
  - 使用 `MappingProxyType` 防止 `phase_completed` 与 `artifacts` 被运行时 mutation 绕过校验。
- 逐项 TDD 证据：
  - Red/Green-1：`hancode.state` 不存在导致单一机器状态源测试收集失败；新增最小 loader 后 1 passed。
  - Red/Green-2：损坏 JSON 首先暴露 `JSONDecodeError`；转换为结构化 `state_parse_error` 后专项 2 passed。
  - Red/Green-3：reconcile 接口缺失导致导入失败；实现漂移检测后专项 3 passed。
  - Red/Green-4：`save_state` 导入失败；加入枚举稳定序列化后专项 9 passed。
  - Red/Green-5：非 code phase 修改 `files_changed` 未被拒绝；加入持久化 phase 权限检查后专项 10 passed。
  - Red/Green-6：schema version、未知字段、非法 test status 和不完整映射未被拒绝；严格 schema 与 TaskState 自校验后专项 16 passed。
  - Red/Green-7：原子替换失败未结构化处理；加入临时文件清理和 `state_write_error` 后专项 19 passed。
  - 两阶段评审首次发现 3 个 Important：code→review/deliver 迟到写入、task_id 串写、冻结对象内部映射可变。修复代理补充回归测试并修复后，专项 23 passed。
- 两阶段评审：
  - 第一阶段 Spec 合规初评：FAIL（3 个 Important）；修复后 `SPEC RE-VERDICT: PASS`，无 Critical/Important。
  - 第二阶段代码质量初评：FAIL（同 3 个 Important）；修复后 `QUALITY RE-VERDICT: PASS`，无新的 Critical/Important/Minor。
- 提交：
  - `84ba160` — `feat: 完成 T4 StateStore`
  - 文档回写提交：本记录所在的文档提交。
- 验证：
  - `$env:PYTHONPATH='src'; $env:UV_CACHE_DIR=Join-Path $env:TEMP 'hancode-uv-cache'; uv run --no-sync pytest tests/test_state.py -v -p no:cacheprovider`：23 passed。
  - `uv run --no-sync ruff check src/hancode/state.py tests/test_state.py --no-cache`：All checks passed。
  - `uv run --no-sync mypy src/hancode/state.py --no-incremental`：Success，无问题。
  - 两阶段复评代理独立确认上述 3 项修复；全量 pytest 首次受 Windows 临时目录 ACL 影响，曾出现 27 passed、81 setup errors。
  - 之后在 worktree 外重新执行 `$env:PYTHONPATH='src'; $env:UV_CACHE_DIR=Join-Path $env:TEMP 'hancode-uv-cache'; uv run --no-sync pytest -p no:cacheprovider`：112 passed in 1.51s。
  - 同步复核 `ruff check src/hancode/state.py tests/test_state.py --no-cache`：All checks passed；`mypy src/hancode/state.py`：Success；`git diff --check HEAD~2..HEAD`：通过。
- 人工干预：
  - 用户明确要求使用 Superpowers 子代理进行两阶段评审，并随后授权代码提交和文档回写。
  - 评审结论中关于 code→review/deliver 的 target phase 语义按 SPEC 的“test/review 只能读取”收紧实现。
- 经验教训：
  - `frozen` dataclass 不会自动冻结内部 dict；机器状态映射必须在构造时深层转为不可变映射。
  - StateStore 保存前必须同时校验持久化 task_id 和 phase 所有权，不能只依赖调用方传入对象。
  - Windows pytest 临时目录 ACL 可能造成 setup 错误；应在批准的沙箱外重跑并区分环境失败和代码失败，最终以新鲜全量结果为准。

### 2026-07-10 返工 — T3 — ConfigLoader 安全与契约加固

- 使用的技能：receiving-code-review；executing-plans；test-driven-development；verification-before-completion
- 使用的智能体：OpenAI Codex
- 关键提示词 / 上下文：
  - 两阶段评审判定 T3 初版不通过，要求修复默认保护可删除、敏感字段绕过、项目根可写、T2 元数据未复用、远程 provider 凭据来源缺失和字段诊断不足。
  - 已确认 T3 不承载工具权限和 phase 策略：固定 phase 规则留在 T5，工具权限决策留在 T14。
  - `max_context_chars=24000`、`max_trace_events=40` 来自 2026-07-10 已批准的 T3 开发计划，而非返工阶段临时调整。
- 摘要：
  - `workspace.py` 提供共享 `load_project_metadata()`；T2 与 T3 现在使用同一 workspace metadata 契约。
  - `ConfigLoader` 只接受 T2 元数据与当前活动配置字段，拒绝未知顶层字段和嵌套配置。
  - protected patterns 改为不可移除基线并支持项目规则追加；补充 `secrets/**`、密钥文件模式和项目根可写拒绝。
  - 敏感字段扫描覆盖 `credentials`、`private_key`、`api_key_value` 等绕过形式；远程 provider 要求 credential source；错误消息只含字段名，不回显值。
- 逐项 TDD 证据：
  - Red-1 / Green-1（元数据）：`test_config_reuses_project_workspace_metadata_validation` 首次运行出现 3 个 `Failed: DID NOT RAISE HanCodeError`；共享校验后该组用例进入返工后专项通过。
  - Red-2 / Green-2（schema）：评审复现初版对未知顶层字段和嵌套对象直接返回配置；新增 `test_config_rejects_unknown_or_nested_configuration` 锁定该行为，严格字段集合实现后通过。该 Red 为评审复现，未在本次续接会话中重新回放。
  - Red-3 / Green-3（保护基线）：评审复现 `protected_patterns=[]` 会清空默认规则；`test_config_keeps_mandatory_protected_patterns` 验证基线保留与追加去重，返工后通过。该 Red 依据初版代码路径和评审报告记录。
  - Red-4 / Green-4（凭据）：评审复现 `credentials.value`、`private_key`、`api_key_value` 可绕过初版后缀扫描；新增三类回归用例，返工后 42 项专项测试通过且异常文本不含测试值。该 Red 未单独在本次续接会话回放。
  - Red-5 / Green-5（路径与诊断）：评审复现 `writable_roots` 为 `""`、`.` 或 `/**` 可解析到项目根，且错误不带字段名；新增边界与字段诊断用例后通过。
  - Red-6 / Green-6（provider 与回归）：评审复现远程 provider 缺少 credential source 仍可加载；新增远程必填、local 例外和既有路径/task ID 回归用例后，专项 42 passed、全量 89 passed。
  - 说明：返工提交 `e3ddce9` 已包含完整测试增量；除 Red-1 外，其余初版失败依据评审报告与初版代码行为记录，不冒充本次续接会话重新执行的命令输出。
- 两阶段评审：
  - 第一阶段 Spec 合规：确认 T2 元数据复用、不可移除课程保护、严格 schema、24000/40 来源、远程凭据来源和 T5/T14 边界已写入任务契约。
  - 第二阶段代码质量：确认 `Path.resolve()` / `PureWindowsPath`、字段级错误、敏感值不回显、local provider 例外与无副作用加载；Ruff 与 MyPy 通过。
- 提交：
  - `e3ddce9` — `fix: 加固 T3 ConfigLoader`
  - 文档回填提交：本记录所在的 `docs: 回填 T3 返工验证记录` 提交。
- 验证：
  - `$env:PYTHONPATH='src'; uv run --no-sync pytest tests/test_config.py -v -p no:cacheprovider`：42 passed。
  - `$env:PYTHONPATH='src'; uv run --no-sync ruff check src/hancode/config.py tests/test_config.py --no-cache`：All checks passed。
  - `$env:PYTHONPATH='src'; uv run --no-sync mypy src/hancode/config.py --cache-dir "$env:TEMP\hancode-mypy-t3-review"`：Success，无问题。
  - `$env:PYTHONPATH='src'; uv run --no-sync pytest -p no:cacheprovider`：89 passed。
- 人工干预：
  - 用户确认采用“仅远程 provider 必须 credential_source，local 可为 None”。
  - 用户确认 T3 仅支持当前活动字段，未来字段由后续任务加入。
- 经验教训：
  - 默认保护规则必须是安全基线，不能把用户配置当作可替换的 deny-list。
  - 配置 schema 需要先拒绝未知/嵌套数据，再谈字段名敏感扫描；字段名扫描只能作为错误分类和防御纵深。

### 2026-07-10 返工后续 — T3 文档与模板契约对齐

- 触发原因：两阶段评审发现 `docs/PLAN.md`、`docs/系统架构.md` 和 `examples/.hancode-template/project.json` 仍保留 T3 当前不接受的工具/phase/交互字段或旧模板字段。
- 修改：
  - 收窄架构文档的 ConfigLoader 当前职责，明确 task state、phase、tool policy 和交互开关属于后续任务。
  - 将架构中的 `project.json` 示例与 T3 严格 schema 对齐，移除 `stack`、`interactive`、`confirm_before_write`，补齐保护规则和 `project_root`。
  - 修正模板 `project.json`，并更新脚手架断言验证 `project_root="."` 且不包含未来 `stack`。
- 验证：
  - `$env:PYTHONPATH='src'; uv run --no-sync pytest tests/test_course_project_scaffold.py -v -p no:cacheprovider`：18 passed。
  - `$env:PYTHONPATH='src'; uv run --no-sync pytest -p no:cacheprovider`：89 passed。
  - `git diff --check`：通过；模板 JSON 解析成功，`project_root` 为 `.`，无 `stack` 字段。

### 2026-07-10 __:__ +08:00 — T3 — ConfigLoader

- 使用的技能：using-superpowers；using-git-worktrees；executing-plans；test-driven-development；karpathy-guidelines；verification-before-completion
- 使用的智能体：OpenAI Codex
- 关键提示词 / 上下文：
  - 用户要求在 `feature/M1` 的 `.worktrees/M1` 中执行已批准的 T3 计划，沿用 M1 单 worktree / 单 PR 策略，不启用子代理。
  - T3 只实现项目级 `project.json` 配置加载；不读取 task state、环境变量、`.env` 或真实凭据。
- 摘要：
  - 新增 `HanCodeConfig` 与 `load_config()`，提供不可变的项目级配置、默认限制、provider / 凭据来源元数据、可写根和可选 task root。
  - `max_context_chars` 与 `max_trace_events` 的批准默认值同步为 24000 / 40。
  - 对损坏配置、非法限制、未知 provider、明文敏感字段、跨平台绝对路径、`..` 与符号链接逃逸返回结构化错误；错误仅含字段名，不回显非法值。
  - `task_id` 仅复用 T2 的 `task_path()` 派生路径，未创建 Task Workspace 或读取 `state.json`。
- TDD 证据：
  - Red/Green-1：默认配置测试先因 `ModuleNotFoundError: hancode.config` 失败，新增最小 dataclass / loader 后通过。
  - Red/Green-2：项目覆盖测试先仍得到 `mock`，加入 JSON 合并后通过。
  - Red/Green-3 至 8：依次验证 workspace 前置条件、损坏 JSON 与字段类型、数值边界/布尔值、provider/credential source、递归明文凭据扫描、可写根及 task 路径逃逸；每项先出现预期失败，再以最小实现转绿。
  - 链接逃逸 fixture 首次将目标放在项目根内，按边界定义不构成逃逸；修正为项目根外的同级临时目录后通过。
- 两阶段评审：
  - Spec 合规：核对 FR-9 与 §10.4，确认项目级加载、默认值、凭据不落盘、结构化错误和路径边界均有测试覆盖；未扩展到 CredentialProvider、StateStore、路由或 ContextBuilder。
  - 代码质量：确认 `Path.resolve()` 与 `PureWindowsPath` 联合处理跨平台路径，敏感错误不包含输入值，静态类型与 lint 均通过；未发现阻塞项。
- 工作流偏离：
  - 无子代理；用户已批准 inline 执行，且当前约束不允许未经明确授权的 delegation。
  - `uv run --extra dev` 首次建立本地开发环境时生成未跟踪 `uv.lock`；该文件不在 T3 范围内，已移除且未提交。
- 提交：
  - `e7fcee3` — `feat: 完成 T3 ConfigLoader`
- 验证：
  - `$env:PYTHONPATH='src'; uv run pytest tests/test_config.py -v -p no:cacheprovider` 通过，25 passed。
  - `$env:PYTHONPATH='src'; uv run ruff check src/hancode/config.py tests/test_config.py --no-cache` 通过。
  - `$env:PYTHONPATH='src'; uv run mypy src/hancode/config.py --cache-dir "$env:TEMP\hancode-mypy-t3"` 通过，no issues found in 1 source file。
  - `$env:PYTHONPATH='src'; uv run pytest -p no:cacheprovider` 通过，72 passed。
- 经验教训：
  - 配置路径的安全判定既要检查字面路径（绝对路径与 `..`），也要检查 `resolve()` 后的真实位置，才能覆盖跨平台字符串与目录链接两类逃逸。
  - 明文凭据防护必须递归扫描字段名，并把错误输出限制为字段名，不能把解析到的值带入异常或日志。

### 2026-07-10 __:__ +08:00 — T2 — Linux CI 路径判定回归修复

- 使用的技能：systematic-debugging；verification-before-completion
- 使用的智能体：OpenAI Codex
- 关键提示词 / 上下文：
  - 用户贴出 GitHub Actions / Linux `make test` 失败输出：`test_workspace_rejects_path_outside_project_root[C:/outside]` 期望 `workspace_path_outside_project_root`，实际得到 `invalid_task_id`。
  - 本轮仅修复 T2 workspace 路径判定的跨平台差异，不扩展 workspace 初始化语义。
- 根因分析：
  - `Path("C:/outside").is_absolute()` 在 Windows 本地返回 `True`，但 Linux / POSIX 语义下不会按 Windows drive absolute path 处理。
  - CI 因此先通过 `Path` 拼接与 `resolve()` 得到仍位于 task root 下的候选路径，随后落入 “包含路径分隔符” 的 `invalid_task_id` 分支。
- 摘要：
  - `src/hancode/workspace.py` 引入 `PureWindowsPath`。
  - `task_path()` 在原有 `Path(task_id).is_absolute()` 基础上增加 `PureWindowsPath(task_id).is_absolute()`，统一拒绝 Windows 风格绝对路径。
- 提交：
  - 未提交；用户明确要求提交交给人类开发者。
- 验证：
  - `$env:PYTHONPATH='src'; uv run --no-sync pytest tests/test_workspace.py -v -p no:cacheprovider` 通过，20 passed。
  - `$env:PYTHONPATH='src'; uv run --no-sync ruff check src/hancode/workspace.py tests/test_workspace.py --no-cache` 通过。
  - `$env:PYTHONPATH='src'; uv run --no-sync mypy src/hancode/workspace.py --cache-dir $env:TEMP\hancode-mypy-t2-ci-fix` 通过，no issues found in 1 source file。
  - `$env:PYTHONPATH='src'; uv run --no-sync pytest -p no:cacheprovider` 通过，47 passed。
- 经验教训：
  - 跨平台路径安全测试不能只依赖当前操作系统的 `Path.is_absolute()`；需要显式处理 Windows drive path 与 POSIX path 的差异。

### 2026-07-10 00:02 +08:00 — T2 — 评审后路径逃逸修复与回归补强

- 使用的技能：systematic-debugging；test-driven-development；verification-before-completion
- 使用的智能体：OpenAI Codex
- 关键提示词 / 上下文：
  - 用户要求按“两阶段评审”先做 spec 合规检查、再做代码质量检查，并在收到评审结论后要求“开始修复”。
  - 评审确认一个真实缺陷和一个测试缺口：`task_path()` 未拒绝 `.hancode/tasks` 经 symlink / junction 逃逸到项目根外；checkpoint / 阶段产物幂等性缺少回归测试。
- 根因分析：
  - `task_path()` 只校验 `candidate` 是否位于已解析 `tasks_root` 下；当 `tasks_root` 自身被目录链接重定向到仓库外时，`candidate` 仍满足该条件，从而绕过 project root 边界。
  - `init_task_workspace` 对 checkpoint / 阶段产物的幂等行为已存在，但此前没有测试锁定，评审只能靠代码阅读确认。
- TDD 证据：
  - Red：`$env:PYTHONPATH='src'; uv run --no-sync pytest tests/test_workspace.py -v -p no:cacheprovider -k "escape_via_link or preserves_existing_checkpoints_and_artifacts"` 失败，`test_workspace_rejects_tasks_directory_escape_via_link` 报 `Failed: DID NOT RAISE HanCodeError`；同批次 `test_task_workspace_init_preserves_existing_checkpoints_and_artifacts` 首次即通过，证明这是覆盖补强而非行为缺陷。
  - Green：`task_path()` 增加 `.hancode` workspace root 内约束后，同一命令通过，2 passed。
- 摘要：
  - 新增目录链接逃逸测试，覆盖 `.hancode/tasks` 被 symlink / junction 重定向到 project root 外的场景。
  - 新增 checkpoint / 阶段产物幂等回归测试，锁定重复 init 不清空既有 evidence。
  - 最小修改 `src/hancode/workspace.py`，仅收紧 `task_path()` 的根边界判断，不扩展 init 语义。
- 人工干预：
  - 用户在看到评审结论后明确要求继续修复。
- 工作流偏离：
  - 未派发 reviewer subagent；原因是当前多代理约束要求只有用户显式要求 delegation 时才允许 spawn，故继续使用 inline 修复与验证。
- 提交：
  - `6d7f894` — `feat: 完成 T2 Workspace 初始化`
- 验证：
  - `$env:PYTHONPATH='src'; uv run --no-sync pytest tests/test_workspace.py -v -p no:cacheprovider` 通过，20 passed。
  - `$env:PYTHONPATH='src'; uv run --no-sync ruff check src/hancode/workspace.py tests/test_workspace.py --no-cache` 通过。
  - `$env:PYTHONPATH='src'; uv run --no-sync mypy src/hancode/workspace.py --cache-dir $env:TEMP\hancode-mypy-t2-fix` 通过，no issues found in 1 source file。
  - `$env:PYTHONPATH='src'; uv run --no-sync pytest -p no:cacheprovider` 在当前 worktree 状态通过，47 passed；该结果包含用户已批准同步到该分支但未并入本次 T2 提交的 `tests/test_course_project_scaffold.py` 变更。
- 经验教训：
  - 只校验“解析后的候选路径在解析后的任务目录下”不足以防止链接逃逸；还必须确认最终路径仍位于 project workspace 根内。
  - 评审发现的“现有行为缺测试”也要补成回归用例，否则后续重构时容易把幂等性悄悄打穿。

### 2026-07-09 22:30 +08:00 — T2 — Workspace 初始化缺口修复

- 使用的技能：test-driven-development；verification-before-completion
- 使用的智能体：OpenAI Codex
- 关键提示词 / 上下文：
  - 用户要求评估 worktree 中的 workspace.py 代码，随后要求接续 T2 任务完成。
  - 评审发现两个阻塞缺口：state.json 缺失 8 个字段（架构文档 §8.4）、init_task_workspace 不幂等。
- 摘要：
  - Red-1：写 `test_task_workspace_state_json_contains_all_required_fields`，验证 state.json 包含全部 18 个字段，失败原因正确（缺失 8 个字段）。
  - Green-1：补齐 `goal`、`checkpoint_seq`、`tests_run`、`test_status_consumed`、`phase_completed`、`source_edits_this_phase`、`rollback_required`、`rollback_done`。
  - Red-2：写 `test_task_workspace_init_preserves_existing_state_and_trace`，失败原因正确（`FileExistsError`）。
  - Green-2：`init_task_workspace` 幂等化——`mkdir(exist_ok=True)` + state/trace/history 只在不存在时写入。
  - 旧测试 `test_task_workspace_initializes_required_artifacts` 的精确等值断言同步更新为完整字段集。
- 人工干预：
  - 用户先要求评估代码，确认缺口后再要求修复。
- 工作流偏离：
  - 未使用 worktree（已在 `codex/workspace-init` worktree 中）；未使用 brainstorming（缺口明确，无需探索）。
- 提交：
  - 未提交
- 验证：
  - `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest -v -p no:cacheprovider` 通过，40 passed。
  - `ruff check src/hancode/workspace.py tests/test_workspace.py --no-cache` 通过。
  - `mypy src/hancode/workspace.py` 通过，no issues found in 1 source file。
- 经验教训：
  - state.json 初始字段必须与架构文档 §8.4 完全对齐，否则 T4 StateStore、T6 WorkspaceRouter、T17 CheckpointManager 都要补字段，破坏幂等性。

### 2026-07-09 21:15 +08:00 — T1 — 共享模型与错误类型返工

- 使用的技能：using-superpowers；brainstorming；writing-plans；using-git-worktrees；test-driven-development；requesting-code-review；verification-before-completion
- 使用的智能体：OpenAI Codex
- 关键提示词 / 上下文：
  - 用户要求“直接按这版 PLAN 返工 T1 代码和测试”。
  - 已先将 `docs/PLAN.md` 与 `docs/SPEC.md` 的错误契约对齐，T1 需改为 `error_code` / `message` / `phase` / `denied_rule` / `suggested_fix`。
  - 本轮只允许返工 `src/hancode/errors.py`、`src/hancode/models.py`、`tests/test_errors.py`、`tests/test_models.py`，不扩到 T2 及后续模块。
- 摘要：
  - 将 `StructuredError` 从旧字段 `code` / `hint` / `details` 返工为 SPEC 顶层字段契约。
  - 保持 `HanCodeError` 包装接口不变，但错误展示文案改为基于 `error_code`。
  - 扩展 `OperationResult.to_dict()` 的递归序列化路径，使嵌套 `Risk`、枚举、tuple/list/mapping 在 `data` 中可稳定导出为 JSON。
  - 重写 T1 测试，使其同时覆盖新错误字段和嵌套共享模型序列化。
- TDD 证据：
  - Red：`$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests/test_errors.py tests/test_models.py -v -p no:cacheprovider` 失败，4 failed；失败原因为 `StructuredError.__init__()` 不接受 `error_code` 等新字段。
  - Green：同一命令在返工后通过，8 passed。
- 评审：
  - Spec 合规检查：确认 `StructuredError` 顶层字段与 `docs/SPEC.md` §10.21.5 一致；解析失败、策略拒绝和工具失败后续可复用同一字段名。
  - 代码质量检查：确认返工只影响 T1 共享模型和对应测试；通过递归 `to_dict()` 避免 `OperationResult.data` 残留不可 JSON 序列化的共享模型对象。
- 工作流偏离：
  - 未创建新 worktree；原因是用户要求在当前工作树直接返工，且目标实现文件在本轮开始时无未提交改动。按当前执行会话保持最小范围修改。
  - 未派发 code-review subagent；原因是当前多代理约束要求只有用户显式要求 delegation 时才允许 spawn，故改为本会话内联两阶段复核。
- 提交：
  - 未提交
- 验证：
  - `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests/test_errors.py tests/test_models.py -v -p no:cacheprovider` 通过，8 passed。
  - `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m ruff check src/hancode/models.py src/hancode/errors.py tests/test_models.py tests/test_errors.py --no-cache` 通过。
  - `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m mypy src/hancode/models.py src/hancode/errors.py --cache-dir $env:TEMP\hancode-mypy-t1-review` 通过，no issues found in 2 source files。
  - `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest -p no:cacheprovider` 通过，27 passed。
- 经验教训：
  - 共享错误模型一旦与上位 SPEC 失配，问题会沿 `ParseError`、`PolicyDecision`、`Feedback`、`ToolResult` 整条链路扩散；必须先收敛字段名，再推进后续任务。
  - 共享结果模型的“可序列化”不能只看顶层字段；嵌套共享 dataclass 也必须在首个任务就被回归测试覆盖。

### 2026-07-09 20:27 +08:00 — DOCS — Python 工具链统一为 uv

- 使用的技能：using-superpowers
- 使用的智能体：OpenAI Codex
- 关键提示词 / 上下文：
  - 用户要求后续包管理统一使用 uv，并查找 Python 相关内容、更新相应文档。
  - 本轮仅更新当前规范、开发指南和未执行任务卡，不修改实现代码、CI 或历史验证事实。
- 摘要：
  - `AGENTS.md`、`README.md` 和安全验证指南增加 uv 环境初始化与质量门禁命令。
  - `docs/SPEC.md` 明确 uv 负责 Python 版本、虚拟环境、依赖、命令执行和包构建。
  - `docs/PLAN.md` 从 T2 起统一使用 `uv run`，T26 增加 `uv.lock`、`uv sync`、`uv build` 和 uv CI 约束。
  - `docs/系统架构.md` 将 Python 包管理器从 pip 收敛为 uv。
  - T1、`docs/SPEC_PROCESS.md` 和既有日志中的旧命令作为真实历史证据保留。
- 工作流偏离：
  - 未使用 brainstorming、worktree、TDD、subagent、code review 和 branch finishing；原因是本轮属于小型文档与开发命令迁移，不修改运行行为。
- 提交：
  - 未提交
- 验证：
  - `uv --version` 返回 `uv 0.11.16`。
  - `uv venv --help`、`uv sync --help`、`uv build --help`、`uv tool install --help` 均确认对应子命令可用。
  - UTF-8 回读全部 6 个目标文档成功，且均包含 uv 约定。
  - 检索确认 `docs/PLAN.md` T2 之后不存在 `python -m pytest/ruff/mypy/build` 或 pip 安装命令。
  - `git diff --check` 通过；本轮未运行代码测试，因为没有修改实现或测试代码。
- 经验教训：
  - 工具链迁移应区分当前规范与历史证据；历史命令必须保留，避免把未实际执行的 uv 命令写成既有验证结果。

### 2026-07-08 19:53 +08:00 — T1 — 共享模型与错误类型

- 使用的技能：using-superpowers；using-git-worktrees；writing-plans；test-driven-development；verification-before-completion
- 使用的智能体：OpenAI Codex
- 关键提示词 / 上下文：
  - 用户要求“现在开始开发，完成 T1，先开辟一个 worktree”，随后修正任务为 T1。
  - 用户要求后续提交信息中冒号后的信息采用中文。
  - 已读取 `AGENTS.md`、`docs/PLAN.md` T1、`docs/SPEC.md`、`docs/agent-guides/workflow.md`、`docs/agent-guides/harness-boundary.md`、`docs/agent-guides/safety-and-verification.md`。
- 摘要：
  - 创建并使用 worktree `D:\agent-leanring\HanCode\.worktrees\t1`，分支为 `codex/t1`。
  - 新增 `src/hancode/models.py`，提供 `Phase`、`TaskStatus`、`OperationStatus`、`Risk`、`OperationResult`。
  - 新增 `src/hancode/errors.py`，提供 `StructuredError` 和 `HanCodeError`。
  - 新增 `tests/test_models.py` 与 `tests/test_errors.py`，覆盖六阶段枚举、任务状态枚举、受限 operation status、结构化错误字段和 JSON 可序列化结果。
  - 新增 `docs/superpowers/plans/2026-07-08-t1-shared-models-errors.md` 作为 T1 执行计划产物。
- TDD 证据：
  - Red：`$env:PYTHONPATH='src'; python -m pytest tests/test_models.py tests/test_errors.py -v` 失败，原因为 `ModuleNotFoundError: No module named 'hancode.errors'`。
  - Green：同一命令通过，8 passed。
- 验证：
  - `$env:PYTHONPATH='src'; python -m pytest` 通过，27 passed；pytest cache 写入 warning 仍存在。
  - `python -m ruff check src/hancode/models.py src/hancode/errors.py tests/test_models.py tests/test_errors.py` 通过；ruff cache 写入 warning 仍存在。
  - 标准 `python -m mypy src/hancode/models.py src/hancode/errors.py` 因 mypy 2.2.0 sqlite cache `disk I/O error` 失败。
  - `$env:PYTHONPATH='src'; python -m mypy src/hancode/models.py src/hancode/errors.py --cache-dir $env:TEMP\hancode-mypy-cache-t1 --show-traceback` 通过，no issues found in 2 source files。
- 人工干预：
  - 用户将任务从 T0 修正为 T1。
  - 用户要求提交信息冒号后采用中文。
  - 用户拒绝提交主 checkout 的 `.gitignore` worktree ignore 配置；该拒绝已遵守，T1 在新 worktree 中继续。
- 工作流偏离：
  - 未 dispatch 独立 subagent，也未使用 executing-plans；原因是用户明确要求当前会话直接开始 T1，并先开辟 worktree。已用本会话执行 `writing-plans` 和 TDD 流程，并保留计划产物。
  - 未派发 code-review subagent；原因是当前多代理工具要求只有用户显式要求 subagent / delegation 时才允许 spawn。改为按 review gate 在本会话执行范围与质量自审。
- 提交：
  - `895065e` — `feat: 完成 T1 共享模型与结构化错误`
- 经验教训：
  - 在 `src/` layout 尚未 editable install 的环境中，T1 测试需要显式 `PYTHONPATH=src` 才能验证本地包。
  - 当前默认 `python` 是 3.10.11，低于项目 3.11+ 目标；后续环境门禁或 CI 任务需要收敛解释器版本。
  - Windows worktree 路径下 pytest / ruff / mypy cache 可能受本地权限或路径语义影响；验证时需要区分代码失败和 cache 写入失败。

### 2026-07-08 17:21 +08:00 — T0 — 冷启动后阶段门收拢与正式开发入口确认

- 使用的技能：using-superpowers；verification-before-completion
- 使用的智能体：OpenAI Codex
- 关键提示词 / 上下文：
  - 用户确认冷启动已经完成，并要求“把文档收拢一下，对于冷启动后开始的工作，做最后的文档完善，然后进入正式开发”。
  - 当前阶段仍只做文档收拢，不修改 `src/hancode/`。
  - 冷启动样本来自 OpenCode + GLM-5.2，对象为 `D:\agent-leanring\demo` 的 T1 / T2 实现。
- 摘要：
  - `AGENTS.md` 的阶段门改为：SPEC / PLAN / 冷启动验证已记录，正式实现可从 `docs/PLAN.md` T1 开始。
  - `docs/agent-guides/workflow.md` 改为冷启动门已完成，并把冷启动发现作为正式实现约束。
  - `README.md` 的项目阶段改为正式实现阶段，列明每个任务必须 TDD、验证、更新 PLAN / AGENT_LOG 并接受审查。
  - `docs/PLAN.md` 的状态改为冷启动后实现准备完成；T1 增加 `OperationResult.status` 边界；T2 增加幂等初始化和 Project Workspace 前置约束；冷启动章节改为结果与正式开发入口。
  - `docs/SPEC_PROCESS.md` 的冷启动结论收口为扩展上下文冷启动验证完成，阶段门不再阻塞实现。
- 人工干预：
  - 用户确认冷启动完成，并要求进入正式开发前做文档收拢。
- 工作流偏离：
  - 未使用 worktree、TDD、subagent 和 finishing-a-development-branch；原因是本轮仍是阶段门后的文档收拢，不是 harness kernel 实现任务。
- 提交：
  - 未提交
- 验证：
  - `Get-Content -Raw -Encoding UTF8` 读取 `AGENTS.md`、`README.md`、`docs/PLAN.md`、`docs/SPEC_PROCESS.md`、`docs/AGENT_LOG.md`、`docs/agent-guides/workflow.md` 成功。
  - `Select-String` 确认正式开发、T1、TDD、扩展上下文冷启动验证、回写约束等关键词已写入。
  - `rg` 未发现 `仍未实际执行`、`正式冷启动验证仍需`、`不得开始完整实现`、`本仓库处于规范和规划阶段` 等旧阻塞表述。
  - `Select-String` 确认 T1 / T2 / T26 的新增约束已写入 `docs/PLAN.md`。
  - `git status --short` 已检查本轮文档修改范围。
- 经验教训：
  - 冷启动验证完成后，必须把发现回写到后续任务卡，否则正式开发会重复 demo 中暴露的设计缺口。

### 2026-07-08 17:13 +08:00 — T0 — OpenCode / GLM-5.2 冷启动验证记录补全

- 使用的技能：using-superpowers；verification-before-completion
- 使用的智能体：
  - 冷启动执行：OpenCode + GLM-5.2
  - 复核与记录：OpenAI Codex
- 关键提示词 / 上下文：
  - 用户说明已使用 OpenCode 搭载 GLM-5.2 进行冷启动验证。
  - 用户说明提供给第二个 agent 的材料为 `系统架构.md`、`SPEC.md`、`PLAN.md`，未提供主开发对话历史或隐藏 memory。
  - 复核对象为 `D:\agent-leanring\demo` 中的冷启动产物。
- 摘要：
  - 第二个 agent 尝试了 T1 共享模型与错误类型、T2 Workspace 初始化。
  - 冷启动产物包含 `src/hancode/models.py`、`src/hancode/errors.py`、`src/hancode/workspace.py` 以及对应测试。
  - 复核验证命令结果：`python -m pytest -p no:cacheprovider` 为 19 passed；`python -m ruff check src tests` 通过；`python -m mypy src` 通过；secret 模式扫描无命中。
  - `docs/SPEC_PROCESS.md` 已补充冷启动记录，明确本次属于“扩展上下文冷启动验证”：额外提供了 `系统架构.md`，因此不能完全等同于课程要求的严格“仅 SPEC + PLAN”版本。
  - 复核发现的主要代码质量问题：workspace 初始化会覆盖已有证据；task workspace 可绕过 project workspace 初始化；`OperationResult.status` 边界过宽；Python 版本目标与 PLAN 不一致。
- 人工干预：
  - 用户指定第二个 agent 与模型，并要求依据课程要求撰写冷启动相关记录说明。
- 工作流偏离：
  - 未创建分支或提交；本轮只补充过程文档。
  - 未把冷启动产物合并到主仓；原因是该产物仍有代码质量问题，且冷启动过程证据不完整。
- 提交：
  - 未提交
- 验证：
  - 已读取 `docs/SPEC_PROCESS.md`、`docs/AGENT_LOG.md`、`D:\agent-leanring\demo` 的源文件和测试文件。
  - 已运行冷启动产物的 pytest、ruff、mypy 和 secret 模式扫描。
- 经验教训：
  - 冷启动验证不仅要看代码能否跑通，还要保存第二个 agent 的上下文、暂停点、误解、红阶段证据和后续修订点。
  - 对 HanCode 这类可复盘 harness，workspace 初始化语义必须优先保护已有 trace、history、state 和学习产物。

### 2026-07-08 16:40 +08:00 — T0 — 规划文档一致性与冷启动验证准备

- 使用的技能：using-superpowers；executing-plans
- 使用的智能体：OpenAI Codex
- 关键提示词 / 上下文：
  - 用户要求“现在进行 PLAN.md 的 P0”；本轮按当前 `docs/PLAN.md` 的前置任务 `T0` 执行。
  - 已读取 `docs/SPEC.md`、课程通用要求、A 类 Harness 要求、`docs/agent-guides/workflow.md` 和 `docs/agent-guides/safety-and-verification.md`。
  - 当前阶段门仍未通过冷启动验证，因此只修订规划、过程和 README 文档，不修改 `src/hancode/`。
- 摘要：
  - `docs/PLAN.md` 统一仓库级文档路径为 `docs/SPEC.md`、`docs/PLAN.md`、`docs/SPEC_PROCESS.md` 和 `docs/AGENT_LOG.md`。
  - `docs/PLAN.md` 的 T0 状态、验证命令和备注对齐“冷启动准备已完成，但正式冷启动仍未执行”的事实。
  - `docs/SPEC_PROCESS.md` 修正冷启动候选任务编号，避免继续引用旧版 T1/T3/T5/T8 任务拆分。
  - `README.md` 的项目阶段和分发说明对齐当前 SPEC：MVP 为 Python package，Docker 仅作可选 MockLLM demo 环境。
- 人工干预：
  - 用户直接要求执行 PLAN 前置任务；未要求创建分支、提交或启动第二个 agent。
- 工作流偏离：
  - 未使用 worktree、TDD、subagent 和 finishing-a-development-branch；原因是本轮是阶段门前的文档一致性修订，不是实现任务。
- 提交：
  - 未提交
- 验证：
  - `Get-Content -Raw -Encoding UTF8` 读取 `docs/PLAN.md`、`docs/SPEC_PROCESS.md`、`docs/AGENT_LOG.md`、`README.md` 成功。
  - `Select-String` 确认 `docs/PLAN.md` 包含 T1、T27、需求追溯、冷启动验证和 `docs/` 路径锚点。
  - `Select-String` 确认 `docs/SPEC_PROCESS.md` 包含 T1/T2/T5/T13/T20 冷启动候选任务和关键迭代 12。
  - `rg -F` 未发现旧任务编号组合、`分发格式为 Docker`、根目录 `SPEC_PROCESS.md` / `AGENT_LOG.md` 引用残留。
  - `git status --short` 显示本轮相关文件已修改；工作区还存在本轮开始前已有的其他未提交修改。
- 经验教训：
  - 冷启动验证前，PLAN 的任务编号和文档路径必须比实现细节更先稳定，否则第二个 agent 会在错误入口受阻。

### 2026-07-08 __:__ — 任务 0 — 架构一致性修订 v1.3

- 使用的技能：Superpowers executing-plans
- 使用的智能体：OpenAI Codex
- 关键提示词 / 上下文：
  - 用户要求按《HanCode 架构一致性修订方案 v1.3》执行。
  - 本轮只修改文档，不修改 `hancode/` 或 `src/hancode/` 实现代码。
  - 已确认三项决策：写入边界由 `PathClassifier` 推导；state 对账不自动回写，进入 `inconsistent`；TraceEvent 事件名以 SPEC 为权威。
- 摘要：
  - SPEC 中移除显式 `target_kind=artifact|source` 强制要求，改为可写 Action 的目标路径由 `PathClassifier` 分类为 artifact / source / protected zone。
  - SPEC TraceEvent 表补齐 `state_reconciled`、`state_inconsistent` 和架构文档使用的生命周期事件。
  - 系统架构文档补齐 CredentialProvider、Config 字段、CLI exit code、`/auth` slash commands、`hancode export`、checkpoint pruning、rollback 副作用、结构化错误、ContextBuilder 限制和 REVIEW / KNOWLEDGE 结构。
  - reconcile 语义改为只检查一致性；发现漂移时标记 `inconsistent`、写 trace、阻止高风险动作，不自动回写 `state.json`。
- 人工干预：
  - 用户提供完整 v1.3 修订方案并要求直接实现。
- 提交：
  - TODO
- 经验教训：
  - 可测试性约定不能引入与架构机制冲突的新字段；写入边界应由单一 `PathClassifier` 机制统一承载。

### 2026-07-08 __:__ — 任务 0 — SPEC 可测试性契约补强

- 使用的技能：Superpowers brainstorming
- 使用的智能体：OpenAI Codex
- 关键提示词 / 上下文：
  - 用户要求关注 SPEC 可测试性，并给出 P0/P1/P2 问题清单。
  - 重点是让 Knowledge、Review、Context、脱敏、性能、CLI 行为具备客观 pass/fail 边界。
- 摘要：
  - 当时草稿中，FR-3 曾补充可写 Action 必须携带 `target_kind=artifact|source`；该方案已在后续 v1.3 修订中被 `PathClassifier` 路径推导替代。
  - §5.1 补充小型项目规模、ContextBuilder、MockLLM demo 和 checkpoint 快照范围的可测阈值。
  - §10 新增 `### 10.21 可测试性约定`。
  - §10.21 集中定义 context include/exclude、secret fixture、Markdown 产物最低结构、REVIEW 覆盖表、结构化错误字段、CLI/TUI 命令矩阵、fake keyring、demo trace 和 Docker 可选测试边界。
- 人工干预：
  - 用户提供完整可测试性评估和建议修订方式。
- 提交：
  - TODO
- 经验教训：
  - Harness SPEC 的可测试性不只看机制能否触发，还要把产物质量、脱敏、错误、上下文和 CLI 行为转化为可断言结构。

### 2026-07-08 __:__ — 任务 0 — SPEC 抽象性清理与架构迁移

- 使用的技能：Superpowers brainstorming
- 使用的智能体：OpenAI Codex
- 关键提示词 / 上下文：
  - 用户指出一致性问题已解决，要求主要处理抽象性问题。
  - 用户强调“开始修改，记住是做迁移而不是删减”。
- 摘要：
  - SPEC 中 `CredentialProvider` Python 接口签名改为能力契约表。
  - SPEC 中具体测试函数名清单迁移到 `docs/系统架构.md` 的 MockLLM 测试架构章节。
  - SPEC 中 `.gitignore` 模板、导出命令形态和 LLM 调用细节迁移到系统架构文档。
  - SPEC 的组件图、实体图和机制模块表补充逻辑层级声明。
- 人工干预：
  - 用户要求迁移而非删减，并确认部分细节可沉淀到系统架构文档。
- 提交：
  - TODO
- 经验教训：
  - SPEC 应作为评分入口和需求契约；系统架构文档承接机制展开；PLAN 承接实现任务和测试函数清单。

### 2026-07-07 __:__ — 任务 0 — SPEC 风险与未决问题补全

- 使用的技能：Superpowers brainstorming
- 使用的智能体：OpenAI Codex
- 关键提示词 / 上下文：
  - 用户要求补充“风险与未决问题”。
  - 通用 SPEC 要求明确预见可能让智能体出问题的环节。
- 摘要：
  - SPEC 新增 `## 12. 风险与未决问题`。
  - 覆盖 Agent 控制流、上下文与记忆、工具与文件安全、checkpoint / rollback、凭据泄露、测试验证和课程项目价值风险。
  - 补充未决问题和 P0/P1/P2 风险优先级。
- 人工干预：
  - 用户确认 §12 草稿后要求写入。
- 提交：
  - TODO
- 经验教训：
  - Harness 风险应围绕智能体失控、机制不可验证、状态不可恢复和凭据泄露展开，而不是停留在普通项目管理风险。

### 2026-07-07 __:__ — 任务 0 — SPEC 领域与机制设计补全

- 使用的技能：Superpowers brainstorming
- 使用的智能体：OpenAI Codex
- 关键提示词 / 上下文：
  - 用户要求继续完成最终 SPEC，并先查看“领域与机制设计”。
  - A 类 Coding Agent Harness 要求 SPEC 独立回答动作 / 工具、客观反馈信号、危险动作和记忆机制。
- 摘要：
  - SPEC 新增 `## 11. 领域与机制设计`。
  - 明确 HanCode 主贡献为 `workspace-scoped course-project memory + reversible coding state`。
  - 集中补充工具类别、反馈信号、危险动作、Project / Task Workspace 记忆机制、代码模块映射和 MockLLM 机制演示。
- 人工干预：
  - 用户确认该节草稿后要求写入。
- 提交：
  - TODO
- 经验教训：
  - A 类 Harness 的评分锚点应集中呈现，不能只分散在功能规约、架构和验收标准中。

### 2026-07-07 __:__ — 任务 0 — SPEC 第 7/10 节评审修订

- 使用的技能：Superpowers brainstorming / receiving-code-review 语境下的 SPEC 修订
- 使用的智能体：OpenAI Codex
- 关键提示词 / 上下文：
  - 用户对 §7 数据模型和 §10 验收标准给出逐项评审。
  - 重点问题包括 TraceEvent 唯一 ID、`state_transition` 语义、Project 附属文档、`files_changed` 时机、WorkspaceRouter / FeedbackBuilder / ResultBuilder 验收标准、状态枚举和 Mock Mode 入口一致性。
- 摘要：
  - SPEC 第 7 节补充 `event_id`、`state_transition`、Project 附属文档和 `files_changed` 更新规则。
  - SPEC 第 10 节新增 WorkspaceRouter、FeedbackBuilder、ResultBuilder 独立验收节，并补充 REPL/TUI slash command、CI unit-test 和风险状态判定。
  - 系统架构文档 MVP 范围同步补充 Python package build 与 CI unit-test 验证要求。
- 人工干预：
  - 用户明确指出结构性问题、一致性问题和小问题，并要求修正后写入。
- 提交：
  - TODO
- 经验教训：
  - SPEC 中出现的每个核心架构模块都应有对应验收标准；状态枚举必须在功能规约、数据模型、结果输出和架构文档中保持一致。

### 2026-07-07 __:__ — 任务 0 — 课程项目定位确认

- 使用的技能：Superpowers brainstorming 语境下的规划确认
- 使用的智能体：OpenAI Codex
- 关键提示词 / 上下文：
  - HanCode 面向学生课程项目，是轻量级 Coding Agent Harness。
  - 核心机制包括 Workspace 分离、Phase Gate、Tool Policy、Trace Logging、Checkpoint Rollback、MockLLM Testing。
  - `.hancode/`、Phase Mode、ContextBuilder、ToolPolicy、Demo 和测试叙事均服务课程项目流程。
- 摘要：
  - README、SPEC、PLAN 使用课程项目定位。
  - `.hancode/` 模板采用 Project Workspace / Task Workspace / Knowledge Delivery 结构。
  - Demo 使用学生成绩统计 CLI 课程项目。
- 人工干预：
  - 用户明确要求最小破坏式修改，不引入复杂 Web UI、数据库、MCP 工具市场或企业级权限系统。
- 提交：
  - TODO
- 经验教训：
  - 课程项目场景要求 Harness 不只控制代码修改，还要沉淀 TEST_REPORT、REVIEW、KNOWLEDGE 和 DELIVERABLES。

### 2026-__-__ __:__ — 任务 0 — 仓库初始化

- 使用的技能：手动初始化 / Superpowers 工作流准备
- 使用的智能体：ChatGPT 指导
- 关键提示词 / 上下文：
  - HanCode 的初始仓库设置。
  - 项目类型：AI4SE 期末项目 A · 编码智能体框架。
- 摘要：
  - 初始化了仓库结构。
  - 添加了文档占位符。
  - 添加了 `.gitignore` 和 `.env.example`。
  - 添加了 Python 打包元数据。
  - 添加了占位测试和 CI 工作流。
- 人工干预：
  - TODO
- 提交：
  - TODO
- 经验教训：
  - TODO
### 2026-07-13 — T19 ContextBuilder

- 使用的技能：`karpathy-guidelines`、`executing-plans`、`test-driven-development`、`subagent-driven-development`。
- 摘要：
  - 新增纯函数 `build_context()` 与 AgentLoop 适配器 `ContextBuilder`，按 phase 组装最小上下文。
  - 新增 `allowed_tools_for_phase()`，从 ToolPolicy 的单一规则矩阵确定性导出 CODE 可用工具。
  - 对 required artifact、course context、checkpoint、trace、task/config 身份和链接路径 fail-closed；可选项目记忆失败写入风险。
  - context 文本、source snippets 和 trace 摘要沿用统一脱敏；预算按确定性顺序省略或截断低优先级段。
  - 新鲜子代理完成两阶段评审，修复 trace 脱敏、CODE writable roots、TEST command 与 checkpoint manifest schema 复用问题。
- 验证：
  - `uv run --no-sync pytest tests/test_context_builder.py -q -p no:cacheprovider`：14 passed。
  - 全量 `pytest -q -p no:cacheprovider`：454 passed、9 skipped；全量 `ruff check src tests` 与 `mypy src` 通过。
- 提交：
  - TODO（等待用户决定提交）。

### 2026-07-13 — T20 FeedbackBuilder 失败分类

- 使用的技能：`karpathy-guidelines`、`executing-plans`、`test-driven-development`、`subagent-driven-development`。
- 摘要：
  - 新增确定性的 `FeedbackReport`、`Observation` 和 `FeedbackBuilder`，覆盖测试、工具、policy denial、parse error、checkpoint 与 rollback 的反馈构造。
  - 测试分类在完整输出上按 syntax、import、assertion、timeout/crash、error exception、成功退出和 unknown 的固定顺序执行；摘要随后脱敏并截断。
  - Observation 深冻结、按 canonical UTF-8 JSON 预算限制；预算不能容纳元数据时返回 `feedback_budget_too_small`，非法预算、phase 或非 JSON 工具输出返回 `feedback_input_invalid`。
  - `ToolResult` 增加 `timed_out`，AgentLoop 仅显式传递当前 phase，未实现 T21 的 retry、rollback 调度、state 或 trace 副作用。
  - 共享脱敏器补充裸 `Bearer <token>`，确保 policy、parse、tool、rollback 等不可信文本不泄露 secret。
- 两阶段评审：
  - 第一阶段发现并修复 timeout 被成功退出码掩盖、分类文档冲突、set 未深冻结和极小预算截断越界。
  - 第二阶段发现并修复裸 Bearer 脱敏、顶层敏感 details 键和公开输入的非结构化异常。
- 验证：
  - `uv run --no-sync pytest -q -p no:cacheprovider`：483 passed、9 skipped。
  - `uv run --no-sync ruff check src tests --no-cache`：通过。
  - `uv run --no-sync mypy src`：通过，19 source files 无问题。
- 提交：
  - TODO（等待用户决定提交）。

### 2026-07-16 — T21 AgentLoop feedback / retry / rollback 修复

- 使用的技能：`brainstorming`、`using-git-worktrees`、`executing-plans`、`test-driven-development`。
- 修复依据：
  - 两个新鲜只读审核发现强制 rollback、AgentLoop trace、checkpoint 元数据一致性和源码写入 fail-closed 边界未闭环。
- 摘要：
  - retry budget 耗尽且存在 checkpoint 时，AgentLoop 进入 review 并强制调用 RollbackManager；rollback 成功后保留 review phase，回滚结果作为 observation 返回。
  - 记录 `test_failed`、`retry_budget_consumed`、`source_write_authorized`、`rollback_started`、`rollback_completed` 等事件，并将 AgentLoop 产生的事件返回给 `AgentRunResult.trace_events`；trace 写入失败会在源码写入前阻断操作。
  - checkpoint 创建后重新加载状态，防止旧 TaskState 覆盖 `latest_checkpoint` 与 `checkpoint_seq`；校验 checkpoint 的 task、phase、pending 状态后才派发源码写入。
  - AgentLoop 对 `write_file` / `edit_file` 强制 checkpoint，不依赖 Policy 漏标；成功写入同步 `files_changed`，写入后的状态持久化异常转换为结构化 `INCONSISTENT`。
- 验证：
  - `uv run --no-sync pytest tests/test_feedback_loop.py -q -p no:cacheprovider`：13 passed。
  - `uv run --no-sync pytest -q -p no:cacheprovider`：497 passed、9 skipped。
  - `uv run --no-sync ruff check src tests --no-cache`：通过。
  - `uv run --no-sync mypy src`：通过，19 source files 无问题。
- 初始实现的剩余风险：
  - 当时尚未覆盖真实文件系统适配层、checkpoint 数量限制和 TOCTOU 锁策略；其中适配层与 workspace 边界已在本轮复审修正，数量限制与外部攻击者级 TOCTOU 仍留给后续任务。
- 提交：
  - 待复审与用户决定提交。

### 2026-07-16 — T21 两阶段复审修正与收尾

- 使用的技能：`karpathy-guidelines`、`test-driven-development`、`executing-plans`。
- 本轮修正：
  - 增加显式 `run(task_id, resume=True)` 恢复入口；默认 blocked 仍 fail-closed，failed / inconsistent 不允许绕过状态门禁，已持久化 completed 状态不会再次调度工具。
  - 上下文构造、checkpoint ID、checkpoint 指针、rollback 结果、tool result、trace event 和 policy decision 增加结构化边界校验；非法结果进入可审计的 blocked / inconsistent 状态。
  - `run_tests` 更新 `tests_run`；source write 仍强制 checkpoint，artifact write 只更新对应 artifact 状态。
  - workspace 拒绝 `.hancode` / task 链接；state 与 manifest 原子写改为同目录独占临时文件，降低临时文件预置/替换风险。
  - feedback、error result、trace、file-tools 使用统一的敏感字段/文本脱敏，覆盖 cookie、credential、private key 和 AWS key 标记。
- 验证证据：
  - `uv run --no-sync pytest tests/test_agent_loop.py tests/test_feedback_loop.py tests/test_feedback.py tests/test_router.py -q -p no:cacheprovider -k 'not real_tool_policy_denial'`：101 passed，1 deselected。
  - `uv run --no-sync ruff check src tests --no-cache`：通过。
  - `uv run --no-sync mypy src`：通过，19 个源文件无错误。
  - 真实文件系统测试受 Windows pytest 临时目录 ACL 阻塞（23 passed，117 个 setup PermissionError）；未将 ACL 阻塞误报为代码通过。
  - 脱敏 smoke：通过；策略 smoke：通过（此前记录）。
- 剩余风险 / 非目标：真实文件系统解析与写入仍存在外部攻击者级 TOCTOU 窗口；checkpoint project_id 未做外部认证绑定；checkpoint 数量 pruning、分布式锁和真实 LLM 不在 T21 范围。
- 提交：未提交，等待最终新鲜两阶段复审与用户后续提交决定。

### 2026-07-16 — T21 最终修正与复审前验证

- 本轮修正：
  - `FilesystemStateStore.reconcile()` 只返回内存中的一致性结果，不自动回写 `state.json`；AgentLoop 启动时记录 `state_reconciled` / `state_inconsistent` 审计事件，漂移状态 fail-closed。
  - AgentLoop 对同一运行内的 trace 序号和 `event_id` 执行连续性校验，同时兼容已有持久化 trace 的首个序号。
  - `append_trace()` 在读取和追加前拒绝 `trace.jsonl` 的 symlink/junction，并增加对应回归测试。
  - 路由器不再信任缺少 `KNOWLEDGE.md` / `DELIVERABLES.md` 的 persisted `completed` 状态，改为 `deliver` 阶段结构化阻断，与 SPEC §10.2 / FR-16 对齐。
  - source write 后的状态持久化失败保留 `rollback_required`；显式 `resume=True` 进入受限 review rollback 恢复通道，不开放 LLM 绕过不一致状态。
  - AgentLoop 校验 TraceAppender 返回的 tool payload；artifact 路径判定绑定当前 task；真实文件系统 rollback 由 AgentLoop 统一写 `rollback_started` / `rollback_performed` 生命周期 trace，避免 manager 与 loop 重复写事件。
  - trace 字符串脱敏复用统一 `file_tools.redact_text()`，覆盖带引号 JSON、cookie 和其他敏感值。
  - 非法或字段类型损坏的 `StructuredError` 在结果边界转换为安全的结构化兜底错误。
  - 增加 trace 序号跳跃和带引号 secret 的回归测试；计划文档明确 write-level checkpoint、resume observation 重放和外部攻击者级 TOCTOU 的范围边界。
- 验证证据：
  - `.venv\Scripts\pytest.exe tests/test_agent_loop.py tests/test_feedback_loop.py tests/test_feedback.py tests/test_router.py -q -p no:cacheprovider -k 'not real_tool_policy_denial'`：106 passed，1 deselected。
  - `.venv\Scripts\ruff.exe check src tests --no-cache`：通过。
  - `.venv\Scripts\mypy.exe src`：通过，19 个源文件无错误。
  - 源码内存 compile：19 个源文件通过。
  - 直接脱敏 smoke：通过；输出未包含 quoted JSON、cookie 或 token 明文。
  - `tests/test_trace.py` 与 `tests/test_agent_loop_adapters.py` 仍受 Windows pytest 临时目录 ACL 阻塞，用例在 setup 阶段无法创建 `.lock`；未把环境失败误报为代码失败。
- 当前非目标 / 剩余风险：
  - checkpoint 仍是单次 source write 粒度，不提供一次 loop 多文件事务聚合；checkpoint pruning、跨进程锁、fsync 耐久性、外部攻击者级 TOCTOU 和 project_id 外部认证绑定留给后续任务。
  - `resume=True` 复用持久化 state/checkpoint/trace，但不跨会话持久化上一次 observation，也不重放完整生命周期上下文。
  - T21 未重构 T16 的完整 phase/context/action 生命周期事件矩阵；当前审计重点是 feedback、retry、rollback 与安全边界事件。
- 提交：`375f735b535c115b2d897adc52da9ae7371bf1c8`（`feat: 完成 T21 AgentLoop 反馈重试回滚集成`）。

### 2026-07-17 — T22 Delivery Artifacts 生成（返工完成，待提交）

- 使用的技能：`karpathy-guidelines`、`executing-plans`、`test-driven-development`、`using-git-worktrees`。
- 摘要：
  - 新增确定性的 `delivery.py`，生成 `TEST_REPORT.md`、`REVIEW.md`、`KNOWLEDGE.md` 和 `DELIVERABLES.md`，并以原子写入同步 `state.json` 的 artifact 标记。
  - 新增 `ResultBuilder` / `DeliveryResult`；最终结果包含需求覆盖、知识项、变更文件、测试状态、checkpoint、rollback、交付物、trace ID、风险与下一步。
  - 交付阶段不修改业务代码；缺测试、缺审查、缺 KNOWLEDGE / DELIVERABLES、测试失败或核心需求未覆盖时，确定性返回 `blocked`，并记录结构化风险。
  - 写入路径拒绝链接，输出统一脱敏；写入和状态同步失败均转换为 `HanCodeError` + `StructuredError`。
- TDD 证据：
  - 初始 `tests/test_delivery.py` 因 `hancode.delivery` 不存在而在 collection 阶段失败（Red）。
  - 新增“DELIVERABLES 必须记录缺测试/审查风险”测试先失败，再以最小实现通过（Red → Green）。
  - 新增“最终结果必须返回需求覆盖与知识项”测试先因接口缺参失败，再以最小接口补全通过（Red → Green）。
  - 新增“交付清单最终状态必须使用核心覆盖证据”测试先因接口缺参失败，再以可选 `coverage` 参数补全通过（Red → Green）。
  - 新鲜复审提出的两项 P1 均先复现为 Red：直接构造的 `Authorization: Basic <credential>` 在结构化结果中泄露凭据；以空 coverage 写入后再以覆盖证据构建结果会使 Markdown 与结构化状态分叉。
  - 最小修复将 Basic 凭据脱敏收口到 T22 输出边界，并把 coverage 的 SHA-256 摘要持久化到 `state.json`；ResultBuilder 对摘要不一致 fail-closed（Red → Green）。旧 state.json 缺少该可选字段时按 `None` 兼容加载，下一次安全保存会写入该字段。
  - 修复后新鲜评审再发现 `AgentRunResult.status` 可覆盖未持久化的最终状态。新增回归先复现该分叉，再让 `write_deliverables()` 在同一原子状态同步中持久化最终状态，ResultBuilder 只从 state 决定状态（Red → Green）。
  - 全量回归曾有两项 Windows junction mock 失败：Python 3.12 的 `Path.is_junction()` 在测试替身缺少 `st_reparse_tag` 时抛出 `AttributeError`。`workspace._is_link()` 将该底层元数据异常按既有安全策略 fail-closed 处理，原有参数化回归由 Red 转 Green。
- 验证证据：
  - `uv run --no-sync pytest tests/test_delivery.py -q -p no:cacheprovider --basetemp '.test-tmp'`：24 passed。
  - `uv run --no-sync ruff check src/hancode/delivery.py src/hancode/state.py tests/test_delivery.py`：通过。
  - `uv run --no-sync mypy src/hancode/delivery.py src/hancode/state.py`：通过。
  - `uv run --no-sync pytest tests/test_workspace.py::test_workspace_rejects_windows_reparse_point_directory_on_python311 -q -p no:cacheprovider --basetemp '.test-tmp-workspace'`：2 passed。
  - `uv run --no-sync ruff check src/hancode/workspace.py tests/test_workspace.py`：通过。
  - `uv run --no-sync mypy src/hancode/workspace.py`：通过。
  - 全量 pytest：573 passed，9 skipped，0 failed。
- 评审状态：
  - 初步新鲜评审已完成并促成状态漂移、Markdown 注入、结果字段与 fail-closed 边界修正；第二阶段新鲜评审继续发现直接构造输出的脱敏缺口。
  - 返工后两阶段自评审完成：第一阶段检查接口、状态一致性、SPEC/PLAN 同步和结构化错误；第二阶段检查链接 fail-closed、溯源、脱敏与全量验证证据；两阶段均无阻塞项。T22 标记为已完成。
- 提交：TODO（等待开发者授权提交）。
- 返工最终验证（2026-07-17）：
  - 专项：`uv run --no-sync pytest tests/test_delivery.py tests/test_state.py tests/test_workspace.py -q -p no:cacheprovider`：75 passed。
  - Lint：`uv run --no-sync ruff check src/hancode/delivery.py src/hancode/state.py src/hancode/workspace.py tests/test_delivery.py tests/test_state.py tests/test_workspace.py`：通过。
  - Type check：`uv run --no-sync mypy src/hancode/delivery.py src/hancode/state.py src/hancode/workspace.py`：no issues found in 3 source files。
  - 全量回归：`uv run --no-sync pytest -q -p no:cacheprovider`：577 passed，9 skipped，0 failed。
  - `git diff --check`：无格式错误。
- 待修复（两阶段评审发现，返工计划 `docs/superpowers/plans/2026-07-17-t22-review-remediation.md`）：
  - SPEC §7.4 未列出 `delivery_coverage_digest` 字段；PLAN T22 未列出 `ResultBuilder.build` / `DeliveryResult` 接口契约。
  - `delivery.py` / `state.py` 的 `_is_link` 未同步 `workspace.py` 的 `AttributeError` fail-closed 修复。
  - `write_knowledge` 未强制至少 1 条 item 有非空 `source_trace_id`（§10.21.4）。
  - `write_deliverables` 缺 `result` 类型防御；blocker / next_steps 文案中英文混用；`_cell` 有冗余换行替换。
- 返工修复（2026-07-17，按返工计划逐任务 TDD 执行）：
  - Task 1（文档同步）：SPEC §7.4 示例新增 `delivery_coverage_digest` 字段与约束；PLAN T22 接口契约补充 `ResultBuilder.build` / `DeliveryResult` 签名与 `to_dict()` 14 个输出键。
  - Task 2（fail-closed 对齐）：`delivery.py` 和 `state.py` 的 `_is_link` 异常子句从 `(OSError)` / `(OSError, RuntimeError)` 统一为 `(AttributeError, OSError, RuntimeError)`，与 `workspace.py` 一致。Red：`test_delivery_link_check_fails_closed_when_junction_probe_is_indeterminate` 和 `test_load_state_fails_closed_when_junction_probe_is_indeterminate` 因 `AttributeError` 传播失败；Green：对齐后 51 passed（delivery + state + workspace junction 回归）。
  - Task 3（KNOWLEDGE 溯源）：`write_knowledge` 在分类完整性检查后新增 `source_trace_id` 非空守卫，`error_code="delivery_knowledge_provenance_required"`。Red：空 trace 集未抛错；Green：2 passed（新守卫 + 既有知识产物回归）。
  - Task 4（输入边界 + 文案清理）：`write_deliverables` 首行新增 `AgentRunResult` 类型守卫，`error_code="delivery_result_invalid"`，断言 state 不变；`_delivery_blockers` coverage digest 不一致消息改为中文；`_next_steps` 两条英文建议翻译为中文；`_cell` 删除冗余 `.replace("\n", " ")`。Red：`test_write_deliverables_rejects_non_run_result` 因 `AttributeError` 失败；Green：27 passed（含文案断言更新）。
  - #6 双重 state 加载保留为写入前重校验（fail-closed 边界），不删除。
  - #9 三处 `_is_link` 重复实现已对齐异常语义；跨六模块共享 helper 抽取列为后续技术债，不在本返工扩大范围。

### 2026-07-17 — T23 MockLLM 机制 Demo（实现与评审前验证）

- 使用的技能：`brainstorming`、`writing-plans`、`executing-plans`、`test-driven-development`、`systematic-debugging`、`requesting-code-review`。
- 任务范围：仅实现 `examples/broken_project/`、`scripts/demo_mock_loop.py` 与 `tests/test_mock_demo.py` 的离线、确定性机制演示；不改 AgentLoop/T21/T22 核心实现，不接真实 LLM、网络或凭据。
- Red → Green 证据：
  - 初始 `tests/test_mock_demo.py` 因 fixture 不存在失败；创建 fixture 后因 demo 脚本不存在再次失败。
  - 初版集成触发 `trace_event_invalid`：`CheckpointManager` 会向持久 trace 追加事件，而单次 AgentLoop 的内存 trace 仍要求局部连续序号。经诊断，在 demo 边界加入 `_DemoTraceAppender`：持久化仍交给文件系统 trace appender，返回给 loop 的仅是本次子运行的局部连续序号；最终结果重新加载持久 trace。
  - 初版 delivery 后仍是 `blocked`：T22 按 persisted state fail-closed，不会自动提升被阶段上限阻断的状态。demo 只在已完成恢复与测试之后显式进入 deliver，再调用 T22 写入器，保持 T22 既有边界不变。
  - 新增“最终 TEST_REPORT 包含真实 unittest 输出 `Ran 1 test`”断言，初版因以 trace 状态合成 `OK` 而失败；`_record_test_evidence()` 改为返回本次 `ToolResult` 的真实分类报告，并直接传给交付写入器后通过。
- 实现摘要：
  - fixture 包含不可修改的 `assignment.md`、最初抛出异常的 `calculator.py` 与标准库 `unittest`。
  - 固定 MockLLM 序列真实触发 protected-write policy denial、source-write checkpoint、两次失败测试、`assertion_failure` 反馈、retry budget 消耗与 rollback；随后以正确实现恢复并通过测试。
  - `_DemoTestRunner` 用固定 argv、`shell=False`、2 秒超时执行本地 `unittest`；6 个 T22 交付物和最终 `ResultBuilder` 输出均来自该运行。
  - 非 fixture 根目录返回 `mock_demo_fixture_required`；未预期异常收口为 `mock_demo_internal_error`，保留 trace 和 blocked state。
- 评审前验证：
  - `uv run --no-sync pytest tests/test_mock_demo.py -q -p no:cacheprovider --basetemp '.test-tmp-t23-r2-green'`：8 passed。
  - `uv run --no-sync ruff check scripts/demo_mock_loop.py tests/test_mock_demo.py --no-cache`：通过。
  - `MYPYPATH=src uv run --no-sync mypy scripts/demo_mock_loop.py tests/test_mock_demo.py --no-incremental`：no issues found in 2 source files。
  - `uv run --no-sync python scripts/demo_mock_loop.py`：退出码 0，输出 `completed`，包含 6 个交付物、checkpoint、rollback 和 69 个持久 trace ID。
- 待办：完成两阶段互相独立的新鲜评审、处理重要问题并做全量验证；尚未提交。

- 两阶段新鲜评审与返工：
  - 第一阶段发现任意 blocked→deliver 绕过、失败结果含虚拟 trace、fixture 可被篡改及 trace 因果测试不足。新增预期 delivery gate allowlist、失败只返回持久 trace、fixture SHA-256/链接/清单校验和对应 Red→Green 回归。
  - 第二阶段进一步要求 gate 校验 `phase=review` 与 `denied_rule=max_steps_limit`；fixture 复制时排除 pytest bytecode cache、传入根仍严格拒绝额外文件；专项回归更新为 8 passed。
  - 最终验证：全量 `uv run --no-sync pytest -q -p no:cacheprovider --basetemp '.test-tmp-t23-postreview-full'`：585 passed，10 skipped；ruff、mypy、离线 demo 与 `git diff --check` 均通过（见本条此前记录）。
  - 状态：T23 已完成，尚未提交，等待开发者授权。

### 2026-07-17 — M6 CI 跨平台 junction 测试夹具修正

- Linux CI 的 `python -m pytest` 首次暴露两个测试夹具错误：Python 3.11 POSIX 的 `pathlib.Path` 没有 `is_junction`，测试在验证 fail-closed 行为前就因 monkeypatch 默认 `raising=True` 失败。
- 将 `tests/test_delivery.py` 与 `tests/test_state.py` 的 `is_junction` monkeypatch 改为 `raising=False`，只在测试运行时注入缺失探针；生产代码仍通过 `getattr` 和异常捕获保持跨平台 fail-closed 语义。
- 验证：两个 junction 回归测试 2 passed；全量 pytest 585 passed、10 skipped；ruff、mypy、`git diff --check` 通过。

### 2026-07-18 — M7 基线 fixture 换行摘要修正

- Red：M7 基线验证发现 T23 的 6 个测试失败，结果为 6 failed、579 passed、10 skipped；失败点均为 `scripts/demo_mock_loop.py::_validate_fixture` 的 fixture SHA-256 校验。
- 根因：Windows 工作树启用了 `core.autocrlf=true`，Git 将 fixture 的 LF 转换为 CRLF；校验直接对原始字节摘要，因换行差异将合法工作树误判为 fixture 被篡改。
- Green：`scripts/demo_mock_loop.py` 新增 `_fixture_digest`，在计算摘要前将 CRLF 规范化为 LF；保留既有 canonical digest，不改变 fixture 内容、安全边界或 demo 行为。
- 验证：T23 专项 8 passed；全量 pytest 585 passed、10 skipped；ruff、mypy、`git diff --check` 均通过。
- 范围：仅修正跨平台 fixture 校验兼容性；未扩展 M7 功能范围。

### 2026-07-18 — T24 CLI 最小入口实施、评审与返工

- 前置：基线 fixture 换行修复已独立提交为 `a48d57d`，T23 专项复验 `8 passed`。
- Task 1 Red→Green：测试首次导入 `hancode.demo` 得到预期模块缺失；runner 迁入 `src/hancode/demo.py`，固定 fixture 放入 `src/hancode/_demo_fixture` 并声明为 package data，`scripts/demo_mock_loop.py` 改为薄入口；T23 demo 专项 `9 passed`。
- Task 2 Red→Green：CLI 首次导入 `hancode.cli` 得到预期模块缺失；新增 Typer `help/init/demo`、结构化 JSON 输出和稳定退出码；修正 `typer.Exit` 被宽泛异常捕获的问题；CLI 专项 `9 passed`。
- Task 3 Red→Green：export 首次导入 `hancode.export` 得到预期模块缺失；新增 state 驱动的六类 delivery artifact 导出、staging 原子目录、防覆盖和 fail-closed 错误；CLI + export 联合专项 `13 passed`。
- 第二阶段评审发现 export 目标父目录 symlink/junction 未被检查；新增逐级路径组件检查与回归测试，先 Red 后 Green（父目录链接测试 `1 passed`），关闭 Important。补充 JSON 键顺序和 Typer 缺参 exit code 回归。
- 分发验证：`uv build --wheel` 成功，wheel 包含 `hancode/cli.py`、`hancode/demo.py`、`hancode/export.py` 和三份 `_demo_fixture`。
- 最终验证：T24 三模块专项 `23 passed`；全量 `pytest` `598 passed、11 skipped`；Ruff 全量通过；Mypy `src scripts/demo_mock_loop.py` 为 `Success: no issues found in 24 source files`；help 与脚本 demo 冒烟均返回 0；`git diff --check` 通过。
- wheel 初次构建发现宽泛 package-data glob 会收集 fixture 测试产生的 `__pycache__`；改为 `_demo_fixture/*.md`、`_demo_fixture/src/*.py`、`_demo_fixture/tests/*.py` 三类明确模式后重新构建，无 warning，wheel 未包含缓存文件。
- 最终复验：全量 `pytest` `600 passed、11 skipped`；Ruff、Mypy 和 wheel 构建均通过。
- 范围：T24 仅实现 `help/init/demo/export`；`auth` 留给 T25，通用 `run`、REPL/TUI 和真实 provider 不在本任务范围。
- 提交：`e272991`（`feat: 完成 T24 CLI 最小入口`）；随后以文档提交补齐本任务的 hash 追踪。

### 2026-07-18 — T25 CredentialProvider 实施、两阶段评审与返工

- 采用规范：用户指定的 M6 `AGENTS.md`、`karpathy-guidelines`、`test-driven-development`、`requesting-code-review`；工作区为 `feature/M7`，只处理 T25，不实现 T26/T27、真实 Provider、TUI/REPL 或企业级 secret manager。
- 目标与边界：建立 `CredentialProvider` 作为唯一凭据访问边界；支持 `keyring → env → dotenv → missing` 状态优先级；keyring-only 写入/清除；CLI `auth status/login/update/clear --provider`；所有 status、错误、stdout/stderr 均不输出真实 secret。
- TDD Red → Green：
  - 核心测试先因 `hancode.credentials` 不存在而在 collection 阶段失败；新增最小 `CredentialStatus`、`SecretStore`、`CredentialProvider` 与三个 wrapper 后专项转绿（12 passed）。
  - CLI 测试先因 root help 缺 `auth`、模块无可替换 provider 和命令不存在得到 8 项失败；接入 auth 子命令后核心+CLI 为 29 passed。
  - 第一阶段评审问题逐项先 Red 后 Green：keyring 读取故障结构化、unknown/mock/local 在 prompt 前拒绝、clear confirmation 与 env/dotenv 外部来源保护、真实 dotenv symlink/解码边界；34 passed、1 skipped。
  - 第二阶段对抗评审问题逐项先 Red 后 Green：`PasswordDeleteError` 不再误报成功、loader 异常统一脱敏、Unicode 控制字符 mask、真实 prompt/confirm 输出通道；最终专项 41 passed、1 skipped。
- 实现摘要：
  - `CredentialStatus` 使用 frozen slots dataclass，status 只返回 `configured/provider/source/masked_id`；mask 仅保留最后四个安全可打印字符。
  - keyring 使用 service `hancode`、account `provider`；写入失败不回退写 `.env`；env/.env 只读，clear 对外部有效来源返回 `credential_external_source_requires_manual_clear`。
  - dotenv 拒绝 symlink/非普通文件、异常或非 Mapping/非字符串 loader 返回；底层异常不穿透，不回显路径、内容或异常文本。
  - CLI 的 provider 先校验再 prompt；prompt 和自定义 confirmation 写 stderr，机器结果保持 stdout 单一 JSON；不存在 `--secret` 明文参数。
- 文档同步：更新 `docs/SPEC.md` 的 auth 命令形态与外部来源 clear 边界；更新 `docs/PLAN.md` T25 接口、测试、实现决策、评审和验证记录；实现提交为 `07f67af`。
- 新鲜评审：第一阶段 4 个 Important；第二阶段 1 个 Critical + 4 个 Important + 2 个 Minor；返工后新鲜复核 Critical / Important / Minor 均 0，结论 clean。
- 验证证据：
  - 专项：`uv run --no-sync pytest tests/test_credentials.py tests/test_cli.py -q -p no:cacheprovider` 等价本地命令最终 `41 passed, 1 skipped`。
  - 静态检查：Ruff T25 文件通过；MyPy `credentials.py` / `cli.py` 通过。
  - 全量回归：串行 `pytest -q -p no:cacheprovider` 为 `632 passed, 12 skipped`；并行运行时既有 T23 demo 的固定 2 秒 subprocess 曾出现 1 个资源竞争超时，串行复验通过。
  - 其余门禁：`uv build` 成功生成 sdist/wheel；`.venv\Scripts\hancode.exe --help`、`auth --help` 返回 0；`hancode demo --provider mock` 在将 `TEMP/TMP` 指向 M7 可写 runtime 临时目录后返回 `completed`；`git diff --check` 通过。
- 人工干预与剩余风险：当前 Windows 环境不允许创建 symlink 时 symlink 用例跳过；真实 OS keyring 不在测试中调用；env/.env 清除必须由用户在外部源手动完成；宿主用户 Temp ACL 会影响 T23 demo，需要可写 TEMP/TMP；ProviderAdapter/真实 LLM 凭据消费留给后续任务。
- 提交：`07f67af`（实现）；文档追踪提交待创建。

### 2026-07-18 — T26 Package Build 与 CI

- 使用的技能：`writing-plans`、`executing-plans`、`subagent-driven-development`、`test-driven-development`、`systematic-debugging`、`requesting-code-review`。
- 任务范围：仅完成 Python package 锁文件、Makefile uv 命令、GitHub/GitLab CI、配置契约测试和过程证据；不实现 Docker、真实 LLM smoke、部署、README 或 Harness Core 变更。
- TDD Red → Green：
  - 新增 `tests/test_package_metadata.py` 与 `tests/test_ci_config.py` 后，初始专项为 6 failed、2 passed：缺 `uv.lock`、Makefile 仍调用系统 Python、GitHub CI 使用 pip editable 安装、GitLab CI 缺失。
  - 最小实现生成 `uv.lock`，Makefile 切换到 `uv run`，两个 CI 使用 Python 3.11、固定 `uv==0.11.8`、`uv sync --locked --extra dev`，并运行 pytest、Ruff、MyPy、build、源码 CLI 与离线 Mock Demo；专项转为 9 passed。
  - 第一阶段新鲜评审指出 `uv build` 后的 `uv run hancode` 仍是源码 editable 安装，不能覆盖 wheel 目标机安装。新增 wheel smoke 配置断言先 Red，随后两个 CI 都创建独立 Python 3.11 venv、安装 `dist/*.whl` 并运行 help / Mock Demo，专项转为 10 passed。
  - 第二阶段新鲜评审提出 wheel venv 不应落在工作区、配置测试应校验命令顺序。新断言先因 CI 使用 `.ci-wheel-venv` 失败；最小修复改用 `$RUNNER_TEMP` / `$CI_BUILDS_DIR`，并断言 `uv sync` 在质量门禁前、`uv build` 在 wheel 安装前，专项转为 11 passed。
- 两阶段新鲜评审：
  - 第一阶段 Important：wheel 未真实安装验证、`.t26-runtime/` 未清理；前者以独立 wheel venv CI smoke 修复，后者在最终验证后定点删除。
  - 第二阶段：Critical 0 / Important 0 / Minor 2；两个 Minor 均已按 TDD 处理为 CI 临时目录和顺序契约，随后由最终全量验证确认。
- 验证证据：
  - `uv lock --check` 与 `uv sync --locked --extra dev`：通过，检查 31 个 package。
  - `uv run --no-sync pytest tests/test_package_metadata.py tests/test_ci_config.py -q -p no:cacheprovider`：11 passed。
  - 全量 `uv run --no-sync pytest -q -p no:cacheprovider --basetemp '.t26-final-runtime\\pytest'`：643 passed、12 skipped。
  - `uv run --no-sync ruff check src tests scripts`：All checks passed。
  - `uv run --no-sync mypy src`：Success: no issues found in 24 source files。
  - `uv build`：成功生成 `hancode-0.1.0.tar.gz` 与 `hancode-0.1.0-py3-none-any.whl`。
  - 源码环境和独立 Python 3.11 wheel 环境均通过 `hancode --help` 与 `hancode demo --provider mock`，Demo 返回 `status=completed`。
  - `git diff --check`：通过；构建、wheel、pytest、uv cache 临时目录已清理。
- 人工干预与环境说明：普通沙箱在 setuptools editable/wheel 构建及 pytest 临时目录清理时返回 `PermissionError`；使用位于 worktree 的受控临时目录并以非沙箱复验成功。该环境限制未改变 package、CI 或安全边界。
- 提交：`e18c71f`（实现）；文档追踪提交待创建。

### 2026-07-18 — T27 README 运行与分发文档实施

- 范围：仅更新 README、README 契约测试和过程文档；不修改生产 Python、CI、SPEC 核心契约、`.env.example`、真实 Provider、REPL/TUI、WebUI 或 Docker。
- TDD Red：新增并收紧 `tests/test_readme.py` 后，使用工作树内 `UV_CACHE_DIR` 执行专项，结果为 `4 failed、1 passed`。宿主默认 uv cache 首次因 ACL 返回 `拒绝访问`，改用 `.t27-runtime/uv-cache` 后进入 pytest，失败原因符合预期。
- TDD Green：README 增加 headless CLI 和 Harness 机制、实际 CLI 命令、Python 3.11+ 源码/wheel 安装、`uv tool install`、MockLLM 无真实凭据运行方式、keyring/env/dotenv 边界、`.env` 明文风险、已知限制和完整验证命令；专项结果为 `6 passed`。
- 人工干预：首个实现子代理未返回验证报告，主代理检查其草稿后发现契约测试过弱，先补强测试取得 Red，再以最小文档变更转 Green；未扩大任务范围。
- 当前状态：专项 Green 已取得；全量回归、Ruff、MyPy、build、独立 wheel smoke、两阶段新鲜评审和临时文件清理待完成后回填。

### 2026-07-18 — T27 第一阶段评审与测试契约加固

- 第一阶段新鲜评审：README 的 Spec Compliance 通过；Task quality 发现 1 个 Important，指出 README 测试主要是宽泛 substring 存在性断言，未验证 wheel 命令分区、未实现能力的区域边界和 secret-like 文本。
- 返工 Red：新增分区解析、当前可用命令负向断言、wheel 裸命令正向断言和 secret-like 文本扫描后，专项结果为 `1 failed、7 passed`；失败原因是 README 尚无 `### wheel 安装后的命令` 分区标题。
- 返工 Green：补充 wheel 安装命令分区标题，专项结果为 `8 passed`。
- 范围：仅强化 README 测试和对应文档标题；未修改生产 Python、CI 或 SPEC 核心契约。第二阶段新鲜评审待执行。

### 2026-07-18 — T27 第二阶段评审、Temp ACL 诊断与修正

- 第二阶段新鲜评审发现：在当前受限沙箱按 README 执行 `uv run --no-sync hancode demo --provider mock` 返回 `cli_internal_error`，并指出 PLAN 状态仍为“未开始”、Anthropic secret-like 扫描不足、init/export 行为边界说明不足。
- 根因调查：默认系统 Temp 和工作树临时目录中的 Python `TemporaryDirectory` 都能创建目录但不能写入/清理内容，复现 `PermissionError: [Errno 13]` / `WinError 5`；这是宿主沙箱 ACL，不是 Demo 命令或 fixture 逻辑错误。
- 对照验证：以受控权限运行同一 MockLLM 命令返回结构化 `status=completed`，证明正常可写 Temp 环境下 README 命令可用；未越界修改 `src/hancode/demo.py`。README 增加 `TEMP/TMP` 可写前提、`cli_internal_error` 诊断提示和已知环境限制。
- TDD Red：加入运行环境与 init/export 文档契约后专项为 `2 failed、8 passed`；修正 Markdown 反引号测试断言后再次得到 `1 failed、9 passed`；补齐文档后 Green 为 `10 passed`。
- 修正内容：secret 扫描加入 `sk-ant-`，环境变量检查改为禁止带值赋值；README 增加 init/export 的实际边界；PLAN 状态改为 `[~] 进行中（待最终验证）`。
- 第二阶段复审结论：此前的环境阻塞已通过“明确前提 + 正常权限对照验证”处理；全量门禁、最终复审复核、临时清理和最终提交 hash待完成。

### 2026-07-18 — T27 最终验证与完成

- 最终 README 专项：`uv run --no-sync pytest tests/test_readme.py -q -p no:cacheprovider`，`10 passed`。
- 全量回归：`uv lock --check` 通过；全量 pytest 为 `653 passed、12 skipped`。
- 质量门禁：Ruff `All checks passed!`；MyPy `Success: no issues found in 24 source files`；`git diff --check` 通过。
- 分发验证：`uv build` 成功生成 wheel/sdist；源码环境和独立 Python 3.11.15 wheel venv 均通过 `hancode --help` 与 `hancode demo --provider mock`，Demo 返回 `status=completed`。wheel 安装阶段仅出现上游依赖元数据版本规范化 warning，无命令失败。
- 两阶段评审：第一阶段 Important 已返工并复审通过；第二阶段评审提出的 Temp ACL、PLAN 状态、secret 扫描和 init/export 文档边界均已修正，第二阶段复审最终 Critical/Important/Minor 均为 0。
- 清理：删除本任务生成的 `.t27-runtime`、`.t27-final-runtime`、`.superpowers`、build/dist/egg-info 和缓存文件；工作树最终只保留提交内容。
- T27 主实现与修正提交：`f0a1d29`、`187365b`、`81151dc`；最终文档追踪提交另行记录。

### 2026-07-18 — T21-R1 内置工具与 pending 恢复收尾（评审前）

- 任务边界：继续在 `feature/M7` 实现 T21-R1；不实现真实 Provider、REPL/TUI、`hancode run`、Docker、通用 shell、pruning、多 checkpoint 事务或多文件 patch。实现由主 agent 完成，子代理只保留给后续两阶段新鲜评审。
- Task 1 文档契约：`docs/PLAN.md` 回填 Task 2 提交 `78acbe7`，切换到 `feature/M7` 并补充 T21-R1 接口；`docs/SPEC.md` 与 `docs/系统架构.md` 同步 `aborted` 生命周期、显式 `resume=True` 恢复边界和当前受限测试执行契约。
- Task 2 Red→Green：共享 `path_security.py` 由 FileTools、PathClassifier、CheckpointManager 共用，新增 certificates/keys、证书后缀和精确凭据名回归；路径别名先 Red 后收紧为 lexical + canonical 双重保护。路径与课程文件专项通过。
- Task 3 Red→Green：新增 `abort_pending_checkpoint()`、`reconcile_pending_checkpoint()` 和 `pending | committed | rolled_back | aborted` manifest 状态；未修改 pending 自动 abort，已变化 pending 普通启动进入 `inconsistent + rollback_required`，显式恢复只处理已预检快照，成功后保持 `blocked` 等待本次 resume。补充快照 hash、manifest、snapshot link 损坏时零业务文件写入与 recovery trace。
- Task 4 Red→Green：新增精确 `edit_file()`，唯一匹配、UTF-8、路径/凭据/目录边界和同目录原子替换；`write_file()` / `edit_file()` 的失败 mutation 标记区分 `False` 与替换阶段不确定的 `None`，并验证 CRLF 字节保持。
- Task 5 Red→Green：新增受限 `run_tests()` 和 `build_default_tool_registry()`，仅使用配置命令、固定 argv/cwd、`shell=False`、捕获输出和 120 秒超时；命令/stdout/stderr 脱敏；默认注册 read/list/search/write/edit/run 六个工具，Mock Demo 通过注入测试工具复用装配。
- Task 6 Red→Green：AgentLoop 接入显式 pending 恢复授权、abort 补偿和状态重载；可证明未写入的 checkpointed tool failure 会 abort 并继续反馈，`mutation_applied=None/True`、abort 或 state reload 失败均保持 inconsistent；run_tests 的脱敏配置命令进入 state.tests_run 和 trace。
- 过程修正证据：变更专项首次暴露旧的 `ToolResult` 断言、无关 inconsistent 状态被误清除、create-only checkpoint 缺少 `files/` 目录和工作树初始化断言未包含新 state 字段；均按 Red→Green 修正并回归。
- 评审前新鲜验证：变更专项 `tests/test_checkpoints.py tests/test_file_tools.py tests/test_feedback_loop.py` 为 `138 passed、7 skipped`；全量 `uv run --no-sync pytest -q -p no:cacheprovider` 为 `711 passed、13 skipped`；Ruff 全量通过；MyPy `src` 无问题；`compileall` 和 `git diff --check` 通过。
- 当前状态：实现与门禁已完成，第一阶段新鲜评审、修复后的专项复验、第二阶段新鲜评审、最终清理和 T21-R1 提交尚未完成。

### 2026-07-18 — T21-R1 评审返工：隐藏凭据后缀与 PEM 脱敏

- 根因：`PurePosixPath(".pem").suffix` 为空，导致 `.pem`、`.key`、`.crt` 等后缀本身作为文件名时未命中敏感路径规则；`redact_text()` 既没有 PEM 私钥块规则，也没有移除私钥正文和 BEGIN/END 标记。
- Red：新增 PathClassifier/FileTools 对隐藏凭据后缀的拒绝测试，以及 `PRIVATE KEY`、`RSA PRIVATE KEY`、`OPENSSH PRIVATE KEY`、`ENCRYPTED PRIVATE KEY` 的 PEM 脱敏测试；修复前直接专项结果为 `4 failed`。
- Green：敏感路径判定增加“文件名等于敏感后缀”的分支；`redact_text()` 在其他通用规则前完整替换 PEM 私钥块；新增安全回归结果为 `7 passed`。
- 环境记录：带 `tmp_path` 的专项测试受宿主 Windows Temp ACL 阻断，曾出现 pytest 临时目录 `PermissionError`；未将该环境错误当作代码结果，完整专项和最终门禁仍待在可写临时目录中重新验证。

### 2026-07-18 — T21-R1 评审返工后全量验证

- 开发者在 `feature/M7` 使用独立可写临时目录 `C:\Temp\HanCode-t21r1` 重新执行全量门禁。
- 安全专项：`7 passed`。
- 全量 pytest：`724 passed, 13 skipped in 30.69s`。
- 质量门禁：Ruff `All checks passed!`；MyPy `Success: no issues found in 27 source files`；compileall 退出码 0；`git diff --check` 通过。Git 输出的 LF/CRLF 为行尾转换提示，不是 diff 错误。
- 当前状态：代码修复及全量验证已有证据；两阶段新鲜评审、评审结论回填、最终清理和 T21-R1 提交仍待完成。

---

### 2026-07-20 — Stage 0 — 固化现有内核基线

- 使用的技能：test-driven-development、requesting-code-review
- 使用的智能体：OpenCode Codex
- 关键提示词 / 上下文：用户要求进行阶段 0 固化，包括整理能力矩阵、固化内核接口、补回归测试、统一错误模型、建立端到端 Mock 测试、更新文档。
- 实现摘要：
  - 整理能力矩阵：将 PLAN.md §8 中 FR-1~FR-16 全部标记为 [x]。
  - 固化内核接口：确认 interfaces/cli.py 只委托 app/* 服务，不直接访问 storage/tooling；确认 providers/mock.py 纯内存无文件访问。
  - 统一错误模型：确认所有核心模块使用 StructuredError（core/errors.py），ToolPolicy/Workspace/Trace/Checkpoint/Rollback 均返回结构化错误。
  - 补回归测试：新增 tests/test_kernel_baseline.py（11 个测试），覆盖 CLI 边界、Provider 隔离、错误结构化、Phase 门禁、Router 纯函数、MockLLM 控制流。
  - 端到端 Mock 验证：hancode demo --provider mock 返回 completed，生成全部 6 个交付产物和 68 条 trace 事件。
- 验证结果：
  - 全量 pytest：751 passed, 13 skipped in 37.41s（基线 740，新增 11 个测试）
  - Ruff：All checks passed!
  - MyPy：Success: no issues found in 53 source files
  - hancode demo --provider mock：status=completed，包含 policy denial、checkpoint、测试失败、retry、rollback、delivery
- 内核接口说明：
  ```
  Presentation Layer (interfaces/cli.py)
    -> 仅委托 app/* 服务，不直接访问 storage/tooling/runtime
  Application Layer (app/*)
    -> 委托 runtime/engine、storage/workspace、app/credentials
  Core Harness Layer (core/, runtime/, policy/, storage/, tooling/)
    -> 所有错误通过 StructuredError 返回
    -> 不依赖 TUI、CLI 或真实 LLM
  Provider Layer (providers/)
    -> MockLLM 纯内存，不访问文件系统
    -> factory 只支持 "mock"，其他抛出 NotImplementedError
  ```
- 未完成项：T21-R1 仍有待提交；hancode run、TUI、真实 Provider 尚未实现（属后续阶段）。

---

### 2026-07-20 — Stage 1 — Headless 任务生命周期与 CLI 入口

- 使用的技能：test-driven-development
- 使用的智能体：OpenCode Codex
- 关键提示词 / 上下文：用户要求实现阶段一，扩展现有 TaskService 为任务生命周期应用服务，新增 CLI task 命令组和根级 run 命令。不新增 TaskController，不修改 AgentLoop 内核。
- TDD 实现顺序：
  - S1-1：Workspace 支持 goal（init_task_workspace 新增 goal 和 allow_existing 参数，新增 list_task_ids 函数）
  - S1-2：任务枚举和 ID 分配（_next_task_id 顺序编号算法）
  - S1-3：TaskSummary 和 TaskService 生命周期（新增 task_models.py，扩展 TaskService 的 create/get/list_tasks/resume）
  - S1-4：CLI task 命令组（task create/run/resume/status/list）
  - S1-5：根级 run 命令（create + run 组合流程）
  - S1-6：Provider 和异常边界（factory 将 NotImplementedError 转为 HanCodeError）
- 实现摘要：
  - 新增 src/hancode/app/task_models.py：TaskSummary 和 TaskRunSummary 应用层数据模型
  - 修改 src/hancode/app/task_service.py：扩展为完整任务生命周期服务（create/get/list_tasks/run/resume）
  - 修改 src/hancode/storage/workspace.py：init_task_workspace 支持 goal 和 allow_existing；新增 list_task_ids
  - 修改 src/hancode/interfaces/cli.py：新增 task 命令组和根级 run 命令
  - 修改 src/hancode/providers/factory.py：未实现 Provider 返回结构化错误
  - 新增 tests/test_task_service.py（18 个测试）
  - 新增 tests/test_cli_tasks.py（16 个测试）
  - 新增 tests/test_provider_factory.py（3 个测试）
  - 修改 tests/test_workspace.py（8 个新测试）
  - 修改 tests/test_structure_layers.py（适配新错误类型）
- 验证结果：
  - 全量 pytest：796 passed, 13 skipped in 38.17s（基线 751，新增 45 个测试）
  - Ruff：All checks passed!
  - MyPy：Success: no issues found in 54 source files
  - CLI smoke：
    - hancode --help 显示 init/demo/export/run/auth/task 六个命令
    - hancode task --help 显示 create/run/resume/status/list 五个命令
    - hancode task create "goal" 创建任务并持久化 goal
    - hancode task status task-001 返回结构化任务摘要
    - hancode task list 返回排序后的任务列表
    - hancode task run task-001 返回 blocked（MockLLM 耗尽），exit code 1
    - hancode task resume task-001 返回 blocked，exit code 1
    - hancode run "goal" 创建并运行任务，自动生成 task-002，exit code 1
- 架构结论：
  ```
  CLI (interfaces/cli.py)
    -> TaskService (app/task_service.py)
      -> runtime/engine.run_task
        -> AgentLoop
  ```
  未新增 TaskController，未修改 AgentLoop 内核，state.json schema version 保持 1。
- 未完成项：真实 Provider、ASK_USER、实时事件流、TUI 仍属后续阶段。
