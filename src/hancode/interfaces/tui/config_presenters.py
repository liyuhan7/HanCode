"""Display descriptors for the full-screen project configuration editor."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ConfigFieldKind(str, Enum):
    READONLY = "readonly"
    TEXT = "text"
    INTEGER = "integer"
    CHOICE = "choice"
    BOOLEAN = "boolean"
    STRING_LIST = "string_list"


@dataclass(frozen=True, slots=True)
class ConfigGroupView:
    group_id: str
    label: str
    summary: str


@dataclass(frozen=True, slots=True)
class ConfigFieldView:
    key: str
    group_id: str
    label: str
    help_text: str
    kind: ConfigFieldKind
    nullable: bool = False
    choices: tuple[tuple[str, str], ...] = ()

    @property
    def widget_id(self) -> str:
        return f"config-field-{self.key.replace('_', '-')}"


CONFIG_GROUPS = (
    ConfigGroupView("project", "项目信息", "稳定标识与课程作业元数据。"),
    ConfigGroupView("provider", "Provider", "模型连接、协议模式与响应边界。"),
    ConfigGroupView("execution", "命令与执行", "测试、构建、步骤、重试与检查点。"),
    ConfigGroupView("workspace", "工作区与保护", "可写目录与追加保护规则。"),
    ConfigGroupView("hitl", "交互与审批", "人工输入、审批门和确认负载限制。"),
    ConfigGroupView("memory", "运行时记忆", "单任务记忆容量、注入数量与热点正文上限。"),
    ConfigGroupView("limits", "上下文与 Diff", "观察、Trace 与变更预览上限。"),
)

CONFIG_FIELDS = (
    ConfigFieldView("workspace_version", "project", "工作区版本", "固定为 1。", ConfigFieldKind.READONLY),
    ConfigFieldView("project_id", "project", "项目 ID", "项目稳定标识，不应包含凭据。", ConfigFieldKind.TEXT),
    ConfigFieldView("course_name", "project", "课程名称", "当前课程或项目上下文名称。", ConfigFieldKind.TEXT),
    ConfigFieldView("assignment_name", "project", "作业名称", "当前作业或交付目标名称。", ConfigFieldKind.TEXT),
    ConfigFieldView("project_root", "project", "项目根", "固定为当前项目目录“.”。", ConfigFieldKind.READONLY),
    ConfigFieldView(
        "llm_provider",
        "provider",
        "LLM Provider",
        "mock 与 openai_compatible 当前可运行；anthropic/local 尚未实现适配器。",
        ConfigFieldKind.CHOICE,
        choices=(
            ("Mock（离线）", "mock"),
            ("OpenAI-Compatible", "openai_compatible"),
            ("Anthropic（适配器未实现）", "anthropic"),
            ("Local（适配器未实现）", "local"),
        ),
    ),
    ConfigFieldView("model_name", "provider", "模型名称", "非 mock Provider 必填。", ConfigFieldKind.TEXT, nullable=True),
    ConfigFieldView(
        "credential_source",
        "provider",
        "凭据来源",
        "远程 Provider 必填；密钥本身不进入 project.json。",
        ConfigFieldKind.CHOICE,
        nullable=True,
        choices=(("未配置", ""), ("系统 Keyring", "keyring"), ("环境变量", "env"), (".env 文件", "dotenv")),
    ),
    ConfigFieldView("provider_base_url", "provider", "Base URL", "远程地址必须为 HTTPS；本地调试允许 localhost HTTP。", ConfigFieldKind.TEXT, nullable=True),
    ConfigFieldView("provider_timeout_seconds", "provider", "超时（秒）", "请求超时，必须大于 0。", ConfigFieldKind.INTEGER),
    ConfigFieldView("provider_max_retries", "provider", "网络重试", "Provider 网络失败重试次数，可为 0。", ConfigFieldKind.INTEGER),
    ConfigFieldView("provider_protocol_retries", "provider", "协议重试", "解码、Schema 或 Action 协议失败重试次数，可为 0。", ConfigFieldKind.INTEGER),
    ConfigFieldView("provider_max_output_tokens", "provider", "最大输出 Token", "Provider 响应 token 上限，必须大于 0。", ConfigFieldKind.INTEGER),
    ConfigFieldView("provider_max_response_bytes", "provider", "最大响应字节", "下载响应硬上限，必须大于 0。", ConfigFieldKind.INTEGER),
    ConfigFieldView(
        "provider_action_mode",
        "provider",
        "Action 模式",
        "auto 仅在明确能力错误时逐级降级。",
        ConfigFieldKind.CHOICE,
        choices=(
            ("自动协商", "auto"),
            ("Native Tools Strict", "native_tools_strict"),
            ("Native Tools", "native_tools"),
            ("JSON Schema", "json_schema"),
            ("JSON Object", "json_object"),
        ),
    ),
    ConfigFieldView("test_command", "execution", "测试命令", "未配置时 Agent 必须提供显式测试命令。", ConfigFieldKind.TEXT, nullable=True),
    ConfigFieldView("build_command", "execution", "构建命令", "未配置时 /build 会提示补充配置。", ConfigFieldKind.TEXT, nullable=True),
    ConfigFieldView("max_steps", "execution", "最大步骤", "单次 AgentLoop 的确定性步骤上限。", ConfigFieldKind.INTEGER),
    ConfigFieldView("retry_budget", "execution", "任务重试预算", "仅影响新建任务，可为 0。", ConfigFieldKind.INTEGER),
    ConfigFieldView("max_checkpoints_per_task", "execution", "最大检查点数", "单任务保留的检查点数量。", ConfigFieldKind.INTEGER),
    ConfigFieldView("writable_roots", "workspace", "可写目录", "只能填写项目内相对目录，不能使用“.”、绝对路径或 ..。", ConfigFieldKind.STRING_LIST),
    ConfigFieldView("protected_patterns", "workspace", "追加保护规则", "这里只显示用户追加项；内置课程、凭据和密钥保护不能删除。", ConfigFieldKind.STRING_LIST),
    ConfigFieldView(
        "interaction_mode",
        "hitl",
        "人工输入模式",
        "ask_user 允许 Provider 请求人工补充信息。",
        ConfigFieldKind.CHOICE,
        choices=(("禁用", "disabled"), ("允许询问", "ask_user")),
    ),
    ConfigFieldView("max_interactions_per_phase", "hitl", "每阶段询问上限", "防止 Agent 无限请求人工输入。", ConfigFieldKind.INTEGER),
    ConfigFieldView("max_interaction_question_chars", "hitl", "问题字符上限", "ask_user 模式下不能超过协议上限 2048。", ConfigFieldKind.INTEGER),
    ConfigFieldView("max_interaction_answer_chars", "hitl", "回答字符上限", "人工回答持久化前的长度上限。", ConfigFieldKind.INTEGER),
    ConfigFieldView(
        "approval_mode",
        "hitl",
        "源码审批模式",
        "控制 Agent 源码写入审批；测试命令仍遵守独立审批规则。",
        ConfigFieldKind.CHOICE,
        choices=(("禁用", "disabled"), ("首次源码写入", "first_source_write"), ("全部源码写入", "all_source_writes")),
    ),
    ConfigFieldView("confirm_agent_rollback", "hitl", "Rollback 需要确认", "Agent 请求恢复检查点时进入确认流程。", ConfigFieldKind.BOOLEAN),
    ConfigFieldView("confirm_agent_build", "hitl", "Build 需要确认", "Agent 请求构建时进入确认流程。", ConfigFieldKind.BOOLEAN),
    ConfigFieldView("max_approvals_per_phase", "hitl", "每阶段审批上限", "限制单阶段可创建的审批请求。", ConfigFieldKind.INTEGER),
    ConfigFieldView("max_approval_payload_bytes", "hitl", "审批负载字节上限", "审批快照的持久化大小上限。", ConfigFieldKind.INTEGER),
    ConfigFieldView("max_approval_preview_chars", "hitl", "审批预览字符上限", "Diff/命令证据的安全预览上限。", ConfigFieldKind.INTEGER),
    ConfigFieldView("max_rejection_reason_chars", "hitl", "拒绝理由字符上限", "人工拒绝原因的持久化长度上限。", ConfigFieldKind.INTEGER),
    ConfigFieldView("max_memory_blob_bytes", "memory", "单 Blob 字节上限", "单个运行时记忆正文的 UTF-8 字节上限。", ConfigFieldKind.INTEGER),
    ConfigFieldView("max_memory_task_bytes", "memory", "单任务记忆字节上限", "events、index 与 blobs 的实际总字节上限。", ConfigFieldKind.INTEGER),
    ConfigFieldView("max_memory_recent_events", "memory", "最近事件数量", "每轮上下文最多注入的最近 Memory 摘要数。", ConfigFieldKind.INTEGER),
    ConfigFieldView("max_memory_file_entries", "memory", "文件索引数量", "每轮上下文最多注入的有效文件索引数。", ConfigFieldKind.INTEGER),
    ConfigFieldView("max_memory_hot_contents", "memory", "热点正文数量", "每轮上下文最多注入的热点文件正文数。", ConfigFieldKind.INTEGER),
    ConfigFieldView("max_observation_bytes", "limits", "Observation 字节上限", "单次工具反馈进入 Agent 上下文前的上限。", ConfigFieldKind.INTEGER),
    ConfigFieldView("max_context_chars", "limits", "上下文字符上限", "PromptBuilder 汇总任务证据的字符上限。", ConfigFieldKind.INTEGER),
    ConfigFieldView("max_trace_events", "limits", "Trace 事件上限", "单次 Prompt 可投影的最近 Trace 数量。", ConfigFieldKind.INTEGER),
    ConfigFieldView("max_diff_files", "limits", "Diff 文件上限", "检查视图最多列出的文件数量。", ConfigFieldKind.INTEGER),
    ConfigFieldView("max_diff_chars", "limits", "Diff 字符上限", "统一 Diff 安全预览的总字符上限。", ConfigFieldKind.INTEGER),
    ConfigFieldView("max_diff_file_bytes", "limits", "单文件 Diff 字节上限", "超过上限的文件仅显示截断状态。", ConfigFieldKind.INTEGER),
    ConfigFieldView("diff_context_lines", "limits", "Diff 上下文行数", "统一 Diff 每个 hunk 的上下文行数。", ConfigFieldKind.INTEGER),
)

FIELDS_BY_KEY = {field.key: field for field in CONFIG_FIELDS}
FIELDS_BY_GROUP = {
    group.group_id: tuple(field for field in CONFIG_FIELDS if field.group_id == group.group_id)
    for group in CONFIG_GROUPS
}


__all__ = [
    "CONFIG_FIELDS",
    "CONFIG_GROUPS",
    "FIELDS_BY_GROUP",
    "FIELDS_BY_KEY",
    "ConfigFieldKind",
    "ConfigFieldView",
    "ConfigGroupView",
]
