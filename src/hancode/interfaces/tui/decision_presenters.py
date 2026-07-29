"""Pure decision-oriented views derived from persisted approval data."""

from __future__ import annotations

from dataclasses import dataclass

from hancode.interfaces.tui.copy.zh_cn import TOOL_LABELS, label_for
from hancode.interfaces.tui.presenters import ApprovalView


@dataclass(frozen=True, slots=True)
class LabeledValueView:
    label: str
    display_value: str
    technical_value: str | None = None


@dataclass(frozen=True, slots=True)
class DecisionView:
    title: str
    intent: str
    reason: str
    scope: tuple[str, ...]
    evidence: tuple[str, ...]
    risk_summary: str
    recoverable: bool
    primary_action: str
    reject_action: str
    technical_detail: tuple[LabeledValueView, ...]


def present_decision(view: ApprovalView) -> DecisionView:
    category = view.category
    if category in {"source_write", "source_overwrite", "multi_file_write"}:
        title, primary, reject, risk = "确认代码修改", "仅允许本次修改", "拒绝并说明原因", "会修改当前源码内容。"
    elif category == "run_tests":
        title, primary, reject, risk = "确认运行测试", "运行本次测试", "拒绝执行", "仅执行经策略验证的一条测试命令。"
    elif category == "run_build":
        title, primary, reject, risk = "确认构建项目", "开始构建", "取消构建", "可能生成构建产物，但不应修改业务源码。"
    else:
        title, primary, reject, risk = "确认操作", "允许本次操作", "拒绝本次操作", "请在技术详情中核对本次请求。"
    evidence = (view.diff_preview,) if view.diff_preview else ()
    return DecisionView(
        title=title,
        intent=label_for(view.tool_name, TOOL_LABELS),
        reason=view.reason or "未提供具体说明",
        scope=view.targets,
        evidence=evidence,
        risk_summary=risk,
        recoverable=category in {"source_write", "source_overwrite", "multi_file_write", "rollback"},
        primary_action=primary,
        reject_action=reject,
        technical_detail=(
            LabeledValueView("Tool Name", view.tool_name, view.tool_name),
            LabeledValueView("Approval ID", view.approval_id, view.approval_id),
            LabeledValueView("Category", category, category),
        ),
    )


__all__ = ["DecisionView", "LabeledValueView", "present_decision"]
