"""Chinese-first labels for the HanCode TUI.

Technical identifiers are intentionally returned unchanged when no stable
translation exists.  Widgets must not carry their own copies of these labels.
"""

from __future__ import annotations

PHASE_LABELS = {
    "spec": "需求分析",
    "plan": "制定计划",
    "code": "编写代码",
    "test": "运行验证",
    "review": "审查结果",
    "deliver": "整理交付",
}

STATUS_LABELS = {
    "created": "已创建",
    "running": "正在运行",
    "waiting_input": "等待输入",
    "waiting_approval": "等待确认",
    "blocked": "已阻塞",
    "failed": "执行失败",
    "completed": "已完成",
    "inconsistent": "状态异常",
    "passed": "通过",
    "timed_out": "执行超时",
    "unknown": "未知",
}

TOOL_LABELS = {
    "read_file": "读取文件",
    "list_files": "查看目录",
    "search_text": "搜索代码",
    "write_file": "创建文件",
    "edit_file": "修改文件",
    "run_tests": "运行测试",
    "run_build": "构建项目",
    "get_diff": "查看改动",
    "read_test_report": "读取测试报告",
    "list_checkpoints": "查看检查点",
    "rollback_last_checkpoint": "恢复检查点",
    "record_review": "记录审查结果",
    "record_knowledge": "记录开发经验",
}

EVENT_LABELS = {
    "phase_started": "阶段开始",
    "phase_completed": "阶段完成",
    "tool_called": "开始执行工具",
    "tool_completed": "工具执行完成",
    "tool_failed": "工具执行失败",
    "policy_denied": "已阻止不安全操作",
    "checkpoint_created": "已创建检查点",
    "test_completed": "测试通过",
    "test_failed": "测试未通过",
    "rollback_started": "开始恢复检查点",
    "rollback_completed": "已恢复检查点",
    "approval_requested": "等待确认",
    "run_completed": "任务完成",
}


def label_for(value: str, labels: dict[str, str]) -> str:
    """Return a translated stable value, preserving unknown technical text."""
    return labels.get(value, value)

